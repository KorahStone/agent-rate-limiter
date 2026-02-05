"""
agent-rate-limiter: Intelligent rate limit handling for AI agents.

Never let your agent die mid-task due to rate limits again.
"""

from .limiter import RateLimiter
from .providers import (
    BaseProvider,
    OpenAIProvider,
    AnthropicProvider,
    GenericProvider,
)
from .models import (
    RateLimitInfo,
    RateLimitError,
    Priority,
    RotationStrategy,
    Capacity,
    RequestResult,
)
from .queue import PriorityQueue
from .key_manager import KeyManager

__version__ = "0.1.0"

__all__ = [
    # Main class
    "RateLimiter",
    # Providers
    "BaseProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GenericProvider",
    # Models
    "RateLimitInfo",
    "RateLimitError",
    "Priority",
    "RotationStrategy",
    "Capacity",
    "RequestResult",
    # Components
    "PriorityQueue",
    "KeyManager",
]
