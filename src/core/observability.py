"""
Observability Infrastructure for Agentic AI Workflows

Provides end-to-end tracing, cost tracking, and metrics collection
following OpenTelemetry semantic conventions for LLM applications.

Key Capabilities:
- Trace: Complete execution path for a single query
- Span: Individual operation within a trace (phase, LLM call, tool use)
- Metrics: Token usage, latency, cost estimation, evaluation scores
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from contextlib import contextmanager
from enum import Enum
import time
import json
import logging
import os
from pathlib import Path
import hashlib

logger = logging.getLogger(__name__)


class SpanKind(Enum):
    """Types of spans for categorization."""
    PIPELINE_PHASE = "pipeline_phase"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    DATA_RETRIEVAL = "data_retrieval"
    CALCULATION = "calculation"
    EVALUATION = "evaluation"


class SpanStatus(Enum):
    """Outcome status of a span."""
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class LLMUsage:
    """Token usage tracking for a single LLM call."""
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    latency_ms: float


@dataclass
class Span:
    """Individual operation in a trace."""
    span_id: str
    name: str
    kind: SpanKind
    start_time: datetime
    end_time: Optional[datetime] = None
    status: SpanStatus = SpanStatus.OK
    parent_span_id: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    llm_usage: Optional[LLMUsage] = None
    error_message: Optional[str] = None
    
    @property
    def duration_ms(self) -> float:
        """Calculate span duration in milliseconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return 0
    
    def add_event(self, name: str, attributes: Dict[str, Any] = None):
        """Add a timestamped event to the span."""
        self.events.append({
            "name": name,
            "timestamp": datetime.utcnow().isoformat(),
            "attributes": attributes or {}
        })
    
    def set_error(self, error: Exception):
        """Mark span as errored."""
        self.status = SpanStatus.ERROR
        self.error_message = f"{type(error).__name__}: {str(error)}"
        self.add_event("exception", {
            "type": type(error).__name__,
            "message": str(error)
        })
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize span for export."""
        result = {
            "span_id": self.span_id,
            "name": self.name,
            "kind": self.kind.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "parent_span_id": self.parent_span_id,
            "attributes": self.attributes,
            "events": self.events,
            "error_message": self.error_message,
        }
        
        if self.llm_usage:
            result["llm_usage"] = {
                "model": self.llm_usage.model,
                "provider": self.llm_usage.provider,
                "input_tokens": self.llm_usage.input_tokens,
                "output_tokens": self.llm_usage.output_tokens,
                "total_tokens": self.llm_usage.total_tokens,
                "estimated_cost_usd": self.llm_usage.estimated_cost_usd,
                "latency_ms": self.llm_usage.latency_ms,
            }
        else:
            result["llm_usage"] = None
            
        return result


@dataclass
class Trace:
    """Complete execution trace for a query."""
    trace_id: str
    query: str
    start_time: datetime
    end_time: Optional[datetime] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    channel: Optional[str] = None  # "slack", "cli", "api"
    
    spans: List[Span] = field(default_factory=list)
    
    # Aggregated metrics
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_llm_calls: int = 0
    estimated_cost_usd: float = 0.0
    
    # Quality metrics
    evaluation_score: Optional[float] = None
    passed_evaluation: Optional[bool] = None
    
    # Outcome
    status: SpanStatus = SpanStatus.OK
    error_message: Optional[str] = None
    
    @property
    def duration_ms(self) -> float:
        """Total trace duration in milliseconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return 0
    
    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens
    
    def add_llm_usage(self, usage: LLMUsage):
        """Aggregate LLM usage from a span."""
        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens
        self.total_llm_calls += 1
        self.estimated_cost_usd += usage.estimated_cost_usd
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize trace for export."""
        return {
            "trace_id": self.trace_id,
            "query": self.query,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "channel": self.channel,
            "status": self.status.value,
            "error_message": self.error_message,
            "metrics": {
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "total_tokens": self.total_tokens,
                "total_llm_calls": self.total_llm_calls,
                "estimated_cost_usd": self.estimated_cost_usd,
                "evaluation_score": self.evaluation_score,
                "passed_evaluation": self.passed_evaluation,
            },
            "spans": [s.to_dict() for s in self.spans],
        }


# Cost estimation per 1M tokens (update as pricing changes)
LLM_COST_PER_1M_TOKENS = {
    "gemini-2.0-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "claude-sonnet-4": {"input": 3.00, "output": 15.00},
    "claude-haiku-3": {"input": 0.25, "output": 1.25},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for token usage."""
    # Normalize model name for lookup
    model_key = model.lower()
    for key in LLM_COST_PER_1M_TOKENS:
        if key in model_key:
            rates = LLM_COST_PER_1M_TOKENS[key]
            return (
                (input_tokens / 1_000_000) * rates["input"] +
                (output_tokens / 1_000_000) * rates["output"]
            )
    # Default fallback
    return (input_tokens + output_tokens) / 1_000_000 * 1.0


