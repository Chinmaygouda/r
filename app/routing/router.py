"""
INTEGRATED ROUTER V2.0
Combines Gemini complexity analysis with filtering+scoring logic.

Flow:
1. STEP 1: Analyze prompt with Gemini → get complexity score + category
2. STEP 2: Fetch models from database
3. STEP 3: Filter models (category, tier, complexity range)
4. STEP 4: Score models (tier + cost + complexity fit)
5. STEP 5: Get top-K candidates
6. STEP 6: Confidence check → select best or defer to bandit
"""

from google import genai
import os
import sys

from database.session import SessionLocal
from app.models import AIModel
from database.db import fetch_models
from app.routing.scoring import score_models, get_top_k
from app.routing.confidence import compute_confidence
from app.routing.bandit import call_bandit
from config.settings import CONFIDENCE_THRESHOLD, TOP_K, TIER_RULES
from sqlalchemy import and_, desc

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

ROUTER_PROMPT = """
Analyze the user's prompt and determine:
1. Complexity score (1.0 to 10.0).
2. Intent Category. Choose the MOST specific one from: [CODE, AGENTS, ANALYSIS, EXTRACTION, CREATIVE, UTILITY, CHAT].
   - Priority: If it involves code, choose CODE. If it involves data/logic, choose ANALYSIS.
3. Needs_CoT (True/False): Does this require complex reasoning or Chain of Thought?
4. Logical_Necessity (True/False): Is a high-tier model absolutely required to prevent failure?
5. Is_Long_Output (True/False): Does the user need a massive output?

Return ONLY comma-separated values matching this format:
score, category, needs_cot, logical_necessity, is_long_output
Example: 8.5, CODE, True, False, True
"""


def complexity_distance(model, complexity_score):
    """Calculate how far a model's range is from the requested complexity."""
    if model["complexity_min"] <= complexity_score <= model["complexity_max"]:
        return 0.0  # Perfect fit
    
    if complexity_score < model["complexity_min"]:
        return model["complexity_min"] - complexity_score  # Below range
    
    return complexity_score - model["complexity_max"]  # Above range


def filter_models(models, category, complexity_score, complexity_label):
    """
    Filter models by:
    - Category match
    - Tier rules (EASY → Tier 2,3 | MEDIUM → Tier 1,2 | HARD → Tier 1)
    - Complexity range (must fall within model's min-max)
    - Sub-tier awareness: Tier 1 A (8.0-9.8) for ultra-high, Tier 1 B (7.5-9.5) for high
    - Active status
    """
    filtered = []
    
    category = category.upper()
    complexity_label = complexity_label.upper()
    
    # Get allowed tiers for this complexity level
    allowed_tiers = TIER_RULES.get(complexity_label, [1, 2, 3])
    
    # Separate by tier for intelligent selection
    tier1_a = []  # Premium ultra-complex (sub_tier A)
    tier1_b = []  # Premium complex (sub_tier B)
    tier2 = []    # Standard medium-complex
    tier3 = []    # Budget low-complex
    
    for m in models:
        # Skip inactive models
        if not m["active"]:
            continue
        
        # FIX: MULTI category should map to AGENTS or CHAT in DB
        target_categories = [category]
        if category == "MULTI":
            target_categories = ["MULTI", "AGENTS", "CHAT"]
            
        if m["category"] not in target_categories:
            continue
        
        # Skip if tier not allowed for this complexity level
        if m["tier"] not in allowed_tiers:
            continue
        
        # Check if complexity score falls within model's range
        if m["complexity_min"] <= complexity_score <= m["complexity_max"]:
            # Categorize by tier and sub_tier
            if m["tier"] == 1:
                if m["sub_tier"] == "A":
                    tier1_a.append(m)
                else:  # sub_tier B or None
                    tier1_b.append(m)
            elif m["tier"] == 2:
                tier2.append(m)
            else:  # tier 3
                tier3.append(m)
    
    # Intelligently prioritize: Tier 1 A > Tier 1 B > Tier 2 > Tier 3
    # For high complexity (7.5+), prefer Tier 1; for medium (5.5-7.5), allow Tier 2
    if complexity_score >= 8.0:
        # Ultra-high: prefer Tier 1 A
        filtered = tier1_a + tier1_b + tier2 + tier3
    elif complexity_score >= 7.5:
        # High: prefer Tier 1 (A then B)
        filtered = tier1_a + tier1_b + tier2 + tier3
    elif complexity_score >= 5.5:
        # Medium: allow Tier 1 B and Tier 2
        filtered = tier1_b + tier1_a + tier2 + tier3
    else:
        # Low: all tiers okay
        filtered = tier3 + tier2 + tier1_b + tier1_a
    
    return filtered


