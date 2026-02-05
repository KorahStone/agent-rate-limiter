"""Cost tracking and budget management"""

from typing import Dict, Optional, Callable
from dataclasses import dataclass, field
from threading import Lock
import time


@dataclass
class CostEntry:
    """Single cost entry"""
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    timestamp: float = field(default_factory=time.time)


class BudgetExceededError(Exception):
    """Raised when budget limit is exceeded"""
    pass


class CostTracker:
    """Track costs and enforce budgets"""
    
    def __init__(
        self,
        daily_budget: Optional[float] = None,
        weekly_budget: Optional[float] = None,
        monthly_budget: Optional[float] = None,
        alert_threshold: float = 0.8,
        on_alert: Optional[Callable[[str, float, float], None]] = None
    ):
        self.daily_budget = daily_budget
        self.weekly_budget = weekly_budget
        self.monthly_budget = monthly_budget
        self.alert_threshold = alert_threshold
        self.on_alert = on_alert
        
        self.entries: list[CostEntry] = []
        self.lock = Lock()
        self._alerted = {"daily": False, "weekly": False, "monthly": False}
    
    def record(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_per_1k_input: float,
        cost_per_1k_output: float
    ) -> float:
        """Record a cost entry and return the cost"""
        cost = (
            (input_tokens / 1000.0) * cost_per_1k_input +
            (output_tokens / 1000.0) * cost_per_1k_output
        )
        
        with self.lock:
            entry = CostEntry(
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost
            )
            self.entries.append(entry)
            
            # Check budgets
            self._check_budgets()
        
        return cost
    
    def _check_budgets(self):
        """Check if budgets are exceeded or approaching limits"""
        now = time.time()
        
        # Calculate costs for different periods
        daily_cost = self._get_cost_since(now - 86400)  # 24 hours
        weekly_cost = self._get_cost_since(now - 604800)  # 7 days
        monthly_cost = self._get_cost_since(now - 2592000)  # 30 days
        
        # Check daily budget
        if self.daily_budget:
            if daily_cost >= self.daily_budget:
                raise BudgetExceededError(f"Daily budget of ${self.daily_budget} exceeded (${daily_cost:.2f})")
            elif daily_cost >= self.daily_budget * self.alert_threshold and not self._alerted["daily"]:
                if self.on_alert:
                    self.on_alert("daily", daily_cost, self.daily_budget)
                self._alerted["daily"] = True
        
        # Check weekly budget
        if self.weekly_budget:
            if weekly_cost >= self.weekly_budget:
                raise BudgetExceededError(f"Weekly budget of ${self.weekly_budget} exceeded (${weekly_cost:.2f})")
            elif weekly_cost >= self.weekly_budget * self.alert_threshold and not self._alerted["weekly"]:
                if self.on_alert:
                    self.on_alert("weekly", weekly_cost, self.weekly_budget)
                self._alerted["weekly"] = True
        
        # Check monthly budget
        if self.monthly_budget:
            if monthly_cost >= self.monthly_budget:
                raise BudgetExceededError(f"Monthly budget of ${self.monthly_budget} exceeded (${monthly_cost:.2f})")
            elif monthly_cost >= self.monthly_budget * self.alert_threshold and not self._alerted["monthly"]:
                if self.on_alert:
                    self.on_alert("monthly", monthly_cost, self.monthly_budget)
                self._alerted["monthly"] = True
    
    def _get_cost_since(self, since: float) -> float:
        """Get total cost since a timestamp"""
        return sum(
            entry.cost
            for entry in self.entries
            if entry.timestamp >= since
        )
    
    def get_costs(self, since: Optional[float] = None) -> Dict[str, float]:
        """Get cost breakdown by provider/model"""
        filtered = self.entries if since is None else [
            e for e in self.entries if e.timestamp >= since
        ]
        
        costs = {}
        for entry in filtered:
            key = f"{entry.provider}/{entry.model}"
            costs[key] = costs.get(key, 0.0) + entry.cost
        
        return costs
    
    def get_total_cost(self, since: Optional[float] = None) -> float:
        """Get total cost"""
        if since is None:
            return sum(entry.cost for entry in self.entries)
        return self._get_cost_since(since)
    
    def reset_alerts(self):
        """Reset alert flags (called when new period starts)"""
        with self.lock:
            self._alerted = {"daily": False, "weekly": False, "monthly": False}
