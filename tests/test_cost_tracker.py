"""Tests for CostTracker"""

import pytest
import time
from agent_rate_limiter.core.cost_tracker import CostTracker, BudgetExceededError


def test_cost_tracker_basic():
    """Test basic cost tracking"""
    tracker = CostTracker()
    
    cost = tracker.record(
        provider="openai",
        model="gpt-4",
        input_tokens=1000,
        output_tokens=500,
        cost_per_1k_input=0.03,
        cost_per_1k_output=0.06
    )
    
    # 1000 * 0.03/1000 + 500 * 0.06/1000 = 0.03 + 0.03 = 0.06
    assert cost == pytest.approx(0.06)
    assert tracker.get_total_cost() == pytest.approx(0.06)


def test_cost_tracker_multiple_entries():
    """Test tracking multiple entries"""
    tracker = CostTracker()
    
    tracker.record("openai", "gpt-4", 1000, 1000, 0.03, 0.06)
    tracker.record("anthropic", "claude-opus-4", 2000, 1000, 0.015, 0.075)
    
    total = tracker.get_total_cost()
    assert total > 0
    
    costs = tracker.get_costs()
    assert "openai/gpt-4" in costs
    assert "anthropic/claude-opus-4" in costs


def test_daily_budget_exceeded():
    """Test that daily budget is enforced"""
    tracker = CostTracker(daily_budget=0.10)
    
    # Record cost that exceeds budget
    with pytest.raises(BudgetExceededError) as exc:
        tracker.record("openai", "gpt-4", 5000, 5000, 0.03, 0.06)
    
    assert "Daily budget" in str(exc.value)


def test_budget_alert():
    """Test budget alert threshold"""
    alert_calls = []
    
    def on_alert(period, current, limit):
        alert_calls.append((period, current, limit))
    
    tracker = CostTracker(
        daily_budget=1.00,
        alert_threshold=0.8,
        on_alert=on_alert
    )
    
    # Record cost that hits 80% threshold
    tracker.record("openai", "gpt-4", 27000, 13000, 0.03, 0.06)
    
    # Should have triggered alert
    assert len(alert_calls) == 1
    assert alert_calls[0][0] == "daily"
    assert alert_calls[0][1] >= 0.8
    assert alert_calls[0][2] == 1.00


def test_cost_breakdown():
    """Test cost breakdown by provider/model"""
    tracker = CostTracker()
    
    tracker.record("openai", "gpt-4", 1000, 1000, 0.03, 0.06)
    tracker.record("openai", "gpt-4", 1000, 1000, 0.03, 0.06)
    tracker.record("anthropic", "claude-opus-4", 1000, 1000, 0.015, 0.075)
    
    costs = tracker.get_costs()
    
    # Should have combined costs for same model
    assert costs["openai/gpt-4"] == pytest.approx(0.18)  # 0.09 * 2
    assert costs["anthropic/claude-opus-4"] == pytest.approx(0.09)


def test_cost_since_timestamp():
    """Test filtering costs by timestamp"""
    tracker = CostTracker()
    
    # Record old cost
    tracker.record("openai", "gpt-4", 1000, 1000, 0.03, 0.06)
    
    # Wait a bit
    time.sleep(0.1)
    now = time.time()
    
    # Record new cost
    tracker.record("anthropic", "claude-opus-4", 1000, 1000, 0.015, 0.075)
    
    # Total cost should include both
    total = tracker.get_total_cost()
    assert total == pytest.approx(0.18)
    
    # Cost since 'now' should only include second entry
    recent = tracker.get_total_cost(since=now)
    assert recent == pytest.approx(0.09)
