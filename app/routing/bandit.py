"""
Bandit/Exploration fallback module.
Implements Thompson Sampling for intelligent model selection under uncertainty.
"""

from app.routing.thompson_sampler import get_thompson_sampler


def call_bandit(candidates, category: str = "UTILITY"):
    """
    Thompson Sampling bandit - select best candidate using learned performance.
    
    When confidence is low, we use Thompson Sampling to:
    1. Leverage historical performance (exploitation)
    2. Explore promising alternatives (exploration)
    3. Balance both automatically through posterior sampling
    
    Args:
        candidates: List of dicts with 'name' and 'score' keys
        category: Task category for context
    
    Returns:
        Selected model name
    """
    if not candidates:
        return None
    
    if len(candidates) == 1:
        return candidates[0]["name"]
    
    # Get Thompson Sampler
    sampler = get_thompson_sampler()
    
    # Register all candidates
    candidate_names = [c["name"] for c in candidates]
    for name in candidate_names:
        sampler.register_model(name)
    
    # Use Thompson Sampling to select best candidate
    selected_model, samples = sampler.select_best_thompson(candidate_names)
    
    print(f"[BANDIT] Thompson Sampling Selection:")
    print(f"  Candidates: {candidate_names}")
    print(f"  Posterior Samples: {{{', '.join(f'{m}: {s:.3f}' for m, s in samples.items())}}}")
    print(f"  Selected: {selected_model} (sample={samples[selected_model]:.3f})")
    
    return selected_model


def get_model_recommendations(limit: int = 5):
    """
    Get top-performing models based on Thompson Sampling posteriors.
    
    Returns:
        List of (model_name, posterior_mean) tuples
    """
    sampler = get_thompson_sampler()
    return sampler.get_model_recommendations(top_k=limit)


def get_bandit_stats(model_name: str = None):
    """
    Get bandit statistics for a model or all models.
    
    Args:
        model_name: Specific model or None for all
    
    Returns:
        Stats dict or dict of all stats
    """
    sampler = get_thompson_sampler()
    if model_name:
        return sampler.get_model_stats(model_name)
    else:
        return sampler.get_all_stats()


def update_bandit_reward(model_name: str, reward: float):
    """
    Update Thompson Sampling with reward feedback.
    
    Args:
        model_name: Model that was used
        reward: Reward score 0-1
    """
    sampler = get_thompson_sampler()
    sampler.register_model(model_name)
    sampler.update_performance(model_name, reward)

