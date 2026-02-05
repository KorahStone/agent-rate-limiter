"""Tests for rate limit providers."""

import pytest
from datetime import datetime, timezone

from agent_rate_limiter.providers import (
    BaseProvider,
    OpenAIProvider,
    AnthropicProvider,
    GenericProvider,
)


class TestOpenAIProvider:
    """Tests for OpenAI provider."""
    
    def test_parse_rate_limit_headers(self):
        """Test parsing OpenAI rate limit headers."""
        provider = OpenAIProvider()
        
        headers = {
            "x-ratelimit-limit-requests": "10000",
            "x-ratelimit-limit-tokens": "200000",
            "x-ratelimit-remaining-requests": "9999",
            "x-ratelimit-remaining-tokens": "199500",
            "x-ratelimit-reset-requests": "1s",
            "x-ratelimit-reset-tokens": "6ms",
        }
        
        info = provider.parse_rate_limit_headers(headers)
        
        assert info.requests_limit == 10000
        assert info.requests_remaining == 9999
        assert info.tokens_limit == 200000
        assert info.tokens_remaining == 199500
    
    def test_parse_empty_headers(self):
        """Test parsing empty headers."""
        provider = OpenAIProvider()
        info = provider.parse_rate_limit_headers({})
        
        assert info.requests_remaining is None
        assert info.requests_limit is None
        assert info.tokens_remaining is None
        assert info.tokens_limit is None
    
    def test_is_rate_limit_error_429(self):
        """Test 429 is rate limit error."""
        provider = OpenAIProvider()
        assert provider.is_rate_limit_error(429, None) is True
    
    def test_is_rate_limit_error_200(self):
        """Test 200 is not rate limit error."""
        provider = OpenAIProvider()
        assert provider.is_rate_limit_error(200, None) is False
    
    def test_is_rate_limit_error_503_with_rate(self):
        """Test 503 with rate in body is rate limit error."""
        provider = OpenAIProvider()
        body = {"error": {"message": "Rate limit exceeded"}}
        assert provider.is_rate_limit_error(503, body) is True
    
    def test_is_rate_limit_error_503_without_rate(self):
        """Test 503 without rate in body is not rate limit error."""
        provider = OpenAIProvider()
        body = {"error": {"message": "Server error"}}
        assert provider.is_rate_limit_error(503, body) is False
    
    def test_parse_reset_time_seconds(self):
        """Test parsing reset time in seconds."""
        provider = OpenAIProvider()
        headers = {"x-ratelimit-reset-requests": "30s"}
        info = provider.parse_rate_limit_headers(headers)
        
        assert info.reset_time is not None
    
    def test_parse_reset_time_minutes(self):
        """Test parsing reset time in minutes."""
        provider = OpenAIProvider()
        headers = {"x-ratelimit-reset-requests": "2m30s"}
        info = provider.parse_rate_limit_headers(headers)
        
        assert info.reset_time is not None
    
    def test_mask_key(self):
        """Test key masking."""
        provider = OpenAIProvider()
        
        assert provider.mask_key("sk-1234567890abcdef") == "sk-1...cdef"
        assert provider.mask_key("short") == "***"


class TestAnthropicProvider:
    """Tests for Anthropic provider."""
    
    def test_parse_rate_limit_headers(self):
        """Test parsing Anthropic rate limit headers."""
        provider = AnthropicProvider()
        
        headers = {
            "anthropic-ratelimit-requests-limit": "1000",
            "anthropic-ratelimit-requests-remaining": "999",
            "anthropic-ratelimit-tokens-limit": "100000",
            "anthropic-ratelimit-tokens-remaining": "99000",
            "anthropic-ratelimit-requests-reset": "2024-01-15T12:00:00Z",
        }
        
        info = provider.parse_rate_limit_headers(headers)
        
        assert info.requests_limit == 1000
        assert info.requests_remaining == 999
        assert info.tokens_limit == 100000
        assert info.tokens_remaining == 99000
        assert info.reset_time is not None
    
    def test_parse_empty_headers(self):
        """Test parsing empty headers."""
        provider = AnthropicProvider()
        info = provider.parse_rate_limit_headers({})
        
        assert info.requests_remaining is None
        assert info.tokens_remaining is None
    
    def test_is_rate_limit_error_429(self):
        """Test 429 is rate limit error."""
        provider = AnthropicProvider()
        assert provider.is_rate_limit_error(429, None) is True
    
    def test_is_rate_limit_error_529(self):
        """Test 529 (overloaded) is rate limit error."""
        provider = AnthropicProvider()
        assert provider.is_rate_limit_error(529, None) is True
    
    def test_is_rate_limit_error_200(self):
        """Test 200 is not rate limit error."""
        provider = AnthropicProvider()
        assert provider.is_rate_limit_error(200, None) is False


