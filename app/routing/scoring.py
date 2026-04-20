"""
Scoring & ranking module for model selection.
Scores models based on tier, cost, and complexity distance.
"""


def score_models(models):
    """
    Score models based on:
    - Better tier (Tier 1 > Tier 2 > Tier 3)
    - Sub-tier within Tier 1 (A > B for complexity 8.0+)
    - Lower cost
    - Complexity fit (penalty if outside range)
    
    Scoring formula:
    - Tier 1 A: 2.0 base score
    - Tier 1 B: 1.8 base score
    - Tier 2: 1.2 base score
    - Tier 3: 0.6 base score
    - Then subtract: 0.3 * cost + 0.1 * complexity_distance
    """
    for m in models:
        # Base tier score with sub_tier awareness
        if m["tier"] == 1:
            if m["sub_tier"] == "A":
                tier_score = 2.0  # Premium ultra (top 3 models)
            else:  # B or None
                tier_score = 1.8  # Premium standard
        elif m["tier"] == 2:
            tier_score = 1.2  # Standard
        else:  # Tier 3
            tier_score = 0.6  # Budget
        
        # Complexity penalty if model is outside the range
        complexity_penalty = 0.1 * m.get("complexity_distance", 0.0)
        
        # Cost optimization
        cost_penalty = 0.3 * m["cost"]
        
        # Final score: higher is better
        # Tier > Cost > Complexity fit
        m["score"] = tier_score - cost_penalty - complexity_penalty

    return models


def get_top_k(models, k):
    """Return top K models sorted by score (highest first)."""
    return sorted(models, key=lambda x: x["score"], reverse=True)[:k]
