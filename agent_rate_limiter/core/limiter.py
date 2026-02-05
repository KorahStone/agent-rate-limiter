"""Core rate limiter implementation using token bucket algorithm"""

import time
import asyncio
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from threading import Lock
from functools import wraps

from .providers import ProviderConfig, ModelConfig


@dataclass
class TokenBucket:
    """Token bucket for rate limiting"""
    capacity: int
    tokens: float = field(init=False)
    last_update: float = field(init=False)
    refill_rate: float  # tokens per second
    lock: Lock = field(default_factory=Lock, init=False)
    
    def __post_init__(self):
        self.tokens = float(self.capacity)
        self.last_update = time.time()
    
    def _refill(self):
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_update = now
    
    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if successful."""
        with self.lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    def wait_time(self, tokens: int = 1) -> float:
        """Calculate wait time needed for tokens to be available"""
        with self.lock:
            self._refill()
            if self.tokens >= tokens:
                return 0.0
            needed = tokens - self.tokens
            return needed / self.refill_rate


class RateLimitError(Exception):
    """Raised when rate limit is exceeded and retry is not enabled"""
    pass


class RateLimiter:
    """Rate limiter for a single model"""
    
    def __init__(
        self,
        provider: str,
        model: str,
        model_config: ModelConfig,
        enable_retries: bool = True,
        max_retries: int = 3,
        on_limit_hit: Optional[Callable[[str, str], None]] = None
    ):
        self.provider = provider
        self.model = model
        self.config = model_config
        self.enable_retries = enable_retries
        self.max_retries = max_retries
        self.on_limit_hit = on_limit_hit
        
        # Create token buckets for requests and tokens
        self.request_bucket = TokenBucket(
            capacity=model_config.rpm,
            refill_rate=model_config.rpm / 60.0  # per second
        )
        self.token_bucket = TokenBucket(
            capacity=model_config.tpm,
            refill_rate=model_config.tpm / 60.0  # per second
        )
        
        # Metrics
        self.total_requests = 0
        self.total_tokens = 0
        self.failed_requests = 0
        self.retried_requests = 0
    
    def _wait_for_capacity(self, tokens: int = 1, estimated_tokens: int = 100):
        """Wait until we have capacity for the request"""
        # Wait for request capacity
        request_wait = self.request_bucket.wait_time(1)
        if request_wait > 0:
            if self.on_limit_hit:
                self.on_limit_hit(self.provider, self.model)
            time.sleep(request_wait)
        
        # Wait for token capacity
        token_wait = self.token_bucket.wait_time(estimated_tokens)
        if token_wait > 0:
            if self.on_limit_hit:
                self.on_limit_hit(self.provider, self.model)
            time.sleep(token_wait)
    
    async def _wait_for_capacity_async(self, tokens: int = 1, estimated_tokens: int = 100):
        """Async version of _wait_for_capacity"""
        request_wait = self.request_bucket.wait_time(1)
        if request_wait > 0:
            if self.on_limit_hit:
                self.on_limit_hit(self.provider, self.model)
            await asyncio.sleep(request_wait)
        
        token_wait = self.token_bucket.wait_time(estimated_tokens)
        if token_wait > 0:
            if self.on_limit_hit:
                self.on_limit_hit(self.provider, self.model)
            await asyncio.sleep(token_wait)
    
    def limit(self, estimated_tokens: int = 100):
        """Decorator for rate-limited functions"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                self._wait_for_capacity(estimated_tokens=estimated_tokens)
                
                try:
                    result = func(*args, **kwargs)
                    self.total_requests += 1
                    
                    # Consume tokens
                    self.request_bucket.consume(1)
                    self.token_bucket.consume(estimated_tokens)
                    self.total_tokens += estimated_tokens
                    
                    return result
                except Exception as e:
                    self.failed_requests += 1
                    raise
            
            return wrapper
        return decorator
    
    def limit_async(self, estimated_tokens: int = 100):
        """Async decorator for rate-limited functions"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                await self._wait_for_capacity_async(estimated_tokens=estimated_tokens)
                
                try:
                    result = await func(*args, **kwargs)
                    self.total_requests += 1
                    
                    # Consume tokens
                    self.request_bucket.consume(1)
                    self.token_bucket.consume(estimated_tokens)
                    self.total_tokens += estimated_tokens
                    
                    return result
                except Exception as e:
                    self.failed_requests += 1
                    raise
            
            return wrapper
        return decorator
    
    def get_metrics(self) -> dict:
        """Get current metrics"""
        return {
            "provider": self.provider,
            "model": self.model,
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "failed_requests": self.failed_requests,
            "retried_requests": self.retried_requests,
            "request_capacity": self.request_bucket.tokens,
            "token_capacity": self.token_bucket.tokens,
        }
