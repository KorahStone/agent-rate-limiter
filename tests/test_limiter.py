"""Tests for RateLimiter"""

import pytest
import time
from agent_rate_limiter.core.limiter import RateLimiter, TokenBucket
from agent_rate_limiter.core.providers import ModelConfig


def test_token_bucket_basic():
    """Test basic token bucket functionality"""
    bucket = TokenBucket(capacity=10, refill_rate=1.0)
    
    # Should be able to consume tokens
    assert bucket.consume(5) == True
    assert bucket.consume(5) == True
    assert bucket.consume(1) == False  # Depleted
    
    # Wait for refill
    time.sleep(1.1)
    assert bucket.consume(1) == True


def test_token_bucket_wait_time():
    """Test wait time calculation"""
    bucket = TokenBucket(capacity=10, refill_rate=10.0)  # 10 tokens/sec
    
    bucket.consume(10)  # Deplete
    wait = bucket.wait_time(5)
    
    assert wait > 0
    assert wait <= 0.5  # Should be ~0.5 seconds


def test_rate_limiter_basic():
    """Test basic rate limiter"""
    config = ModelConfig(
        rpm=60,  # 1 request per second
        tpm=600,  # 10 tokens per second
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03
    )
    
    limiter = RateLimiter(
        provider="test",
        model="test-model",
        model_config=config
    )
    
    @limiter.limit(estimated_tokens=10)
    def dummy_call():
        return "success"
    
    # Should work
    result = dummy_call()
    assert result == "success"
    
    # Check metrics
    metrics = limiter.get_metrics()
    assert metrics["total_requests"] == 1
    assert metrics["total_tokens"] == 10


def test_rate_limiter_enforces_limits():
    """Test that rate limiter enforces limits"""
    config = ModelConfig(
        rpm=2,  # Very low limit for testing
        tpm=100,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03
    )
    
    limiter = RateLimiter(
        provider="test",
        model="test-model",
        model_config=config
    )
    
    call_times = []
    
    @limiter.limit(estimated_tokens=10)
    def dummy_call():
        call_times.append(time.time())
        return "success"
    
    # Make 3 calls - should be rate limited
    for _ in range(3):
        dummy_call()
    
    # Check that there was delay between calls
    assert len(call_times) == 3
    # With 2 RPM, calls should be ~30 seconds apart
    assert call_times[1] - call_times[0] >= 29  # Allow some slack
    assert call_times[2] - call_times[1] >= 29


def test_rate_limiter_metrics():
    """Test metrics tracking"""
    config = ModelConfig(
        rpm=1000,
        tpm=10000,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03
    )
    
    limiter = RateLimiter(
        provider="openai",
        model="gpt-4",
        model_config=config
    )
    
    @limiter.limit(estimated_tokens=100)
    def successful_call():
        return "ok"
    
    @limiter.limit(estimated_tokens=100)
    def failing_call():
        raise ValueError("Test error")
    
    # Successful calls
    successful_call()
    successful_call()
    
    # Failed call
    with pytest.raises(ValueError):
        failing_call()
    
    metrics = limiter.get_metrics()
    assert metrics["total_requests"] == 2  # Only successful
    assert metrics["failed_requests"] == 1
    assert metrics["total_tokens"] == 200  # 2 * 100


def test_rate_limiter_callback():
    """Test on_limit_hit callback"""
    hit_count = {"count": 0}
    
    def on_hit(provider, model):
        hit_count["count"] += 1
    
    config = ModelConfig(
        rpm=2,
        tpm=100,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03
    )
    
    limiter = RateLimiter(
        provider="test",
        model="test-model",
        model_config=config,
        on_limit_hit=on_hit
    )
    
    @limiter.limit(estimated_tokens=10)
    def dummy_call():
        return "ok"
    
    # First call - no limit
    dummy_call()
    assert hit_count["count"] == 0
    
    # Second call - should hit limit
    dummy_call()
    assert hit_count["count"] > 0
