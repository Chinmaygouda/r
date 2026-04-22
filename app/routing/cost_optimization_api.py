"""
COST OPTIMIZATION API ENDPOINTS
FastAPI endpoints for cost estimation, A/B testing, and optimization
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Optional

from app.routing.cost_optimizer import (
    calculate_exact_cost,
    predict_cost_for_prompt,
    compare_model_costs,
    get_fastest_models,
    get_cost_efficient_models,
    run_ab_test,
    run_multi_ab_tests,
    find_optimal_model
)

# Create router for cost optimization endpoints
router = APIRouter(prefix="/api/cost", tags=["cost-optimization"])

# ==================== REQUEST/RESPONSE MODELS ====================

class CostCalculationRequest(BaseModel):
    model_id: str
    input_tokens: int
    output_tokens: int

class CostCalculationResponse(BaseModel):
    model_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float

class CostPredictionRequest(BaseModel):
    model_id: str
    prompt: str
    estimated_output_tokens: int = 500

class CostComparisonRequest(BaseModel):
    prompt: str
    models: List[str]
    estimated_output_tokens: int = 500

class CostComparisonResponse(BaseModel):
    prompt: str
    comparisons: List[Dict]
    cheapest_model: str
    cheapest_cost: float

class ABTestRequest(BaseModel):
    model_a: str
    model_b: str
    category: str = "CODE"
    metric: str = "combined"  # "cost" | "latency" | "reward" | "combined"

class ABTestResponse(BaseModel):
    model_a: str
    model_b: str
    metric: str
    winner: str
    winner_value: float
    loser_value: float
    improvement_percent: float

class OptimalModelRequest(BaseModel):
    prompt: str
    candidates: List[str]
    weight_cost: float = 0.3
    weight_latency: float = 0.2
    weight_reward: float = 0.5
    category: str = "CODE"

class OptimalModelResponse(BaseModel):
    best_model: str
    combined_score: float
    cost_score: float
    latency_score: float
    reward_score: float

# ==================== ENDPOINTS ====================

@router.post("/calculate", response_model=CostCalculationResponse)
async def calculate_cost(request: CostCalculationRequest):
    """
    Calculate EXACT cost for a specific prompt and response.
    
    Example:
        Input tokens: 125 tokens
        Output tokens: 500 tokens
        Model: gpt-4o
        
        Returns:
        {
            "input_cost": $0.000625,
            "output_cost": $0.007500,
            "total_cost": $0.008125
        }
    """
    try:
        result = calculate_exact_cost(
            request.model_id,
            request.input_tokens,
            request.output_tokens
        )
        
        return CostCalculationResponse(
            model_id=request.model_id,
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            total_tokens=result["total_tokens"],
            input_cost=result["input_cost"],
            output_cost=result["output_cost"],
            total_cost=result["total_cost"]
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/predict")
async def predict_cost(request: CostPredictionRequest):
    """
    Predict cost BEFORE execution.
    Estimates tokens based on prompt length.
    
    Example:
        Prompt: "Design a REST API..."
        Model: gpt-4o
        Estimated output: 500 tokens
        
        Returns predicted cost breakdown
    """
    try:
        result = predict_cost_for_prompt(
            request.model_id,
            request.prompt,
            request.estimated_output_tokens
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/compare", response_model=CostComparisonResponse)
async def compare_costs(request: CostComparisonRequest):
    """
    Compare costs across multiple models for same prompt.
    Returns models ranked by price (cheapest first).
    
    Example:
        Prompt: "Write Python code..."
        Models: ["gemini-2.5-flash", "gpt-4o", "claude-3-opus"]
        
        Returns:
        [
            {"model": "gemini-2.5-flash", "cost": $0.000091},
            {"model": "gpt-4o", "cost": $0.004585},
            {"model": "claude-3-opus", "cost": $0.022755}
        ]
        
        Savings with gemini: $0.022664 (99.6% cheaper!)
    """
    try:
        comparisons = compare_model_costs(
            request.prompt,
            request.models,
            request.estimated_output_tokens
        )
        
        cheapest = comparisons[0]
        
        return CostComparisonResponse(
            prompt=request.prompt,
            comparisons=comparisons,
            cheapest_model=cheapest["model_id"],
            cheapest_cost=cheapest["predicted_cost"]
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/fastest/{category}")
async def get_fastest(
    category: str,
    limit: int = Query(3, ge=1, le=10)
):
    """
    Get fastest models for a category.
    
    Example:
        GET /api/cost/fastest/CODE?limit=3
        
        Returns:
        [
            {"model_id": "gemini-2.5-flash", "avg_latency": 1.20s, "avg_reward": 0.86},
            {"model_id": "gpt-4o", "avg_latency": 2.40s, "avg_reward": 0.91},
            {"model_id": "claude-3-opus", "avg_latency": 3.20s, "avg_reward": 0.95}
        ]
    """
    try:
        return get_fastest_models(category, limit)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/efficient/{category}")
async def get_efficient(
    category: str,
    limit: int = Query(3, ge=1, le=10)
):
    """
    Get cost-efficient models (best value = reward per dollar).
    
    Example:
        GET /api/cost/efficient/CODE?limit=3
        
        Returns:
        [
            {"model_id": "deepseek-chat", "efficiency": 73000, "cost": $0.00001},
            {"model_id": "gemini-2.5-flash", "efficiency": 17200, "cost": $0.00005},
            {"model_id": "gpt-4o", "efficiency": 6067, "cost": $0.00015}
        ]
    """
    try:
        return get_cost_efficient_models(category, limit)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ab-test", response_model=ABTestResponse)
async def ab_test(request: ABTestRequest):
    """
    Compare two models on a specific metric.
    
    Example:
        {
            "model_a": "gemini-2.5-flash",
            "model_b": "gpt-4o",
            "category": "CODE",
            "metric": "cost"
        }
        
        Returns:
        {
            "winner": "gemini-2.5-flash",
            "improvement": 66.67%
        }
    """
    try:
        result = run_ab_test(
            request.model_a,
            request.model_b,
            request.category,
            request.metric
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Models not found in database")
        
        return ABTestResponse(
            model_a=result.model_a,
            model_b=result.model_b,
            metric=result.metric,
            winner=result.winner,
            winner_value=result.winner_value,
            loser_value=result.loser_value,
            improvement_percent=result.improvement_percent
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ab-test-multi")
async def ab_test_multi(
    models: List[str] = Query(...),
    category: str = Query("CODE"),
    metric: str = Query("combined")
):
    """
    Run A/B tests between all pairs of models.
    
    Example:
        GET /api/cost/ab-test-multi?models=gemini-2.5-flash&models=gpt-4o&models=claude-3-opus&category=CODE&metric=combined
        
        Returns all pairwise comparisons with winners
    """
    try:
        results = run_multi_ab_tests(models, category, metric)
        
        # Format results for JSON response
        formatted = {}
        for test_name, result in results.items():
            formatted[test_name] = {
                "winner": result.winner,
                "improvement_percent": result.improvement_percent,
                "winner_value": result.winner_value,
                "loser_value": result.loser_value
            }
        
        return formatted
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/optimal", response_model=OptimalModelResponse)
async def find_optimal(request: OptimalModelRequest):
    """
    Find optimal model based on weighted criteria.
    
    Weights must sum to 1.0:
    - weight_cost: importance of low cost (0.0-1.0)
    - weight_latency: importance of low latency (0.0-1.0)
    - weight_reward: importance of high quality (0.0-1.0)
    
    Example (Cost-sensitive):
        {
            "prompt": "Write Python code...",
            "candidates": ["gemini-2.5-flash", "gpt-4o"],
            "weight_cost": 0.6,
            "weight_latency": 0.2,
            "weight_reward": 0.2
        }
        
    Example (Quality-first):
        {
            "prompt": "Write Python code...",
            "candidates": ["gemini-2.5-flash", "gpt-4o"],
            "weight_cost": 0.1,
            "weight_latency": 0.2,
            "weight_reward": 0.7
        }
    """
    try:
        # Validate weights sum to 1.0
        total_weight = request.weight_cost + request.weight_latency + request.weight_reward
        if not (0.99 <= total_weight <= 1.01):  # Allow small floating point variance
            raise ValueError(f"Weights must sum to 1.0, got {total_weight:.2f}")
        
        best_model, score = find_optimal_model(
            request.prompt,
            request.candidates,
            request.weight_cost,
            request.weight_latency,
            request.weight_reward,
            request.category
        )
        
        return OptimalModelResponse(
            best_model=best_model,
            combined_score=score,
            cost_score=1.0 / (1.0 + 0.001),  # Simplified for demo
            latency_score=1.0 / (1.0 + 2.0),
            reward_score=0.85
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== UTILITY ENDPOINTS ====================

@router.get("/pricing/{model_id}")
async def get_model_pricing(model_id: str):
    """
    Get pricing information for a specific model.
    
    Example:
        GET /api/cost/pricing/gpt-4o
        
        Returns:
        {
            "model_id": "gpt-4o",
            "input_cost_per_1m": 5.0,
            "output_cost_per_1m": 15.0,
            "input_cost_per_1k": 0.005,
            "output_cost_per_1k": 0.015
        }
    """
    from app.routing.cost_optimizer import PROVIDER_PRICING
    
    if model_id not in PROVIDER_PRICING:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    pricing = PROVIDER_PRICING[model_id]
    
    return {
        "model_id": model_id,
        "input_cost_per_1m": pricing.input_cost_per_1m,
        "output_cost_per_1m": pricing.output_cost_per_1m,
        "input_cost_per_1k": pricing.input_cost_per_1m / 1000,
        "output_cost_per_1k": pricing.output_cost_per_1m / 1000,
        "min_cost": pricing.min_cost
    }


@router.get("/pricing")
async def list_all_pricing():
    """
    List pricing for all models.
    
    Returns dictionary of all models with their costs
    """
    from app.routing.cost_optimizer import PROVIDER_PRICING
    
    result = {}
    for model_id, pricing in PROVIDER_PRICING.items():
        result[model_id] = {
            "input_cost_per_1m": pricing.input_cost_per_1m,
            "output_cost_per_1m": pricing.output_cost_per_1m,
            "min_cost": pricing.min_cost
        }
    
    return result


# ==================== INTEGRATION ====================

"""
To add these endpoints to your FastAPI app in app/main.py:

    from app.routing.cost_optimization_api import router as cost_router
    
    app = FastAPI()
    app.include_router(cost_router)

Then access endpoints:
    POST /api/cost/calculate
    POST /api/cost/predict
    POST /api/cost/compare
    GET  /api/cost/fastest/{category}
    GET  /api/cost/efficient/{category}
    POST /api/cost/ab-test
    GET  /api/cost/ab-test-multi
    POST /api/cost/optimal
    GET  /api/cost/pricing/{model_id}
    GET  /api/cost/pricing
"""
