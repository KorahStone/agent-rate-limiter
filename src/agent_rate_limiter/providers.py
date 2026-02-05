"""Rate limit providers for different APIs."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from .models import RateLimitInfo


class BaseProvider(ABC):
    """Base class for rate limit providers."""
    
    name: str = "base"
    
    @abstractmethod
    def parse_rate_limit_headers(self, headers: dict[str, str]) -> RateLimitInfo:
        """Parse rate limit information from response headers."""
        pass
    
    @abstractmethod
    def is_rate_limit_error(self, status_code: int, response_body: Any) -> bool:
        """Check if a response indicates a rate limit error."""
        pass
    
    def get_retry_after(self, headers: dict[str, str], response_body: Any) -> Optional[float]:
        """Get retry-after time in seconds if available."""
        # Standard Retry-After header
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                # Could be a date string
                pass
        return None
    
    def mask_key(self, key: str) -> str:
        """Mask an API key for logging."""
        if len(key) <= 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"


class OpenAIProvider(BaseProvider):
    """Provider for OpenAI API rate limits."""
    
    name: str = "openai"
    
    def parse_rate_limit_headers(self, headers: dict[str, str]) -> RateLimitInfo:
        """Parse OpenAI rate limit headers.
        
        OpenAI uses headers like:
        - x-ratelimit-limit-requests
        - x-ratelimit-limit-tokens
        - x-ratelimit-remaining-requests
        - x-ratelimit-remaining-tokens
        - x-ratelimit-reset-requests
        - x-ratelimit-reset-tokens
        """
        info = RateLimitInfo()
        
        # Request limits
        if "x-ratelimit-remaining-requests" in headers:
            try:
                info.requests_remaining = int(headers["x-ratelimit-remaining-requests"])
            except ValueError:
                pass
                
        if "x-ratelimit-limit-requests" in headers:
            try:
                info.requests_limit = int(headers["x-ratelimit-limit-requests"])
            except ValueError:
                pass
        
        # Token limits
        if "x-ratelimit-remaining-tokens" in headers:
            try:
                info.tokens_remaining = int(headers["x-ratelimit-remaining-tokens"])
            except ValueError:
                pass
                
        if "x-ratelimit-limit-tokens" in headers:
            try:
                info.tokens_limit = int(headers["x-ratelimit-limit-tokens"])
            except ValueError:
                pass
        
        # Reset time (OpenAI uses relative time like "1s", "2m", etc.)
        reset_str = headers.get("x-ratelimit-reset-requests") or headers.get("x-ratelimit-reset-tokens")
        if reset_str:
            info.reset_time = self._parse_reset_time(reset_str)
        
        # Retry-After
        info.retry_after = self.get_retry_after(headers, None)
        
        return info
    
    def _parse_reset_time(self, reset_str: str) -> Optional[datetime]:
        """Parse OpenAI reset time string."""
        try:
            # OpenAI uses formats like "1s", "2m3s", "1h2m3s"
            seconds = 0
            current_num = ""
            
            for char in reset_str:
                if char.isdigit() or char == ".":
                    current_num += char
                elif char == "h" and current_num:
                    seconds += float(current_num) * 3600
                    current_num = ""
                elif char == "m" and current_num:
                    seconds += float(current_num) * 60
                    current_num = ""
                elif char == "s" and current_num:
                    seconds += float(current_num)
                    current_num = ""
                elif char == "m" and current_num:
                    # Could be "ms" for milliseconds
                    pass
            
            if seconds > 0:
                return datetime.now(timezone.utc).replace(microsecond=0) + \
                       __import__("datetime").timedelta(seconds=seconds)
        except (ValueError, TypeError):
            pass
        return None
    
    def is_rate_limit_error(self, status_code: int, response_body: Any) -> bool:
        """Check if response is a rate limit error."""
        if status_code == 429:
            return True
        
        # OpenAI sometimes returns 503 for rate limits
        if status_code == 503:
            if isinstance(response_body, dict):
                error = response_body.get("error", {})
                if "rate" in str(error).lower():
                    return True
        
        return False


class AnthropicProvider(BaseProvider):
    """Provider for Anthropic API rate limits."""
    
    name: str = "anthropic"
    
    def parse_rate_limit_headers(self, headers: dict[str, str]) -> RateLimitInfo:
        """Parse Anthropic rate limit headers.
        
        Anthropic uses headers like:
        - anthropic-ratelimit-requests-limit
        - anthropic-ratelimit-requests-remaining
        - anthropic-ratelimit-requests-reset
        - anthropic-ratelimit-tokens-limit
        - anthropic-ratelimit-tokens-remaining
        - anthropic-ratelimit-tokens-reset
        - retry-after
        """
        info = RateLimitInfo()
        
        # Request limits
        if "anthropic-ratelimit-requests-remaining" in headers:
            try:
                info.requests_remaining = int(headers["anthropic-ratelimit-requests-remaining"])
            except ValueError:
                pass
                
        if "anthropic-ratelimit-requests-limit" in headers:
            try:
                info.requests_limit = int(headers["anthropic-ratelimit-requests-limit"])
            except ValueError:
                pass
        
        # Token limits
        if "anthropic-ratelimit-tokens-remaining" in headers:
            try:
                info.tokens_remaining = int(headers["anthropic-ratelimit-tokens-remaining"])
            except ValueError:
                pass
                
        if "anthropic-ratelimit-tokens-limit" in headers:
            try:
                info.tokens_limit = int(headers["anthropic-ratelimit-tokens-limit"])
            except ValueError:
                pass
        
        # Reset time (Anthropic uses ISO 8601 timestamps)
        reset_str = headers.get("anthropic-ratelimit-requests-reset") or \
                   headers.get("anthropic-ratelimit-tokens-reset")
        if reset_str:
            try:
                info.reset_time = datetime.fromisoformat(reset_str.replace("Z", "+00:00"))
            except ValueError:
                pass
        
        # Retry-After
        info.retry_after = self.get_retry_after(headers, None)
        
        return info
    
    def is_rate_limit_error(self, status_code: int, response_body: Any) -> bool:
        """Check if response is a rate limit error."""
        if status_code == 429:
            return True
        
        if status_code == 529:  # Anthropic overloaded
            return True
        
        return False


class GenericProvider(BaseProvider):
    """Generic provider for APIs with standard rate limit headers."""
    
    name: str = "generic"
    
    def __init__(
        self,
        requests_remaining_header: str = "x-ratelimit-remaining",
        requests_limit_header: str = "x-ratelimit-limit",
        reset_header: str = "x-ratelimit-reset",
    ):
        self.requests_remaining_header = requests_remaining_header.lower()
        self.requests_limit_header = requests_limit_header.lower()
        self.reset_header = reset_header.lower()
    
    def parse_rate_limit_headers(self, headers: dict[str, str]) -> RateLimitInfo:
        """Parse generic rate limit headers."""
        # Normalize headers to lowercase
        headers_lower = {k.lower(): v for k, v in headers.items()}
        
        info = RateLimitInfo()
        
        if self.requests_remaining_header in headers_lower:
            try:
                info.requests_remaining = int(headers_lower[self.requests_remaining_header])
            except ValueError:
                pass
                
        if self.requests_limit_header in headers_lower:
            try:
                info.requests_limit = int(headers_lower[self.requests_limit_header])
            except ValueError:
                pass
        
        if self.reset_header in headers_lower:
            reset_value = headers_lower[self.reset_header]
            try:
                # Try as Unix timestamp
                timestamp = float(reset_value)
                if timestamp > 1e12:  # Milliseconds
                    timestamp = timestamp / 1000
                info.reset_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            except ValueError:
                # Try as ISO 8601
                try:
                    info.reset_time = datetime.fromisoformat(reset_value.replace("Z", "+00:00"))
                except ValueError:
                    pass
        
        info.retry_after = self.get_retry_after(headers, None)
        
        return info
    
    def is_rate_limit_error(self, status_code: int, response_body: Any) -> bool:
        """Check if response is a rate limit error."""
        return status_code == 429
