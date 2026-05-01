#FROZEN CODE - DO NOT MODIFY

from google import genai
import os
from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv
from app.database_init import SessionLocal
from app.models import AIModel

load_dotenv()
from core.dispatcher import Dispatcher
dispatcher = Dispatcher()
ALLOWED_CATEGORIES = ["CODE", "AGENTS", "ANALYSIS", "EXTRACTION", "CREATIVE", "UTILITY", "CHAT"]

CATEGORY_MAP = {
    "PROGRAMMING": "CODE",
    "DEVELOPMENT": "CODE",
    "TECHNICAL": "ANALYSIS",
    "LOGIC": "ANALYSIS",
    "REASONING": "ANALYSIS",
    "WRITING": "CREATIVE",
    "SCRAPING": "EXTRACTION",
    "GENERAL": "UTILITY",
    "CONVERSATION": "CHAT"
}

LIBRARIAN_PROMPT = f"""
You are an AI Architect. Categorize these AI models for routing purposes.
If a model is good at multiple things, list them separated by a SEMICOLON (;).
USE ONLY THESE CATEGORIES: {", ".join(ALLOWED_CATEGORIES)}.

For the tier field, you MUST use exactly one of these text values:
  HIGH   = Premium/flagship model (GPT-4, Claude Opus, Gemini Pro, etc.)
  MEDIUM = Standard/mid-range model (GPT-3.5, Claude Sonnet, Gemini Flash, etc.)
  LOW    = Budget/small/fast model (small quantized models, lite variants, etc.)

For complexity_min and complexity_max, use a float from 1.0 to 10.0.
For cost_per_1m, use the approximate USD cost per 1 million tokens as a float.

Return ONLY comma-separated lines with NO header row, NO explanation, NO markdown:
model_id, provider, category_list, tier, complexity_min, complexity_max, cost_per_1m

Examples:
gemini-2.0-flash, Google, CODE; ANALYSIS, MEDIUM, 4.0, 8.0, 0.075
claude-opus-4, Anthropic, CODE; ANALYSIS; AGENTS, HIGH, 7.0, 10.0, 15.0
gpt-3.5-turbo, OpenAI, CHAT; UTILITY, LOW, 1.0, 5.0, 0.50
"""

_LAST_SUCCESSFUL_AUDITOR = None

def audit_models(provider_name, model_list):
    global _LAST_SUCCESSFUL_AUDITOR
    """Processes models into the DB, allowing one model to occupy multiple rows/categories."""
    # BUG #1 FIX: Use confirmed-working model names (verified via client.models.list()).
    # Previous list used invalid/deprecated names that returned 404 from the generateContent API.
    audit_candidates = []
    
    # 0. Reuse the model that successfully categorized the previous provider!
    if _LAST_SUCCESSFUL_AUDITOR:
        audit_candidates.append(_LAST_SUCCESSFUL_AUDITOR)
    
    # 1. Try active Utility models from the database first
    db = SessionLocal()
    try:
        db_models = db.query(AIModel).filter(
            AIModel.is_active == True,
            AIModel.category.in_(["UTILITY", "CHAT", "CODE"]),
            ~AIModel.model_id.startswith("---")
        ).order_by(AIModel.tier.asc()).limit(3).all()
        for m in db_models:
            audit_candidates.append((m.provider, m.model_id))
    except Exception:
        pass
    finally:
        db.close()
        
    # 2. Try the models we just discovered for this provider
    # If the user only has one obscure API key, we use that API's own models to categorize itself!
    for m in model_list[:3]:
        audit_candidates.append((provider_name, m))
        
    # 3. Finally, known good global fallbacks
    fallbacks = [
        ("Google", "gemini-2.5-flash"),
        ("OpenAI", "gpt-4o-mini"),
        ("Anthropic", "claude-3-5-haiku-20241022"),
        ("NVIDIA", "meta/llama-3.1-70b-instruct")
    ]
    audit_candidates.extend(fallbacks)
    
    # Deduplicate while preserving order
    seen = set()
    unique_candidates = []
    for prov, mod in audit_candidates:
        if (prov, mod) not in seen:
            seen.add((prov, mod))
            unique_candidates.append((prov, mod))
    
    audit_candidates = unique_candidates
    response = None
    
    print(f"📡 Requesting audit for {len(model_list)} models...")
    
    for provider, model_name in audit_candidates:
        try:
            print(f"   ⏳ Attempting categorization using {provider}/{model_name}...")
            # Format the model list as a clean string for the prompt
            models_string = "\n".join(model_list)
            
            res = dispatcher.execute(provider, model_name, f"{LIBRARIAN_PROMPT}\n\nModels:\n{models_string}")
            
            if res.get("success") and res.get("text"):
                class DummyResponse:
                    text = res["text"]
                response = DummyResponse()
                print(f"✅ AI Response received using {provider}/{model_name}")
                _LAST_SUCCESSFUL_AUDITOR = (provider, model_name)
                break
        except Exception as e:
            print(f"⚠️ {provider}/{model_name} failed: {e}")
            continue

    if not response or not response.text:
        print("❌ CRITICAL: No response from AI. Check your API key or Quota.")
        return

    db = SessionLocal()
    
    tier_map = {"VERY HIGH": 1, "HIGH": 1, "MEDIUM": 2, "MID": 2, "LOW": 3, "VERY LOW": 3}
    val_map = {"VERY HIGH": 9.5, "HIGH": 8.0, "MEDIUM": 5.0, "MID": 4.0, "LOW": 1.0, "VERY LOW": 0.1}

    lines = response.text.strip().split('\n')
    print(f"Processing {len(lines)} lines from AI...")

    for line in lines:
        if not line.strip() or "model_id" in line.lower(): continue
        parts = [p.strip() for p in line.split(',')]
        
        if len(parts) >= 7: # Use >= to be safe
            try:
                m_id, prov, raw_cats, raw_tier, raw_min, raw_max, raw_cost = parts[:7]
                
                tier = tier_map.get(raw_tier.upper(), 2)
                # Robust float conversion
                def to_f(val, default):
                    try: return float(val)
                    except: return val_map.get(val.upper(), default)

                c_min = to_f(raw_min, 1.0)
                c_max = to_f(raw_max, 10.0)
                cost = to_f(raw_cost, 0.5)

                category_parts = [c.strip().upper() for c in raw_cats.split(';') if c.strip()]
                
                for cat_token in category_parts:
                    final_cat = CATEGORY_MAP.get(cat_token, cat_token)
                    if final_cat not in ALLOWED_CATEGORIES:
                        final_cat = "UTILITY"

                    # DB Operation
                    existing = db.query(AIModel).filter_by(model_id=m_id, category=final_cat).first()
                    
                    if existing:
                        existing.tier, existing.complexity_min = tier, c_min
                        existing.complexity_max, existing.cost_per_1m_tokens = c_max, cost
                    else:
                        print(f"➕ Adding: {m_id} [{final_cat}]")
                        db.add(AIModel(
                            model_id=m_id, provider=prov, category=final_cat, tier=tier,
                            complexity_min=c_min, complexity_max=c_max,
                            cost_per_1m_tokens=cost, is_active=True
                        ))
            except Exception as e:
                print(f"❌ Line Error: {e} in line: {line}")
                continue
    
    try:
        db.commit()
        print("💾 Changes committed to Database.")
        
        print("📊 Updating Sub-Tiers...")
        assign_sub_tiers(db)
        
        print("🏗️ Reconstructing Layout...")
        reconstruct_database_layout(db)
        print("✨ Database successfully audited and organized!")
    except SQLAlchemyError as e:
        print(f"❌ DB COMMIT ERROR: {e}")
        db.rollback()
    finally:
        db.close()

