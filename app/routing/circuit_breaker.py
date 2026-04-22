"""
Circuit Breaker for Model Failures
Implements fault tolerance with automatic failover and circuit breaker pattern.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict
import threading

class CircuitBreakerState:
    """Tracks state of a single model's circuit breaker."""
    
    def __init__(self, failure_threshold: int = 3, timeout_seconds: int = 300):
        """
        Initialize circuit breaker for a model.
        
        Args:
            failure_threshold: Number of consecutive failures before tripping
            timeout_seconds: Seconds to pause traffic after trip (default 5 min)
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.circuit_open = False  # True when tripped
        self.trip_time: Optional[datetime] = None
        self.lock = threading.Lock()
    
    def record_success(self):
        """Record a successful call - reset failure counter."""
        with self.lock:
            self.failure_count = 0
            # If circuit was open and timeout passed, close it
            if self.circuit_open and self.trip_time:
                elapsed = (datetime.now() - self.trip_time).total_seconds()
                if elapsed > self.timeout_seconds:
                    self.circuit_open = False
                    self.trip_time = None
                    print(f"🟢 Circuit CLOSED - traffic resumed")
    
    def record_failure(self) -> bool:
        """
        Record a failed call - may trip the circuit.
        
        Returns:
            True if circuit is now open (traffic should be stopped)
        """
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            if self.failure_count >= self.failure_threshold:
                self.circuit_open = True
                self.trip_time = datetime.now()
                print(f"🔴 Circuit OPEN ({self.failure_count} failures) - traffic paused for {self.timeout_seconds}s")
                return True
            
            print(f"⚠️  Failure #{self.failure_count}/{self.failure_threshold}")
            return False
    
    def is_open(self) -> bool:
        """Check if circuit is currently open (tripped)."""
        with self.lock:
            if not self.circuit_open:
                return False
            
            # Check if timeout has elapsed
            if self.trip_time:
                elapsed = (datetime.now() - self.trip_time).total_seconds()
                if elapsed > self.timeout_seconds:
                    self.circuit_open = False
                    self.trip_time = None
                    return False
            
            return True
    
    def get_status(self) -> Dict:
        """Get current status."""
        with self.lock:
            return {
                "is_open": self.circuit_open,
                "failures": self.failure_count,
                "last_failure": self.last_failure_time,
                "trip_time": self.trip_time
            }


class ModelCircuitBreaker:
    """
    Manages circuit breakers for all models.
    Provides fallback model selection when primary fails.
    """
    
    def __init__(self):
        """Initialize circuit breaker manager."""
        self.breakers: Dict[str, CircuitBreakerState] = defaultdict(
            lambda: CircuitBreakerState(failure_threshold=3, timeout_seconds=300)
        )
        self.model_rankings: Dict[str, List[str]] = {}  # category → [model1, model2, ...]
    
    def register_model_ranking(self, category: str, models: List[str]):
        """
        Register the ranked list of models for a category.
        Used for fallback selection.
        
        Args:
            category: Task category (CODE, ANALYSIS, etc.)
            models: List of model IDs in preference order
        """
        self.model_rankings[category] = models
    
    def record_success(self, model_id: str):
        """Record successful model call."""
        self.breakers[model_id].record_success()
        print(f"✓ {model_id} success - circuit healthy")
    
    def record_failure(self, model_id: str) -> bool:
        """
        Record failed model call.
        
        Returns:
            True if circuit is now open
        """
        is_open = self.breakers[model_id].record_failure()
        return is_open
    
    def get_available_models(self, category: str) -> List[str]:
        """
        Get available models for a category (excluding open circuits).
        
        Returns:
            List of model IDs with closed circuits, in preference order
        """
        ranked_models = self.model_rankings.get(category, [])
        available = []
        
        for model_id in ranked_models:
            if not self.breakers[model_id].is_open():
                available.append(model_id)
        
        return available
    
    def get_failover_model(self, category: str, primary_model: str) -> Optional[str]:
        """
        Get the next best model if primary fails.
        
        Args:
            category: Task category
            primary_model: The model that just failed
        
        Returns:
            Next best available model, or None if all circuits open
        """
        ranked = self.model_rankings.get(category, [])
        
        # Find primary model's index
        try:
            primary_idx = ranked.index(primary_model)
        except ValueError:
            return None
        
        # Try next models in ranking
        for i in range(primary_idx + 1, len(ranked)):
            candidate = ranked[i]
            if not self.breakers[candidate].is_open():
                print(f"📌 Failover: {primary_model} → {candidate}")
                return candidate
        
        return None
    
    def get_status_report(self) -> Dict:
        """Get status report for all models."""
        return {
            model_id: breaker.get_status()
            for model_id, breaker in self.breakers.items()
        }


# Global instance
_circuit_breaker = None

def get_circuit_breaker() -> ModelCircuitBreaker:
    """Get or initialize the global circuit breaker."""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = ModelCircuitBreaker()
    return _circuit_breaker
