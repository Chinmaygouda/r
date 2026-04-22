"""
COST OPTIMIZATION MODULE
Calculates exact token costs, predicts costs, and optimizes model selection
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from database.session import SessionLocal
from app.models import AIModel, ModelPerformance


@dataclass
class TokenPricing:
    """Token pricing structure for a model"""
    input_cost_per_1m: float      # Cost per 1M input tokens
    output_cost_per_1m: float     # Cost per 1M output tokens
    min_cost: float = 0.0         # Minimum charge per request
    

# Updated pricing data - EXACT TOKEN COSTS (not averaged)
PROVIDER_PRICING = {
    # Google Gemini models
    "gemini-2.5-flash": TokenPricing(
        input_cost_per_1m=0.075,
        output_cost_per_1m=0.3
    ),
    "gemini-2.0-flash": TokenPricing(
        input_cost_per_1m=0.075,
        output_cost_per_1m=0.3
    ),
    "gemini-1.5-pro": TokenPricing(
        input_cost_per_1m=3.5,
        output_cost_per_1m=10.5
    ),
    "gemini-1.5-flash": TokenPricing(
        input_cost_per_1m=0.075,
        output_cost_per_1m=0.3
    ),
    
    # OpenAI models
    "gpt-4o": TokenPricing(
        input_cost_per_1m=5.0,
        output_cost_per_1m=15.0
    ),
    "gpt-4-turbo": TokenPricing(
        input_cost_per_1m=10.0,
        output_cost_per_1m=30.0
    ),
    "gpt-4": TokenPricing(
        input_cost_per_1m=30.0,
        output_cost_per_1m=60.0
    ),
    "gpt-3.5-turbo": TokenPricing(
        input_cost_per_1m=0.5,
        output_cost_per_1m=1.5
    ),
    
    # Anthropic models
    "claude-3-opus": TokenPricing(
        input_cost_per_1m=15.0,
        output_cost_per_1m=75.0
    ),
    "claude-3-sonnet": TokenPricing(
        input_cost_per_1m=3.0,
        output_cost_per_1m=15.0
    ),
    "claude-3-haiku": TokenPricing(
        input_cost_per_1m=0.8,
        output_cost_per_1m=4.0
    ),
    
    # Cohere models
    "command-r-plus": TokenPricing(
        input_cost_per_1m=3.0,
        output_cost_per_1m=15.0
    ),
    "command-r": TokenPricing(
        input_cost_per_1m=0.5,
        output_cost_per_1m=1.5
    ),
    
    # DeepSeek models
    "deepseek-chat": TokenPricing(
        input_cost_per_1m=0.14,
        output_cost_per_1m=0.28
    ),
    
    # xAI models
    "grok-2": TokenPricing(
        input_cost_per_1m=2.0,
        output_cost_per_1m=10.0
    ),
    
    # Mistral models
    "mistral-large": TokenPricing(
        input_cost_per_1m=2.0,
        output_cost_per_1m=6.0
    ),
    "mistral-medium": TokenPricing(
        input_cost_per_1m=0.27,
        output_cost_per_1m=0.81
    ),
    
    # Together models
    "gemma-3-27b-it": TokenPricing(
        input_cost_per_1m=0.3,
        output_cost_per_1m=0.3
    ),
    "llama-3-70b": TokenPricing(
        input_cost_per_1m=0.9,
        output_cost_per_1m=0.9
    ),
}


# ==================== EXACT COST CALCULATION ====================

def calculate_exact_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int
) -> Dict[str, float]:
    """
    Calculate EXACT cost for a specific prompt and response.
    
    Args:
        model_id: Model name
        input_tokens: Tokens in user's prompt
        output_tokens: Tokens in model's response
    
    Returns:
        Dict with input_cost, output_cost, total_cost
    """
    if model_id not in PROVIDER_PRICING:
        # Fallback: estimate from database
        pricing = _get_pricing_from_db(model_id)
        if not pricing:
            pricing = TokenPricing(input_cost_per_1m=0.1, output_cost_per_1m=0.3)
    else:
        pricing = PROVIDER_PRICING[model_id]
    
    input_cost = (input_tokens / 1_000_000) * pricing.input_cost_per_1m
    output_cost = (output_tokens / 1_000_000) * pricing.output_cost_per_1m
    total_cost = input_cost + output_cost
    
    # Apply minimum cost if set
    if total_cost < pricing.min_cost:
        total_cost = pricing.min_cost
    
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "total_cost": round(total_cost, 6)
    }


def _get_pricing_from_db(model_id: str) -> Optional[TokenPricing]:
    """Fetch pricing from database if available"""
    db = SessionLocal()
    try:
        model = db.query(AIModel).filter(
            AIModel.model_id == model_id
        ).first()
        
        if model and model.cost_per_1m_tokens:
            return TokenPricing(
                input_cost_per_1m=model.cost_per_1m_tokens,
                output_cost_per_1m=model.cost_per_1m_tokens * 3  # Rough estimate
            )
        return None
    finally:
        db.close()


# ==================== COST PREDICTION ====================

def predict_cost_for_prompt(
    model_id: str,
    prompt: str,
    estimated_output_tokens: int = 500
) -> Dict[str, float]:
    """
    Predict cost for a prompt BEFORE execution.
    
    Args:
        model_id: Model to use
        prompt: User's prompt
        estimated_output_tokens: Expected response length (default 500)
    
    Returns:
        Predicted cost breakdown
    """
    # Rough estimate: 1 token ≈ 4 characters for English
    input_tokens = max(len(prompt) // 4, 1)
    
    return calculate_exact_cost(model_id, input_tokens, estimated_output_tokens)


def compare_model_costs(
    prompt: str,
    model_ids: List[str],
    estimated_output_tokens: int = 500
) -> List[Dict]:
    """
    Compare costs across multiple models for same prompt.
    
    Args:
        prompt: User's prompt
        model_ids: List of models to compare
        estimated_output_tokens: Expected response length
    
    Returns:
        Sorted list of models with costs (cheapest first)
    """
    results = []
    
    for model_id in model_ids:
        cost_data = predict_cost_for_prompt(model_id, prompt, estimated_output_tokens)
        results.append({
            "model_id": model_id,
            "predicted_cost": cost_data["total_cost"],
            "input_cost": cost_data["input_cost"],
            "output_cost": cost_data["output_cost"]
        })
    
    # Sort by total cost (ascending)
    return sorted(results, key=lambda x: x["predicted_cost"])


# ==================== LATENCY OPTIMIZATION ====================

def get_fastest_models(
    category: str,
    limit: int = 3
) -> List[Dict]:
    """
    Get models with best average latency for a category.
    
    Args:
        category: Task category (CODE, ANALYSIS, etc.)
        limit: Number of models to return
    
    Returns:
        List of fastest models with latency stats
    """
    db = SessionLocal()
    try:
        results = db.query(ModelPerformance).filter(
            ModelPerformance.category == category
        ).order_by(
            ModelPerformance.avg_latency.asc()
        ).limit(limit).all()
        
        return [{
            "model_id": r.model_id,
            "avg_latency": round(r.avg_latency, 2),
            "avg_reward": round(r.avg_reward, 4),
            "selections": r.total_selections
        } for r in results]
    finally:
        db.close()


def get_cost_efficient_models(
    category: str,
    limit: int = 3
) -> List[Dict]:
    """
    Get models with best cost-to-performance ratio.
    
    Args:
        category: Task category
        limit: Number of models to return
    
    Returns:
        List of cost-efficient models
    """
    db = SessionLocal()
    try:
        results = db.query(ModelPerformance).filter(
            ModelPerformance.category == category
        ).all()
        
        # Calculate cost-efficiency score: reward per dollar
        scored = []
        for r in results:
            if r.avg_cost > 0:
                efficiency = r.avg_reward / r.avg_cost
            else:
                efficiency = r.avg_reward
            
            scored.append({
                "model_id": r.model_id,
                "avg_cost": round(r.avg_cost, 6),
                "avg_reward": round(r.avg_reward, 4),
                "efficiency_score": round(efficiency, 4),
                "selections": r.total_selections
            })
        
        # Sort by efficiency (descending)
        return sorted(scored, key=lambda x: x["efficiency_score"], reverse=True)[:limit]
    finally:
        db.close()


# ==================== A/B TESTING ====================

@dataclass
class ABTestResult:
    """Result of an A/B test comparison"""
    model_a: str
    model_b: str
    metric: str  # "cost", "latency", "reward", "combined"
    winner: str
    winner_value: float
    loser_value: float
    improvement_percent: float


def run_ab_test(
    model_a: str,
    model_b: str,
    category: str,
    metric: str = "combined"
) -> Optional[ABTestResult]:
    """
    Compare two models on a metric.
    
    Args:
        model_a: First model
        model_b: Second model
        category: Task category
        metric: "cost" | "latency" | "reward" | "combined"
    
    Returns:
        Comparison result
    """
    db = SessionLocal()
    try:
        perf_a = db.query(ModelPerformance).filter(
            ModelPerformance.model_id == model_a,
            ModelPerformance.category == category
        ).first()
        
        perf_b = db.query(ModelPerformance).filter(
            ModelPerformance.model_id == model_b,
            ModelPerformance.category == category
        ).first()
        
        if not perf_a or not perf_b:
            return None
        
        # Determine metric and winner
        if metric == "cost":
            val_a, val_b = perf_a.avg_cost, perf_b.avg_cost
            winner = model_b if val_b < val_a else model_a
            winner_val = min(val_a, val_b)
            loser_val = max(val_a, val_b)
            
        elif metric == "latency":
            val_a, val_b = perf_a.avg_latency, perf_b.avg_latency
            winner = model_b if val_b < val_a else model_a
            winner_val = min(val_a, val_b)
            loser_val = max(val_a, val_b)
            
        elif metric == "reward":
            val_a, val_b = perf_a.avg_reward, perf_b.avg_reward
            winner = model_a if val_a > val_b else model_b
            winner_val = max(val_a, val_b)
            loser_val = min(val_a, val_b)
            
        else:  # combined
            score_a = perf_a.avg_reward / (perf_a.avg_cost + 0.0001)
            score_b = perf_b.avg_reward / (perf_b.avg_cost + 0.0001)
            winner = model_a if score_a > score_b else model_b
            winner_val = max(score_a, score_b)
            loser_val = min(score_a, score_b)
        
        improvement = ((winner_val - loser_val) / loser_val * 100) if loser_val > 0 else 0
        
        return ABTestResult(
            model_a=model_a,
            model_b=model_b,
            metric=metric,
            winner=winner,
            winner_value=round(winner_val, 6),
            loser_value=round(loser_val, 6),
            improvement_percent=round(improvement, 2)
        )
    finally:
        db.close()


def run_multi_ab_tests(
    models: List[str],
    category: str,
    metric: str = "combined"
) -> Dict[str, ABTestResult]:
    """
    Run A/B tests between all pairs of models.
    
    Args:
        models: List of model IDs
        category: Task category
        metric: Test metric
    
    Returns:
        Dict of test results
    """
    results = {}
    
    for i, model_a in enumerate(models):
        for model_b in models[i+1:]:
            test_name = f"{model_a} vs {model_b}"
            result = run_ab_test(model_a, model_b, category, metric)
            if result:
                results[test_name] = result
    
    return results


# ==================== HYBRID COST-PERFORMANCE ====================

def find_optimal_model(
    prompt: str,
    candidates: List[str],
    weight_cost: float = 0.3,
    weight_latency: float = 0.2,
    weight_reward: float = 0.5,
    category: str = "CODE"
) -> Tuple[str, float]:
    """
    Find best model balancing cost, latency, and reward.
    
    Args:
        prompt: User's prompt
        candidates: List of candidate models
        weight_cost: Cost weight (0-1)
        weight_latency: Latency weight (0-1)
        weight_reward: Reward weight (0-1)
        category: Task category
    
    Returns:
        (best_model_id, combined_score)
    """
    db = SessionLocal()
    try:
        scores = []
        
        for model_id in candidates:
            # Get performance stats
            perf = db.query(ModelPerformance).filter(
                ModelPerformance.model_id == model_id,
                ModelPerformance.category == category
            ).first()
            
            if not perf or perf.total_selections < 5:
                # Not enough data, skip
                continue
            
            # Normalize metrics to 0-1 scale
            cost_score = 1.0 / (1.0 + perf.avg_cost)  # Lower cost = higher score
            latency_score = 1.0 / (1.0 + perf.avg_latency)  # Lower latency = higher score
            reward_score = perf.avg_reward  # Already 0-1
            
            # Weighted combination
            combined = (
                cost_score * weight_cost +
                latency_score * weight_latency +
                reward_score * weight_reward
            )
            
            scores.append({
                "model_id": model_id,
                "score": combined,
                "cost_score": cost_score,
                "latency_score": latency_score,
                "reward_score": reward_score
            })
        
        if not scores:
            return (candidates[0], 0.0)
        
        best = max(scores, key=lambda x: x["score"])
        return (best["model_id"], round(best["score"], 4))
    finally:
        db.close()
