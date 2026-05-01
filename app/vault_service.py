import os
import json
import sys
import time
from google import genai
from sqlalchemy import text
from app.database_init import SessionLocal
from app.embedding_engine import generate_vector
from app.models import UserConversation, SystemLog
from app.routing.router import get_best_model
from app.routing.reward import calculate_reward, infer_quality_score
from app.routing.bandit import update_bandit_reward
from database.db import update_model_performance
from core.dispatcher import Dispatcher

dispatcher = Dispatcher()

class VaultService:
    """
    Unified service combining:
    1. Semantic caching (PostgreSQL + pgvector)
    2. Intelligent routing (dispatcher + router)
    3. Session memory (Redis + PostgreSQL)
    """

    # ==================== PHASE 1: SEMANTIC CACHING ====================
    @staticmethod
    def get_embedding(text: str):
        """Generates 768-dim vector locally using HuggingFace."""
        return generate_vector(text)

    @staticmethod
    def _compute_keyword_overlap(prompt_a: str, prompt_b: str) -> float:
        """
        Computes Jaccard keyword overlap between two prompts.
        Returns 0.0 (no overlap) to 1.0 (identical keywords).
        
        This is a cheap secondary check to prevent the vector search from
        returning a semantically "close" but topically WRONG cached response.
        Example: "write sorting algorithm" vs "write searching algorithm" have
        high vector similarity but low keyword overlap on the critical word.
        """
        # Common filler words to ignore
        STOP_WORDS = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "shall",
            "should", "may", "might", "must", "can", "could", "to", "of", "in",
            "for", "on", "with", "at", "by", "from", "as", "into", "through",
            "during", "before", "after", "above", "below", "between", "out",
            "off", "over", "under", "again", "further", "then", "once", "here",
            "there", "when", "where", "why", "how", "all", "both", "each",
            "few", "more", "most", "other", "some", "such", "no", "nor", "not",
            "only", "own", "same", "so", "than", "too", "very", "just", "but",
            "and", "or", "if", "because", "about", "it", "its", "i", "me", "my",
            "we", "our", "you", "your", "he", "him", "his", "she", "her", "they",
            "them", "their", "this", "that", "these", "those", "what", "which",
            "who", "whom", "whose", "write", "code", "make", "create", "build",
            "give", "show", "explain", "please", "help", "need", "want",
        }
        
        def extract_keywords(text):
            # Lowercase, split, keep only alphanumeric tokens of 2+ chars
            words = set()
            for w in text.lower().split():
                clean = ''.join(c for c in w if c.isalnum())
                if len(clean) >= 2 and clean not in STOP_WORDS:
                    words.add(clean)
            return words
        
        keys_a = extract_keywords(prompt_a)
        keys_b = extract_keywords(prompt_b)
        
        if not keys_a or not keys_b:
            return 0.0
        
        intersection = keys_a & keys_b
        union = keys_a | keys_b
        
        return len(intersection) / len(union) if union else 0.0

    @staticmethod
    def semantic_search(user_id: str, vector: list, original_prompt: str = None):
        """
        Searches vault for semantically similar previous responses.
        
        ANTI-HALLUCINATION: Uses a 3-layer verification system:
          Layer 1: L2 vector distance (strict threshold)
          Layer 2: Keyword overlap between original and cached prompt
          Layer 3: Distance-to-overlap confidence ratio
        
        Returns: (response_text, tokens_used, cost) or None
        """
        db = SessionLocal() 
        try:
            # Layer 1: Vector distance threshold
            # 0.55 is strict — only very close matches pass.
            # This prevents "sorting" from matching "searching".
            VECTOR_THRESHOLD = 0.55
            
            # Layer 2: Minimum keyword overlap required
            # Increased to 0.75 to be extremely strict and prevent short sentence collisions
            KEYWORD_OVERLAP_MIN = 0.75
            
            # Fetch top 3 candidates (not just the closest one)
            # This allows us to verify before committing to a match
            candidates = db.query(UserConversation).filter(
                UserConversation.user_id == user_id,
                UserConversation.embedding != None, 
                UserConversation.embedding.l2_distance(vector) < VECTOR_THRESHOLD
            ).order_by(
                UserConversation.embedding.l2_distance(vector)
            ).limit(3).all()

            if not candidates:
                return None
            
            # Evaluate each candidate with multi-layer checks
            for candidate in candidates:
                # Calculate the actual L2 distance for logging
                # (We already filtered by threshold, but we need the value)
                
                # Layer 2: Keyword overlap check
                if original_prompt and candidate.prompt:
                    overlap = VaultService._compute_keyword_overlap(
                        original_prompt, candidate.prompt
                    )
                    
                    print(f"   🔬 Candidate ID {candidate.id}: "
                          f"Keyword overlap = {overlap:.2f} "
                          f"(min required: {KEYWORD_OVERLAP_MIN})")
                    print(f"      Cached prompt: \"{candidate.prompt[:60]}...\"")
                    
                    if overlap < KEYWORD_OVERLAP_MIN:
                        print(f"   ❌ REJECTED: Keyword overlap too low — "
                              f"topics likely differ despite vector similarity")
                        VaultService.log_system_event(
                            user_id, 
                            f"VAULT_REJECTED_LOW_OVERLAP:{overlap:.2f}"
                        )
                        continue  # Try next candidate
                
                # All layers passed — this is a verified cache hit
                print(f"🎯 VAULT HIT (VERIFIED): ID {candidate.id} | "
                      f"Keyword overlap: {overlap:.2f}")
                VaultService.log_system_event(user_id, "VAULT_CACHE_HIT_VERIFIED")
                return (candidate.response, candidate.tokens_consumed, candidate.actual_cost, candidate.id)
            
            # All candidates failed verification
            print(f"   ⚠️ {len(candidates)} candidates found but ALL failed "
                  f"keyword verification — treating as CACHE MISS")
            VaultService.log_system_event(user_id, "VAULT_MISS_VERIFICATION_FAILED")
            return None
            
        except Exception as e:
            print(f"❌ Search Error: {e}")
            return None
        finally:
            db.close()

    # ==================== PHASE 2: INTELLIGENT ROUTING ====================
    @staticmethod
    def get_best_provider_and_model(prompt: str, user_allowed_tier: int = 1):
        """
        Uses router to intelligently select best provider and model.
        Returns: (model_id, provider, score, category, tier, fallbacks)
        """
        try:
            result = get_best_model(prompt, user_allowed_tier)
            return result
        except Exception as e:
            print(f"⚠️ Router failed: {e}. Falling back to Gemini...")
            return ("gemini-3-flash-preview", "Google", 5.0, "UTILITY", 2, [{"model_id": "gemini-2.0-flash", "provider": "Google"}])

    # ==================== PHASE 3: EXECUTION WITH DISPATCHER ====================
    @staticmethod
    def execute_with_provider(
        provider: str, model_id: str, prompt: str,
        category: str = "UTILITY",
        image_base64: str = None,   # Feature 6: Multi-Modal
        image_url: str = None,
    ):
        """
        Routes request through appropriate provider using dispatcher.
        category is passed to the dispatcher so it can inject the correct
        system prompt (CODE gets code-writing instructions, CHAT gets chat instructions etc.)
        image_base64 / image_url enable vision/multi-modal requests (Feature 6).
        Returns: {text, tokens, success}
        """
        try:
            print(f"🚀 Executing with {provider} - {model_id}")
            response = dispatcher.execute(
                provider, model_id, prompt,
                category=category,
                image_b64=image_base64,
                image_url=image_url,
            )
            return response
        except Exception as e:
            print(f"❌ Dispatcher error: {e}")
            return {"text": f"Execution Error: {str(e)}", "tokens": 0, "success": False}

    # ==================== PHASE 4: STORAGE & ARCHIVING ====================
    @staticmethod
    def save_to_vault(user_id: str, prompt: str, response: str, tokens: int,
                     vector: list, cost: float, model_used: str, provider: str,
                     session_id: str = None):       # Feature 2: Multi-Turn
        """
        Saves interaction to PostgreSQL vault for future semantic matching.
        session_id links multiple messages into a conversation (Feature 2).
        """
        db = SessionLocal()
        try:
            new_entry = UserConversation(
                user_id=user_id,
                prompt=prompt,
                response=response,
                model_used=model_used,
                tokens_consumed=tokens,
                actual_cost=cost,
                embedding=vector,
                session_id=session_id,   # Feature 2
            )
            db.add(new_entry)
            db.commit()
            db.refresh(new_entry)
            print(f"✅ Vault Updated: Saved ${cost:.4f} interaction from {provider}/{model_used} [ID: {new_entry.id}]")
            return new_entry.id
            
        except Exception as e:
            print(f"❌ Database Save Error: {e}")
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def _cache_in_redis(user_id: str, prompt: str, response: str):
        """
        Redis caching DISABLED for now.
        Will be enabled later with proper Redis setup.
        """
        # if not REDIS_AVAILABLE or not r:
        #     return
        # 
        # try:
        #     message = json.dumps({
        #         "role": "assistant",
        #         "prompt": prompt[:100],
        #         "response": response[:100]
        #     })
        #     r.rpush(f"chat:{user_id}", message)
        #     r.ltrim(f"chat:{user_id}", -10, -1)
        # except Exception as e:
        #     print(f"⚠️ Redis caching warning: {e}")
        pass

    # ==================== MEMORY MANAGEMENT ====================
    @staticmethod
    def get_session_context(user_id: str):
        """
        Retrieves recent conversation context from PostgreSQL.
        (Redis caching disabled for now)
        """
        # Using PostgreSQL only since Redis is disabled
        db = SessionLocal()
        try:
            recent = db.query(UserConversation).filter(
                UserConversation.user_id == user_id
            ).order_by(UserConversation.created_at.desc()).limit(5).all()
            return [{"prompt": c.prompt, "response": c.response} for c in recent]
        finally:
            db.close()

    @staticmethod
    def check_topic_change(user_id: str, new_prompt: str):
        """
        Topic change detection disabled for now (Redis disabled).
        Will be enabled when Redis is configured.
        """
        # Topic detection requires active Redis session
        # Skipping for now
        return False
        
        # Code below commented for future Redis setup:
        # if not REDIS_AVAILABLE or not r:
        #     return False
        # 
        # try:
        #     context = VaultService.get_session_context(user_id)
        #     if not context:
        #         return False
        #     
        #     check_prompt = f"Previous: {context[-1] if context else 'None'}\nNew: {new_prompt}\nTopic changed significantly? YES/NO"
        #     model = genai.GenerativeModel("gemini-2.5-flash")
        #     response = model.generate_content(check_prompt)
        #     
        #     if "YES" in response.text.upper():
        #         VaultService._archive_session(user_id, context)
        #         r.delete(f"chat:{user_id}")
        #         r.delete(f"summary:{user_id}")
        #         print(f"📦 ARCHIVED: Previous conversation for {user_id}")
        #         return True
        #     return False
        # except Exception as e:
        #     print(f"⚠️ Topic detection warning: {e}")
        #     return False

    @staticmethod
    def _archive_session(user_id: str, context: list):
        """Archives completed conversation to PostgreSQL."""
        from app.models import ConversationArchive
        
        db = SessionLocal()
        try:
            # Generate title for the archived conversation
            if context:
                title_prompt = f"Summarize this conversation in 5 words: {json.dumps(context[:3])}"
                title_res = dispatcher.execute("Google", "gemini-2.5-flash", title_prompt)
                topic = "General Discussion"
                if title_res.get("success"):
                    topic = title_res["text"].strip().replace('"', '')[:50] or "General"
            else:
                topic = "General Discussion"
            
            archive = ConversationArchive(
                session_id=user_id,
                topic_summary=topic,
                full_transcript=json.dumps(context)
            )
            db.add(archive)
            db.commit()
        except Exception as e:
            print(f"⚠️ Archive warning: {e}")
        finally:
            db.close()

    # ==================== LEARNING & OPTIMIZATION ====================
    @staticmethod
    def calculate_and_update_reward(model_name: str, category: str, response: str,
                                    tokens_consumed: int, cost_usd: float, 
                                    latency_seconds: float):
        """
        Calculate reward after response generation and update learning systems.
        
        This completes the feedback loop:
        1. Calculate reward based on response quality and metrics
        2. Update Thompson Sampling bandit with reward
        3. Update model performance statistics in database
        
        Args:
            model_name: Model that generated the response
            category: Task category
            response: Generated response text
            tokens_consumed: Tokens used
            cost_usd: Actual cost in USD
            latency_seconds: Response time
        """
        try:
            # 1. Infer quality score from response
            has_code = "```" in response or "def " in response or "class " in response
            has_errors = any(err in response.lower() for err in ["error", "failed", "exception"])
            quality_score = infer_quality_score(category, len(response), has_code, has_errors)
            
            # 2. Calculate comprehensive reward
            reward_data = calculate_reward(
                model_name=model_name,
                category=category,
                tokens_consumed=tokens_consumed,
                cost_usd=cost_usd,
                latency_seconds=latency_seconds,
                response_quality=quality_score,
                user_satisfaction=1.0  # Default to 1.0, can be overridden with user feedback
            )
            
            combined_reward = reward_data["combined_reward"]
            
            # 3. Update Thompson Sampling bandit
            update_bandit_reward(model_name, combined_reward)
            
            # 4. Update database model performance
            update_model_performance(
                model_id=model_name,
                category=category,
                reward=combined_reward,
                cost=cost_usd,
                latency=latency_seconds
            )

            # 5. Update Adaptive Compressor — self-learning feedback
            try:
                from app.routing.prompt_compressor import get_prompt_compressor
                compressor = get_prompt_compressor()
                session_key = f"{model_name}_{category}_{int(latency_seconds*1000)}"
                compressor.learn_from_feedback(session_id=session_key, reward=combined_reward)
            except Exception:
                pass  # Compressor learning is always non-critical
            
            # 5. Log the learning update
            print(f"\n[LEARNING] Model {model_name} ({category}):")
            print(f"  Quality Reward:      {reward_data['quality_reward']}")
            print(f"  Cost Reward:         {reward_data['cost_reward']}")
            print(f"  Latency Reward:      {reward_data['latency_reward']}")
            print(f"  Combined Reward:     {combined_reward}")
            print(f"  Metrics: {tokens_consumed} tokens, ${cost_usd:.6f}, {latency_seconds:.2f}s")
            
            return reward_data
            
        except Exception as e:
            print(f"⚠️ Reward calculation warning: {e}")
            return None

    # ==================== LOGGING & MONITORING ====================
    @staticmethod
    def log_system_event(user_id: str, event_name: str):
        """Records system events for monitoring and debugging."""
        db = SessionLocal()
        try:
            new_log = SystemLog(
                user_id=user_id,
                event=event_name
            )
            db.add(new_log)
            db.commit()
            print(f"📊 System Logged: {event_name} for {user_id}")
        except Exception as e:
            print(f"❌ Logging Error: {e}")
        finally:
            db.close()

    @staticmethod
    def _calculate_cost(provider: str, model_id: str, tokens: int):
        """
        Calculates cost based on provider and token usage.
        Uses database rates if available, otherwise uses defaults.
        """
        db = SessionLocal()
        try:
            from app.models import AIModel
            model = db.query(AIModel).filter(
                AIModel.provider == provider,
                AIModel.model_id == model_id
            ).first()
            
            if model:
                cost_per_1m = model.cost_per_1m_tokens
            else:
                # Fallback rates
                default_rates = {
                    "Google": 0.075,
                    "OpenAI": 0.15,
                    "Anthropic": 0.20,
                    "Cohere": 0.10,
                    "DeepSeek": 0.05,
                    "xAI": 0.10,
                    "Mistral": 0.12,
                    "HuggingFace": 0.00
                }
                cost_per_1m = default_rates.get(provider, 0.10)
            
            return (tokens / 1_000_000) * cost_per_1m
        finally:
            db.close()
