import os
import sys
import io
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from datetime import datetime

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
from app.models import UserConversation, AIModel
from database.session import SessionLocal
from core.auto_discovery import run_auto_update

load_dotenv()

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

# --- STARTUP EVENT ---
@app.on_event("startup")
async def startup_event():
    print("🚀 App is starting up...")
    print("📊 Redis: Disabled (PostgreSQL only)")
    initialize_v2_db()
    print("✅ Database check complete.")
    
    # Try to seed with basic models if empty
    _seed_models_if_empty()
    
    # Run auto-update librarian (checks if 30+ days or API keys changed)
    try:
        print("\n📚 Running Auto-Update Librarian...")
        run_auto_update()
    except Exception as e:
        print(f"⚠️ Librarian error (non-fatal): {e}")
    
    print("🎯 System Mode: CACHING FIRST (Vault → Router → Dispatcher → Store)")

# 3. Define the Request Data
class QueryRequest(BaseModel):
    user_id: str      # Required for privacy separation
    prompt: str       # The user's question
    user_tier: int = 1  # Optional: 1 (Premium), 2 (Standard), 3 (Budget)
    modality: str = "TEXT"  # TEXT, IMAGE, VIDEO, AUDIO, MULTIMODAL
    image_data: str = None  # Optional Base64 image
    audio_data: str = None  # Optional Base64 audio

class QueryResponse(BaseModel):
    status: str
    source: str  # "VAULT_CACHE", "AI_GENERATION", or "ERROR"
    data: dict
    vault_id: str = None  # ID for later feedback

class FeedbackRequest(BaseModel):
    vault_id: str  # Which conversation to update
    feedback: float  # +1.0 (thumbs up) or -1.0 (thumbs down)
    comments: str = None  # Optional user feedback

# ==================== MAIN UNIFIED ENDPOINT ====================
@app.post("/ask", response_model=QueryResponse)
async def ask_unified(request: QueryRequest):
    """
    Unified endpoint implementing CACHING FIRST workflow:
    1. Check semantic vault for cached response
    2. If miss, use intelligent router to select best model
    3. Execute with dispatcher
    4. Store result in vault + Redis cache
    """
    print("\n" + "="*70)
    print(f"🚀 UNIFIED REQUEST | User: {request.user_id} | Tier: {request.user_tier}")
    print(f"📝 Prompt: {request.prompt[:60]}...")

    try:
        # ======================================================
        # PHASE 1: SEMANTIC VAULT LOOKUP (Check Cache)
        # ======================================================
        print("\n[PHASE 1] 🔍 Checking semantic vault...")
        query_vector = VaultService.get_embedding(request.prompt)
        
        if not query_vector:
            raise Exception("Failed to generate embedding vector")

        cache_result = VaultService.semantic_search(request.user_id, query_vector)
        
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

        # ======================================================
        # PHASE 2: INTELLIGENT ROUTING (Select Best Model)
        # ======================================================
        print("\n[PHASE 2] 🧭 VAULT MISS - Intelligent routing...")
        model_id, provider, score, category, tier, fallbacks = VaultService.get_best_provider_and_model(
            request.prompt, 
            request.user_tier
        )
        print(f"🎯 Routed to {provider}/{model_id}")
        print(f"   Complexity Score: {score} | Category: {category} | Tier: {tier}")

        # ======================================================
        # PHASE 3: EXECUTION (Call Selected Provider with Fallback)
        # ======================================================
        print("\n[PHASE 3] 🚀 Executing with selected model...")
        
        execution_success = False
        real_ai_response = ""
        real_tokens_used = 0
        cost = 0.0
        
        # We will try the primary model, and if it fails, try up to 2 fallbacks (max 3 total attempts)
        models_to_try = [{"model_id": model_id, "provider": provider}] + fallbacks[:2]
        
        for attempt_idx, candidate in enumerate(models_to_try):
            c_provider = candidate["provider"]
            c_model = candidate["model_id"]
            
            if attempt_idx > 0:
                print(f"\n[FALLBACK {attempt_idx}] 🔄 Attempting alternative model: {c_provider}/{c_model}")
            
            response_data = VaultService.execute_with_provider(
                c_provider, c_model, request.prompt
            )
            
            if response_data and response_data.get("success") is True:
                real_ai_response = response_data["text"]
                real_tokens_used = response_data.get("tokens", 0)
                cost = VaultService._calculate_cost(c_provider, c_model, real_tokens_used)
                
                print(f"✅ Generated from {c_model} | Tokens: {real_tokens_used} | Cost: ${cost:.4f}")
                
                # Update our primary variables so it saves in DB correctly
                model_id = c_model
                provider = c_provider
                execution_success = True
                break
            else:
                err_msg = response_data.get('text', 'Unknown Error') if response_data else 'Invalid Empty Response'
                print(f"❌ Execution failed for {c_provider}/{c_model}: {err_msg}")
                # Loop naturally continues to next fallback candidate
        if not execution_success:
            final_err = f"System attempted to route your request, but all AI providers failed or exhausted their quotas.\n\nModels Attempted: {', '.join([m['model_id'] for m in models_to_try])}\n\nLast Exact Error: {err_msg}"
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
        # PHASE 4: STORAGE (Save to Vault + Redis)
        # ======================================================
        print("\n[PHASE 4] 💾 Storing in vault...")
        VaultService.save_to_vault(
            request.user_id,
            request.prompt,
            real_ai_response,
            real_tokens_used,
            query_vector,
            cost,
            model_id,
            provider
        )

        # Check for topic changes in session (disabled - Redis off)
        # if REDIS_AVAILABLE:
        #     VaultService.check_topic_change(request.user_id, request.prompt)

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
                    "cost_usd": round(cost, 4)
                }
            }
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
        
        total_tokens = db.query(UserConversation).filter(
            UserConversation.user_id == user_id
        ).count()
        
        total_cost = db.query(UserConversation).filter(
            UserConversation.user_id == user_id
        ).count()
        
        return {
            "user_id": user_id,
            "total_queries": total_queries,
            "vault_entries": total_tokens,
            "estimated_tokens": total_tokens * 100,  # Rough estimate
            "estimated_cost": f"${total_cost * 0.01:.2f}"
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
        "mode": "PostgreSQL Only (Redis Disabled)"
    }

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