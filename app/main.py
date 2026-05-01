import os
import sys
import io
import json
import time
from collections import defaultdict
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from datetime import datetime
from sqlalchemy import func

load_dotenv()

# Prevent Windows console from crashing on emoji prints
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Add root to path so we can import from root modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# --- INTERNAL IMPORTS ---
from app.database_init import initialize_v2_db
from app.vault_service import VaultService
from app.embedding_engine import generate_vector
from app.models import UserConversation, AIModel, UserMemory
from app.database_init import SessionLocal          # Single DB engine — no split brain
from core.auto_discovery import run_auto_update
from core.dispatcher import get_dispatcher           # Use singleton, not module-level instance
from app.routing.prompt_compressor import get_prompt_compressor
from app.routing.circuit_breaker import get_circuit_breaker
from app.guardrails import GuardrailsChecker         # Feature 7
from app.memory_service import MemoryService         # Feature 12
from config.settings import NON_TEXT_KEYWORDS, SAFE_FALLBACK_MODELS

# --- SEED MODELS FUNCTION ---
def _seed_models_if_empty():
    """Populate AIModel table with seed models if empty."""
    db = SessionLocal()
    try:
        count = db.query(AIModel).count()
        print(f"📊 Current AIModel table count: {count}")
        
        if count > 0:
            print(f"✅ Models table already populated ({count} models)")
            return
        
        print("📚 Seeding AIModel table with default models...")
        
        seed_models = [
            AIModel(model_id="gemini-2.5-flash", provider="Google", category="ANALYSIS", tier=2, sub_tier="A", complexity_min=1.0, complexity_max=5.0, cost_per_1m_tokens=0.075, is_active=True),
            AIModel(model_id="gemini-1.5-pro", provider="Google", category="CODE", tier=1, sub_tier="A", complexity_min=6.0, complexity_max=10.0, cost_per_1m_tokens=3.5, is_active=True),
            AIModel(model_id="claude-3-opus", provider="Anthropic", category="CODE", tier=1, sub_tier="B", complexity_min=7.0, complexity_max=10.0, cost_per_1m_tokens=15.0, is_active=True),
            AIModel(model_id="claude-3-sonnet", provider="Anthropic", category="ANALYSIS", tier=2, sub_tier="A", complexity_min=3.0, complexity_max=8.0, cost_per_1m_tokens=3.0, is_active=True),
            AIModel(model_id="gpt-4o", provider="OpenAI", category="CODE", tier=1, sub_tier="A", complexity_min=7.0, complexity_max=10.0, cost_per_1m_tokens=5.0, is_active=True),
            AIModel(model_id="gpt-4-turbo", provider="OpenAI", category="ANALYSIS", tier=2, sub_tier="A", complexity_min=4.0, complexity_max=9.0, cost_per_1m_tokens=10.0, is_active=True),
            AIModel(model_id="command-r-plus", provider="Cohere", category="EXTRACTION", tier=2, sub_tier="B", complexity_min=2.0, complexity_max=7.0, cost_per_1m_tokens=3.0, is_active=True),
        ]
        
        db.add_all(seed_models)
        db.commit()
        print(f"✅ Seeded {len(seed_models)} models into database")
        
        # Verify insertion
        verify_count = db.query(AIModel).count()
        print(f"✅ Verified: {verify_count} models now in database")
    except Exception as e:
        print(f"⚠️ Error seeding models: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

# 1. Initialize FastAPI app
app = FastAPI(title="Unified Router Gateway - Caching First + Intelligent Routing")

# --- RATE LIMITING ---
_rate_limit_store = defaultdict(list)  # {user_id: [timestamp, ...]}
RATE_LIMIT_MAX = 30  # Max requests per minute per user
RATE_LIMIT_WINDOW = 60  # Window in seconds

def _check_rate_limit(user_id: str) -> bool:
    """Returns True if user is within rate limit, False if exceeded."""
    now = time.time()
    # Clean old entries
    _rate_limit_store[user_id] = [t for t in _rate_limit_store[user_id] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limit_store[user_id]) >= RATE_LIMIT_MAX:
        return False
    _rate_limit_store[user_id].append(now)
    return True

# --- STARTUP EVENT ---
@app.on_event("startup")
async def startup_event():
    import asyncio
    print("App starting up...")
    print("Redis: Disabled (PostgreSQL only)")
    initialize_v2_db()
    print("Database check complete.")

    # Try to seed with basic models if empty
    _seed_models_if_empty()

    # Run auto-update librarian in a BACKGROUND THREAD.
    # run_auto_update() makes synchronous network calls (Google, Anthropic APIs).
    # Calling it directly inside async def blocks the entire FastAPI event loop —
    # no endpoint (not even /health) can respond until it finishes.
    # asyncio.to_thread() dispatches it to a thread pool so the server stays responsive.
    async def _run_librarian():
        try:
            print("\nRunning Auto-Update Librarian (background thread)...")
            await asyncio.to_thread(run_auto_update)
            print("Librarian complete.")
        except Exception as e:
            print(f"Librarian error (non-fatal): {e}")

    asyncio.create_task(_run_librarian())
    print("System Mode: CACHING FIRST (Vault -> Router -> Dispatcher -> Store)")
    print("Server ready - all endpoints accepting requests.\n")

# ==================== REQUEST / RESPONSE MODELS ====================

class QueryRequest(BaseModel):
    user_id: str                        # Required for privacy separation
    prompt: str                         # The user's question
    user_tier: int = 1                  # 1=Premium, 2=Standard, 3=Budget
    # Feature 2: Multi-Turn Conversation History
    session_id: Optional[str] = None    # Links messages in a conversation
    max_history_turns: int = 5          # How many past turns to include
    # Feature 6: Multi-Modal Input
    image_base64: Optional[str] = None  # Base64-encoded image (e.g. ore image)
    image_url: Optional[str] = None     # Or a public image URL

class QueryResponse(BaseModel):
    status: str
    source: str       # "VAULT_CACHE", "AI_GENERATION", or "ERROR"
    data: dict
    vault_id: str = None

class FeedbackRequest(BaseModel):
    vault_id: str
    feedback: float   # +1.0 (thumbs up) or -1.0 (thumbs down)
    comments: str = None

# ==================== MAIN UNIFIED ENDPOINT ====================
@app.post("/ask", response_model=QueryResponse)
async def ask_unified(request: QueryRequest):
    """
    Unified endpoint implementing CACHING FIRST workflow:
    1. Guardrails: safety + PII check (Feature 7)
    2. Check semantic vault for cached response
    3. Build conversation history context (Feature 2)
    4. Prepend user memory context (Feature 12)
    5. Intelligent routing → select best model
    6. Execute with dispatcher (supports images - Feature 6)
    7. Store result + extract new memories
    """
    print("\n" + "="*70)
    print(f"🚀 UNIFIED REQUEST | User: {request.user_id} | Tier: {request.user_tier}")
    print(f"📝 Prompt: {request.prompt[:60]}...")
    if request.image_base64 or request.image_url:
        print("🖼️  Image detected — Multi-Modal request (Feature 6)")
    if request.session_id:
        print(f"💬 Session: {request.session_id} (Multi-Turn - Feature 2)")

    # --- RATE LIMITING ---
    if not _check_rate_limit(request.user_id):
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Max {RATE_LIMIT_MAX} requests per minute.")

    # ── FEATURE 7: GUARDRAILS ─────────────────────────────────────────────
    print("\n[GUARDRAILS] 🛡️  Running safety checks...")
    safety = GuardrailsChecker.check(request.prompt)
    if safety.blocked:
        print(f"[GUARDRAILS] ❌ BLOCKED: {safety.reason}")
        raise HTTPException(status_code=400, detail=f"Request blocked by safety guardrails: {safety.reason}")
    if safety.pii_detected:
        print(f"[GUARDRAILS] ⚠️  PII detected and redacted: {safety.pii_types}")
    safe_prompt = safety.redacted_prompt   # Use redacted version throughout

    try:
        # ======================================================
        # PHASE 1: SEMANTIC VAULT LOOKUP (Check Cache)
        # ======================================================
        print("\n[PHASE 1] 🔍 Checking semantic vault...")
        query_vector = VaultService.get_embedding(safe_prompt)

        if not query_vector:
            raise Exception("Failed to generate embedding vector")

        cache_result = VaultService.semantic_search(
            request.user_id, query_vector, original_prompt=safe_prompt
        )

        if cache_result:
            response_text, tokens_used, cost = cache_result
            print(f"✅ CACHE HIT | Saved tokens: {tokens_used} | Cost averted: ${cost:.4f}")
            return QueryResponse(
                status="Success",
                source="VAULT_CACHE",
                data={
                    "user_id": request.user_id,
                    "ai_response": response_text,
                    "metrics": {
                        "source": "Cached Response",
                        "tokens_consumed": 0,
                        "cost_usd": 0.0,
                        "original_tokens": tokens_used
                    }
                }
            )

        # ── FEATURE 2: CONVERSATION HISTORY ──────────────────────
        history_context = ""
        if request.session_id:
            db = SessionLocal()
            try:
                history_turns = (
                    db.query(UserConversation)
                    .filter(
                        UserConversation.user_id == request.user_id,
                        UserConversation.session_id == request.session_id
                    )
                    .order_by(UserConversation.created_at.desc())
                    .limit(request.max_history_turns)
                    .all()
                )
                if history_turns:
                    turns_text = []
                    for turn in reversed(history_turns):
                        turns_text.append(f"User: {turn.prompt}")
                        turns_text.append(f"Assistant: {turn.response[:500]}")
                    history_context = "[CONVERSATION HISTORY]\n" + "\n".join(turns_text) + "\n[END HISTORY]\n\n"
                    print(f"[HISTORY] 💬 Loaded {len(history_turns)} previous turn(s)")
            finally:
                db.close()

        # ── FEATURE 12: PERSISTENT USER MEMORY ───────────────────
        memory_context = ""
        db = SessionLocal()
        try:
            memories = MemoryService.get_memories(request.user_id, db)
            if memories:
                memory_context = MemoryService.build_memory_context(memories)
                print(f"[MEMORY] 🧠 Loaded {len(memories)} user memories")
        finally:
            db.close()

        # Combine all context into final enriched prompt
        enriched_prompt = f"{memory_context}{history_context}{safe_prompt}"

        # ======================================================
        # PHASE 2: INTELLIGENT ROUTING (Select Best Model)
        # ======================================================
        print("\n[PHASE 2] Intelligent routing...")
        # Route on the raw user question ONLY — not enriched_prompt.
        # If we passed enriched_prompt, history text like 'AI systems' would trigger
        # the ML heuristic and misclassify 'What is my name?' as CODE.
        model_id, provider, score, category, tier, fallbacks = VaultService.get_best_provider_and_model(
            safe_prompt,
            request.user_tier
        )
        print(f"🎯 Routed to {provider}/{model_id}")
        print(f"   Complexity Score: {score} | Category: {category} | Tier: {tier}")

        # ======================================================
        # PHASE 3: EXECUTION (Call Selected Provider with Fallback)
        # ======================================================
        print("\n[PHASE 3] 🚀 Executing with selected model...")

        # Compress only the USER's new message (not history/memory — they must be preserved intact)
        compressor = get_prompt_compressor()
        compressed_user_msg, compression_metrics = compressor.compress(request.prompt, category)

        # Re-attach history + memory AFTER compression so context always reaches the AI
        compressed_prompt = f"{memory_context}{history_context}{compressed_user_msg}"

        orig_preview = request.prompt[:200].replace('\n', ' ').strip()
        comp_preview = compressed_user_msg[:200].replace('\n', ' ').strip()
        print(f"\n[COMPRESSION] Token Reduction (user message only):")
        print(f"  ORIGINAL  ({compression_metrics['original_words']}w): {orig_preview}{'...' if len(request.prompt) > 200 else ''}")
        print(f"  COMPRESSED({compression_metrics['compressed_words']}w): {comp_preview}{'...' if len(compressed_user_msg) > 200 else ''}")
        print(f"  Saved: {compression_metrics['savings_percent']}% | History/Memory context preserved and prepended")

        execution_success = False
        real_ai_response = ""
        real_tokens_used = 0
        cost = 0.0
        execution_start_time = time.time()

        # ── CASCADING FALLBACK CHAIN ─────────────────────────────────
        # Rule 1: Try primary model → all same-category fallbacks (no cap)
        # Rule 2: If all same-category fail → try best models from ALL other categories
        # Rule 3: Last resort → hardcoded safe models guaranteed to produce text
        # Non-text models (veo, lyria, imagen, etc.) are pre-filtered in router.py

        # Build same-category candidates (all fallbacks, not just 2)
        same_category_candidates = [{"model_id": model_id, "provider": provider}] + fallbacks

        # Build cross-category candidates from DB — uses NON_TEXT_KEYWORDS from config/settings.py
        same_ids = {m["model_id"] for m in same_category_candidates}
        try:
            db_cross = SessionLocal()
            all_db_models = db_cross.query(AIModel).filter(
                AIModel.is_active == True,
                AIModel.category != category
            ).all()
            db_cross.close()
            cross_category_candidates = []
            for m in all_db_models:
                m_lower = m.model_id.lower()
                if any(kw in m_lower for kw in NON_TEXT_KEYWORDS):
                    continue
                if m.model_id in same_ids:
                    continue
                cross_category_candidates.append({"model_id": m.model_id, "provider": m.provider})
        except Exception:
            cross_category_candidates = []

        # Last-resort fallbacks from config/settings.py (SAFE_FALLBACK_MODELS)
        all_tried_ids = same_ids | {m["model_id"] for m in cross_category_candidates}
        last_resort_candidates = [m for m in SAFE_FALLBACK_MODELS if m["model_id"] not in all_tried_ids]

        models_to_try = same_category_candidates + cross_category_candidates + last_resort_candidates

        # FIX #8: Get circuit breaker for tracking model health
        circuit_breaker = get_circuit_breaker()

        for attempt_idx, candidate in enumerate(models_to_try):
            c_provider = candidate["provider"]
            c_model = candidate["model_id"]

            # FIX #8: Skip if circuit breaker has tripped this model
            if circuit_breaker.breakers[c_model].is_open():
                print(f"[CIRCUIT] {c_model} circuit OPEN — skipping")
                continue

            if attempt_idx == 0:
                print(f"[ATTEMPT] Primary: {c_provider}/{c_model}")
            elif attempt_idx < len(same_category_candidates):
                print(f"\n[FALLBACK {attempt_idx}] Same-category: {c_provider}/{c_model}")
            elif attempt_idx < len(same_category_candidates) + len(cross_category_candidates):
                print(f"\n[FALLBACK {attempt_idx}] Cross-category: {c_provider}/{c_model}")
            else:
                print(f"\n[FALLBACK {attempt_idx}] Last resort: {c_provider}/{c_model}")

            response_data = VaultService.execute_with_provider(
                c_provider, c_model, compressed_prompt, category=category,
                image_base64=request.image_base64,
                image_url=request.image_url
            )

            if response_data and response_data.get("success") is True:
                circuit_breaker.record_success(c_model)
                real_ai_response = response_data["text"]
                real_tokens_used = response_data.get("tokens", 0)
                cost = VaultService._calculate_cost(c_provider, c_model, real_tokens_used)
                print(f"SUCCESS: {c_model} | Tokens: {real_tokens_used} | Cost: ${cost:.4f}")
                model_id = c_model
                provider = c_provider
                execution_success = True
                execution_latency = time.time() - execution_start_time
                print(f"Latency: {execution_latency:.2f}s")
                break
            else:
                err_msg = response_data.get('text', 'Unknown Error') if response_data else 'Invalid Empty Response'
                print(f"FAILED: {c_provider}/{c_model}: {err_msg[:80]}")
                circuit_breaker.record_failure(c_model)

        if not execution_success:
            final_err = (
                f"System attempted to route your request, but all AI providers failed or exhausted their quotas.\n\n"
                f"Models Attempted: {', '.join([m['model_id'] for m in models_to_try])}\n\n"
                f"Last Exact Error: {err_msg}"
            )

            return QueryResponse(
                status="Error - Provider Failure",
                source="FALLBACK_EXHAUSTED",
                data={
                    "user_id": request.user_id,
                    "ai_response": final_err,
                    "metrics": {
                        "provider": provider,
                        "model_used": model_id,
                        "complexity_score": score,
                        "category": category,
                        "tier": tier,
                        "tokens_consumed": 0,
                        "cost_usd": 0.0
                    }
                }
            )
        # ======================================================
        # PHASE 4: STORAGE (Save to Vault)
        # ======================================================
        print("\n[PHASE 4] 💾 Storing in vault...")
        vault_id = VaultService.save_to_vault(
            request.user_id,
            request.prompt,
            real_ai_response,
            real_tokens_used,
            query_vector,
            cost,
            model_id,
            provider,
            session_id=request.session_id,  # Feature 2: track conversation session
        )

        # ======================================================
        # PHASE 5: REWARD & LEARNING + MEMORY EXTRACTION
        # ======================================================
        print("\n[PHASE 5] 🧠 Updating learning systems...")
        try:
            VaultService.calculate_and_update_reward(
                model_name=model_id,
                category=category,
                response=real_ai_response,
                tokens_consumed=real_tokens_used,
                cost_usd=cost,
                latency_seconds=execution_latency
            )
        except Exception as e:
            print(f"⚠️ Learning update warning (non-fatal): {e}")

        # Feature 12: Extract and persist user memories (non-fatal)
        try:
            db = SessionLocal()
            MemoryService.save_memories(
                request.user_id, db,
                prompt=request.prompt,
                response=real_ai_response,
                conversation_id=vault_id
            )
            db.close()
        except Exception as e:
            print(f"⚠️ Memory extraction warning (non-fatal): {e}")

        print("="*70 + "\n")

        return QueryResponse(
            status="Success",
            source="AI_GENERATION",
            data={
                "user_id": request.user_id,
                "ai_response": real_ai_response,
                "metrics": {
                    "provider": provider,
                    "model_used": model_id,
                    "complexity_score": score,
                    "category": category,
                    "tier": tier,
                    "tokens_consumed": real_tokens_used,
                    "cost_usd": round(cost, 4),
                    "latency_seconds": round(execution_latency, 2)
                }
            },
            vault_id=str(vault_id) if vault_id else None  # FIX #10
        )

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        VaultService.log_system_event(request.user_id, f"ERROR: {str(e)[:50]}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== HELPER ENDPOINTS ====================
@app.get("/vault/stats/{user_id}")
async def get_vault_stats(user_id: str):
    """Get statistics for a user's vault entries."""
    db = SessionLocal()
    try:
        total_queries = db.query(UserConversation).filter(
            UserConversation.user_id == user_id
        ).count()
        
        # FIX #4: Use func.sum() instead of .count() for actual totals
        total_tokens = db.query(func.sum(UserConversation.tokens_consumed)).filter(
            UserConversation.user_id == user_id
        ).scalar() or 0
        
        total_cost = db.query(func.sum(UserConversation.actual_cost)).filter(
            UserConversation.user_id == user_id
        ).scalar() or 0.0
        
        return {
            "user_id": user_id,
            "total_queries": total_queries,
            "total_tokens": int(total_tokens),
            "total_cost_usd": f"${float(total_cost):.4f}"
        }
    finally:
        db.close()

# ==================== EXPLICIT FEEDBACK LOOP ====================
@app.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    """
    User feedback endpoint for Thompson Sampling training.
    
    Thumbs up (+1.0) or thumbs down (-1.0) explicitly trains the bandit.
    This is the ground-truth signal that improves model selection over time.
    
    Args:
        vault_id: ID of the conversation to update
        feedback: +1.0 (good) or -1.0 (bad)
        comments: Optional user comments
    
    Returns:
        Confirmation of feedback recorded
    """
    from app.routing.thompson_sampler import get_thompson_sampler
    
    db = SessionLocal()
    try:
        # Find the conversation in the vault
        conversation = db.query(UserConversation).filter(
            UserConversation.id == request.vault_id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Normalize feedback to 0-1 scale for reward
        reward_score = (request.feedback + 1.0) / 2.0  # -1 → 0, +1 → 1
        
        # Update Thompson Sampler with explicit reward
        sampler = get_thompson_sampler()
        sampler.register_model(conversation.model_used)
        sampler.update_model_performance(
            conversation.model_used,
            reward=reward_score,
            category=conversation.category
        )
        
        print(f"✅ Feedback recorded: {conversation.model_used} | Reward: {reward_score:.2f}")
        
        # Store feedback in database (optional logging)
        conversation.user_feedback = request.feedback
        if request.comments:
            conversation.feedback_comments = request.comments
        db.commit()
        
        return {
            "status": "success",
            "message": f"Feedback recorded for {conversation.model_used}",
            "reward_score": reward_score,
            "comments": request.comments or "No comments"
        }
    
    except Exception as e:
        db.rollback()
        print(f"❌ Feedback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "OK",
        "redis_available": False,
        "mode": "PostgreSQL Only (Redis Disabled)",
        "features": ["streaming", "conversation_history", "multi_modal", "guardrails", "user_memory", "operator_prompts"]
    }

# ==================== FEATURE 1: STREAMING ENDPOINT ====================
@app.post("/ask/stream")
async def ask_stream(request: QueryRequest):
    """
    Streaming endpoint — returns tokens word-by-word via Server-Sent Events (SSE).
    The client receives the response as it is generated instead of waiting 30+ seconds.

    Usage with JavaScript:
        const source = new EventSource('/ask/stream');
        source.onmessage = (e) => { if (e.data !== '[DONE]') display(e.data); };
    """
    if not _check_rate_limit(request.user_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")

    # Feature 7: Guardrails
    safety = GuardrailsChecker.check(request.prompt)
    if safety.blocked:
        raise HTTPException(status_code=400, detail=f"Blocked: {safety.reason}")
    safe_prompt = safety.redacted_prompt

    # Feature 2: Conversation History
    history_context = ""
    if request.session_id:
        db = SessionLocal()
        try:
            turns = (
                db.query(UserConversation)
                .filter(UserConversation.user_id == request.user_id,
                        UserConversation.session_id == request.session_id)
                .order_by(UserConversation.created_at.desc())
                .limit(request.max_history_turns).all()
            )
            if turns:
                lines = []
                for t in reversed(turns):
                    lines += [f"User: {t.prompt}", f"Assistant: {t.response[:500]}"]
                history_context = "[CONVERSATION HISTORY]\n" + "\n".join(lines) + "\n[END HISTORY]\n\n"
        finally:
            db.close()

    # Feature 12: Memory
    memory_context = ""
    db = SessionLocal()
    try:
        memories = MemoryService.get_memories(request.user_id, db)
        if memories:
            memory_context = MemoryService.build_memory_context(memories)
    finally:
        db.close()

    enriched_prompt = f"{memory_context}{history_context}{safe_prompt}"

    # Route on the actual user question ONLY — not enriched_prompt.
    # Prevents ML heuristic from misclassifying history context words as CODE.
    model_id, provider, score, category, tier, fallbacks = VaultService.get_best_provider_and_model(
        safe_prompt, request.user_tier
    )
    print(f"[STREAM] {provider}/{model_id} | Category: {category}")

    async def event_generator():
        full_response = []
        try:
            async for token in get_dispatcher().execute_stream(
                provider, model_id, enriched_prompt, category=category,
                image_b64=request.image_base64, image_url=request.image_url
            ):
                full_response.append(token)
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ==================== FEATURE 12: MEMORY ADMIN ENDPOINTS ====================
@app.get("/memory/{user_id}")
async def get_user_memories(user_id: str):
    """Get all stored memories for a user."""
    db = SessionLocal()
    try:
        memories = (
            db.query(UserMemory)
            .filter(UserMemory.user_id == user_id)
            .order_by(UserMemory.importance.desc())
            .all()
        )
        return {
            "user_id": user_id,
            "total_memories": len(memories),
            "memories": [
                {"id": m.id, "text": m.memory_text, "importance": m.importance,
                 "created_at": str(m.created_at)}
                for m in memories
            ]
        }
    finally:
        db.close()

@app.delete("/memory/{user_id}")
async def clear_user_memories(user_id: str):
    """Clear all memories for a user."""
    db = SessionLocal()
    try:
        count = MemoryService.clear_memories(user_id, db)
        return {"status": "success", "memories_deleted": count}
    finally:
        db.close()

@app.delete("/memory/{user_id}/{memory_id}")
async def delete_single_memory(user_id: str, memory_id: int):
    """Delete a single memory by ID."""
    db = SessionLocal()
    try:
        success = MemoryService.delete_memory(user_id, memory_id, db)
        if not success:
            raise HTTPException(status_code=404, detail="Memory not found.")
        return {"status": "success", "deleted_id": memory_id}
    finally:
        db.close()

# ==================== DEBUG/ADMIN ENDPOINTS ====================

@app.get("/admin/models/check")
async def check_models():
    """Check models table status."""
    db = SessionLocal()
    try:
        count = db.query(AIModel).count()
        models = db.query(AIModel).all()
        return {
            "status": "success",
            "total_models": count,
            "models": [{"model_id": m.model_id, "provider": m.provider, "tier": m.tier} for m in models]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@app.post("/admin/models/seed")
async def seed_models():
    """Manually seed models table."""
    db = SessionLocal()
    try:
        # Clear existing models
        db.query(AIModel).delete()
        db.commit()
        print("🗑️ Cleared existing models")
        
        seed_models = [
            AIModel(model_id="gemini-2.5-flash", provider="Google", category="ANALYSIS", tier=2, sub_tier="A", complexity_min=1.0, complexity_max=5.0, cost_per_1m_tokens=0.075, is_active=True),
            AIModel(model_id="gemini-1.5-pro", provider="Google", category="CODE", tier=1, sub_tier="A", complexity_min=6.0, complexity_max=10.0, cost_per_1m_tokens=3.5, is_active=True),
            AIModel(model_id="claude-3-opus", provider="Anthropic", category="CODE", tier=1, sub_tier="B", complexity_min=7.0, complexity_max=10.0, cost_per_1m_tokens=15.0, is_active=True),
            AIModel(model_id="claude-3-sonnet", provider="Anthropic", category="ANALYSIS", tier=2, sub_tier="A", complexity_min=3.0, complexity_max=8.0, cost_per_1m_tokens=3.0, is_active=True),
            AIModel(model_id="gpt-4o", provider="OpenAI", category="CODE", tier=1, sub_tier="A", complexity_min=7.0, complexity_max=10.0, cost_per_1m_tokens=5.0, is_active=True),
            AIModel(model_id="gpt-4-turbo", provider="OpenAI", category="ANALYSIS", tier=2, sub_tier="A", complexity_min=4.0, complexity_max=9.0, cost_per_1m_tokens=10.0, is_active=True),
            AIModel(model_id="command-r-plus", provider="Cohere", category="EXTRACTION", tier=2, sub_tier="B", complexity_min=2.0, complexity_max=7.0, cost_per_1m_tokens=3.0, is_active=True),
        ]
        
        db.add_all(seed_models)
        db.commit()
        
        verify_count = db.query(AIModel).count()
        return {
            "status": "success",
            "message": f"Seeded {len(seed_models)} models",
            "verified_count": verify_count
        }
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@app.post("/admin/models/auto-discover")
async def trigger_auto_discover():
    """Manually trigger the auto-discovery & categorization process."""
    try:
        print("🚀 Manual auto-discovery triggered")
        run_auto_update()
        
        db = SessionLocal()
        total = db.query(AIModel).count()
        db.close()
        
        return {
            "status": "success",
            "message": "Auto-discovery completed",
            "total_models": total
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@app.post("/admin/models/refresh-all")
async def refresh_all_models():
    """Clear all models and force fresh discovery with corrected tier logic."""
    try:
        print("🔄 FORCE REFRESHING ALL MODELS...")
        db = SessionLocal()
        
        # Clear all models
        db.query(AIModel).delete()
        db.commit()
        print("✅ Cleared all existing models")
        db.close()
        
        # Delete API key hash to force full discovery
        import os
        hash_file = ".api_key_hash"
        if os.path.exists(hash_file):
            os.remove(hash_file)
            print("✅ Cleared API key hash")
        
        # Run fresh discovery
        print("🚀 Starting fresh model discovery...")
        run_auto_update()
        
        db = SessionLocal()
        total = db.query(AIModel).count()
        
        # Count by tier
        tier1 = db.query(AIModel).filter(AIModel.tier == 1).count()
        tier2 = db.query(AIModel).filter(AIModel.tier == 2).count()
        tier3 = db.query(AIModel).filter(AIModel.tier == 3).count()
        
        db.close()
        
        return {
            "status": "success",
            "message": "All models refreshed with corrected tier logic",
            "total_models": total,
            "tier_breakdown": {
                "tier_1_premium": tier1,
                "tier_2_standard": tier2,
                "tier_3_budget": tier3
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/admin/models/status")
async def model_discovery_status():
    """Get status of last model discovery."""
    import os
    hash_file = ".api_key_hash"
    
    db = SessionLocal()
    try:
        total = db.query(AIModel).count()
        latest = db.query(AIModel).order_by(AIModel.last_audited.desc()).first()
        
        last_audit = None
        days_since = None
        
        if latest:
            last_audit = latest.last_audited
            days_since = (datetime.utcnow() - latest.last_audited).days
        
        api_key_tracked = os.path.exists(hash_file)
        
        return {
            "status": "success",
            "total_models": total,
            "last_audit": last_audit,
            "days_since_audit": days_since,
            "api_key_tracking": api_key_tracked,
            "update_needed": days_since >= 30 if days_since else True
        }
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)