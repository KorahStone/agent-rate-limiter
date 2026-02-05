"""Main RateLimiter class."""

import asyncio
import random
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Optional

import httpx

from .key_manager import KeyManager
from .models import (
    Capacity,
    Priority,
    QueueFullError,
    RateLimitError,
    RateLimitInfo,
    RequestResult,
    RotationStrategy,
)
from .providers import BaseProvider, GenericProvider
from .queue import PriorityQueue


class RateLimiter:
    """Intelligent rate limiter for AI agent API calls.
    
    Features:
    - Smart retry with exponential backoff and jitter
    - Multi-key rotation
    - Priority-based request queuing
    - Rate limit prediction and warnings
    """
    
    def __init__(
        self,
        api_keys: list[str],
        provider: Optional[BaseProvider] = None,
        # Retry settings
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        # Queue settings
        max_queue_size: int = 1000,
        queue_timeout: float = 300.0,
        enable_queue: bool = True,
        # Key rotation settings
        rotation_strategy: RotationStrategy = RotationStrategy.ROUND_ROBIN,
        key_cooldown: float = 60.0,
        # Callbacks
        on_rate_limit: Optional[Callable[[str, RateLimitInfo], None]] = None,
        on_retry: Optional[Callable[[int, float], None]] = None,
        on_capacity_warning: Optional[Callable[[Capacity], None]] = None,
        capacity_warning_threshold: float = 0.1,
    ):
        self._provider = provider or GenericProvider()
        self._key_manager = KeyManager(
            keys=api_keys,
            strategy=rotation_strategy,
            cooldown_seconds=key_cooldown,
        )
        
        # Retry settings
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._jitter = jitter
        
        # Queue
        self._enable_queue = enable_queue
        self._queue = PriorityQueue(
            max_size=max_queue_size,
            default_timeout=queue_timeout,
        )
        
        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None
        self._owns_client = True
        
        # Callbacks
        self._on_rate_limit = on_rate_limit
        self._on_retry = on_retry
        self._on_capacity_warning = on_capacity_warning
        self._capacity_warning_threshold = capacity_warning_threshold
        
        # Stats
        self._total_requests = 0
        self._total_retries = 0
        self._total_rate_limits = 0
    
    async def __aenter__(self) -> "RateLimiter":
        """Enter async context."""
        await self._ensure_client()
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context."""
        await self.close()
    
    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
            self._owns_client = True
        return self._client
    
    async def close(self) -> None:
        """Close the rate limiter and cleanup resources."""
        if self._client and self._owns_client:
            await self._client.aclose()
            self._client = None
    
    def set_client(self, client: httpx.AsyncClient) -> None:
        """Set a custom HTTP client."""
        self._client = client
        self._owns_client = False
    
    @property
    def current_key(self) -> Optional[str]:
        """Get the current API key (for manual header setting)."""
        return self._key_manager.get_key()
    
    async def request(
        self,
        method: str,
        url: str,
        priority: Priority = Priority.NORMAL,
        **kwargs: Any,
    ) -> RequestResult:
        """Make a rate-limited request.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            priority: Request priority
            **kwargs: Additional arguments passed to httpx
            
        Returns:
            RequestResult with response data and rate limit info
        """
        self._total_requests += 1
        
        client = await self._ensure_client()
        
        retries = 0
        total_wait = 0.0
        last_rate_limit_info: Optional[RateLimitInfo] = None
        keys_tried: set[str] = set()
        
        while retries <= self._max_retries:
            # Get an API key
            key = self._key_manager.get_key()
            
            if key is None:
                # All keys exhausted
                raise RateLimitError(
                    "All API keys are rate limited",
                    rate_limit_info=last_rate_limit_info,
                    retries_attempted=retries,
                    keys_tried=len(keys_tried),
                )
            
            keys_tried.add(key)
            
            # Add authorization header if not present
            headers = kwargs.pop("headers", {})
            if "Authorization" not in headers and "authorization" not in headers:
                headers["Authorization"] = f"Bearer {key}"
            
            try:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    **kwargs,
                )
                
                # Parse rate limit info from headers
                rate_limit_info = self._provider.parse_rate_limit_headers(
                    dict(response.headers)
                )
                
                # Check for rate limit error
                if self._provider.is_rate_limit_error(response.status_code, None):
                    last_rate_limit_info = rate_limit_info
                    self._total_rate_limits += 1
                    
                    # Report to key manager
                    self._key_manager.report_rate_limit(key, rate_limit_info)
                    
                    # Callback
                    if self._on_rate_limit:
                        self._on_rate_limit(self._provider.mask_key(key), rate_limit_info)
                    
                    # Calculate retry delay
                    delay = self._calculate_delay(retries, rate_limit_info)
                    total_wait += delay
                    
                    # Callback
                    if self._on_retry:
                        self._on_retry(retries + 1, delay)
                    
                    # Wait and retry
                    await asyncio.sleep(delay)
                    retries += 1
                    self._total_retries += 1
                    continue
                
                # Success!
                self._key_manager.report_success(key, rate_limit_info)
                
                # Check capacity warning
                await self._check_capacity_warning(rate_limit_info)
                
                # Parse response
                try:
                    data = response.json()
                except Exception:
                    data = response.text
                
                return RequestResult(
                    success=True,
                    status_code=response.status_code,
                    data=data,
                    headers=dict(response.headers),
                    rate_limit_info=rate_limit_info,
                    retries=retries,
                    total_wait_time=total_wait,
                    key_used=self._provider.mask_key(key),
                )
                
            except httpx.TimeoutException as e:
                # Timeout - retry with different key if available
                retries += 1
                if retries > self._max_retries:
                    return RequestResult(
                        success=False,
                        error=f"Request timed out after {retries} retries: {e}",
                        retries=retries,
                        total_wait_time=total_wait,
                    )
                continue
                
            except httpx.RequestError as e:
                # Network error
                return RequestResult(
                    success=False,
                    error=f"Request failed: {e}",
                    retries=retries,
                    total_wait_time=total_wait,
                )
        
        # Max retries exceeded
        raise RateLimitError(
            f"Max retries ({self._max_retries}) exceeded",
            rate_limit_info=last_rate_limit_info,
            retries_attempted=retries,
            keys_tried=len(keys_tried),
        )
    
    def _calculate_delay(
        self,
        retry_count: int,
        rate_limit_info: Optional[RateLimitInfo],
    ) -> float:
        """Calculate delay before next retry."""
        # Use retry-after if available
        if rate_limit_info and rate_limit_info.retry_after:
            delay = rate_limit_info.retry_after
        # Use reset time if available
        elif rate_limit_info and rate_limit_info.reset_time:
            now = datetime.now(timezone.utc)
            delay = max(0, (rate_limit_info.reset_time - now).total_seconds())
        # Exponential backoff
        else:
            delay = self._base_delay * (2 ** retry_count)
        
        # Cap at max delay
        delay = min(delay, self._max_delay)
        
        # Add jitter
        if self._jitter:
            delay = delay * (0.5 + random.random())
        
        return delay
    
    async def _check_capacity_warning(self, rate_limit_info: RateLimitInfo) -> None:
        """Check if capacity is low and trigger warning."""
        if not self._on_capacity_warning:
            return
        
        usage_ratio = rate_limit_info.usage_ratio
        if usage_ratio is not None and usage_ratio >= (1.0 - self._capacity_warning_threshold):
            capacity = await self.get_remaining_capacity()
            self._on_capacity_warning(capacity)
    
    async def get_remaining_capacity(self) -> Capacity:
        """Get current remaining capacity across all keys."""
        states = self._key_manager.get_all_states()
        
        total_requests = 0
        total_tokens = 0
        earliest_reset: Optional[datetime] = None
        
        available = 0
        exhausted = 0
        
        for state in states:
            if state.is_on_cooldown:
                exhausted += 1
            else:
                available += 1
                if state.rate_limit_info:
                    info = state.rate_limit_info
                    if info.requests_remaining is not None:
                        total_requests += info.requests_remaining
                    if info.tokens_remaining is not None:
                        total_tokens += info.tokens_remaining
                    if info.reset_time:
                        if earliest_reset is None or info.reset_time < earliest_reset:
                            earliest_reset = info.reset_time
        
        return Capacity(
            requests_remaining=total_requests if total_requests > 0 else None,
            tokens_remaining=total_tokens if total_tokens > 0 else None,
            reset_time=earliest_reset,
            keys_available=available,
            keys_exhausted=exhausted,
        )
    
    def get_stats(self) -> dict[str, Any]:
        """Get limiter statistics."""
        return {
            "total_requests": self._total_requests,
            "total_retries": self._total_retries,
            "total_rate_limits": self._total_rate_limits,
            "keys": {
                "total": self._key_manager.total_keys,
                "available": self._key_manager.available_keys,
                "exhausted": self._key_manager.exhausted_keys,
            },
            "queue": self._queue.get_stats() if self._enable_queue else None,
        }
    
    def get_httpx_client(self) -> httpx.AsyncClient:
        """Get an httpx client configured to use this limiter.
        
        Note: This returns the internal client. For full rate limiting,
        use the request() method instead.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
            self._owns_client = True
        return self._client
    
    def on_capacity_warning(
        self,
        threshold: float,
        callback: Callable[[Capacity], None],
    ) -> None:
        """Set callback for low capacity warnings.
        
        Args:
            threshold: Trigger when remaining capacity is below this ratio (0.1 = 10%)
            callback: Function to call with current capacity
        """
        self._capacity_warning_threshold = threshold
        self._on_capacity_warning = callback