# ... (keep your assign_sub_tiers and reconstruct_database_layout as is)

def assign_sub_tiers(db):
    """Refreshes sub-tier rankings for ALL tiers (A = top half, B = bottom half).
    
    BUG #5 FIX: Previously only Tier 1 got sub_tiers. Tier 2 & 3 stayed None,
    causing the router to misroute them into the tier1_b bucket.
    """
    for tier_num in [1, 2, 3]:
        tier_list = db.query(AIModel).filter(
            AIModel.tier == tier_num,
            AIModel.is_active == True
        ).order_by(desc(AIModel.cost_per_1m_tokens)).all()
        
        seen = {}
        rank = 0
        midpoint = max(1, len(tier_list) // 2)  # Top half = A, bottom half = B
        
        for model in tier_list:
            if model.model_id not in seen:
                # Tier 1: Top 3 = A (legacy behaviour preserved)
                # Tier 2 & 3: Top half = A, bottom half = B
                cutoff = 3 if tier_num == 1 else midpoint
                seen[model.model_id] = "A" if rank < cutoff else "B"
                rank += 1
            model.sub_tier = seen[model.model_id]
    db.commit()

def reconstruct_database_layout(db):
    """Physically re-orders the DB by category priority and inserts spacers.
    
    BUG #4 FIX: Added try/except with rollback so a bad model row can't
    silently wipe the entire table without recovery.
    """
    try:
        active = db.query(AIModel).filter(
            AIModel.is_active == True,
            ~AIModel.model_id.startswith("---")
        ).all()
        inactive = db.query(AIModel).filter(
            AIModel.is_active == False,
            ~AIModel.model_id.startswith("---")
        ).all()

        new_layout = []
        for cat in ALLOWED_CATEGORIES:
            cat_models = [m for m in active if m.category == cat]
            if not cat_models:
                continue

            # Sort by Tier then Complexity descending
            sorted_models = sorted(cat_models, key=lambda x: (x.tier, -x.complexity_min))
            new_layout.extend(sorted_models)

            # Category Spacer (visual separator, is_active=False so router skips it)
            new_layout.append(AIModel(
                model_id=f"--- {cat} END ---", provider="---", category=cat, tier=0,
                complexity_min=0.0, complexity_max=0.0, cost_per_1m_tokens=0.0, is_active=False
            ))

        new_layout.extend(inactive)

        # Snapshot count before delete for safety check
        pre_delete_count = len([m for m in new_layout if m.is_active and not m.model_id.startswith("---")])

        db.query(AIModel).delete()
        for item in new_layout:
            db.add(AIModel(
                model_id=item.model_id,
                provider=item.provider,
                category=item.category,
                tier=item.tier,
                sub_tier=item.sub_tier,
                complexity_min=item.complexity_min,
                complexity_max=item.complexity_max,
                cost_per_1m_tokens=item.cost_per_1m_tokens,
                is_active=item.is_active
            ))
        db.commit()
        print(f"   ✅ Layout reconstructed: {pre_delete_count} active models re-inserted.")
    except Exception as e:
        print(f"   ❌ reconstruct_database_layout FAILED: {e} — rolling back to preserve data.")
        db.rollback()
        raise
