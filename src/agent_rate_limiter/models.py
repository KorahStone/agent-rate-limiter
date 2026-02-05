"""Data models for agent-rate-limiter."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional


class Priority(Enum):
    """Request priority levels."""
    
    CRITICAL = 0  # System-critical, bypass queue if possible
    HIGH = 1      # User-facing requests
    NORMAL = 2    # Standard requests
    LOW = 3       # Background tasks
    BULK = 4      # Batch processing, lowest priority


class RotationStrategy(Enum):
    """API key rotation strategies."""
    
    ROUND_ROBIN = auto()    # Rotate through keys in order
    LEAST_USED = auto()     # Use the key with most remaining capacity
    RANDOM = auto()         # Random selection
    FAILOVER = auto()       # Only rotate when current key fails


@dataclass
class RateLimitInfo:
    """Information about current rate limit status."""
    
    requests_remaining: Optional[int] = None
    requests_limit: Optional[int] = None
    tokens_remaining: Optional[int] = None
    tokens_limit: Optional[int] = None
    reset_time: Optional[datetime] = None
    retry_after: Optional[float] = None  # seconds
    
    @property
    def is_exhausted(self) -> bool:
        """Check if rate limit is exhausted."""
        if self.requests_remaining is not None and self.requests_remaining <= 0:
            return True
        if self.tokens_remaining is not None and self.tokens_remaining <= 0:
            return True
        return False
    
    @property
    def usage_ratio(self) -> Optional[float]:
        """Get usage ratio (0.0 = fresh, 1.0 = exhausted)."""
        if self.requests_remaining is not None and self.requests_limit is not None:
            if self.requests_limit > 0:
                return 1.0 - (self.requests_remaining / self.requests_limit)
        return None


@dataclass
class Capacity:
    """Current capacity information."""
    
    requests_remaining: Optional[int] = None
    tokens_remaining: Optional[int] = None
    reset_time: Optional[datetime] = None
    keys_available: int = 0
    keys_exhausted: int = 0
    
    @property
    def total_keys(self) -> int:
        """Total number of keys."""
        return self.keys_available + self.keys_exhausted


@dataclass
class RequestResult:
    """Result of a rate-limited request."""
    
    success: bool
    status_code: Optional[int] = None
    data: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    rate_limit_info: Optional[RateLimitInfo] = None
    retries: int = 0
    total_wait_time: float = 0.0
    key_used: Optional[str] = None  # Masked key identifier
    error: Optional[str] = None


class RateLimitError(Exception):
    """Raised when rate limit cannot be handled."""
    
    def __init__(
        self,
        message: str,
        rate_limit_info: Optional[RateLimitInfo] = None,
        retries_attempted: int = 0,
        keys_tried: int = 0,
    ):
        super().__init__(message)
        self.rate_limit_info = rate_limit_info
        self.retries_attempted = retries_attempted
        self.keys_tried = keys_tried


class QueueFullError(Exception):
    """Raised when request queue is full."""
    pass


class QueueTimeoutError(Exception):
    """Raised when request times out in queue."""
    pass
