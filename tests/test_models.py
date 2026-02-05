"""Tests for data models."""

import pytest
from datetime import datetime, timezone

from agent_rate_limiter.models import (
    Priority,
    RotationStrategy,
    RateLimitInfo,
    Capacity,
    RequestResult,
    RateLimitError,
    QueueFullError,
    QueueTimeoutError,
)


class TestPriority:
    """Tests for Priority enum."""
    
    def test_priority_ordering(self):
        """Test that priorities have correct ordering."""
        assert Priority.CRITICAL.value < Priority.HIGH.value
        assert Priority.HIGH.value < Priority.NORMAL.value
        assert Priority.NORMAL.value < Priority.LOW.value
        assert Priority.LOW.value < Priority.BULK.value
    
    def test_all_priorities_exist(self):
        """Test all expected priorities exist."""
        priorities = [p.name for p in Priority]
        assert "CRITICAL" in priorities
        assert "HIGH" in priorities
        assert "NORMAL" in priorities
        assert "LOW" in priorities
        assert "BULK" in priorities


class TestRotationStrategy:
    """Tests for RotationStrategy enum."""
    
    def test_all_strategies_exist(self):
        """Test all expected strategies exist."""
        strategies = [s.name for s in RotationStrategy]
        assert "ROUND_ROBIN" in strategies
        assert "LEAST_USED" in strategies
        assert "RANDOM" in strategies
        assert "FAILOVER" in strategies


class TestRateLimitInfo:
    """Tests for RateLimitInfo dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        info = RateLimitInfo()
        assert info.requests_remaining is None
        assert info.requests_limit is None
        assert info.tokens_remaining is None
        assert info.tokens_limit is None
        assert info.reset_time is None
        assert info.retry_after is None
    
    def test_is_exhausted_requests(self):
        """Test exhaustion check for requests."""
        info = RateLimitInfo(requests_remaining=0, requests_limit=100)
        assert info.is_exhausted is True
        
        info = RateLimitInfo(requests_remaining=50, requests_limit=100)
        assert info.is_exhausted is False
    
    def test_is_exhausted_tokens(self):
        """Test exhaustion check for tokens."""
        info = RateLimitInfo(tokens_remaining=0, tokens_limit=10000)
        assert info.is_exhausted is True
        
        info = RateLimitInfo(tokens_remaining=5000, tokens_limit=10000)
        assert info.is_exhausted is False
    
    def test_is_exhausted_not_exhausted(self):
        """Test not exhausted when limits not set."""
        info = RateLimitInfo()
        assert info.is_exhausted is False
    
    def test_usage_ratio(self):
        """Test usage ratio calculation."""
        info = RateLimitInfo(requests_remaining=25, requests_limit=100)
        assert info.usage_ratio == 0.75
        
        info = RateLimitInfo(requests_remaining=100, requests_limit=100)
        assert info.usage_ratio == 0.0
        
        info = RateLimitInfo(requests_remaining=0, requests_limit=100)
        assert info.usage_ratio == 1.0
    
    def test_usage_ratio_none_when_not_set(self):
        """Test usage ratio is None when limits not set."""
        info = RateLimitInfo()
        assert info.usage_ratio is None
        
        info = RateLimitInfo(requests_remaining=50)
        assert info.usage_ratio is None


class TestCapacity:
    """Tests for Capacity dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        capacity = Capacity()
        assert capacity.requests_remaining is None
        assert capacity.tokens_remaining is None
        assert capacity.reset_time is None
        assert capacity.keys_available == 0
        assert capacity.keys_exhausted == 0
    
    def test_total_keys(self):
        """Test total keys calculation."""
        capacity = Capacity(keys_available=3, keys_exhausted=2)
        assert capacity.total_keys == 5


class TestRequestResult:
    """Tests for RequestResult dataclass."""
    
    def test_successful_result(self):
        """Test successful result."""
        result = RequestResult(
            success=True,
            status_code=200,
            data={"message": "ok"},
        )
        assert result.success is True
        assert result.status_code == 200
        assert result.data == {"message": "ok"}
        assert result.error is None
    
    def test_failed_result(self):
        """Test failed result."""
        result = RequestResult(
            success=False,
            error="Connection refused",
        )
        assert result.success is False
        assert result.error == "Connection refused"
    
    def test_default_values(self):
        """Test default values."""
        result = RequestResult(success=True)
        assert result.headers == {}
        assert result.retries == 0
        assert result.total_wait_time == 0.0


class TestRateLimitError:
    """Tests for RateLimitError exception."""
    
    def test_basic_error(self):
        """Test basic error."""
        error = RateLimitError("Rate limit exceeded")
        assert str(error) == "Rate limit exceeded"
        assert error.rate_limit_info is None
        assert error.retries_attempted == 0
        assert error.keys_tried == 0
    
    def test_error_with_info(self):
        """Test error with rate limit info."""
        info = RateLimitInfo(requests_remaining=0, retry_after=60.0)
        error = RateLimitError(
            "Rate limit exceeded",
            rate_limit_info=info,
            retries_attempted=3,
            keys_tried=2,
        )
        assert error.rate_limit_info == info
        assert error.retries_attempted == 3
        assert error.keys_tried == 2


class TestQueueErrors:
    """Tests for queue-related errors."""
    
    def test_queue_full_error(self):
        """Test QueueFullError."""
        error = QueueFullError("Queue is full")
        assert str(error) == "Queue is full"
    
    def test_queue_timeout_error(self):
        """Test QueueTimeoutError."""
        error = QueueTimeoutError("Request timed out")
        assert str(error) == "Request timed out"
