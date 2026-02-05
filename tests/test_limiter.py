"""Tests for the main RateLimiter class."""

import pytest
import asyncio
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from agent_rate_limiter.limiter import RateLimiter
from agent_rate_limiter.providers import OpenAIProvider, GenericProvider
from agent_rate_limiter.models import (
    Priority,
    RotationStrategy,
    RateLimitError,
    RateLimitInfo,
    Capacity,
)


class TestRateLimiterInit:
    """Tests for RateLimiter initialization."""
    
    def test_basic_init(self):
        """Test basic initialization."""
        limiter = RateLimiter(api_keys=["key1", "key2"])
        assert limiter._max_retries == 5
        assert limiter._base_delay == 1.0
    
    def test_custom_provider(self):
        """Test initialization with custom provider."""
        provider = OpenAIProvider()
        limiter = RateLimiter(api_keys=["key1"], provider=provider)
        assert limiter._provider == provider
    
    def test_custom_retry_settings(self):
        """Test custom retry settings."""
        limiter = RateLimiter(
            api_keys=["key1"],
            max_retries=10,
            base_delay=2.0,
            max_delay=120.0,
            jitter=False,
        )
        assert limiter._max_retries == 10
        assert limiter._base_delay == 2.0
        assert limiter._max_delay == 120.0
        assert limiter._jitter is False
    
    def test_rotation_strategy(self):
        """Test rotation strategy configuration."""
        limiter = RateLimiter(
            api_keys=["key1", "key2"],
            rotation_strategy=RotationStrategy.LEAST_USED,
        )
        assert limiter._key_manager._strategy == RotationStrategy.LEAST_USED


class TestRateLimiterContext:
    """Tests for async context manager."""
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        limiter = RateLimiter(api_keys=["key1"])
        
        async with limiter:
            assert limiter._client is not None
        
        # Client should be closed after context
        assert limiter._client is None
    
    @pytest.mark.asyncio
    async def test_close(self):
        """Test explicit close."""
        limiter = RateLimiter(api_keys=["key1"])
        await limiter._ensure_client()
        assert limiter._client is not None
        
        await limiter.close()
        assert limiter._client is None