def route_model(category, complexity_score, complexity_label):
    """
    Main routing function integrating filtering + scoring + confidence.
    
    Returns:
    {
        "candidate_models": [model names],
        "selected_model": best model name,
        "confidence": confidence score (0.0-1.0),
        "category": detected category,
        "complexity_score": complexity score
    }
    """
    print(f"\n[ROUTING] category={category}, complexity={complexity_label}({complexity_score})")
    
    # STEP 1: Fetch all models
    all_models = fetch_models()
    print(f"[MODELS] Fetched {len(all_models)} models from database")
    
    # STEP 2: Filter models
    filtered = filter_models(all_models, category, complexity_score, complexity_label)
    print(f"[FILTER] Filtered: {len(filtered)} models match criteria")
    
    if not filtered:
        # FALLBACK: Relax to nearest complexity
        print("[WARN] No exact match - relaxing complexity constraint")
        filtered = [m for m in all_models if m["active"] and m["category"] == category]
        
        for m in filtered:
            m["complexity_distance"] = complexity_distance(m, complexity_score)
        
        # Sort by distance, then tier, then cost
        filtered.sort(key=lambda x: (x["complexity_distance"], x["tier"], x["cost"]))
        
        if filtered:
            print(f"📍 Relaxed: {len(filtered)} models by category alone")
            filtered = filtered[:TOP_K]
    
    if not filtered:
        print("❌ No models available - fallback to Gemini")
        return {
            "candidate_models": [],
            "selected_model": "gemini-2.5-flash",
            "confidence": 0.0,
            "category": category,
            "complexity_score": complexity_score
        }
    
    # STEP 3: Score models
    scored = score_models(filtered)
    
    # STEP 4: Get top-K
    candidates = get_top_k(scored, TOP_K)
    print(f"[CANDIDATES] Top candidates: {[m['name'] for m in candidates]}")
    
    # STEP 5: Confidence check
    confidence = compute_confidence(candidates)
    print(f"[CONFIDENCE] Score: {confidence:.3f}")
    
    # STEP 6: Decision
    if confidence >= CONFIDENCE_THRESHOLD:
        selected_model = candidates[0]["name"]
        print(f"[SELECTED] HIGH CONFIDENCE: Selected {selected_model}")
    else:
        selected_model = call_bandit(candidates)
        print(f"[SELECTED] LOW CONFIDENCE: Bandit selected {selected_model}")
    
    return {
        "candidate_models": [m["name"] for m in candidates],
        "selected_model": selected_model,
        "confidence": round(confidence, 3),
        "category": category,
        "complexity_score": complexity_score
    }


def get_best_model(user_prompt, user_allowed_tier):
    """
    Legacy wrapper for compatibility with existing vault_service.py
    
    Flow:
    1. Analyze prompt with DeBERTa → complexity + category
    2. Convert complexity score to label (EASY/MEDIUM/HARD)
    3. Apply heuristics for MULTI classification (Fix 1)
    4. Route using new filtering+scoring logic
    5. Return model_id, provider, score, category, tier, candidate_fallbacks
    """
    # --- STEP 1: MACRO-ROUTING (DeBERTa Offline Analysis) ---
    print(f"[ANALYSIS] Analyzing prompt with Local DeBERTa...")
    from app.routing.deberta_classifier import get_semantic_classifier
    
    classifier = get_semantic_classifier()
    
    try:
        category, confidence, complexity_label = classifier.classify_with_complexity(user_prompt)
        
        # We need a float score for micro-routing logic.
        if complexity_label == "HARD":
            score = 8.5
        elif complexity_label == "MEDIUM":
            score = 5.5
        else:
            score = 3.0
            
    except Exception as e:
        print(f"[WARN] Local classifier error: {e} - using fallback")
        score, category, complexity_label = 5.0, "UTILITY", "MEDIUM"
        
    # --- FIX 1: HEURISTIC OVERRIDE FOR "MULTI" ---
    # DeBERTa doesn't know 'MULTI', so it maps complex multi-step prompts to 'AGENTS' or 'CODE'.
    multi_step_keywords = ["first", "then", "finally", "also", "and then"]
    keyword_count = sum(1 for kw in multi_step_keywords if kw in user_prompt.lower())
    if keyword_count >= 2:
        print("[HEURISTIC] Detected multi-step prompt. Overriding category to MULTI.")
        category = "MULTI"
    
    print(f"📊 Analysis: score={score}, category={category}, label={complexity_label}")
    
    # --- STEP 2-6: MICRO-ROUTING ---
    result = route_model(category, score, complexity_label)
    selected_model_id = result["selected_model"]
    candidate_names = result["candidate_models"]
    
    db = SessionLocal()
    try:
        # Resolve the top model
        top_model = db.query(AIModel).filter(AIModel.model_id == selected_model_id).first()
        top_provider = top_model.provider if top_model else "Unknown"
        top_tier = top_model.tier if top_model else 2
        
        # Resolve fallbacks
        fallbacks = []
        for c_name in candidate_names:
            c_model = db.query(AIModel).filter(AIModel.model_id == c_name).first()
            if c_model:
                fallbacks.append({"model_id": c_model.model_id, "provider": c_model.provider})
                
        # If fallback list is empty, put gemini-flash-latest as universal fallback
        if not fallbacks:
            fallbacks.append({"model_id": "gemini-flash-latest", "provider": "Google"})
            
        print(f"🔄 Routing resolved with {len(fallbacks)-1} fallbacks.")
        return selected_model_id, top_provider, score, category, top_tier, fallbacks
    finally:
        db.close()
