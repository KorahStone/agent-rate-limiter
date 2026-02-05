"""API key management with rotation strategies."""

import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .models import RateLimitInfo, RotationStrategy


@dataclass
class KeyState:
    """State tracking for a single API key."""
    
    key: str
    requests_made: int = 0
    tokens_used: int = 0
    last_used: Optional[float] = None
    last_rate_limit: Optional[float] = None
    cooldown_until: Optional[float] = None
    rate_limit_info: Optional[RateLimitInfo] = None
    
    @property
    def is_on_cooldown(self) -> bool:
        """Check if key is currently on cooldown."""
        if self.cooldown_until is None:
            return False
        return time.time() < self.cooldown_until
    
    @property
    def masked(self) -> str:
        """Get masked version of key for logging."""
        if len(self.key) <= 8:
            return "***"
        return f"{self.key[:4]}...{self.key[-4:]}"


class KeyManager:
    """Manages multiple API keys with rotation strategies."""
    
    def __init__(
        self,
        keys: list[str],
        strategy: RotationStrategy = RotationStrategy.ROUND_ROBIN,
        cooldown_seconds: float = 60.0,
    ):
        if not keys:
            raise ValueError("At least one API key is required")
        
        self._keys = [KeyState(key=k) for k in keys]
        self._strategy = strategy
        self._cooldown_seconds = cooldown_seconds
        self._current_index = 0
        self._lock_holder: Optional[str] = None
    
    @property
    def total_keys(self) -> int:
        """Total number of keys."""
        return len(self._keys)
    
    @property
    def available_keys(self) -> int:
        """Number of keys not on cooldown."""
        return sum(1 for k in self._keys if not k.is_on_cooldown)
    
    @property
    def exhausted_keys(self) -> int:
        """Number of keys on cooldown."""
        return sum(1 for k in self._keys if k.is_on_cooldown)
    
    def get_key(self) -> Optional[str]:
        """Get the next API key according to rotation strategy."""
        available = [k for k in self._keys if not k.is_on_cooldown]
        
        if not available:
            return None
        
        if self._strategy == RotationStrategy.ROUND_ROBIN:
            key_state = self._get_round_robin(available)
        elif self._strategy == RotationStrategy.LEAST_USED:
            key_state = self._get_least_used(available)
        elif self._strategy == RotationStrategy.RANDOM:
            key_state = random.choice(available)
        elif self._strategy == RotationStrategy.FAILOVER:
            key_state = self._get_failover(available)
        else:
            key_state = available[0]
        
        key_state.last_used = time.time()
        key_state.requests_made += 1
        
        return key_state.key
    
    def _get_round_robin(self, available: list[KeyState]) -> KeyState:
        """Get next key in round-robin order."""
        # Find the next available key starting from current index
        for i in range(len(self._keys)):
            idx = (self._current_index + i) % len(self._keys)
            key_state = self._keys[idx]
            if key_state in available:
                self._current_index = (idx + 1) % len(self._keys)
                return key_state
        return available[0]
    
    def _get_least_used(self, available: list[KeyState]) -> KeyState:
        """Get key with most remaining capacity."""
        # First, prefer keys with known remaining capacity
        with_info = [k for k in available if k.rate_limit_info and k.rate_limit_info.requests_remaining is not None]
        
        if with_info:
            return max(with_info, key=lambda k: k.rate_limit_info.requests_remaining or 0)
        
        # Fall back to least requests made
        return min(available, key=lambda k: k.requests_made)
    
    def _get_failover(self, available: list[KeyState]) -> KeyState:
        """Get primary key, only switch on failure."""
        # Always try to use the first available key (primary)
        for key_state in self._keys:
            if key_state in available:
                return key_state
        return available[0]
    
    def report_success(self, key: str, rate_limit_info: Optional[RateLimitInfo] = None) -> None:
        """Report a successful request with a key."""
        key_state = self._find_key(key)
        if key_state:
            key_state.rate_limit_info = rate_limit_info
    
    def report_rate_limit(self, key: str, rate_limit_info: Optional[RateLimitInfo] = None) -> None:
        """Report that a key hit a rate limit."""
        key_state = self._find_key(key)
        if key_state:
            key_state.last_rate_limit = time.time()
            key_state.rate_limit_info = rate_limit_info
            
            # Calculate cooldown
            if rate_limit_info and rate_limit_info.retry_after:
                cooldown = rate_limit_info.retry_after
            elif rate_limit_info and rate_limit_info.reset_time:
                now = datetime.now(timezone.utc)
                delta = (rate_limit_info.reset_time - now).total_seconds()
                cooldown = max(delta, self._cooldown_seconds)
            else:
                cooldown = self._cooldown_seconds
            
            key_state.cooldown_until = time.time() + cooldown
    
    def _find_key(self, key: str) -> Optional[KeyState]:
        """Find key state by key value."""
        for key_state in self._keys:
            if key_state.key == key:
                return key_state
        return None
    
    def get_key_state(self, key: str) -> Optional[KeyState]:
        """Get state for a specific key."""
        return self._find_key(key)
    
    def get_all_states(self) -> list[KeyState]:
        """Get state for all keys."""
        return self._keys.copy()
    
    def reset_key(self, key: str) -> None:
        """Reset cooldown for a specific key."""
        key_state = self._find_key(key)
        if key_state:
            key_state.cooldown_until = None
            key_state.last_rate_limit = None
    
    def reset_all(self) -> None:
        """Reset all keys."""
        for key_state in self._keys:
            key_state.cooldown_until = None
            key_state.last_rate_limit = None
            key_state.requests_made = 0
            key_state.tokens_used = 0
