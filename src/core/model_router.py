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
from src.core.observability import get_tracer, SpanKind
import time

logger = logging.getLogger(__name__)

# Custom exception classes for LLM errors
class LLMError(Exception):
    """Base exception for LLM-related errors."""
    pass

class LLMQuotaExhaustedError(LLMError):
    """Raised when API quota/credits are exhausted."""
    pass

class LLMContentBlockedError(LLMError):
    """Raised when content is blocked by the API."""
    pass

class LLMAPIError(LLMError):
    """Raised for general API errors."""
    pass

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
        """Generate a response from Gemini with comprehensive error handling."""
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
        
        try:
            # Make the API call
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
            
            # Check for empty or blocked response
            if not response.candidates:
                block_reason = getattr(response, 'prompt_feedback', None)
                if block_reason:
                    logger.error(f"Gemini blocked prompt: {block_reason}")
                    raise LLMContentBlockedError(f"Content blocked by Gemini: {block_reason}")
                raise LLMAPIError("Gemini returned empty response with no candidates")
            
            # Check candidate finish reason
            candidate = response.candidates[0]
            finish_reason = getattr(candidate, 'finish_reason', None)
            
            # Handle blocked or problematic finish reasons
            if finish_reason and str(finish_reason) not in ['STOP', 'MAX_TOKENS', '1', '2']:
                logger.warning(f"Gemini finish reason: {finish_reason}")
                if 'SAFETY' in str(finish_reason) or 'BLOCKED' in str(finish_reason):
                    raise LLMContentBlockedError(f"Content blocked: {finish_reason}")
            
            # Extract text safely
            try:
                content = response.text
            except ValueError as e:
                # response.text raises ValueError if no valid text
                logger.error(f"Failed to extract text from Gemini response: {e}")
                raise LLMAPIError(f"No valid text in response: {e}") from e
            
            return LLMResponse(
                content=content,
                model=self.config.model_name,
                provider=ModelProvider.GEMINI,
                usage={
                    "prompt_tokens": response.usage_metadata.prompt_token_count if hasattr(response, 'usage_metadata') and response.usage_metadata else 0,
                    "completion_tokens": response.usage_metadata.candidates_token_count if hasattr(response, 'usage_metadata') and response.usage_metadata else 0,
                },
                raw_response=response
            )
        
        except LLMError:
            # Re-raise our custom exceptions as-is
            raise
        
        except Exception as e:
            error_str = str(e).lower()
            error_type = type(e).__name__
            
            # Check for quota/billing errors
            if any(term in error_str for term in [
                'resourceexhausted', 'quota', '429', 'rate limit', 
                'billing', 'payment', 'insufficient'
            ]):
                logger.error(f"Gemini API quota exhausted: {e}")
                raise LLMQuotaExhaustedError(
                    f"Gemini API quota exhausted or billing issue. "
                    f"Check your quota at https://console.cloud.google.com/apis/api/generativelanguage.googleapis.com/quotas "
                    f"or billing at https://console.cloud.google.com/billing. "
                    f"Original error: {e}"
                ) from e
            
            # Check for authentication errors
            if any(term in error_str for term in [
                'authentication', 'unauthorized', '401', 'invalid api key', 'permission'
            ]):
                logger.error(f"Gemini API authentication failed: {e}")
                raise LLMAPIError(
                    f"Gemini API authentication failed. Check your GEMINI_API_KEY. "
                    f"Original error: {e}"
                ) from e
            
            # Check for blocked content
            if any(term in error_str for term in [
                'blocked', 'safety', 'harmful', 'prohibited'
            ]):
                logger.error(f"Gemini blocked content: {e}")
                raise LLMContentBlockedError(f"Content blocked by Gemini: {e}") from e
            
            # Check for network/timeout errors
            if any(term in error_str for term in [
                'timeout', 'connection', 'network', 'unreachable'
            ]):
                logger.error(f"Gemini API network error: {e}")
                raise LLMAPIError(f"Network error calling Gemini API: {e}") from e
            
            # Generic API error
            logger.error(f"Gemini API error ({error_type}): {e}")
            raise LLMAPIError(f"Gemini API call failed ({error_type}): {e}") from e

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
        """Generate a response from Claude with comprehensive error handling."""
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
        
        try:
            response = self.client.messages.create(**kwargs)
            
            # Check for empty response
            if not response.content:
                raise LLMAPIError("Claude returned empty response")
            
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
        
        except LLMError:
            raise
        
        except Exception as e:
            error_str = str(e).lower()
            error_type = type(e).__name__
            
            # Check for quota/billing errors
            if any(term in error_str for term in [
                'rate_limit', 'quota', '429', 'billing', 'credit', 'insufficient'
            ]):
                logger.error(f"Claude API quota exhausted: {e}")
                raise LLMQuotaExhaustedError(
                    f"Claude API quota exhausted or billing issue. "
                    f"Check your usage at https://console.anthropic.com/settings/usage. "
                    f"Original error: {e}"
                ) from e
            
            # Check for authentication errors
            if any(term in error_str for term in [
                'authentication', 'unauthorized', '401', 'invalid api key'
            ]):
                logger.error(f"Claude API authentication failed: {e}")
                raise LLMAPIError(
                    f"Claude API authentication failed. Check your ANTHROPIC_API_KEY. "
                    f"Original error: {e}"
                ) from e
            
            # Generic error
            logger.error(f"Claude API error ({error_type}): {e}")
            raise LLMAPIError(f"Claude API call failed ({error_type}): {e}") from e

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
        """Generate a response from OpenAI with comprehensive error handling."""
        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens if max_tokens is not None else self.config.max_tokens
        
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        
        try:
            response = self.client.chat.completions.create(
                model=self.config.model_name,
                messages=api_messages,
                temperature=temp,
                max_tokens=tokens,
            )
            
            # Check for empty response
            if not response.choices:
                raise LLMAPIError("OpenAI returned empty response")
            
            content = response.choices[0].message.content
            if content is None:
                raise LLMAPIError("OpenAI returned null content")
            
            return LLMResponse(
                content=content,
                model=self.config.model_name,
                provider=ModelProvider.OPENAI,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                },
                raw_response=response
            )
        
        except LLMError:
            raise
        
        except Exception as e:
            error_str = str(e).lower()
            error_type = type(e).__name__
            
            # Check for quota/billing errors
            if any(term in error_str for term in [
                'rate_limit', 'quota', '429', 'billing', 'insufficient_quota'
            ]):
                logger.error(f"OpenAI API quota exhausted: {e}")
                raise LLMQuotaExhaustedError(
                    f"OpenAI API quota exhausted or billing issue. "
                    f"Check your usage at https://platform.openai.com/usage. "
                    f"Original error: {e}"
                ) from e
            
            # Check for authentication errors
            if any(term in error_str for term in [
                'authentication', 'unauthorized', '401', 'invalid api key'
            ]):
                logger.error(f"OpenAI API authentication failed: {e}")
                raise LLMAPIError(
                    f"OpenAI API authentication failed. Check your OPENAI_API_KEY. "
                    f"Original error: {e}"
                ) from e
            
            # Check for content policy
            if any(term in error_str for term in ['content_policy', 'flagged', 'moderation']):
                logger.error(f"OpenAI content policy violation: {e}")
                raise LLMContentBlockedError(f"Content blocked by OpenAI: {e}") from e
            
            # Generic error
            logger.error(f"OpenAI API error ({error_type}): {e}")
            raise LLMAPIError(f"OpenAI API call failed ({error_type}): {e}") from e

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
        """Route generation request to the active model with observability tracking."""
        tracer = get_tracer()
        start_time = time.time()
        
        logger.info(f"Routing request to {self.config.provider.value}:{self.config.model_name}")
        
        with tracer.start_span(f"llm_generate_{self.config.model_name}", SpanKind.LLM_CALL) as span:
            try:
                response = self._client.generate(messages, temperature, max_tokens)
                
                latency_ms = (time.time() - start_time) * 1000
                
                if span:
                    tracer.record_llm_usage(
                        span=span,
                        model=self.config.model_name,
                        provider=self.config.provider.value,
                        input_tokens=response.usage.get("input_tokens", 0),
                        output_tokens=response.usage.get("output_tokens", 0),
                        latency_ms=latency_ms,
                    )
                    span.attributes["temperature"] = temperature or self.config.temperature
                    span.attributes["max_tokens"] = max_tokens or self.config.max_tokens
                
                return response
            except LLMQuotaExhaustedError as e:
                if span:
                    span.set_error(e)
                logger.error(f"LLM quota exhausted: {e}")
                raise
            except LLMContentBlockedError as e:
                if span:
                    span.set_error(e)
                logger.warning(f"LLM content blocked: {e}")
                raise
            except LLMAPIError as e:
                if span:
                    span.set_error(e)
                logger.error(f"LLM API error: {e}")
                raise
            except Exception as e:
                if span:
                    span.set_error(e)
                logger.error(f"Unexpected error in model router: {e}")
                raise LLMAPIError(f"Unexpected error: {e}") from e
    
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

# Export custom exceptions for use by other modules
__all__ = [
    'Message',
    'LLMResponse',
    'ModelRouter',
    'get_router',
    'get_judge_router',
    'LLMError',
    'LLMQuotaExhaustedError',
    'LLMContentBlockedError',
    'LLMAPIError',
]