class TestRateLimiterRequest:
    """Tests for request method."""
    
    @pytest.mark.asyncio
    async def test_successful_request(self):
        """Test successful request."""
        limiter = RateLimiter(api_keys=["sk-test123456789"])
        
        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {
            "x-ratelimit-remaining": "99",
            "x-ratelimit-limit": "100",
        }
        mock_response.json.return_value = {"data": "test"}
        
        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            async with limiter:
                result = await limiter.request("GET", "https://api.example.com/test")
        
        assert result.success is True
        assert result.status_code == 200
        assert result.data == {"data": "test"}
    
    @pytest.mark.asyncio
    async def test_rate_limit_retry(self):
        """Test retry on rate limit."""
        limiter = RateLimiter(
            api_keys=["sk-test123456789"],
            max_retries=2,
            base_delay=0.01,  # Fast for testing
            key_cooldown=0.001,  # Very short cooldown so key becomes available again
        )
        
        # First response is rate limited, second is success
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"retry-after": "0.01"}
        
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.headers = {}
        success_response.json.return_value = {"status": "ok"}
        
        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [rate_limit_response, success_response]
            
            async with limiter:
                result = await limiter.request("GET", "https://api.example.com/test")
        
        assert result.success is True
        assert result.retries == 1
    
    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Test RateLimitError when max retries exceeded or keys exhausted."""
        limiter = RateLimiter(
            api_keys=["sk-test123456789"],
            max_retries=2,
            base_delay=0.01,
            key_cooldown=60.0,  # Long cooldown so key stays exhausted
        )
        
        # Always return rate limit
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"retry-after": "0.01"}
        
        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = rate_limit_response
            
            async with limiter:
                with pytest.raises(RateLimitError) as exc_info:
                    await limiter.request("GET", "https://api.example.com/test")
        
        # Could be either message depending on timing
        error_msg = str(exc_info.value)
        assert "Max retries" in error_msg or "All API keys are rate limited" in error_msg
    
    @pytest.mark.asyncio
    async def test_key_rotation_on_rate_limit(self):
        """Test key rotation when one key hits rate limit."""
        limiter = RateLimiter(
            api_keys=["key1-123456789", "key2-123456789"],
            max_retries=3,
            base_delay=0.01,
            rotation_strategy=RotationStrategy.ROUND_ROBIN,
        )
        
        call_count = 0
        
        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            # First call (key1) rate limited
            if call_count == 1:
                response = MagicMock()
                response.status_code = 429
                response.headers = {"retry-after": "0.01"}
                return response
            
            # Second call (key2) succeeds
            response = MagicMock()
            response.status_code = 200
            response.headers = {}
            response.json.return_value = {"status": "ok"}
            return response
        
        with patch.object(httpx.AsyncClient, "request", side_effect=mock_request):
            async with limiter:
                result = await limiter.request("GET", "https://api.example.com/test")
        
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_all_keys_exhausted(self):
        """Test error when all keys are exhausted."""
        limiter = RateLimiter(
            api_keys=["key1-123456789", "key2-123456789"],
            max_retries=5,
            base_delay=0.01,
            max_delay=0.02,  # Cap delay for fast test
            key_cooldown=0.5,  # Short cooldown for test
        )
        
        # Always return rate limit with short retry
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"retry-after": "0.01"}
        
        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = rate_limit_response
            
            async with limiter:
                with pytest.raises(RateLimitError) as exc_info:
                    await limiter.request("GET", "https://api.example.com/test")
        
        assert "All API keys are rate limited" in str(exc_info.value) or "Max retries" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_adds_authorization_header(self):
        """Test that authorization header is added."""
        limiter = RateLimiter(api_keys=["sk-test123456789"])
        
        captured_headers = {}
        
        async def capture_request(*args, **kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            response = MagicMock()
            response.status_code = 200
            response.headers = {}
            response.json.return_value = {}
            return response
        
        with patch.object(httpx.AsyncClient, "request", side_effect=capture_request):
            async with limiter:
                await limiter.request("GET", "https://api.example.com/test")
        
        assert "Authorization" in captured_headers
        assert captured_headers["Authorization"] == "Bearer sk-test123456789"
    
    @pytest.mark.asyncio
    async def test_respects_existing_auth_header(self):
        """Test that existing auth header is not overwritten."""
        limiter = RateLimiter(api_keys=["sk-test123456789"])
        
        captured_headers = {}
        
        async def capture_request(*args, **kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            response = MagicMock()
            response.status_code = 200
            response.headers = {}
            response.json.return_value = {}
            return response
        
        with patch.object(httpx.AsyncClient, "request", side_effect=capture_request):
            async with limiter:
                await limiter.request(
                    "GET",
                    "https://api.example.com/test",
                    headers={"Authorization": "Bearer custom-key"}
                )
        
        assert captured_headers["Authorization"] == "Bearer custom-key"


class TestRateLimiterCallbacks:
    """Tests for callback functionality."""
    
    @pytest.mark.asyncio
    async def test_on_rate_limit_callback(self):
        """Test on_rate_limit callback is called."""
        callback_called = False
        callback_info = None
        
        def on_rate_limit(key, info):
            nonlocal callback_called, callback_info
            callback_called = True
            callback_info = info
        
        limiter = RateLimiter(
            api_keys=["sk-test123456789"],
            max_retries=1,
            base_delay=0.01,
            on_rate_limit=on_rate_limit,
        )
        
        # Rate limit then success
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"retry-after": "0.01"}
        
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.headers = {}
        success_response.json.return_value = {}
        
        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [rate_limit_response, success_response]
            
            async with limiter:
                await limiter.request("GET", "https://api.example.com/test")
        
        assert callback_called is True
    
    @pytest.mark.asyncio
    async def test_on_retry_callback(self):
        """Test on_retry callback is called."""
        retry_count = 0
        
        def on_retry(attempt, delay):
            nonlocal retry_count
            retry_count = attempt
        
        limiter = RateLimiter(
            api_keys=["sk-test123456789"],
            max_retries=2,
            base_delay=0.01,
            key_cooldown=0.001,  # Very short cooldown so key becomes available again
            on_retry=on_retry,
        )
        
        # Rate limit then success
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"retry-after": "0.01"}
        
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.headers = {}
        success_response.json.return_value = {}
        
        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [rate_limit_response, success_response]
            
            async with limiter:
                await limiter.request("GET", "https://api.example.com/test")
        
        assert retry_count == 1


class TestRateLimiterCapacity:
    """Tests for capacity tracking."""
    
    @pytest.mark.asyncio
    async def test_get_remaining_capacity(self):
        """Test getting remaining capacity."""
        limiter = RateLimiter(api_keys=["key1", "key2"])
        
        # Report some usage
        limiter._key_manager.report_success(
            "key1",
            RateLimitInfo(requests_remaining=50, requests_limit=100)
        )
        limiter._key_manager.report_success(
            "key2",
            RateLimitInfo(requests_remaining=75, requests_limit=100)
        )
        
        capacity = await limiter.get_remaining_capacity()
        
        assert capacity.requests_remaining == 125  # 50 + 75
        assert capacity.keys_available == 2
        assert capacity.keys_exhausted == 0
    
    @pytest.mark.asyncio
    async def test_capacity_with_exhausted_keys(self):
        """Test capacity when some keys are exhausted."""
        limiter = RateLimiter(api_keys=["key1", "key2", "key3"])
        
        # Exhaust key1
        limiter._key_manager.report_rate_limit("key1")
        
        capacity = await limiter.get_remaining_capacity()
        
        assert capacity.keys_available == 2
        assert capacity.keys_exhausted == 1


class TestRateLimiterStats:
    """Tests for statistics."""
    
    def test_get_stats(self):
        """Test getting statistics."""
        limiter = RateLimiter(api_keys=["key1", "key2"])
        
        stats = limiter.get_stats()
        
        assert "total_requests" in stats
        assert "total_retries" in stats
        assert "total_rate_limits" in stats
        assert "keys" in stats
        assert stats["keys"]["total"] == 2
    
    @pytest.mark.asyncio
    async def test_stats_update_after_requests(self):
        """Test stats update after making requests."""
        limiter = RateLimiter(api_keys=["sk-test123456789"], base_delay=0.01)
        
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.headers = {}
        success_response.json.return_value = {}
        
        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = success_response
            
            async with limiter:
                await limiter.request("GET", "https://api.example.com/test")
                await limiter.request("GET", "https://api.example.com/test")
        
        stats = limiter.get_stats()
        assert stats["total_requests"] == 2


class TestDelayCalculation:
    """Tests for delay calculation."""
    
    def test_exponential_backoff(self):
        """Test exponential backoff calculation."""
        limiter = RateLimiter(
            api_keys=["key1"],
            base_delay=1.0,
            max_delay=60.0,
            jitter=False,
        )
        
        # Retry 0: 1 * 2^0 = 1
        delay = limiter._calculate_delay(0, None)
        assert delay == 1.0
        
        # Retry 1: 1 * 2^1 = 2
        delay = limiter._calculate_delay(1, None)
        assert delay == 2.0
        
        # Retry 2: 1 * 2^2 = 4
        delay = limiter._calculate_delay(2, None)
        assert delay == 4.0
    
    def test_max_delay_cap(self):
        """Test delay is capped at max_delay."""
        limiter = RateLimiter(
            api_keys=["key1"],
            base_delay=1.0,
            max_delay=10.0,
            jitter=False,
        )
        
        # Retry 10: 1 * 2^10 = 1024, but should be capped at 10
        delay = limiter._calculate_delay(10, None)
        assert delay == 10.0
    
    def test_retry_after_respected(self):
        """Test retry-after header is respected."""
        limiter = RateLimiter(
            api_keys=["key1"],
            base_delay=1.0,
            jitter=False,
        )
        
        info = RateLimitInfo(retry_after=30.0)
        delay = limiter._calculate_delay(0, info)
        assert delay == 30.0
    
    def test_jitter_adds_randomness(self):
        """Test jitter adds randomness to delay."""
        limiter = RateLimiter(
            api_keys=["key1"],
            base_delay=10.0,
            jitter=True,
        )
        
        # With jitter, delay should be between 5 and 15 (10 * 0.5 to 10 * 1.5)
        delays = [limiter._calculate_delay(0, None) for _ in range(10)]
        
        # All delays should be different (very unlikely to be same with randomness)
        assert len(set(delays)) > 1
        
        # All should be in range
        for d in delays:
            assert 5.0 <= d <= 15.0
