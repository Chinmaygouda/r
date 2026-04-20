"""
Database wrapper for model fetching.
Uses SQLAlchemy ORM instead of raw psycopg2.
"""

from database.session import SessionLocal
from app.models import AIModel, ModelPerformance


def fetch_models():
    """
    Fetch all active models from database.
    
    Returns list of dicts with keys:
    - name: model_id
    - category: model category
    - tier: 1, 2, or 3
    - complexity_min: minimum complexity score
    - complexity_max: maximum complexity score
    - cost: cost_per_1m_tokens
    - active: is_active boolean
    """
    db = SessionLocal()
    
    try:
        models_query = db.query(AIModel).filter(
            AIModel.is_active == True
        ).all()
        
        models = []
        for m in models_query:
            models.append({
                "name": m.model_id,
                "category": m.category,
                "tier": m.tier,
                "complexity_min": m.complexity_min,
                "complexity_max": m.complexity_max,
                "cost": m.cost_per_1m_tokens,
                "active": m.is_active,
                "provider": m.provider,
                "sub_tier": m.sub_tier
            })
        
        return models
    
    finally:
        db.close()


def get_model_performance(model_id: str, category: str = None):
    """
    Get performance data for a model.
    If category is None, return all categories for the model.
    """
    db = SessionLocal()
    try:
        if category:
            perf = db.query(ModelPerformance).filter(
                ModelPerformance.model_id == model_id,
                ModelPerformance.category == category
            ).first()
            if perf:
                return {
                    "model_id": perf.model_id,
                    "category": perf.category,
                    "alpha": perf.alpha,
                    "beta": perf.beta,
                    "total_selections": perf.total_selections,
                    "successful_responses": perf.successful_responses,
                    "failed_responses": perf.failed_responses,
                    "total_reward": round(perf.total_reward, 4),
                    "avg_reward": round(perf.avg_reward, 4),
                    "avg_cost": round(perf.avg_cost, 6),
                    "avg_latency": round(perf.avg_latency, 2)
                }
            return None
        else:
            perfs = db.query(ModelPerformance).filter(
                ModelPerformance.model_id == model_id
            ).all()
            return [
                {
                    "model_id": p.model_id,
                    "category": p.category,
                    "alpha": p.alpha,
                    "beta": p.beta,
                    "avg_reward": round(p.avg_reward, 4),
                }
                for p in perfs
            ]
    finally:
        db.close()


def update_model_performance(model_id: str, category: str, reward: float, 
                            cost: float = 0.0, latency: float = 0.0):
    """
    Update model performance after response.
    
    Args:
        model_id: Model identifier
        category: Task category
        reward: Reward score 0-1
        cost: Actual cost of the response
        latency: Response time in seconds
    """
    db = SessionLocal()
    try:
        # Find or create performance record
        perf = db.query(ModelPerformance).filter(
            ModelPerformance.model_id == model_id,
            ModelPerformance.category == category
        ).first()
        
        if not perf:
            perf = ModelPerformance(
                model_id=model_id,
                category=category,
                alpha=1.0,
                beta=1.0,
                total_selections=0,
                successful_responses=0,
                failed_responses=0,
                total_reward=0.0,
                avg_reward=0.0,
                avg_cost=0.0,
                avg_latency=0.0
            )
            db.add(perf)
        
        # Update statistics
        perf.total_selections = (perf.total_selections or 0) + 1
        perf.total_reward = (perf.total_reward or 0.0) + reward
        perf.avg_reward = perf.total_reward / perf.total_selections
        
        # Update cost average
        if (perf.avg_cost or 0.0) == 0.0:
            perf.avg_cost = cost
        else:
            perf.avg_cost = (perf.avg_cost * (perf.total_selections - 1) + cost) / perf.total_selections
        
        # Update latency average
        if (perf.avg_latency or 0.0) == 0.0:
            perf.avg_latency = latency
        else:
            perf.avg_latency = (perf.avg_latency * (perf.total_selections - 1) + latency) / perf.total_selections
        
        # Update Thompson Sampling parameters (Beta distribution)
        if reward >= 0.7:  # Good reward
            perf.alpha += 1
            perf.successful_responses = (perf.successful_responses or 0) + 1
        else:
            perf.beta += 1
            perf.failed_responses = (perf.failed_responses or 0) + 1
        
        db.commit()
        
        return {
            "model_id": perf.model_id,
            "category": perf.category,
            "alpha": perf.alpha,
            "beta": perf.beta,
            "avg_reward": round(perf.avg_reward, 4),
            "total_selections": perf.total_selections
        }
    except Exception as e:
        db.rollback()
        print(f"Error updating model performance: {e}")
        raise
    finally:
        db.close()


def get_top_performing_models(category: str = None, limit: int = 10):
    """
    Get top performing models by average reward.
    """
    db = SessionLocal()
    try:
        query = db.query(ModelPerformance)
        
        if category:
            query = query.filter(ModelPerformance.category == category)
        
        results = query.order_by(
            ModelPerformance.avg_reward.desc()
        ).limit(limit).all()
        
        return [
            {
                "model_id": r.model_id,
                "category": r.category,
                "avg_reward": round(r.avg_reward, 4),
                "total_selections": r.total_selections,
                "success_rate": round(
                    r.successful_responses / r.total_selections if r.total_selections > 0 else 0,
                    4
                )
            }
            for r in results
        ]
    finally:
        db.close()

