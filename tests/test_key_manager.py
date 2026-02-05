"""Tests for key manager."""

import pytest
import time
from unittest.mock import patch

from agent_rate_limiter.key_manager import KeyManager, KeyState
from agent_rate_limiter.models import RateLimitInfo, RotationStrategy


class TestKeyState:
    """Tests for KeyState dataclass."""
    
    def test_default_state(self):
        """Test default key state."""
        state = KeyState(key="sk-test")
        assert state.key == "sk-test"
        assert state.requests_made == 0
        assert state.tokens_used == 0
        assert state.last_used is None
        assert state.is_on_cooldown is False
    
    def test_is_on_cooldown(self):
        """Test cooldown check."""
        state = KeyState(key="sk-test")
        
        # Not on cooldown
        assert state.is_on_cooldown is False
        
        # Set cooldown in future
        state.cooldown_until = time.time() + 60
        assert state.is_on_cooldown is True
        
        # Set cooldown in past
        state.cooldown_until = time.time() - 1
        assert state.is_on_cooldown is False
    
    def test_masked_key(self):
        """Test key masking."""
        state = KeyState(key="sk-1234567890abcdef")
        assert state.masked == "sk-1...cdef"
        
        state = KeyState(key="short")
        assert state.masked == "***"


class TestKeyManager:
    """Tests for KeyManager class."""
    
    def test_init_with_keys(self):
        """Test initialization with keys."""
        manager = KeyManager(keys=["key1", "key2", "key3"])
        assert manager.total_keys == 3
        assert manager.available_keys == 3
        assert manager.exhausted_keys == 0
    
    def test_init_empty_keys_raises(self):
        """Test initialization with empty keys raises error."""
        with pytest.raises(ValueError, match="At least one API key"):
            KeyManager(keys=[])
    
    def test_get_key_round_robin(self):
        """Test round-robin key rotation."""
        manager = KeyManager(
            keys=["key1", "key2", "key3"],
            strategy=RotationStrategy.ROUND_ROBIN,
        )
        
        # Should cycle through keys
        assert manager.get_key() == "key1"
        assert manager.get_key() == "key2"
        assert manager.get_key() == "key3"
        assert manager.get_key() == "key1"
    
    def test_get_key_random(self):
        """Test random key selection."""
        manager = KeyManager(
            keys=["key1", "key2", "key3"],
            strategy=RotationStrategy.RANDOM,
        )
        
        # Should return one of the keys
        key = manager.get_key()
        assert key in ["key1", "key2", "key3"]
    
    def test_get_key_failover(self):
        """Test failover key selection."""
        manager = KeyManager(
            keys=["primary", "secondary", "tertiary"],
            strategy=RotationStrategy.FAILOVER,
        )
        
        # Should always return primary
        assert manager.get_key() == "primary"
        assert manager.get_key() == "primary"
        assert manager.get_key() == "primary"
    
    def test_get_key_least_used(self):
        """Test least-used key selection."""
        manager = KeyManager(
            keys=["key1", "key2", "key3"],
            strategy=RotationStrategy.LEAST_USED,
        )
        
        # Mark key1 as having remaining capacity
        info = RateLimitInfo(requests_remaining=100, requests_limit=100)
        manager.report_success("key1", info)
        
        # Mark key2 as having less capacity
        info2 = RateLimitInfo(requests_remaining=50, requests_limit=100)
        manager.report_success("key2", info2)
        
        # Should prefer key1 (most remaining)
        # First call gets initial key, subsequent should prefer higher capacity
        manager.get_key()  # First call
        key = manager.get_key()
        # Either key1 (highest capacity) or key3 (unused, so least requests_made)
        assert key in ["key1", "key3"]
    
    def test_report_rate_limit(self):
        """Test reporting rate limit."""
        manager = KeyManager(
            keys=["key1", "key2"],
            cooldown_seconds=60.0,
        )
        
        # Report rate limit on key1
        manager.report_rate_limit("key1")
        
        # key1 should be on cooldown
        state = manager.get_key_state("key1")
        assert state.is_on_cooldown is True
        
        # Should only return key2 now
        assert manager.available_keys == 1
        assert manager.get_key() == "key2"
    
    def test_report_rate_limit_with_retry_after(self):
        """Test rate limit with retry-after."""
        manager = KeyManager(keys=["key1"], cooldown_seconds=60.0)
        
        # Report with specific retry-after
        info = RateLimitInfo(retry_after=30.0)
        manager.report_rate_limit("key1", info)
        
        state = manager.get_key_state("key1")
        assert state.is_on_cooldown is True
        # Cooldown should be ~30 seconds, not 60
        assert state.cooldown_until is not None
        assert state.cooldown_until < time.time() + 35
    
    def test_report_success(self):
        """Test reporting success."""
        manager = KeyManager(keys=["key1"])
        
        info = RateLimitInfo(requests_remaining=99, requests_limit=100)
        manager.report_success("key1", info)
        
        state = manager.get_key_state("key1")
        assert state.rate_limit_info == info
    
    def test_all_keys_exhausted(self):
        """Test when all keys are exhausted."""
        manager = KeyManager(keys=["key1", "key2"])
        
        # Exhaust both keys
        manager.report_rate_limit("key1")
        manager.report_rate_limit("key2")
        
        # Should return None
        assert manager.get_key() is None
        assert manager.available_keys == 0
        assert manager.exhausted_keys == 2
    
    def test_reset_key(self):
        """Test resetting a key."""
        manager = KeyManager(keys=["key1"])
        
        # Put key on cooldown
        manager.report_rate_limit("key1")
        assert manager.available_keys == 0
        
        # Reset key
        manager.reset_key("key1")
        assert manager.available_keys == 1
    
    def test_reset_all(self):
        """Test resetting all keys."""
        manager = KeyManager(keys=["key1", "key2", "key3"])
        
        # Put all keys on cooldown
        manager.report_rate_limit("key1")
        manager.report_rate_limit("key2")
        manager.report_rate_limit("key3")
        assert manager.available_keys == 0
        
        # Reset all
        manager.reset_all()
        assert manager.available_keys == 3
    
    def test_get_all_states(self):
        """Test getting all key states."""
        manager = KeyManager(keys=["key1", "key2"])
        
        states = manager.get_all_states()
        assert len(states) == 2
        assert all(isinstance(s, KeyState) for s in states)
    
    def test_skips_cooldown_keys_round_robin(self):
        """Test round-robin skips keys on cooldown."""
        manager = KeyManager(
            keys=["key1", "key2", "key3"],
            strategy=RotationStrategy.ROUND_ROBIN,
        )
        
        # Put key2 on cooldown
        manager.report_rate_limit("key2")
        
        # Should skip key2
        assert manager.get_key() == "key1"
        assert manager.get_key() == "key3"
        assert manager.get_key() == "key1"
