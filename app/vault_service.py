import os
import json
import sys
import time
from google import genai
from sqlalchemy import text
from database.session import SessionLocal
from app.embedding_engine import generate_vector
from app.models import UserConversation, SystemLog
from app.routing.router import get_best_model
from app.routing.reward import calculate_reward, infer_quality_score
from app.routing.bandit import update_bandit_reward
from database.db import update_model_performance
from core.dispatcher import Dispatcher

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
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
    def semantic_search(user_id: str, vector: list):
        """
        Searches vault for semantically similar previous responses.
        Returns: (response_text, tokens_used, cost) or None
        """
        db = SessionLocal() 
        try:
            threshold = 0.7  # L2 distance threshold (lowered for better cache hits)
            
            match = db.query(UserConversation).filter(
                UserConversation.user_id == user_id,
                UserConversation.embedding != None, 
                UserConversation.embedding.l2_distance(vector) < threshold
            ).order_by(
                UserConversation.embedding.l2_distance(vector)
            ).first()

            if match:
                print(f"🎯 VAULT HIT: Found similar prompt in ID {match.id}")
                VaultService.log_system_event(user_id, "VAULT_CACHE_HIT")
                return (match.response, match.tokens_consumed, match.actual_cost)
                
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
        Returns: (model_id, provider, score, category, tier)
        """
        try:
            result = get_best_model(prompt, user_allowed_tier)
            return result
        except Exception as e:
            print(f"⚠️ Router failed: {e}. Falling back to Gemini...")
            return ("gemini-2.5-flash", "Google", 5.0, "UTILITY", 2)

    # ==================== PHASE 3: EXECUTION WITH DISPATCHER ====================
    @staticmethod
    def execute_with_provider(provider: str, model_id: str, prompt: str):
        """
        Routes request through appropriate provider using dispatcher.
        Returns: {text, tokens}
        """
        try:
            print(f"🚀 Executing with {provider} - {model_id}")
            response = dispatcher.execute(provider, model_id, prompt)
            return response
        except Exception as e:
            print(f"❌ Dispatcher error: {e}")
            return {"text": f"Execution Error: {str(e)}", "tokens": 0}

    # ==================== PHASE 4: STORAGE & ARCHIVING ====================
    @staticmethod
    def save_to_vault(user_id: str, prompt: str, response: str, tokens: int, 
                     vector: list, cost: float, model_used: str, provider: str):
        """
        Saves interaction to PostgreSQL vault for future semantic matching.
        Stores both in DB and Redis.
        """
        db = SessionLocal()
        try:
            # 1. Save to PostgreSQL
            new_entry = UserConversation(
                user_id=user_id,
                prompt=prompt,
                response=response,
                model_used=model_used,
                tokens_consumed=tokens,
                actual_cost=cost,
                embedding=vector
            )
            db.add(new_entry)
            db.commit()
            print(f"✅ Vault Updated: Saved ${cost:.4f} interaction from {provider}/{model_used}")
            
            # 2. Cache in Redis - DISABLED (Redis off per user request)
            # if REDIS_AVAILABLE:
            #     VaultService._cache_in_redis(user_id, prompt, response)
            
        except Exception as e:
            print(f"❌ Database Save Error: {e}")
            db.rollback()
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
                title_res = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=title_prompt
                )
                topic = title_res.text.strip().replace('"', '')[:50] or "General"
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
