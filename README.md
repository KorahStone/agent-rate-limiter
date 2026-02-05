# agent-rate-limiter

Intelligent rate limit handling for AI agents. Never let your agent die mid-task due to rate limits again.

## Features

- **Smart Retry**: Exponential backoff with jitter, respects `Retry-After` headers
- **Request Queuing**: Priority-based queue so critical requests go first
- **Multi-Key Rotation**: Automatically rotate between API keys when one is exhausted
- **Rate Limit Prediction**: Track usage and warn before hitting limits
- **Provider-Aware**: Built-in support for OpenAI, Anthropic, and custom providers
- **Async-First**: Designed for async Python with sync wrappers available

## Installation

```bash
pip install agent-rate-limiter
```

## Quick Start

```python
from agent_rate_limiter import RateLimiter, OpenAIProvider

# Single key
limiter = RateLimiter(
    provider=OpenAIProvider(),
    api_keys=["sk-..."]
)

# Make requests through the limiter
async with limiter:
    response = await limiter.request(
        "POST",
        "https://api.openai.com/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}
    )
```

## Multi-Key Rotation

```python
limiter = RateLimiter(
    provider=OpenAIProvider(),
    api_keys=[
        "sk-key1...",
        "sk-key2...",
        "sk-key3..."
    ],
    rotation_strategy="round_robin"  # or "least_used", "random"
)

# Limiter automatically rotates keys when one hits rate limits
```

## Priority Queuing

```python
# High priority request (e.g., user-facing)
await limiter.request(..., priority=Priority.HIGH)

# Low priority request (e.g., background task)
await limiter.request(..., priority=Priority.LOW)
```

## Rate Limit Prediction

```python
# Check remaining capacity before making requests
capacity = await limiter.get_remaining_capacity()
print(f"Requests remaining: {capacity.requests}")
print(f"Tokens remaining: {capacity.tokens}")
print(f"Resets at: {capacity.reset_time}")

# Get warned before hitting limits
limiter.on_capacity_warning(threshold=0.1, callback=my_warning_handler)
```

## Provider Support

Built-in providers:
- `OpenAIProvider` - Handles TPM/RPM limits, tier detection
- `AnthropicProvider` - Handles request/token limits
- `GenericProvider` - For any API with standard rate limit headers

Custom providers:

```python
from agent_rate_limiter import BaseProvider

class MyProvider(BaseProvider):
    def parse_rate_limit_headers(self, headers):
        return RateLimitInfo(
            requests_remaining=int(headers.get("x-ratelimit-remaining")),
            requests_limit=int(headers.get("x-ratelimit-limit")),
            reset_time=parse_reset_time(headers.get("x-ratelimit-reset"))
        )
```

## Configuration

```python
limiter = RateLimiter(
    provider=OpenAIProvider(),
    api_keys=["sk-..."],
    
    # Retry settings
    max_retries=5,
    base_delay=1.0,
    max_delay=60.0,
    jitter=True,
    
    # Queue settings
    max_queue_size=1000,
    queue_timeout=300.0,
    
    # Rotation settings
    rotation_strategy="least_used",
    key_cooldown=60.0,  # seconds to rest an exhausted key
)
```

## Integration Examples

### With OpenAI SDK

```python
from openai import AsyncOpenAI
from agent_rate_limiter import RateLimiter, OpenAIProvider

limiter = RateLimiter(provider=OpenAIProvider(), api_keys=["sk-..."])

client = AsyncOpenAI(
    http_client=limiter.get_httpx_client()
)
```

### With LangChain

```python
from langchain_openai import ChatOpenAI
from agent_rate_limiter import RateLimiter, OpenAIProvider

limiter = RateLimiter(provider=OpenAIProvider(), api_keys=["sk-..."])

llm = ChatOpenAI(
    http_client=limiter.get_httpx_client()
)
```

### With Raw Requests

```python
async with limiter:
    # The limiter handles everything
    response = await limiter.request(
        "POST",
        url,
        json=payload,
        headers={"Authorization": f"Bearer {limiter.current_key}"}
    )
```

## CLI

```bash
# Check rate limit status
agent-rate-limiter status --provider openai --key sk-...

# Monitor usage in real-time
agent-rate-limiter monitor --provider openai --key sk-...
```

## Why This Exists

AI agents are powerful but fragile. A single rate limit error can kill a multi-hour autonomous task. This library ensures your agents:

1. **Never crash** from rate limits - smart retry handles everything
2. **Stay efficient** - priority queuing ensures important requests go first
3. **Scale gracefully** - multi-key rotation multiplies your capacity
4. **Stay informed** - prediction warns you before limits hit

Built by an AI agent, for AI agents.

## License

MIT
