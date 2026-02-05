"""
Basic usage example for agent-rate-limiter

This example shows how to use the library to rate-limit and track costs
for OpenAI API calls.
"""

from agent_rate_limiter import MultiProviderLimiter, Provider


def main():
    # Initialize limiter with OpenAI provider
    limiter = MultiProviderLimiter(
        providers=[Provider.openai()],
        daily_budget=10.00,  # $10/day limit
        alert_threshold=0.8,  # Alert at 80% usage
        on_budget_alert=lambda period, current, limit: 
            print(f"⚠️ Budget alert: {period} spending is ${current:.2f} / ${limit:.2f}"),
        on_limit_hit=lambda provider, model:
            print(f"⏱️ Rate limit hit for {provider}/{model}, waiting...")
    )
    
    # Define a function that makes API calls
    @limiter.limit(provider="openai", model="gpt-3.5-turbo", estimated_tokens=100)
    def generate_text(prompt: str) -> str:
        """Simulated API call (replace with actual OpenAI call)"""
        # In real usage:
        # import openai
        # response = openai.chat.completions.create(
        #     model="gpt-3.5-turbo",
        #     messages=[{"role": "user", "content": prompt}]
        # )
        # return response.choices[0].message.content
        
        return f"Response to: {prompt}"
    
    # Make some calls - rate limiting happens automatically
    print("Making API calls...")
    
    for i in range(5):
        response = generate_text(f"Hello, this is request {i+1}")
        print(f"{i+1}. {response}")
    
    # Check metrics
    print("\n📊 Metrics:")
    metrics = limiter.get_metrics()
    
    print(f"Total cost: ${metrics['costs']['total']:.4f}")
    print(f"Daily cost: ${metrics['costs']['daily']:.4f}")
    
    for provider, models in metrics['limiters'].items():
        for model, stats in models.items():
            print(f"\n{provider}/{model}:")
            print(f"  Total requests: {stats['total_requests']}")
            print(f"  Total tokens: {stats['total_tokens']}")
            print(f"  Failed requests: {stats['failed_requests']}")


if __name__ == "__main__":
    main()
