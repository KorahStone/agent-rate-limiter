"""Multi-provider rate limiter with failover"""

from typing import List, Optional, Callable, Any
from functools import wraps

from .providers import ProviderConfig
from .limiter import RateLimiter
from .cost_tracker import CostTracker, BudgetExceededError


class MultiProviderLimiter:
    """Manage rate limiting across multiple providers with failover"""
    
    def __init__(
        self,
        providers: List[ProviderConfig],
        daily_budget: Optional[float] = None,
        weekly_budget: Optional[float] = None,
        monthly_budget: Optional[float] = None,
        alert_threshold: float = 0.8,
        on_limit_hit: Optional[Callable[[str, str], None]] = None,
        on_budget_alert: Optional[Callable[[str, float, float], None]] = None
    ):
        self.providers = {p.name: p for p in providers}
        self.limiters: dict[str, dict[str, RateLimiter]] = {}
        self.cost_tracker = CostTracker(
            daily_budget=daily_budget,
            weekly_budget=weekly_budget,
            monthly_budget=monthly_budget,
            alert_threshold=alert_threshold,
            on_alert=on_budget_alert
        )
        
        # Initialize limiters for each provider/model
        for provider in providers:
            self.limiters[provider.name] = {}
            for model_name, model_config in provider.models.items():
                self.limiters[provider.name][model_name] = RateLimiter(
                    provider=provider.name,
                    model=model_name,
                    model_config=model_config,
                    on_limit_hit=on_limit_hit
                )
    
    def get_limiter(self, provider: str, model: str) -> RateLimiter:
        """Get limiter for a specific provider/model"""
        if provider not in self.limiters:
            raise ValueError(f"Unknown provider: {provider}")
        if model not in self.limiters[provider]:
            raise ValueError(f"Unknown model: {model} for provider {provider}")
        return self.limiters[provider][model]
    
    def limit(
        self,
        provider: str,
        model: str,
        estimated_tokens: int = 100,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None
    ):
        """Decorator for rate-limited and cost-tracked functions"""
        def decorator(func: Callable) -> Callable:
            limiter = self.get_limiter(provider, model)
            provider_config = self.providers[provider]
            model_config = provider_config.models[model]
            
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Apply rate limiting
                limited_func = limiter.limit(estimated_tokens=estimated_tokens)(func)
                result = limited_func(*args, **kwargs)
                
                # Track costs if token counts provided
                if input_tokens is not None and output_tokens is not None:
                    try:
                        self.cost_tracker.record(
                            provider=provider,
                            model=model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cost_per_1k_input=model_config.cost_per_1k_input,
                            cost_per_1k_output=model_config.cost_per_1k_output
                        )
                    except BudgetExceededError as e:
                        raise e
                
                return result
            
            return wrapper
        return decorator
    
    def get_metrics(self) -> dict:
        """Get metrics for all providers/models"""
        metrics = {
            "limiters": {},
            "costs": {
                "total": self.cost_tracker.get_total_cost(),
                "by_model": self.cost_tracker.get_costs(),
                "daily": self.cost_tracker.get_total_cost(
                    since=time.time() - 86400
                ),
                "weekly": self.cost_tracker.get_total_cost(
                    since=time.time() - 604800
                ),
                "monthly": self.cost_tracker.get_total_cost(
                    since=time.time() - 2592000
                ),
            }
        }
        
        for provider_name, models in self.limiters.items():
            metrics["limiters"][provider_name] = {}
            for model_name, limiter in models.items():
                metrics["limiters"][provider_name][model_name] = limiter.get_metrics()
        
        return metrics


import time
