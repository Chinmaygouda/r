"""
Reward Calculation Module
Calculates reward based on cost, latency, and quality signals
"""

import time
from typing import Dict, Any


def calculate_reward(
    model_name: str,
    category: str,
    tokens_consumed: int,
    cost_usd: float,
    latency_seconds: float,
    response_quality: float = 1.0,
    user_satisfaction: float = 1.0
) -> Dict[str, float]:
    """
    Calculate reward for model performance.
    
    Reward components:
    1. Quality reward (0-1): How good was the response
    2. Cost efficiency reward (0-1): Low cost = high reward
    3. Latency reward (0-1): Low latency = high reward
    4. Combined reward: Weighted average of all components
    
    Args:
        model_name: Name of the model used
        category: Task category (CODE, ANALYSIS, etc.)
        tokens_consumed: Number of tokens used
        cost_usd: Actual cost in USD
        latency_seconds: Response time in seconds
        response_quality: Quality score 0-1 (default 1.0 = good)
        user_satisfaction: User satisfaction 0-1 (default 1.0 = satisfied)
    
    Returns:
        Dict with reward breakdown and combined score
    """
    
    # 1. Quality Reward (normalized 0-1)
    quality_reward = min(response_quality, 1.0)
    
    # 2. Cost Efficiency Reward
    # Penalize expensive models, reward cheap ones
    # Assuming typical cost range $0.001 - $0.05 per request
    cost_penalty = min(cost_usd / 0.05, 1.0)  # Max penalty at $0.05
    cost_reward = 1.0 - (cost_penalty * 0.3)  # Cost has 30% weight
    cost_reward = max(cost_reward, 0.0)
    
    # 3. Latency Reward
    # Fast responses = high reward, slow responses = low reward
    # Assuming typical latency 0.5s - 30s for API calls
    latency_penalty = min(latency_seconds / 30.0, 1.0)  # Max penalty at 30s
    latency_reward = 1.0 - (latency_penalty * 0.2)  # Latency has 20% weight
    latency_reward = max(latency_reward, 0.0)
    
    # 4. User Satisfaction Reward
    satisfaction_reward = min(user_satisfaction, 1.0)
    
    # Combined reward: 50% quality, 20% cost, 20% latency, 10% satisfaction
    combined_reward = (
        quality_reward * 0.50 +
        cost_reward * 0.20 +
        latency_reward * 0.20 +
        satisfaction_reward * 0.10
    )
    combined_reward = max(min(combined_reward, 1.0), 0.0)
    
    return {
        "model_name": model_name,
        "quality_reward": round(quality_reward, 4),
        "cost_reward": round(cost_reward, 4),
        "latency_reward": round(latency_reward, 4),
        "satisfaction_reward": round(satisfaction_reward, 4),
        "combined_reward": round(combined_reward, 4),
        "metrics": {
            "tokens": tokens_consumed,
            "cost_usd": round(cost_usd, 6),
            "latency_seconds": round(latency_seconds, 2)
        }
    }


def infer_quality_score(
    category: str,
    response_length: int,
    has_code: bool = False,
    has_errors: bool = False
) -> float:
    """
    Infer basic quality score from response characteristics.
    
    Args:
        category: Task category
        response_length: Length of response in characters
        has_code: Whether response contains code (relevant for CODE category)
        has_errors: Whether response indicates errors/failures
    
    Returns:
        Quality score 0-1
    """
    
    base_score = 1.0
    
    # If empty response, quality is poor
    if response_length == 0:
        return 0.0
    
    # If response has errors, reduce quality
    if has_errors:
        base_score -= 0.3
    
    # For CODE category, having code is good
    if category == "CODE" and has_code:
        base_score += 0.1
    
    # If response too short, assume incomplete
    if response_length < 50:
        base_score -= 0.1
    
    return max(min(base_score, 1.0), 0.0)
