"""CLI for agent-rate-limiter."""

import argparse
import asyncio
import sys
from typing import Optional

from .limiter import RateLimiter
from .providers import AnthropicProvider, GenericProvider, OpenAIProvider


def get_provider(name: str):
    """Get provider by name."""
    providers = {
        "openai": OpenAIProvider(),
        "anthropic": AnthropicProvider(),
        "generic": GenericProvider(),
    }
    return providers.get(name.lower(), GenericProvider())


async def check_status(provider_name: str, api_key: str) -> None:
    """Check rate limit status for an API key."""
    provider = get_provider(provider_name)
    
    limiter = RateLimiter(
        api_keys=[api_key],
        provider=provider,
    )
    
    async with limiter:
        # Make a minimal request to get rate limit headers
        if provider_name == "openai":
            url = "https://api.openai.com/v1/models"
        elif provider_name == "anthropic":
            url = "https://api.anthropic.com/v1/models"
        else:
            print("Status check requires openai or anthropic provider")
            return
        
        try:
            result = await limiter.request("GET", url)
            
            if result.success and result.rate_limit_info:
                info = result.rate_limit_info
                print(f"\n📊 Rate Limit Status ({provider_name})")
                print("=" * 40)
                
                if info.requests_remaining is not None and info.requests_limit is not None:
                    pct = (info.requests_remaining / info.requests_limit) * 100
                    print(f"Requests: {info.requests_remaining}/{info.requests_limit} ({pct:.1f}% remaining)")
                
                if info.tokens_remaining is not None and info.tokens_limit is not None:
                    pct = (info.tokens_remaining / info.tokens_limit) * 100
                    print(f"Tokens:   {info.tokens_remaining}/{info.tokens_limit} ({pct:.1f}% remaining)")
                
                if info.reset_time:
                    print(f"Resets:   {info.reset_time.isoformat()}")
                
                print()
            elif not result.success:
                print(f"❌ Request failed: {result.error}")
            else:
                print("ℹ️  No rate limit information available in response headers")
                
        except Exception as e:
            print(f"❌ Error: {e}")


async def monitor(provider_name: str, api_key: str, interval: int = 30) -> None:
    """Monitor rate limits in real-time."""
    provider = get_provider(provider_name)
    
    print(f"🔍 Monitoring {provider_name} rate limits (Ctrl+C to stop)")
    print("=" * 50)
    
    limiter = RateLimiter(
        api_keys=[api_key],
        provider=provider,
    )
    
    async with limiter:
        while True:
            await check_status(provider_name, api_key)
            print(f"Next check in {interval}s...")
            await asyncio.sleep(interval)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Intelligent rate limit handling for AI agents",
        prog="agent-rate-limiter",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Check rate limit status")
    status_parser.add_argument(
        "--provider", "-p",
        choices=["openai", "anthropic"],
        required=True,
        help="API provider",
    )
    status_parser.add_argument(
        "--key", "-k",
        required=True,
        help="API key",
    )
    
    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Monitor rate limits")
    monitor_parser.add_argument(
        "--provider", "-p",
        choices=["openai", "anthropic"],
        required=True,
        help="API provider",
    )
    monitor_parser.add_argument(
        "--key", "-k",
        required=True,
        help="API key",
    )
    monitor_parser.add_argument(
        "--interval", "-i",
        type=int,
        default=30,
        help="Check interval in seconds (default: 30)",
    )
    
    args = parser.parse_args()
    
    if args.command == "status":
        asyncio.run(check_status(args.provider, args.key))
    elif args.command == "monitor":
        try:
            asyncio.run(monitor(args.provider, args.key, args.interval))
        except KeyboardInterrupt:
            print("\n👋 Monitoring stopped")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
