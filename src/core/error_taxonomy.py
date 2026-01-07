"""
Error Taxonomy for Agentic AI Workflows

Provides systematic classification of failure modes with:
- Error categories aligned to pipeline phases
- Recoverability indicators
- Suggested recovery actions
- Structured error context for debugging
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import logging
import traceback

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Systematic classification of failure modes."""
    # Phase 0: Query Understanding
    AMBIGUOUS_QUERY = auto()
    UNKNOWN_ENTITY = auto()
    MISSING_TIME_PERIOD = auto()
    CONFLICTING_FILTERS = auto()
    
    # Phase 1: Data Retrieval
    AUTHENTICATION_FAILED = auto()
    AUTHORIZATION_DENIED = auto()
    RATE_LIMITED = auto()
    DATA_SOURCE_UNAVAILABLE = auto()
    DATA_RETRIEVAL_TIMEOUT = auto()
    NO_MATCHING_DATA = auto()
    DATA_FORMAT_ERROR = auto()
    
    # Phase 2: Calculation
    CALCULATION_ERROR = auto()
    DIVISION_BY_ZERO = auto()
    INSUFFICIENT_DATA_POINTS = auto()
    INVALID_DATA_TYPE = auto()
    
    # Phase 3: Visualization
    CHART_GENERATION_FAILED = auto()
    INVALID_CHART_DATA = auto()
    FILE_SYSTEM_ERROR = auto()
    
    # Phase 4: Analysis Generation
    LLM_QUOTA_EXHAUSTED = auto()
    LLM_RATE_LIMITED = auto()
    LLM_CONTENT_BLOCKED = auto()
    LLM_CONTEXT_LENGTH_EXCEEDED = auto()
    LLM_RESPONSE_PARSE_ERROR = auto()
    LLM_TIMEOUT = auto()
    
    # Phase 5: Evaluation
    EVALUATION_FAILED = auto()
    JUDGE_MODEL_UNAVAILABLE = auto()
    
    # System Errors
    CONFIGURATION_ERROR = auto()
    INTERNAL_ERROR = auto()
    UNKNOWN_ERROR = auto()


