"""
Model Router - The Framework's Most Critical Component

This module implements the Model-Agnostic Architecture pattern.
ALL LLM calls route through this interface - NEVER directly to provider APIs.

To swap models across the entire system: change ACTIVE_MODEL environment variable.
"""
import os
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Union
from enum import Enum

from config.settings import ModelConfig, ModelProvider, get_config

logger = logging.getLogger(__name__)

@dataclass
class Message:
    """Standardized message format across all providers."""
    role: str  # "system", "user", "assistant"
    content: str

@dataclass
class LLMResponse:
    """Standardized response format from any LLM provider."""
    content: str
    model: str
    provider: ModelProvider
    usage: Dict[str, int]  # tokens used
    raw_response: Any = None  # Original response for debugging
    
class BaseLLMClient(ABC):
    """Abstract base class for LLM provider clients."""
    
    def __init__(self, config: ModelConfig):
        self.config = config
    
    @abstractmethod
    def generate(
        self, 
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate a response from the LLM."""
        pass

class GeminiClient(BaseLLMClient):
    """Google Gemini API client."""
    
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        try:
            import google.generativeai as genai
            genai.configure(api_key=config.api_key)
            self.genai = genai
            self.model = genai.GenerativeModel(config.model_name)
        except ImportError:
            raise ImportError("Install google-generativeai: pip install google-generativeai")
    
    def generate(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens if max_tokens is not None else self.config.max_tokens
        
        # Convert to Gemini format
        system_instruction = None
        chat_messages = []
        
        for msg in messages:
            if msg.role == "system":
                system_instruction = msg.content
            elif msg.role == "user":
                chat_messages.append({"role": "user", "parts": [msg.content]})
            elif msg.role == "assistant":
                chat_messages.append({"role": "model", "parts": [msg.content]})
        
        # Create model with system instruction if provided
        if system_instruction:
            model = self.genai.GenerativeModel(
                self.config.model_name,
                system_instruction=system_instruction
            )
        else:
            model = self.model
        
        generation_config = self.genai.GenerationConfig(
            temperature=temp,
            max_output_tokens=tokens,
        )
        
        # Start chat and send messages
        if len(chat_messages) > 1:
            chat = model.start_chat(history=chat_messages[:-1])
            response = chat.send_message(
                chat_messages[-1]["parts"][0],
                generation_config=generation_config
            )
        else:
            response = model.generate_content(
                chat_messages[0]["parts"][0] if chat_messages else "",
                generation_config=generation_config
            )
        
        return LLMResponse(
            content=response.text,
            model=self.config.model_name,
            provider=ModelProvider.GEMINI,
            usage={
                "prompt_tokens": response.usage_metadata.prompt_token_count if hasattr(response, 'usage_metadata') else 0,
                "completion_tokens": response.usage_metadata.candidates_token_count if hasattr(response, 'usage_metadata') else 0,
            },
            raw_response=response
        )

class ClaudeClient(BaseLLMClient):
    """Anthropic Claude API client."""
    
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=config.api_key)
        except ImportError:
            raise ImportError("Install anthropic: pip install anthropic")
    
    def generate(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens if max_tokens is not None else self.config.max_tokens
        
        # Extract system message
        system = None
        api_messages = []
        
        for msg in messages:
            if msg.role == "system":
                system = msg.content
            else:
                api_messages.append({"role": msg.role, "content": msg.content})
        
        kwargs = {
            "model": self.config.model_name,
            "max_tokens": tokens,
            "temperature": temp,
            "messages": api_messages,
        }
        if system:
            kwargs["system"] = system
        
        response = self.client.messages.create(**kwargs)
        
        return LLMResponse(
            content=response.content[0].text,
            model=self.config.model_name,
            provider=ModelProvider.CLAUDE,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            },
            raw_response=response
        )

class OpenAIClient(BaseLLMClient):
    """OpenAI GPT API client."""
    
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=config.api_key)
        except ImportError:
            raise ImportError("Install openai: pip install openai")
    
    def generate(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens if max_tokens is not None else self.config.max_tokens
        
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        
        response = self.client.chat.completions.create(
            model=self.config.model_name,
            messages=api_messages,
            temperature=temp,
            max_tokens=tokens,
        )
        
        return LLMResponse(
            content=response.choices[0].message.content,
            model=self.config.model_name,
            provider=ModelProvider.OPENAI,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            },
            raw_response=response
        )

class ModelRouter:
    """
    Central routing hub for all LLM requests.
    
    This is the ONLY class that should be instantiated for LLM access.
    All agent logic uses this router, never direct provider clients.
    """
    
    _client_cache: Dict[str, BaseLLMClient] = {}
    
    def __init__(self, config: Optional[ModelConfig] = None):
        """Initialize with optional explicit config, otherwise use ACTIVE_MODEL."""
        if config is None:
            app_config = get_config()
            config = app_config.model_config
        self.config = config
        self._client = self._get_or_create_client(config)
    
    def _get_or_create_client(self, config: ModelConfig) -> BaseLLMClient:
        """Get cached client or create new one."""
        cache_key = f"{config.provider.value}:{config.model_name}"
        
        if cache_key not in self._client_cache:
            if config.provider == ModelProvider.GEMINI:
                self._client_cache[cache_key] = GeminiClient(config)
            elif config.provider == ModelProvider.CLAUDE:
                self._client_cache[cache_key] = ClaudeClient(config)
            elif config.provider == ModelProvider.OPENAI:
                self._client_cache[cache_key] = OpenAIClient(config)
            else:
                raise ValueError(f"Unsupported provider: {config.provider}")
        
        return self._client_cache[cache_key]
    
    def generate(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Route generation request to the active model."""
        logger.info(f"Routing request to {self.config.provider.value}:{self.config.model_name}")
        return self._client.generate(messages, temperature, max_tokens)
    
    def generate_with_system(
        self,
        system_prompt: str,
        user_message: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Convenience method for simple system + user message patterns."""
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_message),
        ]
        return self.generate(messages, temperature, max_tokens)

def get_router(model_name: Optional[str] = None) -> ModelRouter:
    """Factory function to get a model router.
    
    Args:
        model_name: Optional explicit model name. If None, uses ACTIVE_MODEL env var.
    
    Returns:
        ModelRouter configured for the specified or active model.
    """
    if model_name:
        from config.settings import MODEL_REGISTRY
        if model_name not in MODEL_REGISTRY:
            raise ValueError(f"Unknown model: {model_name}")
        config = MODEL_REGISTRY[model_name]
    else:
        config = None  # Will use ACTIVE_MODEL
    
    return ModelRouter(config)

def get_judge_router() -> ModelRouter:
    """Get a router configured for the judge model (cross-model evaluation)."""
    app_config = get_config()
    return ModelRouter(app_config.judge_model_config)
