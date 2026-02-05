"""Basic smoke tests without long sleeps"""

import pytest
from agent_rate_limiter.core.limiter import TokenBucket
from agent_rate_limiter.core.providers import Provider, ModelConfig
from agent_rate_limiter.core.cost_tracker import CostTracker


def test_token_bucket_creation():
    """Test creating a token bucket"""
    bucket = TokenBucket(capacity=100, refill_rate=10.0)
    assert bucket.capacity == 100
    assert bucket.refill_rate == 10.0
    assert bucket.tokens == 100.0


def test_provider_presets():
    """Test provider presets exist"""
    openai = Provider.openai()
    assert openai.name == "openai"
    assert "gpt-4" in openai.models
    
    anthropic = Provider.anthropic()
    assert anthropic.name == "anthropic"
    assert "claude-opus-4" in anthropic.models
    
    google = Provider.google()
    assert google.name == "google"
    assert "gemini-2.0-pro" in google.models


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
    
    assert cost == pytest.approx(0.06)
    assert tracker.get_total_cost() == pytest.approx(0.06)


def test_model_config():
    """Test creating model config"""
    config = ModelConfig(
        rpm=100,
        tpm=10000,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03
    )
    
    assert config.rpm == 100
    assert config.tpm == 10000
    assert config.cost_per_1k_input == 0.01
    assert config.cost_per_1k_output == 0.03