class Tracer:
    """
    Global tracer for managing traces and spans.
    
    Usage:
        tracer = get_tracer()
        
        with tracer.start_trace("user query", user_id="123") as trace:
            with tracer.start_span("phase_1_parsing", SpanKind.PIPELINE_PHASE) as span:
                # do parsing
                span.attributes["parsed_intent"] = "total"
            
            with tracer.start_span("llm_call", SpanKind.LLM_CALL) as span:
                response = llm.generate(...)
                tracer.record_llm_usage(span, model, input_tokens, output_tokens, latency)
    """
    
    def __init__(self, export_dir: Optional[Path] = None):
        self.export_dir = export_dir or Path("traces")
        self.export_dir.mkdir(parents=True, exist_ok=True)
        
        self._current_trace: Optional[Trace] = None
        self._span_stack: List[Span] = []
        self._span_counter: int = 0
    
    def _generate_trace_id(self, query: str) -> str:
        """Generate unique trace ID."""
        timestamp = int(time.time() * 1000)
        query_hash = hashlib.md5(query.encode()).hexdigest()[:8]
        return f"trace_{timestamp}_{query_hash}"
    
    def _generate_span_id(self) -> str:
        """Generate unique span ID."""
        self._span_counter += 1
        return f"span_{int(time.time() * 1000)}_{self._span_counter}"
    
    @contextmanager
    def start_trace(
        self, 
        query: str, 
        user_id: str = None, 
        session_id: str = None,
        channel: str = None,
    ):
        """Start a new trace for a query."""
        self._current_trace = Trace(
            trace_id=self._generate_trace_id(query),
            query=query,
            start_time=datetime.utcnow(),
            user_id=user_id,
            session_id=session_id,
            channel=channel,
        )
        self._span_stack = []
        self._span_counter = 0
        
        logger.info(f"Started trace {self._current_trace.trace_id} for query: {query[:50]}...")
        
        try:
            yield self._current_trace
            self._current_trace.status = SpanStatus.OK
        except Exception as e:
            self._current_trace.status = SpanStatus.ERROR
            self._current_trace.error_message = f"{type(e).__name__}: {str(e)}"
            raise
        finally:
            self._current_trace.end_time = datetime.utcnow()
            self._export_trace(self._current_trace)
            logger.info(
                f"Completed trace {self._current_trace.trace_id} "
                f"in {self._current_trace.duration_ms:.0f}ms, "
                f"cost=${self._current_trace.estimated_cost_usd:.4f}, "
                f"tokens={self._current_trace.total_tokens}"
            )
            self._current_trace = None
    
    @contextmanager
    def start_span(
        self, 
        name: str, 
        kind: SpanKind,
        attributes: Dict[str, Any] = None,
    ):
        """Start a new span within the current trace."""
        if not self._current_trace:
            # No active trace - create a dummy context
            yield None
            return
        
        span = Span(
            span_id=self._generate_span_id(),
            name=name,
            kind=kind,
            start_time=datetime.utcnow(),
            parent_span_id=self._span_stack[-1].span_id if self._span_stack else None,
            attributes=attributes or {},
        )
        
        self._span_stack.append(span)
        self._current_trace.spans.append(span)
        
        try:
            yield span
            span.status = SpanStatus.OK
        except Exception as e:
            span.set_error(e)
            raise
        finally:
            span.end_time = datetime.utcnow()
            self._span_stack.pop()
            
            logger.debug(
                f"Span {name} completed in {span.duration_ms:.0f}ms"
                + (f" (error: {span.error_message})" if span.error_message else "")
            )
    
    def record_llm_usage(
        self,
        span: Span,
        model: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
    ):
        """Record LLM usage on a span and aggregate to trace."""
        if not span:
            return
        
        cost = estimate_cost(model, input_tokens, output_tokens)
        
        usage = LLMUsage(
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            estimated_cost_usd=cost,
            latency_ms=latency_ms,
        )
        
        span.llm_usage = usage
        
        if self._current_trace:
            self._current_trace.add_llm_usage(usage)
    
    def record_evaluation(self, score: float, passed: bool):
        """Record evaluation results on current trace."""
        if self._current_trace:
            self._current_trace.evaluation_score = score
            self._current_trace.passed_evaluation = passed
    
    def add_span_attribute(self, key: str, value: Any):
        """Add attribute to current span."""
        if self._span_stack:
            self._span_stack[-1].attributes[key] = value
    
    def add_span_event(self, name: str, attributes: Dict[str, Any] = None):
        """Add event to current span."""
        if self._span_stack:
            self._span_stack[-1].add_event(name, attributes)
    
    @property
    def current_trace(self) -> Optional[Trace]:
        return self._current_trace
    
    @property
    def current_span(self) -> Optional[Span]:
        return self._span_stack[-1] if self._span_stack else None
    
    def _export_trace(self, trace: Trace):
        """Export trace to JSON file."""
        filename = f"{trace.trace_id}.json"
        filepath = self.export_dir / filename
        
        try:
            with open(filepath, 'w') as f:
                json.dump(trace.to_dict(), f, indent=2, default=str)
            logger.debug(f"Exported trace to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export trace: {e}")


# Global tracer instance
_tracer: Optional[Tracer] = None


def get_tracer() -> Tracer:
    """Get the global tracer instance."""
    global _tracer
    if _tracer is None:
        export_dir = Path(os.getenv("TRACE_EXPORT_DIR", "traces"))
        _tracer = Tracer(export_dir=export_dir)
    return _tracer


def reset_tracer():
    """Reset the global tracer (for testing)."""
    global _tracer
    _tracer = None

