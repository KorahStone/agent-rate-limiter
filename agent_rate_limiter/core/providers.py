"""Provider configuration and presets for common LLM APIs"""

from typing import Dict, Optional
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """Configuration for a specific model"""
    rpm: int = Field(description="Requests per minute")
    tpm: int = Field(description="Tokens per minute")
    cost_per_1k_input: float = Field(description="Cost per 1K input tokens")
    cost_per_1k_output: float = Field(description="Cost per 1K output tokens")


class ProviderConfig(BaseModel):
    """Configuration for an API provider"""
    name: str
    models: Dict[str, ModelConfig]
    api_key: Optional[str] = None
    base_url: Optional[str] = None


# Preset configurations for common providers
OPENAI_PRESET = ProviderConfig(
    name="openai",
    models={
        "gpt-4": ModelConfig(
            rpm=500,
            tpm=10000,
            cost_per_1k_input=0.03,
            cost_per_1k_output=0.06
        ),
        "gpt-4-turbo": ModelConfig(
            rpm=500,
            tpm=30000,
            cost_per_1k_input=0.01,
            cost_per_1k_output=0.03
        ),
        "gpt-3.5-turbo": ModelConfig(
            rpm=3500,
            tpm=60000,
            cost_per_1k_input=0.0005,
            cost_per_1k_output=0.0015
        ),
    }
)

ANTHROPIC_PRESET = ProviderConfig(
    name="anthropic",
    models={
        "claude-opus-4": ModelConfig(
            rpm=50,
            tpm=40000,
            cost_per_1k_input=0.015,
            cost_per_1k_output=0.075
        ),
        "claude-sonnet-4": ModelConfig(
            rpm=50,
            tpm=40000,
            cost_per_1k_input=0.003,
            cost_per_1k_output=0.015
        ),
        "claude-haiku-4": ModelConfig(
            rpm=50,
            tpm=50000,
            cost_per_1k_input=0.0008,
            cost_per_1k_output=0.004
        ),
    }
)

GOOGLE_PRESET = ProviderConfig(
    name="google",
    models={
        "gemini-2.0-pro": ModelConfig(
            rpm=360,
            tpm=120000,
            cost_per_1k_input=0.00125,
            cost_per_1k_output=0.005
        ),
        "gemini-1.5-flash": ModelConfig(
            rpm=1000,
            tpm=1000000,
            cost_per_1k_input=0.000075,
            cost_per_1k_output=0.0003
        ),
    }
)


class Provider:
    """Helper class for creating provider configs"""
    
    @staticmethod
    def openai(api_key: Optional[str] = None) -> ProviderConfig:
        config = OPENAI_PRESET.model_copy(deep=True)
        if api_key:
            config.api_key = api_key
        return config
    
    @staticmethod
    def anthropic(api_key: Optional[str] = None) -> ProviderConfig:
        config = ANTHROPIC_PRESET.model_copy(deep=True)
        if api_key:
            config.api_key = api_key
        return config
    
    @staticmethod
    def google(api_key: Optional[str] = None) -> ProviderConfig:
        config = GOOGLE_PRESET.model_copy(deep=True)
        if api_key:
            config.api_key = api_key
        return config
    
    @staticmethod
    def custom(
        name: str,
        models: Dict[str, ModelConfig],
        api_key: Optional[str] = None,
        base_url: Optional[str] = None
    ) -> ProviderConfig:
        return ProviderConfig(
            name=name,
            models=models,
            api_key=api_key,
            base_url=base_url
        )
