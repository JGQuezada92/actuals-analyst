"""
Configuration settings for the NetSuite Financial Analyst Agent.
Follows the Model-Agnostic Architecture pattern from the Accuracy-First Framework.

Key Design Principle: All model selection via environment variables, never hardcoded.
"""
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum

class ModelProvider(Enum):
    GEMINI = "gemini"
    CLAUDE = "claude"
    OPENAI = "openai"

@dataclass
class ModelConfig:
    """Configuration for a specific LLM provider."""
    provider: ModelProvider
    model_name: str
    api_key_env: str
    temperature: float = 0.1  # Low temperature for accuracy
    max_tokens: int = 4096
    
    @property
    def api_key(self) -> str:
        key = os.getenv(self.api_key_env)
        if not key:
            raise ValueError(f"Missing API key: {self.api_key_env}")
        return key

# Model Registry - Add new models here
MODEL_REGISTRY: Dict[str, ModelConfig] = {
    "gemini-2.0-flash": ModelConfig(
        provider=ModelProvider.GEMINI,
        model_name="gemini-2.0-flash",
        api_key_env="GEMINI_API_KEY",
    ),
    "gemini-1.5-pro": ModelConfig(
        provider=ModelProvider.GEMINI,
        model_name="gemini-1.5-pro",
        api_key_env="GEMINI_API_KEY",
    ),
    "claude-sonnet-4": ModelConfig(
        provider=ModelProvider.CLAUDE,
        model_name="claude-sonnet-4-20250514",
        api_key_env="ANTHROPIC_API_KEY",
    ),
    "gpt-4o": ModelConfig(
        provider=ModelProvider.OPENAI,
        model_name="gpt-4o",
        api_key_env="OPENAI_API_KEY",
    ),
}

# Cross-model evaluation mapping (generate with X, judge with Y)
# Note: Using same model for evaluation when only one API key is available
JUDGE_MODEL_MAP = {
    ModelProvider.GEMINI: "gemini-2.0-flash",
    ModelProvider.CLAUDE: "gemini-2.0-flash",
    ModelProvider.OPENAI: "gemini-2.0-flash",
}

@dataclass
class NetSuiteConfig:
    """NetSuite API configuration."""
    account_id: str = field(default_factory=lambda: os.getenv("NETSUITE_ACCOUNT_ID", ""))
    consumer_key: str = field(default_factory=lambda: os.getenv("NETSUITE_CONSUMER_KEY", ""))
    consumer_secret: str = field(default_factory=lambda: os.getenv("NETSUITE_CONSUMER_SECRET", ""))
    token_id: str = field(default_factory=lambda: os.getenv("NETSUITE_TOKEN_ID", ""))
    token_secret: str = field(default_factory=lambda: os.getenv("NETSUITE_TOKEN_SECRET", ""))
    saved_search_id: str = field(default_factory=lambda: os.getenv("NETSUITE_SAVED_SEARCH_ID", ""))
    restlet_url: str = field(default_factory=lambda: os.getenv("NETSUITE_RESTLET_URL", ""))
    
    # OneLogin SSO Configuration
    onelogin_client_id: str = field(default_factory=lambda: os.getenv("ONELOGIN_CLIENT_ID", ""))
    onelogin_client_secret: str = field(default_factory=lambda: os.getenv("ONELOGIN_CLIENT_SECRET", ""))
    onelogin_subdomain: str = field(default_factory=lambda: os.getenv("ONELOGIN_SUBDOMAIN", ""))

@dataclass
class SlackConfig:
    """Slack Bot configuration."""
    bot_token: str = field(default_factory=lambda: os.getenv("SLACK_BOT_TOKEN", ""))
    signing_secret: str = field(default_factory=lambda: os.getenv("SLACK_SIGNING_SECRET", ""))
    app_token: str = field(default_factory=lambda: os.getenv("SLACK_APP_TOKEN", ""))

@dataclass
class FiscalConfig:
    """Fiscal calendar configuration."""
    # Fiscal year start month (1-12). February = 2.
    # FY2025 with month=2 means Feb 1, 2025 - Jan 31, 2026
    fiscal_year_start_month: int = field(
        default_factory=lambda: int(os.getenv("FISCAL_YEAR_START_MONTH", "2"))
    )

@dataclass 
class EvaluationConfig:
    """Evaluation and accuracy thresholds."""
    # Objective metrics
    numerical_tolerance: float = 0.01  # 1% tolerance for calculated values
    minimum_accuracy_score: float = 0.85  # 85% accuracy required
    
    # Qualitative metrics
    minimum_judge_score: float = 7.0  # Out of 10
    
    # Reflection settings
    max_reflection_iterations: int = 3
    reflection_improvement_threshold: float = 0.5  # Points improvement to continue

@dataclass
class AppConfig:
    """Main application configuration."""
    # Model selection - THE SINGLE POINT OF CONTROL
    active_model: str = field(
        default_factory=lambda: os.getenv("ACTIVE_MODEL", "gemini-2.0-flash")
    )
    
    # Sub-configurations
    netsuite: NetSuiteConfig = field(default_factory=NetSuiteConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    fiscal: FiscalConfig = field(default_factory=FiscalConfig)
    
    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    
    @property
    def model_config(self) -> ModelConfig:
        """Get the active model configuration."""
        if self.active_model not in MODEL_REGISTRY:
            raise ValueError(f"Unknown model: {self.active_model}. Available: {list(MODEL_REGISTRY.keys())}")
        return MODEL_REGISTRY[self.active_model]
    
    @property
    def judge_model_config(self) -> ModelConfig:
        """Get the judge model (different from generation model for unbiased evaluation)."""
        provider = self.model_config.provider
        judge_model_name = JUDGE_MODEL_MAP[provider]
        return MODEL_REGISTRY[judge_model_name]

def get_config() -> AppConfig:
    """Factory function to get application configuration."""
    return AppConfig()