class TestGenericProvider:
    """Tests for generic provider."""
    
    def test_default_headers(self):
        """Test default header names."""
        provider = GenericProvider()
        
        headers = {
            "x-ratelimit-remaining": "50",
            "x-ratelimit-limit": "100",
            "x-ratelimit-reset": "1705320000",
        }
        
        info = provider.parse_rate_limit_headers(headers)
        
        assert info.requests_remaining == 50
        assert info.requests_limit == 100
        assert info.reset_time is not None
    
    def test_custom_headers(self):
        """Test custom header names."""
        provider = GenericProvider(
            requests_remaining_header="X-Rate-Limit-Remaining",
            requests_limit_header="X-Rate-Limit-Limit",
            reset_header="X-Rate-Limit-Reset",
        )
        
        headers = {
            "X-Rate-Limit-Remaining": "25",
            "X-Rate-Limit-Limit": "50",
        }
        
        info = provider.parse_rate_limit_headers(headers)
        
        assert info.requests_remaining == 25
        assert info.requests_limit == 50
    
    def test_case_insensitive_headers(self):
        """Test headers are case insensitive."""
        provider = GenericProvider()
        
        headers = {
            "X-RATELIMIT-REMAINING": "50",
            "x-RateLimit-Limit": "100",
        }
        
        info = provider.parse_rate_limit_headers(headers)
        
        assert info.requests_remaining == 50
        assert info.requests_limit == 100
    
    def test_is_rate_limit_error(self):
        """Test rate limit error detection."""
        provider = GenericProvider()
        
        assert provider.is_rate_limit_error(429, None) is True
        assert provider.is_rate_limit_error(200, None) is False
        assert provider.is_rate_limit_error(503, None) is False
    
    def test_parse_unix_timestamp_reset(self):
        """Test parsing Unix timestamp reset time."""
        provider = GenericProvider()
        
        # Unix timestamp in seconds
        headers = {"x-ratelimit-reset": "1705320000"}
        info = provider.parse_rate_limit_headers(headers)
        assert info.reset_time is not None
    
    def test_parse_unix_timestamp_ms_reset(self):
        """Test parsing Unix timestamp in milliseconds."""
        provider = GenericProvider()
        
        # Unix timestamp in milliseconds
        headers = {"x-ratelimit-reset": "1705320000000"}
        info = provider.parse_rate_limit_headers(headers)
        assert info.reset_time is not None
    
    def test_parse_iso_reset(self):
        """Test parsing ISO 8601 reset time."""
        provider = GenericProvider()
        
        headers = {"x-ratelimit-reset": "2024-01-15T12:00:00Z"}
        info = provider.parse_rate_limit_headers(headers)
        assert info.reset_time is not None


class TestRetryAfter:
    """Tests for retry-after parsing."""
    
    def test_retry_after_numeric(self):
        """Test parsing numeric retry-after."""
        provider = OpenAIProvider()
        retry = provider.get_retry_after({"retry-after": "30"}, None)
        assert retry == 30.0
    
    def test_retry_after_float(self):
        """Test parsing float retry-after."""
        provider = OpenAIProvider()
        retry = provider.get_retry_after({"retry-after": "30.5"}, None)
        assert retry == 30.5
    
    def test_retry_after_missing(self):
        """Test missing retry-after."""
        provider = OpenAIProvider()
        retry = provider.get_retry_after({}, None)
        assert retry is None
    
    def test_retry_after_case_insensitive(self):
        """Test case insensitive retry-after."""
        provider = OpenAIProvider()
        retry = provider.get_retry_after({"Retry-After": "60"}, None)
        assert retry == 60.0
