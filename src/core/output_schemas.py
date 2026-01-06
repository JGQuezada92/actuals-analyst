"""
Structured Output Schemas for LLM Responses

Provides Pydantic models for validating LLM outputs to prevent
silent failures from malformed responses.
"""

try:
    from pydantic import BaseModel, Field, validator
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    # Create dummy BaseModel for when pydantic is not available
    class BaseModel:
        pass
    def Field(*args, **kwargs):
        return None
    def validator(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

from typing import List, Optional, Dict, Any, Tuple, Type
import json
import logging

logger = logging.getLogger(__name__)


if HAS_PYDANTIC:
    class EvaluationScoreDetail(BaseModel):
        """Individual evaluation dimension score."""
        score: float = Field(..., ge=0, le=10)
        rationale: str = Field(..., min_length=5)
    
    
    class EvaluationResponseSchema(BaseModel):
        """Schema for LLM-as-Judge evaluation output."""
        scores: Dict[str, EvaluationScoreDetail]
        overall_assessment: str = Field(..., min_length=10, max_length=1000)
        improvement_suggestions: List[str] = Field(default_factory=list)
        
        @validator('scores')
        def validate_required_dimensions(cls, v):
            required = {'numerical_accuracy', 'claim_substantiation', 'completeness', 
                       'insight_quality', 'actionability', 'clarity'}
            missing = required - set(v.keys())
            if missing:
                raise ValueError(f"Missing required dimensions: {missing}")
            return v
    
    
    class ReflectionResponseSchema(BaseModel):
        """Schema for self-reflection output."""
        self_score: float = Field(..., ge=0, le=10)
        should_revise: bool
        revised_analysis: Optional[str] = None
        reasoning: str = Field(..., min_length=10)
        
        @validator('revised_analysis')
        def validate_revision_present(cls, v, values):
            if values.get('should_revise') and not v:
                raise ValueError("revised_analysis required when should_revise is True")
            return v
    
    
    class ParsedQuerySchema(BaseModel):
        """Schema for query parser LLM fallback output."""
        intent: str = Field(..., pattern="^(summary|total|trend|comparison|variance|breakdown|top_n|detail|ratio|correlation|regression|volatility)$")
        departments: List[str] = Field(default_factory=list)
        accounts: List[str] = Field(default_factory=list)
        time_period: Optional[str] = None
        comparison_type: Optional[str] = None
        group_by: Optional[str] = None
        top_n: Optional[int] = Field(None, ge=1, le=100)
else:
    # Dummy classes when pydantic is not available
    class EvaluationScoreDetail:
        pass
    
    class EvaluationResponseSchema:
        pass
    
    class ReflectionResponseSchema:
        pass
    
    class ParsedQuerySchema:
        pass


def validate_llm_output(
    raw_output: str, 
    schema: Type[BaseModel]
) -> Tuple[bool, Any, List[str]]:
    """
    Validate LLM output against a Pydantic schema.
    
    Returns:
        Tuple of (is_valid, parsed_object_or_none, list_of_errors)
    """
    if not HAS_PYDANTIC:
        logger.warning("Pydantic not available - skipping validation")
        return True, None, []
    
    errors = []
    
    # Clean the output
    cleaned = raw_output.strip()
    
    # Remove markdown code blocks if present
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    
    # Try to parse JSON
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON: {str(e)}")
        logger.warning(f"Failed to parse LLM output as JSON: {e}")
        return False, None, errors
    
    # Validate against schema
    try:
        validated = schema(**data)
        return True, validated, []
    except Exception as e:
        errors.append(f"Schema validation failed: {str(e)}")
        logger.warning(f"Schema validation failed: {e}")
        return False, None, errors


def safe_parse_evaluation(raw_output: str) -> Tuple[Optional[EvaluationResponseSchema], List[str]]:
    """Safely parse evaluation response with fallback."""
    if not HAS_PYDANTIC:
        return None, ["Pydantic not available"]
    is_valid, parsed, errors = validate_llm_output(raw_output, EvaluationResponseSchema)
    return parsed if is_valid else None, errors


def safe_parse_reflection(raw_output: str) -> Tuple[Optional[ReflectionResponseSchema], List[str]]:
    """Safely parse reflection response with fallback."""
    if not HAS_PYDANTIC:
        return None, ["Pydantic not available"]
    is_valid, parsed, errors = validate_llm_output(raw_output, ReflectionResponseSchema)
    return parsed if is_valid else None, errors