class ErrorSeverity(Enum):
    """Severity levels for errors."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RecoveryAction:
    """Suggested action to recover from an error."""
    action_type: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    @staticmethod
    def retry(delay_seconds: float = 1.0, max_attempts: int = 3) -> "RecoveryAction":
        return RecoveryAction(
            action_type="retry",
            description=f"Retry after {delay_seconds}s (max {max_attempts} attempts)",
            parameters={"delay": delay_seconds, "max_attempts": max_attempts}
        )
    
    @staticmethod
    def fallback(fallback_method: str) -> "RecoveryAction":
        return RecoveryAction(
            action_type="fallback",
            description=f"Use fallback: {fallback_method}",
            parameters={"method": fallback_method}
        )
    
    @staticmethod
    def clarify(message: str) -> "RecoveryAction":
        return RecoveryAction(
            action_type="clarify",
            description="Request clarification from user",
            parameters={"message": message}
        )
    
    @staticmethod
    def abort(reason: str) -> "RecoveryAction":
        return RecoveryAction(
            action_type="abort",
            description=f"Abort operation: {reason}",
            parameters={"reason": reason}
        )


@dataclass
class ClassifiedError:
    """A classified error with full context."""
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    recoverable: bool
    recovery_actions: List[RecoveryAction]
    
    original_exception: Optional[Exception] = None
    pipeline_phase: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    stack_trace: Optional[str] = None
    user_message: Optional[str] = None
    
    def __post_init__(self):
        if self.original_exception and not self.stack_trace:
            self.stack_trace = ''.join(traceback.format_exception(
                type(self.original_exception),
                self.original_exception,
                self.original_exception.__traceback__
            ))
        
        if not self.user_message:
            self.user_message = self._generate_user_message()
    
    def _generate_user_message(self) -> str:
        """Generate a user-friendly error message."""
        messages = {
            ErrorCategory.AMBIGUOUS_QUERY: "I'm not sure what you're asking. Could you be more specific?",
            ErrorCategory.UNKNOWN_ENTITY: "I don't recognize one of the entities in your query.",
            ErrorCategory.RATE_LIMITED: "I'm being rate limited. Please try again in a moment.",
            ErrorCategory.NO_MATCHING_DATA: "No data found matching your criteria.",
            ErrorCategory.LLM_QUOTA_EXHAUSTED: "API quota exceeded. Please try again later.",
            ErrorCategory.AUTHENTICATION_FAILED: "Unable to authenticate with data source.",
            ErrorCategory.DATA_SOURCE_UNAVAILABLE: "Data source is temporarily unavailable.",
        }
        return messages.get(self.category, f"An error occurred: {self.message}")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.name,
            "severity": self.severity.value,
            "message": self.message,
            "user_message": self.user_message,
            "recoverable": self.recoverable,
            "recovery_actions": [
                {"type": a.action_type, "description": a.description}
                for a in self.recovery_actions
            ],
            "pipeline_phase": self.pipeline_phase,
            "context": self.context,
        }


class AgentError(Exception):
    """Base exception for agent errors with classification."""
    
    def __init__(
        self, 
        message: str, 
        category: ErrorCategory = ErrorCategory.UNKNOWN_ERROR,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        recoverable: bool = False,
        recovery_actions: List[RecoveryAction] = None,
        context: Dict[str, Any] = None,
    ):
        super().__init__(message)
        self.category = category
        self.severity = severity
        self.recoverable = recoverable
        self.recovery_actions = recovery_actions or []
        self.context = context or {}
    
    def classify(self) -> ClassifiedError:
        return ClassifiedError(
            category=self.category,
            severity=self.severity,
            message=str(self),
            recoverable=self.recoverable,
            recovery_actions=self.recovery_actions,
            original_exception=self,
            context=self.context,
        )


def classify_error(
    exception: Exception,
    pipeline_phase: str = None,
    context: Dict[str, Any] = None,
) -> ClassifiedError:
    """Classify an exception into a structured error."""
    context = context or {}
    
    if isinstance(exception, AgentError):
        classified = exception.classify()
        classified.pipeline_phase = pipeline_phase
        classified.context.update(context)
        return classified
    
    # Check for NetSuite request limit exceeded exception
    error_type_name = type(exception).__name__
    if error_type_name == "NetSuiteRequestLimitExceededError":
        return ClassifiedError(
            category=ErrorCategory.RATE_LIMITED,
            severity=ErrorSeverity.CRITICAL,
            message=str(exception),
            recoverable=False,
            recovery_actions=[
                RecoveryAction.abort(
                    "NetSuite API request limit exceeded. "
                    "Please wait before making more requests or reduce concurrent requests."
                )
            ],
            original_exception=exception,
            pipeline_phase=pipeline_phase,
            context=context,
        )
    
    error_str = str(exception).lower()
    
    # NetSuite request limit exceeded - check first before generic rate limit
    if "netsuite" in error_str and ("request limit exceeded" in error_str or "sss_request_limit_exceeded" in error_str):
        return ClassifiedError(
            category=ErrorCategory.RATE_LIMITED,
            severity=ErrorSeverity.CRITICAL,
            message=str(exception),
            recoverable=False,
            recovery_actions=[
                RecoveryAction.abort(
                    "NetSuite API request limit exceeded. "
                    "Please wait before making more requests or reduce concurrent requests."
                )
            ],
            original_exception=exception,
            pipeline_phase=pipeline_phase,
            context=context,
        )
    
    # Rate limiting
    if "rate limit" in error_str or "429" in error_str:
        if "quota" in error_str or "exhausted" in error_str:
            return ClassifiedError(
                category=ErrorCategory.LLM_QUOTA_EXHAUSTED,
                severity=ErrorSeverity.CRITICAL,
                message=str(exception),
                recoverable=False,
                recovery_actions=[RecoveryAction.abort("API quota exhausted")],
                original_exception=exception,
                pipeline_phase=pipeline_phase,
                context=context,
            )
        return ClassifiedError(
            category=ErrorCategory.LLM_RATE_LIMITED,
            severity=ErrorSeverity.MEDIUM,
            message=str(exception),
            recoverable=True,
            recovery_actions=[RecoveryAction.retry(delay_seconds=60)],
            original_exception=exception,
            pipeline_phase=pipeline_phase,
            context=context,
        )
    
    # Authentication
    if "auth" in error_str or "401" in error_str or "403" in error_str:
        return ClassifiedError(
            category=ErrorCategory.AUTHENTICATION_FAILED,
            severity=ErrorSeverity.HIGH,
            message=str(exception),
            recoverable=False,
            recovery_actions=[],
            original_exception=exception,
            pipeline_phase=pipeline_phase,
            context=context,
        )
    
    # Timeout
    if "timeout" in error_str:
        return ClassifiedError(
            category=ErrorCategory.DATA_RETRIEVAL_TIMEOUT,
            severity=ErrorSeverity.MEDIUM,
            message=str(exception),
            recoverable=True,
            recovery_actions=[RecoveryAction.retry(delay_seconds=5.0)],
            original_exception=exception,
            pipeline_phase=pipeline_phase,
            context=context,
        )
    
    # Default
    return ClassifiedError(
        category=ErrorCategory.UNKNOWN_ERROR,
        severity=ErrorSeverity.HIGH,
        message=str(exception),
        recoverable=False,
        recovery_actions=[],
        original_exception=exception,
        pipeline_phase=pipeline_phase,
        context=context,
    )

