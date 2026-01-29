"""
Financial Analyst Agent

Implements the Accuracy-First Framework's agentic design patterns:
1. Tool Use Pattern: Calculations performed by deterministic code
2. Reflection Pattern: Self-critique and iterative refinement
3. Planning Pattern: Structured analysis approach

This agent analyzes NetSuite saved search data and produces
professional financial analysis with verified accuracy.

Enhanced with:
- Fiscal calendar awareness
- Query parsing and understanding
- Data filtering and aggregation
- Conversational memory
"""
import json
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from src.core.model_router import get_router, Message, LLMResponse, ModelRouter
from src.core.fiscal_calendar import FiscalCalendar, FiscalPeriod, get_fiscal_calendar
from src.core.query_parser import QueryParser, ParsedQuery, QueryIntent, get_query_parser
from src.core.memory import Session, SessionManager, get_session_manager, DisambiguationRecord
from src.core.data_context import DataContext, get_data_context
from src.core.financial_semantics import apply_disambiguation_choice, get_semantic_term
from src.core.query_cost_estimator import QueryCostEstimator, QueryCostEstimate, get_query_cost_estimator
from src.core.query_rewriter import QueryRewriter, get_query_rewriter
from src.core.observability import get_tracer, SpanKind
from src.core.prompt_manager import get_prompt_manager
from src.tools.netsuite_client import NetSuiteDataRetriever, SavedSearchResult, get_data_retriever
from src.tools.calculator import FinancialCalculator, CalculationResult, get_calculator, MetricType
from src.tools.charts import ChartGenerator, ChartOutput, get_chart_generator
from src.tools.data_processor import DataProcessor, FilterResult, get_data_processor
from src.tools.statistical_analyzer import (
    StatisticalAnalyzer,
    CorrelationAnalysis,
    RegressionResult,
    ARCHResult,
    get_statistical_analyzer
)
from src.evaluation.evaluator import (
    EvaluationHarness, EvaluationResult, 
    get_evaluation_harness
)
from config.settings import get_config

logger = logging.getLogger(__name__)

@dataclass
class AnalysisContext:
    """Context passed through the analysis pipeline."""
    query: str
    raw_data: SavedSearchResult
    data_summary: Dict[str, Any]
    
    # Enhanced context
    parsed_query: Optional[ParsedQuery] = None
    filtered_data: Optional[List[Dict[str, Any]]] = None
    filter_summary: str = ""
    comparison_data: Optional[Dict[str, List[Dict[str, Any]]]] = None  # NEW: For department comparisons
    
    # Conversation context
    session: Optional[Session] = None
    conversation_context: str = ""
    
    # Results
    calculations: List[CalculationResult] = field(default_factory=list)
    charts: List[ChartOutput] = field(default_factory=list)
    analysis_text: str = ""
    evaluation: Optional[EvaluationResult] = None
    iteration_count: int = 0
    
    # Statistical analysis (NEW)
    statistical_analysis: Optional[Dict[str, Any]] = None
    statistical_context: str = ""
    
    # Trace ID for observability
    trace_id: Optional[str] = None
    
    @property
    def working_data(self) -> List[Dict[str, Any]]:
        """Get the data to work with (filtered or raw)."""
        return self.filtered_data if self.filtered_data is not None else self.raw_data.data
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "data_row_count": self.raw_data.row_count,
            "filtered_row_count": len(self.working_data),
            "data_columns": self.raw_data.column_names,
            "calculation_count": len(self.calculations),
            "chart_count": len(self.charts),
            "iteration_count": self.iteration_count,
            "passes_evaluation": self.evaluation.passes_threshold if self.evaluation else None,
            "parsed_intent": self.parsed_query.intent.value if self.parsed_query else None,
        }

@dataclass
class AgentResponse:
    """Final response from the agent."""
    analysis: str
    calculations: List[Dict[str, Any]]
    charts: List[ChartOutput]
    evaluation_summary: Dict[str, Any]
    metadata: Dict[str, Any]
    
    # Disambiguation support (NEW)
    requires_clarification: bool = False
    clarification_message: Optional[str] = None
    ambiguous_terms: List[str] = field(default_factory=list)
    pending_query: Optional[str] = None
    trace_id: Optional[str] = None
    
    @property
    def slack_formatted(self) -> str:
        """Format analysis for Slack."""
        if self.requires_clarification:
            return self.clarification_message or "I need some clarification."
        return self.analysis
    
    @property
    def chart_files(self) -> List[str]:
        """Get list of chart file paths for Slack upload."""
        return [c.file_path for c in self.charts]
    
    @property
    def is_complete(self) -> bool:
        """Check if this is a complete response (not waiting for clarification)."""
        return not self.requires_clarification

class FinancialAnalystAgent:
    """
    def __init__(

Provide a comprehensive analysis following the structure in your instructions.
Remember: Use the pre-calculated metrics exactly as provided - do not recalculate.

When interpreting statistical results:
1. Focus on statistically significant correlations (p < 0.05)
2. Explain correlation vs causation distinction
3. Note the lag if correlations are lagged
4. Mention seasonality adjustments made
5. Interpret ARCH results in terms of revenue volatility patterns

IMPORTANT: Statistical significance does not imply causation. Present correlations 
as "associated with" not "causes" unless there's clear causal reasoning.
"""
    
    def __init__(
        self,
        data_retriever: Optional[NetSuiteDataRetriever] = None,
        calculator: Optional[FinancialCalculator] = None,
        chart_generator: Optional[ChartGenerator] = None,
        evaluator: Optional[EvaluationHarness] = None,
        router: Optional[ModelRouter] = None,
        fiscal_calendar: Optional[FiscalCalendar] = None,
        query_parser: Optional[QueryParser] = None,
        data_processor: Optional[DataProcessor] = None,
        session_manager: Optional[SessionManager] = None,
        data_context: Optional[DataContext] = None,
        cost_estimator: Optional[QueryCostEstimator] = None,
        statistical_analyzer: Optional[StatisticalAnalyzer] = None,
        query_rewriter: Optional[QueryRewriter] = None,
    ):
        self.data_retriever = data_retriever or get_data_retriever()
        self.calculator = calculator or get_calculator()
        self.chart_generator = chart_generator or get_chart_generator()
        self.evaluator = evaluator or get_evaluation_harness()
        self.router = router or get_router()
        self.fiscal_calendar = fiscal_calendar or get_fiscal_calendar()
        self.query_parser = query_parser or get_query_parser(self.router)
        self.data_processor = data_processor or get_data_processor()
        self.session_manager = session_manager or get_session_manager()
        self.data_context = data_context or get_data_context()
        self.cost_estimator = cost_estimator or get_query_cost_estimator()
        self.statistical_analyzer = statistical_analyzer or get_statistical_analyzer(
            fiscal_start_month=self.fiscal_calendar.fy_start_month
        )
        self.query_rewriter = query_rewriter or get_query_rewriter(self.router)
        self.prompt_manager = get_prompt_manager()
        self.config = get_config()
    
    async def analyze(
        self,
        query: str,
        search_id: Optional[str] = None,
        include_charts: bool = True,
        max_iterations: int = 3,
        session: Optional[Session] = None,
        session_id: Optional[str] = None,
        disambiguation_choice: Optional[Dict[str, int]] = None,
        user_id: Optional[str] = None,
        channel: Optional[str] = None,
    ) -> AgentResponse:
        """
        Main analysis entry point with observability.
        
        Args:
            query: User's analysis question
            search_id: NetSuite saved search ID (uses default if None)
            include_charts: Whether to generate visualizations
            max_iterations: Max reflection iterations for quality
            session: Existing conversation session for context
            session_id: Session ID to retrieve existing session
            disambiguation_choice: Dict mapping ambiguous terms to user's choice index.
                                  Example: {"sales": 0} means user chose option 0 (revenue)
            user_id: User identifier for tracing
            channel: Channel identifier (slack, cli, api) for tracing
        
        Returns:
            Complete AgentResponse with analysis, charts, and evaluation.
            If disambiguation is required, returns early with clarification request.
        """
        tracer = get_tracer()
        
        with tracer.start_trace(query, user_id=user_id, session_id=session_id, channel=channel) as trace:
            logger.info(f"Starting analysis for query: {query[:100]}...")
            trace_id = trace.trace_id if trace else None
            
            # Get or create session for conversation memory
            # load_session tries disk persistence first, then memory cache
            if session is None and session_id:
                session = self.session_manager.load_session(session_id)
                if session:
                    logger.info(f"Loaded existing session {session_id} (turns: {len(session.turns)}, pending: {session.has_pending_disambiguation()})")
            if session is None:
                session = self.session_manager.create_session()
                logger.info(f"Created new session {session.session_id}")
            
            # Check for pending disambiguation response
            # If session has pending disambiguation and this query looks like a response, merge them
            if session and session.has_pending_disambiguation():
                merged_result = self._try_merge_disambiguation_response(query, session)
                if merged_result:
                    # User's response was successfully parsed as a disambiguation choice
                    query, disambiguation_choice = merged_result
                    logger.info(f"Merged disambiguation response with pending query: {query[:50]}...")
                    logger.info(f"Disambiguation choice: {disambiguation_choice}")
            
            # Phase -1: Query Rewriting (for conversational follow-ups)
            # This handles messages like "filter by department instead" or "same thing for G&A"
            # Only runs if disambiguation merge didn't handle the message
            original_query = query
            if session and session.turns and not disambiguation_choice:
                with tracer.start_span("phase_minus1_query_rewriting", SpanKind.PIPELINE_PHASE) as span:
                    rewritten = self.query_rewriter.rewrite_if_needed(query, session)
                    if rewritten and rewritten != query:
                        logger.info(f"Rewrote follow-up: '{query[:50]}...' -> '{rewritten[:50]}...'")
                        query = rewritten
                        if span:
                            span.attributes["original_query"] = original_query[:100]
                            span.attributes["rewritten_query"] = rewritten[:100]
                            span.attributes["was_rewritten"] = True
                    else:
                        if span:
                            span.attributes["was_rewritten"] = False
            
            # Phase 0: Parse Query
            with tracer.start_span("phase_0_query_parsing", SpanKind.PIPELINE_PHASE) as span:
                parsed_query = self._parse_query(query, session)
                logger.info(f"Parsed intent: {parsed_query.intent.value}, confidence: {parsed_query.confidence:.2f}")
                if span:
                    span.attributes["parsed_intent"] = parsed_query.intent.value
                    span.attributes["confidence"] = parsed_query.confidence
            
            # Check for disambiguation requirement (NEW)
            if parsed_query.requires_disambiguation:
                if disambiguation_choice:
                    # User has provided their choice, apply it
                    # Pass session to record disambiguation for future topic-aware rewriting
                    parsed_query = self._apply_disambiguation(parsed_query, disambiguation_choice, session)
                    logger.info(f"Applied disambiguation choice: {disambiguation_choice}")
                else:
                    # Return early asking for clarification
                    logger.info(f"Disambiguation required for: {parsed_query.ambiguous_terms}")
                    return self._build_disambiguation_response(query, parsed_query, session)
            
            # Estimate query cost and warn if expensive (Phase 2.4)
            cost_estimate = self.cost_estimator.estimate(parsed_query)
            if cost_estimate.should_warn_user:
                logger.warning(
                    f"Expensive query detected: {cost_estimate.estimated_rows:,} rows, "
                    f"~{cost_estimate.estimated_time_seconds}s, complexity={cost_estimate.complexity}"
                )
            
            # Phase 1: Data Retrieval (always uses RESTlet for accuracy)
            with tracer.start_span("phase_1_data_retrieval", SpanKind.DATA_RETRIEVAL) as span:
                context = await self._retrieve_data(query, search_id, parsed_query)
                context.parsed_query = parsed_query
                context.session = session
                if span:
                    span.attributes["rows_retrieved"] = context.raw_data.row_count
            
            # Phase 1.5: Filter Data based on parsed query (now happens at DB level too)
            with tracer.start_span("phase_1.5_data_filtering", SpanKind.DATA_RETRIEVAL) as span:
                context = self._filter_data(context)
                if span:
                    span.attributes["rows_filtered"] = len(context.working_data)
            
            # Phase 2: Deterministic Calculations (now with fiscal awareness)
            with tracer.start_span("phase_2_calculations", SpanKind.CALCULATION) as span:
                context = self._perform_calculations(context)
                if span:
                    span.attributes["calculation_count"] = len(context.calculations)
                
                # Phase 2.5: Statistical Analysis (if requested)
                if parsed_query.intent in [QueryIntent.CORRELATION, QueryIntent.REGRESSION, QueryIntent.VOLATILITY]:
                    with tracer.start_span("phase_2.5_statistical_analysis", SpanKind.CALCULATION) as span:
                        context = self._run_statistical_analysis(context)
            
            # Phase 3: Chart Generation
            if include_charts:
                with tracer.start_span("phase_3_chart_generation", SpanKind.TOOL_CALL) as span:
                    context = self._generate_charts(context)
                    if span:
                        span.attributes["chart_count"] = len(context.charts)
            
            # Phase 4: Analysis Generation with Reflection
            with tracer.start_span("phase_4_analysis_generation", SpanKind.LLM_CALL) as span:
                try:
                    context = self._generate_analysis(context, max_iterations)
                    if span:
                        span.attributes["iteration_count"] = context.iteration_count
                except Exception as e:
                    # If LLM fails, continue with empty analysis but keep calculations
                    error_type = type(e).__name__
                    logger.error(f"Phase 4 (Analysis Generation) failed: {error_type}: {e}")
                    logger.info("Continuing with calculations only - analysis text will be empty")
                    context.analysis_text = f"[Analysis generation unavailable: {error_type}]"
                    context.iteration_count = 0
                    if span:
                        span.attributes["error"] = str(e)
                        span.attributes["error_type"] = error_type
            
            # Phase 5: Final Evaluation (skip if analysis generation failed)
            if context.analysis_text and not context.analysis_text.startswith("[Analysis generation unavailable"):
                with tracer.start_span("phase_5_evaluation", SpanKind.EVALUATION) as span:
                    try:
                        context = self._evaluate_analysis(context)
                        if span and context.evaluation:
                            span.attributes["evaluation_score"] = context.evaluation.average_qualitative_score
                            span.attributes["passed_threshold"] = context.evaluation.passes_threshold
                            tracer.record_evaluation(
                                score=context.evaluation.average_qualitative_score,
                                passed=context.evaluation.passes_threshold
                            )
                    except Exception as e:
                        # If evaluation fails, continue without evaluation
                        error_type = type(e).__name__
                        logger.error(f"Phase 5 (Evaluation) failed: {error_type}: {e}")
                        logger.info("Continuing without evaluation")
                        if span:
                            span.attributes["error"] = str(e)
                            span.attributes["error_type"] = error_type
            else:
                logger.info("Skipping Phase 5 (Evaluation) - analysis generation was unavailable")
            
            # Update session with this conversation
            self._update_session(context)
            
            return self._build_response(context)
    
    def _apply_disambiguation(
        self,
        parsed_query: ParsedQuery,
        choices: Dict[str, int],
        session: Optional[Session] = None,
    ) -> ParsedQuery:
        """
        Apply user's disambiguation choices to update the parsed query.
        
        Also records the disambiguation choice in the session for future
        topic-aware query rewriting.
        
        Args:
            parsed_query: The original parsed query with ambiguous terms
            choices: Dict mapping term -> choice index (1-based for user-friendly display)
            session: Optional session to record disambiguation choices
        
        Returns:
            Updated ParsedQuery with resolved semantic filters
        """
        from src.core.financial_semantics import SemanticCategory
        
        resolved_terms = set()
        unresolved_terms = []
        
        # Generate topic summary for disambiguation records
        topic_summary = self._summarize_topic(parsed_query) if session else ""
        
        for term, choice_index in choices.items():
            # Check if this is a department disambiguation from registry
            if term in parsed_query.department_disambiguation_options:
                options = parsed_query.department_disambiguation_options[term]
                
                # Handle both old format (list of strings) and new format (list of dicts)
                # New format: [{"num": 1, "label": "...", "filter_values": [...], "is_consolidated": bool}, ...]
                # Old format: ["dept1", "dept2", ...]
                
                if options and isinstance(options[0], dict):
                    # NEW enhanced format with filter_values
                    # Find option by 'num' field (user's 1-based choice)
                    selected_option = None
                    for opt in options:
                        if opt.get("num") == choice_index:
                            selected_option = opt
                            break
                    
                    if selected_option:
                        filter_values = selected_option.get("filter_values", [])
                        is_consolidated = selected_option.get("is_consolidated", False)
                        label = selected_option.get("label", "")
                        
                        # Replace the ambiguous term with selected department(s)
                        if term in parsed_query.departments:
                            parsed_query.departments.remove(term)
                        
                        # Add all filter values (supports consolidated option with multiple departments)
                        for dept in filter_values:
                            if dept not in parsed_query.departments:
                                parsed_query.departments.append(dept)
                        
                        logger.info(
                            f"Resolved department '{term}' to {len(filter_values)} department(s): "
                            f"{filter_values[:3]}{'...' if len(filter_values) > 3 else ''} "
                            f"(choice {choice_index}, consolidated={is_consolidated})"
                        )
                        
                        # Remove from disambiguation options after successful resolution
                        parsed_query.department_disambiguation_options.pop(term, None)
                        resolved_terms.add(term)
                        
                        # Record disambiguation choice in session
                        if session:
                            record = DisambiguationRecord(
                                term=term,
                                chosen_dimension="department",
                                chosen_value={
                                    "label": label,
                                    "departments": filter_values,
                                    "is_consolidated": is_consolidated
                                },
                                topic_summary=topic_summary,
                                turn_index=len(session.turns),
                                disambiguation_type="entity",  # Entity-level disambiguation
                            )
                            session.resolved_disambiguations.append(record)
                            logger.info(f"Recorded entity disambiguation: '{term}' -> {label}")
                    else:
                        logger.warning(
                            f"Invalid choice {choice_index} for term '{term}' "
                            f"(valid options: {[o.get('num') for o in options]}). Keeping term unresolved."
                        )
                        unresolved_terms.append(term)
                else:
                    # OLD format - list of strings (backward compatibility)
                    user_choice = choice_index - 1 if choice_index > 0 else choice_index
                    if 0 <= user_choice < len(options):
                        selected_dept = options[user_choice]
                        # Replace the ambiguous term with the selected department
                        if term in parsed_query.departments:
                            parsed_query.departments.remove(term)
                        parsed_query.departments.append(selected_dept)
                        logger.info(f"Resolved department '{term}' to '{selected_dept}' (choice {choice_index})")
                        # Remove from disambiguation options after successful resolution
                        parsed_query.department_disambiguation_options.pop(term, None)
                        resolved_terms.add(term)
                        
                        # Record disambiguation choice in session
                        if session:
                            record = DisambiguationRecord(
                                term=term,
                                chosen_dimension="department",
                                chosen_value={"name": selected_dept},
                                topic_summary=topic_summary,
                                turn_index=len(session.turns),
                            )
                            session.resolved_disambiguations.append(record)
                            logger.info(f"Recorded disambiguation: '{term}' -> department '{selected_dept}'")
                    else:
                        logger.warning(
                            f"Invalid choice index {choice_index} for term '{term}' "
                            f"(valid range: 1-{len(options)}). Keeping term unresolved."
                        )
                        unresolved_terms.append(term)
                continue
            
            # Handle semantic term disambiguation (existing logic)
            semantic_term = get_semantic_term(term)
            if semantic_term and semantic_term.disambiguation_required:
                # Convert 1-based user choice to 0-based index
                user_choice = choice_index - 1 if choice_index > 0 else choice_index
                resolved = apply_disambiguation_choice(semantic_term, user_choice)
                if resolved:
                    logger.debug(f"Resolved '{term}' to {resolved.category.value}")
                    resolved_terms.add(term)
                    
                    if resolved.category == SemanticCategory.ACCOUNT:
                        # User chose to filter by ACCOUNT, not department
                        # Set the account filter
                        parsed_query.account_type_filter = {
                            "filter_type": resolved.filter_type.value,
                            "values": resolved.filter_values,
                        }
                        # IMPORTANT: Remove the term from departments if it was there
                        # because user explicitly chose account, not department
                        term_upper = term.upper()
                        term_lower = term.lower()
                        depts_to_remove = [
                            d for d in parsed_query.departments
                            if d.upper() == term_upper or d.lower() == term_lower
                            or term_lower in d.lower()  # Handle "R&D" matching "R&D (Parent)"
                        ]
                        for d in depts_to_remove:
                            parsed_query.departments.remove(d)
                            logger.info(f"Removed department '{d}' - user chose account filter instead")
                        
                        # Record disambiguation choice in session
                        if session:
                            record = DisambiguationRecord(
                                term=term,
                                chosen_dimension="account",
                                chosen_value={
                                    "filter_type": resolved.filter_type.value,
                                    "values": resolved.filter_values,
                                },
                                topic_summary=topic_summary,
                                turn_index=len(session.turns),
                            )
                            session.resolved_disambiguations.append(record)
                            logger.info(f"Recorded disambiguation: '{term}' -> account filter")
                        
                    elif resolved.category == SemanticCategory.DEPARTMENT:
                        # User chose to filter by DEPARTMENT, not account
                        parsed_query.departments.extend(resolved.filter_values)
                        # Remove any account type filter that was set for this term
                        # (in case both were initially extracted)
                        
                        # Record disambiguation choice in session
                        if session:
                            record = DisambiguationRecord(
                                term=term,
                                chosen_dimension="department",
                                chosen_value={"departments": resolved.filter_values},
                                topic_summary=topic_summary,
                                turn_index=len(session.turns),
                            )
                            session.resolved_disambiguations.append(record)
                            logger.info(f"Recorded disambiguation: '{term}' -> department filter")
                else:
                    unresolved_terms.append(term)
                    logger.warning(f"Failed to resolve semantic term '{term}' with choice {choice_index}")
        
        # Only clear disambiguation flags if all terms were resolved
        # Check if there are any remaining ambiguous terms or department options
        remaining_ambiguous = [
            t for t in parsed_query.ambiguous_terms 
            if t not in resolved_terms
        ]
        remaining_dept_options = parsed_query.department_disambiguation_options
        
        if not remaining_ambiguous and not remaining_dept_options:
            # All disambiguations resolved - clear flags
            parsed_query.requires_disambiguation = False
            parsed_query.disambiguation_message = None
            parsed_query.ambiguous_terms = []
            parsed_query.department_disambiguation_options = {}
        elif unresolved_terms:
            # Some terms couldn't be resolved - keep disambiguation flags but update message
            logger.warning(
                f"Some terms could not be resolved: {unresolved_terms}. "
                f"Keeping disambiguation flags active."
            )
            # Update ambiguous terms list to only include unresolved ones
            parsed_query.ambiguous_terms = [
                t for t in parsed_query.ambiguous_terms 
                if t not in resolved_terms
            ]
        
        return parsed_query
    
    def _summarize_topic(self, parsed_query: ParsedQuery) -> str:
        """
        Generate a brief topic summary for a parsed query.
        
        Used to help the LLM determine if a follow-up query is related
        to the same topic as a previous disambiguation.
        
        Args:
            parsed_query: The parsed query to summarize
        
        Returns:
            Brief string describing the query topic (e.g., "R&D expenses analysis")
        """
        # Add intent - use actual QueryIntent enum values
        intent_map = {
            QueryIntent.SUMMARY: "summary",
            QueryIntent.TOTAL: "totals",
            QueryIntent.TREND: "trend analysis",
            QueryIntent.COMPARISON: "comparison",
            QueryIntent.VARIANCE: "variance analysis",
            QueryIntent.BREAKDOWN: "breakdown",
            QueryIntent.TOP_N: "top items",
            QueryIntent.DETAIL: "details",
            QueryIntent.RATIO: "ratio analysis",
            QueryIntent.CORRELATION: "correlation analysis",
            QueryIntent.REGRESSION: "regression analysis",
            QueryIntent.VOLATILITY: "volatility analysis",
        }
        intent_str = intent_map.get(parsed_query.intent, "analysis")
        
        # Add primary entities (departments, accounts)
        entities = []
        if parsed_query.departments:
            entities.extend(parsed_query.departments[:2])  # Limit to first 2
        if parsed_query.account_type_filter:
            filter_vals = parsed_query.account_type_filter.get("values", [])
            if filter_vals:
                entities.append(f"accounts {filter_vals[0]}")
        
        # Add time period if present
        time_str = ""
        if parsed_query.time_period:
            tp = parsed_query.time_period
            # FiscalPeriod uses period_name, not period_type
            if hasattr(tp, 'period_name') and tp.period_name:
                time_str = f" for {tp.period_name}"
        
        # Construct summary
        if entities:
            entity_str = ", ".join(entities[:2])
            return f"{entity_str} {intent_str}{time_str}"
        else:
            return f"financial {intent_str}{time_str}"
    
    def _build_disambiguation_response(
        self,
        query: str,
        parsed_query: ParsedQuery,
        session: Optional[Session],
    ) -> AgentResponse:
        """
        Build a response asking for clarification on ambiguous terms.
        Also stores the pending query context in the session for follow-up.
        """
        # Store pending disambiguation context in session for follow-up
        if session:
            # Build disambiguation options dict for persistence
            disambiguation_options = {}
            for term in parsed_query.ambiguous_terms:
                # Get options from department disambiguation options first
                if term in parsed_query.department_disambiguation_options:
                    dept_options = parsed_query.department_disambiguation_options[term]
                    
                    # Handle enhanced format (list of dicts with filter_values)
                    if dept_options and isinstance(dept_options[0], dict):
                        # Already in enhanced format - preserve it
                        disambiguation_options[term] = [
                            {
                                "num": opt.get("num"),
                                "label": opt.get("label"),
                                "description": opt.get("description", ""),
                                "type": "department",
                                "filter_values": opt.get("filter_values", []),
                                "is_consolidated": opt.get("is_consolidated", False)
                            }
                            for opt in dept_options
                        ]
                    else:
                        # Old format - convert to standard format
                        disambiguation_options[term] = [
                            {"label": opt, "type": "department"} 
                            for opt in dept_options
                        ]
                else:
                    # Check semantic_terms list for disambiguation options
                    # semantic_terms is a list of dicts from SemanticTerm.to_dict()
                    for sem_term in parsed_query.semantic_terms:
                        if sem_term.get("term", "").lower() == term.lower():
                            if sem_term.get("disambiguation_options"):
                                disambiguation_options[term] = sem_term["disambiguation_options"]
                            break
            
            session.set_pending_disambiguation(
                query=query,
                parsed_query_dict={
                    "intent": parsed_query.intent.value,
                    "departments": parsed_query.departments,
                    "accounts": parsed_query.accounts,
                    "time_period": parsed_query.time_period.to_dict() if parsed_query.time_period else None,
                    "ambiguous_terms": parsed_query.ambiguous_terms,
                },
                ambiguous_terms=parsed_query.ambiguous_terms,
                disambiguation_options=disambiguation_options,
            )
            
            # Add user message to conversation history
            session.add_user_message(content=query)
            
            # Save session with pending disambiguation
            self.session_manager.save_session(session.session_id)
            logger.info(f"Saved pending disambiguation for session {session.session_id}")
        
        return AgentResponse(
            analysis="",
            calculations=[],
            charts=[],
            evaluation_summary={},
            metadata={
                "query": query,
                "session_id": session.session_id if session else None,
                "parsed_intent": parsed_query.intent.value,
                "requires_disambiguation": True,
            },
            requires_clarification=True,
            clarification_message=parsed_query.disambiguation_message,
            ambiguous_terms=parsed_query.ambiguous_terms,
            pending_query=query,
        )
    
    def _try_merge_disambiguation_response(
        self,
        user_response: str,
        session: Session,
    ) -> Optional[tuple]:
        """
        Try to parse a user's response as a disambiguation choice.
        
        If successful, returns (original_query, disambiguation_choice_dict).
        If the response doesn't look like a disambiguation choice, returns None.
        
        Examples of disambiguation responses:
        - "1" or "2" or "3" (numeric choice)
        - "account" or "accounts" (choosing account dimension)
        - "department" or "departments" (choosing department dimension)
        - "I mean filter by account"
        - "R&D departments please"
        - "both" (if that's an option)
        """
        import re
        
        if not session.pending_query or not session.pending_ambiguous_terms:
            return None
        
        response_lower = user_response.lower().strip()
        pending_terms = session.pending_ambiguous_terms
        pending_options = session.pending_disambiguation_options or {}
        
        # Short responses are more likely to be disambiguation choices
        is_short_response = len(response_lower.split()) <= 10
        
        disambiguation_choice = {}
        
        # Pattern 1: Numeric choice (e.g., "1", "2", "option 1")
        numeric_match = re.search(r'\b(\d)\b', response_lower)
        if numeric_match and is_short_response:
            choice_num = int(numeric_match.group(1))
            # Apply to all pending terms (user chose a single option number)
            for term in pending_terms:
                disambiguation_choice[term] = choice_num
            logger.info(f"Parsed numeric disambiguation choice: {choice_num} for terms {pending_terms}")
            return (session.pending_query, disambiguation_choice)
        
        # Pattern 2: Keyword matching for account/department/both
        account_keywords = ["account", "accounts", "filter by account", "account number", "52"]
        department_keywords = ["department", "departments", "filter by department", "org", "hierarchy"]
        both_keywords = ["both", "all", "both account and department", "accounts and departments"]
        
        for term in pending_terms:
            options = pending_options.get(term, [])
            
            # Check for "both" option (usually option 3)
            if any(kw in response_lower for kw in both_keywords):
                # "Both" is typically option 3
                for i, opt in enumerate(options):
                    if isinstance(opt, dict) and "both" in opt.get("label", "").lower():
                        disambiguation_choice[term] = i + 1  # 1-based
                        break
                else:
                    disambiguation_choice[term] = 3  # Default "both" position
                continue
            
            # Check for account option (usually option 1)
            if any(kw in response_lower for kw in account_keywords):
                for i, opt in enumerate(options):
                    if isinstance(opt, dict) and "account" in opt.get("label", "").lower():
                        disambiguation_choice[term] = i + 1
                        break
                else:
                    disambiguation_choice[term] = 1  # Default account position
                continue
            
            # Check for department option (usually option 2)
            if any(kw in response_lower for kw in department_keywords):
                for i, opt in enumerate(options):
                    if isinstance(opt, dict) and "department" in opt.get("label", "").lower():
                        disambiguation_choice[term] = i + 1
                        break
                else:
                    disambiguation_choice[term] = 2  # Default department position
                continue
        
        # If we found choices for all pending terms, return the merge
        if disambiguation_choice and len(disambiguation_choice) == len(pending_terms):
            logger.info(f"Parsed keyword disambiguation choice: {disambiguation_choice}")
            return (session.pending_query, disambiguation_choice)
        
        # Pattern 3: If response is very short and session has pending, assume it's related
        # and try to extract context
        if is_short_response and len(response_lower) < 50:
            # Check if response mentions any of the disambiguation options by label
            for term in pending_terms:
                options = pending_options.get(term, [])
                for i, opt in enumerate(options):
                    if isinstance(opt, dict):
                        label = opt.get("label", "").lower()
                        if label and label in response_lower:
                            disambiguation_choice[term] = i + 1
                            break
            
            if disambiguation_choice:
                logger.info(f"Parsed label-based disambiguation choice: {disambiguation_choice}")
                return (session.pending_query, disambiguation_choice)
        
        # Could not parse as disambiguation response
        # This might be a new query entirely
        logger.debug(f"Response '{user_response[:50]}' not recognized as disambiguation choice")
        return None
    
    def analyze_sync(
        self,
        query: str,
        search_id: Optional[str] = None,
        include_charts: bool = True,
        max_iterations: int = 3,
        session: Optional[Session] = None,
        session_id: Optional[str] = None,
    ) -> AgentResponse:
        """Synchronous version of analyze for non-async contexts."""
        import asyncio
        return asyncio.run(self.analyze(
            query, search_id, include_charts, max_iterations, session, session_id
        ))
    
    def _parse_query(self, query: str, session: Optional[Session] = None) -> ParsedQuery:
        """Phase 0: Parse the user query to extract intent and filters."""
        context = {}
        if session and session.context.has_context():
            context = session.context.to_dict()
        
        return self.query_parser.parse(query, context)
    
    def _filter_data(self, context: AnalysisContext) -> AnalysisContext:
        """
        Phase 1.5: Filter data based on parsed query.
        
        Note: All filters are applied in Python after data retrieval.
        RESTlet fetches all data, then filters are applied sequentially.
        """
        parsed = context.parsed_query
        if not parsed:
            return context
        
        data = context.raw_data.data
        filters_applied = []
        
        # Apply time period filter using periodname (text string like "Jan 2025") or formuladate (date like "1/1/2025")
        if parsed.time_period:
            result = self.data_processor.filter_by_period(data, parsed.time_period)
            data = result.data
            filters_applied.extend(result.filters_applied)
            logger.info(f"Time filter: {result.filter_summary}")
        
        # Apply account type filter (NEW - from financial semantics)
        if parsed.account_type_filter:
            result = self.data_processor.filter_by_account_type(
                data, parsed.account_type_filter
            )
            data = result.data
            filters_applied.extend(result.filters_applied)
            logger.info(f"Account type filter: {result.filter_summary}")
        
        # Apply account NAME filter (NEW - for compound filters like "Sales & Marketing")
        if parsed.account_name_filter:
            result = self.data_processor.filter_by_account_name(
                data, parsed.account_name_filter
            )
            data = result.data
            filters_applied.extend(result.filters_applied)
            logger.info(f"Account name filter: {result.filter_summary}")
        
        # Apply transaction type filter (NEW - from financial semantics)
        if parsed.transaction_type_filter:
            result = self.data_processor.filter_by_transaction_type(
                data, parsed.transaction_type_filter
            )
            data = result.data
            filters_applied.extend(result.filters_applied)
            logger.info(f"Transaction type filter: {result.filter_summary}")
        
        # Apply department filter
        # NEW: Handle department comparisons separately
        if parsed.departments:
            if parsed.is_department_comparison and len(parsed.departments) >= 2:
                # For comparisons, filter each department separately
                comparison_data = {}
                for dept in parsed.departments:
                    dept_result = self.data_processor.apply_filters(
                        data, departments=[dept]
                    )
                    comparison_data[dept] = dept_result.data
                    logger.info(f"Comparison department '{dept}': {dept_result.filter_summary}")
                
                # Store comparison data in context (will be used by calculations)
                context.comparison_data = comparison_data
                # Use first department's data as primary filtered data for backward compatibility
                data = comparison_data[parsed.departments[0]] if parsed.departments else []
                filters_applied.append(f"department comparison: {', '.join(parsed.departments)}")
            else:
                # Normal department filter (OR logic)
                result = self.data_processor.apply_filters(
                    data, departments=parsed.departments
                )
                data = result.data
                filters_applied.extend(result.filters_applied)
                logger.info(f"Department filter: {result.filter_summary}")
        
        # Apply account filter (specific account names/numbers)
        if parsed.accounts:
            result = self.data_processor.apply_filters(
                data, accounts=parsed.accounts
            )
            data = result.data
            filters_applied.extend(result.filters_applied)
            logger.info(f"Account filter: {result.filter_summary}")
        
        # NEW: Apply exclusion filters (after inclusion filters)
        if parsed.exclude_departments or parsed.exclude_accounts:
            result = self.data_processor.apply_filters(
                data,
                exclude_departments=parsed.exclude_departments,
                exclude_accounts=parsed.exclude_accounts,
            )
            data = result.data
            filters_applied.extend(result.filters_applied)
            logger.info(f"Exclusion filter: {result.filter_summary}")
        
        context.filtered_data = data
        context.filter_summary = f"Filtered {context.raw_data.row_count} -> {len(data)} rows"
        
        if filters_applied:
            context.filter_summary += f" ({', '.join(filters_applied)})"
        
        # NEW: Validate that expected filters were applied
        self._validate_filters(context, parsed, filters_applied)
        
        return context
    
    def _validate_filters(self, context: AnalysisContext, parsed: ParsedQuery, filters_applied: List[str]):
        """
        Validate that expected filters were applied and log warnings if missing.
        
        This helps catch cases where filter extraction failed silently.
        """
        expected_filters = []
        missing_filters = []
        
        # Check time period filter
        if parsed.time_period:
            expected_filters.append("time period")
            if not any("period" in f.lower() or "date" in f.lower() for f in filters_applied):
                missing_filters.append(f"Time period filter ({parsed.time_period.period_name})")
        
        # Check department filter
        if parsed.departments and not parsed.is_department_comparison:
            expected_filters.append("department")
            if not any("department" in f.lower() for f in filters_applied):
                missing_filters.append(f"Department filter ({', '.join(parsed.departments)})")
        
        # Check account type filter
        if parsed.account_type_filter:
            expected_filters.append("account type")
            if not any("account" in f.lower() and "prefix" in f.lower() for f in filters_applied):
                missing_filters.append(f"Account type filter ({parsed.account_type_filter})")
        
        # Check account name filter
        if parsed.account_name_filter:
            expected_filters.append("account name")
            if not any("account name" in f.lower() for f in filters_applied):
                missing_filters.append(f"Account name filter ({parsed.account_name_filter})")
        
        # Check transaction type filter
        if parsed.transaction_type_filter:
            expected_filters.append("transaction type")
            if not any("type" in f.lower() or "transaction" in f.lower() for f in filters_applied):
                missing_filters.append(f"Transaction type filter ({parsed.transaction_type_filter})")
        
        # Check exclusion filters
        if parsed.exclude_departments:
            expected_filters.append("exclude department")
            if not any("exclude" in f.lower() and "department" in f.lower() for f in filters_applied):
                missing_filters.append(f"Exclude department filter ({', '.join(parsed.exclude_departments)})")
        
        if parsed.exclude_accounts:
            expected_filters.append("exclude account")
            if not any("exclude" in f.lower() and "account" in f.lower() for f in filters_applied):
                missing_filters.append(f"Exclude account filter ({', '.join(parsed.exclude_accounts)})")
        
        # Log warnings for missing filters
        if missing_filters:
            logger.warning(
                f"Expected filters were not applied: {', '.join(missing_filters)}. "
                f"Applied filters: {filters_applied}. "
                f"This may indicate a filter extraction issue."
            )
        else:
            logger.debug(f"All expected filters were applied: {expected_filters}")
    
    def _update_session(self, context: AnalysisContext):
        """Update the session with this conversation turn and save to disk."""
        if not context.session:
            return
        
        # Clear any pending disambiguation since we completed the analysis
        if context.session.has_pending_disambiguation():
            context.session.clear_pending_disambiguation()
            logger.debug("Cleared pending disambiguation after successful analysis")
        
        # Add user message
        parsed = context.parsed_query
        context.session.add_user_message(
            content=context.query,
            departments=parsed.departments if parsed else None,
            accounts=parsed.accounts if parsed else None,
            time_periods=[parsed.time_period.period_name] if parsed and parsed.time_period else None,
        )
        
        # Add assistant response with context
        summary = context.analysis_text[:200] + "..." if len(context.analysis_text) > 200 else context.analysis_text
        context.session.add_assistant_message(
            content=context.analysis_text,
            analysis_type=parsed.intent.value if parsed else "summary",
            result_summary=summary,
            data_filters={
                "departments": parsed.departments if parsed else [],
                "accounts": parsed.accounts if parsed else [],
                "time_period": parsed.time_period.period_name if parsed and parsed.time_period else None,
            },
        )
        
        # Save session to disk for persistence across process invocations
        self.session_manager.save_session(context.session.session_id)
        logger.debug(f"Saved session {context.session.session_id} to disk")
    
    async def _retrieve_data(
        self,
        query: str,
        search_id: Optional[str],
        parsed_query: Optional[ParsedQuery] = None,
    ) -> AnalysisContext:
        """
        Phase 1: Retrieve data from NetSuite.
        
        Always uses RESTlet for accurate financial reporting (posting period dates).
        """
        logger.info("Phase 1: Retrieving data from NetSuite")
        
        # Always use RESTlet for accurate financial data (posting period dates)
        result = self.data_retriever.get_saved_search_data(
            search_id,
            parsed_query=parsed_query,
            use_suiteql_optimization=False,  # SuiteQL removed - always use RESTlet
        )
        summary = self.data_retriever.get_data_summary(result)
        
        logger.info(f"Retrieved {result.row_count} rows with columns: {result.column_names}")
        
        return AnalysisContext(
            query=query,
            raw_data=result,
            data_summary=summary,
        )
    
    
    def _perform_calculations(self, context: AnalysisContext) -> AnalysisContext:
        """Phase 2: Perform deterministic calculations with fiscal awareness."""
        logger.info("Phase 2: Performing deterministic calculations")
        
        calculations = []
        data = context.working_data  # Use filtered data if available
        columns = [c.lower() for c in context.raw_data.column_names]
        parsed = context.parsed_query
        
        # Auto-detect and calculate relevant metrics based on available columns
        category_fields = ['type', 'account', 'department', 'class', 'location', 'category']
        amount_fields = ['amount', 'total', 'value', 'balance', 'credit', 'debit']
        
        # Find amount field
        amount_field = None
        for col in context.raw_data.column_names:
            if col.lower() in amount_fields or 'amount' in col.lower():
                amount_field = col
                break
        
        # Find date field - prioritize formuladate (month-end date) over trandate
        date_field = None
        # Priority order: formuladate (month-end date) > trandate (transaction date) > other date fields
        preferred_fields = ['formuladate', 'trandate']
        for preferred in preferred_fields:
            if preferred in context.raw_data.column_names:
                date_field = preferred
                break
        
        # Fallback to any date field if preferred not found
        if not date_field:
            date_fields_patterns = ['date', 'created', 'posted']
            for col in context.raw_data.column_names:
                if col.lower() in date_fields_patterns or 'date' in col.lower():
                    date_field = col
                    break
        
        if amount_field:
            # Calculate total
            total = sum(float(row.get(amount_field, 0) or 0) for row in data)
            calculations.append(CalculationResult(
                metric_name="Total Amount",
                value=total,
                formatted_value=f"${total:,.2f}",
                metric_type=MetricType.CASH_FLOW,
                inputs={"field": amount_field, "row_count": len(data)},
                formula=f"Sum of {amount_field}",
                interpretation_guide=f"The total across all {len(data)} records is ${total:,.2f}.",
            ))
            
            # Fiscal YTD calculation if requested
            if parsed and parsed.intent in [QueryIntent.TOTAL, QueryIntent.SUMMARY]:
                if date_field:
                    ytd_result = self.calculator.ytd_total(
                        data=data,
                        amount_field=amount_field,
                        date_field=date_field,
                        fiscal_start_month=self.config.fiscal.fiscal_year_start_month,
                    )
                    calculations.append(ytd_result)
            
            # Sum by category if available
            for cat_col in context.raw_data.column_names:
                if cat_col.lower() in category_fields or 'type' in cat_col.lower():
                    category_sums = self.calculator.sum_by_category(data, amount_field, cat_col)
                    calculations.extend(category_sums.values())
                    break
            
            # Variance calculations if comparison requested
            if parsed and parsed.comparison_type and parsed.time_period and parsed.comparison_period:
                current_data = self.data_processor.filter_by_period(
                    context.raw_data.data, parsed.time_period
                ).data
                prior_data = self.data_processor.filter_by_period(
                    context.raw_data.data, parsed.comparison_period
                ).data
                
                # Find category field for breakdown
                category_field = None
                for cat_col in context.raw_data.column_names:
                    if cat_col.lower() in category_fields:
                        category_field = cat_col
                        break
                
                if category_field:
                    variance_results = self.calculator.period_variance_by_category(
                        current_data=current_data,
                        prior_data=prior_data,
                        amount_field=amount_field,
                        category_field=category_field,
                        current_period_name=parsed.time_period.period_name,
                        prior_period_name=parsed.comparison_period.period_name,
                    )
                    calculations.extend(variance_results)
                else:
                    # Total comparison
                    current_total = sum(float(r.get(amount_field, 0) or 0) for r in current_data)
                    prior_total = sum(float(r.get(amount_field, 0) or 0) for r in prior_data)
                    comparison = self.calculator.comparative_summary(
                        current_total=current_total,
                        prior_total=prior_total,
                        current_period_name=parsed.time_period.period_name,
                        prior_period_name=parsed.comparison_period.period_name,
                    )
                    calculations.append(comparison)
            
            # Monthly breakdown if query requests monthly totals
            query_lower = context.query.lower()
            is_monthly_query = (
                "monthly" in query_lower or 
                "by month" in query_lower or 
                "each month" in query_lower or
                "per month" in query_lower
            )
            
            if is_monthly_query and date_field:
                logger.info("Detected monthly query - generating monthly breakdown")
                monthly_breakdown = self.data_processor.group_by_period(
                    data=data,
                    period_type="month",
                    amount_field=amount_field,
                    date_field=date_field
                )
                
                if monthly_breakdown.data:
                    # Create calculation results for each month
                    for month_key, month_data in sorted(monthly_breakdown.data.items()):
                        month_total = month_data.get("sum", 0)
                        month_count = month_data.get("count", 0)
                        
                        # Format month key (e.g., "2025-02" -> "February 2025")
                        try:
                            year, month_num = month_key.split("-")
                            month_name = datetime(int(year), int(month_num), 1).strftime("%B %Y")
                        except:
                            month_name = month_key
                        
                        calculations.append(CalculationResult(
                            metric_name=f"{month_name} Total",
                            value=month_total,
                            formatted_value=f"${month_total:,.2f}",
                            metric_type=MetricType.CASH_FLOW,
                            inputs={
                                "month": month_key,
                                "transaction_count": month_count,
                                "field": amount_field
                            },
                            formula=f"Sum of {amount_field} for {month_key}",
                            interpretation_guide=(
                                f"Total for {month_name} is ${month_total:,.2f} "
                                f"across {month_count} transactions."
                            ),
                        ))
                    
                    logger.info(f"Generated {len(monthly_breakdown.data)} monthly calculations")
            
            # Trend analysis if date field exists
            if date_field:
                trend = self.calculator.time_series_trend(data, amount_field, date_field)
                calculations.append(trend)
        
        context.calculations = calculations
        logger.info(f"Completed {len(calculations)} calculations")
        
        return context
    
    def _run_statistical_analysis(self, context: AnalysisContext) -> AnalysisContext:
        """Phase 2.5: Run statistical analysis if query requires it."""
        logger.info("Phase 2.5: Running statistical analysis")
        
        parsed = context.parsed_query
        if not parsed:
            return context
        
        # Check if query mentions seasonality or ARCH
        query_lower = context.query.lower()
        include_arch = "arch" in query_lower or "garch" in query_lower or parsed.intent == QueryIntent.VOLATILITY
        seasonally_adjust = "season" in query_lower or parsed.intent == QueryIntent.CORRELATION
        
        try:
            # Run full correlation analysis
            result = self.statistical_analyzer.full_revenue_correlation_analysis(
                data=context.working_data,
                include_arch=include_arch,
                seasonally_adjust=seasonally_adjust,
                top_n=10
            )
            
            context.statistical_analysis = result
            context.statistical_context = result.get("llm_context", "")
            
            # Log completion
            corr_analysis = result.get("correlation_analysis")
            if corr_analysis and hasattr(corr_analysis, 'correlations'):
                logger.info(f"Statistical analysis completed: {len(corr_analysis.correlations)} correlations found")
            else:
                logger.info("Statistical analysis completed (no correlations found)")
        except Exception as e:
            logger.error(f"Statistical analysis error: {e}", exc_info=True)
            context.statistical_context = f"Statistical analysis encountered an error: {str(e)}"
        
        return context
    
    def _generate_charts(self, context: AnalysisContext) -> AnalysisContext:
        """Phase 3: Generate visualizations."""
        logger.info("Phase 3: Generating charts")
        
        charts = []
        data = context.working_data  # Use filtered data if available
        
        if not data:
            return context
        
        # Find relevant columns
        columns = context.raw_data.column_names
        amount_field = None
        category_field = None
        date_field = None
        
        for col in columns:
            col_lower = col.lower()
            if 'amount' in col_lower or 'total' in col_lower or 'value' in col_lower:
                amount_field = col
            if 'type' in col_lower or 'category' in col_lower or 'account' in col_lower:
                category_field = col
        
        # Prioritize formuladate (month-end date) over trandate for date-based filtering
        preferred_fields = ['formuladate', 'trandate']
        for preferred in preferred_fields:
            if preferred in columns:
                date_field = preferred
                break
        
        # Fallback to any date field
        if not date_field:
            for col in columns:
                if 'date' in col.lower():
                    date_field = col
                    break
        
        # NEW: Generate quarterly trend chart if sufficient data
        if amount_field and date_field and self.chart_generator:
            try:
                quarterly_data = self.data_processor.aggregate_to_quarters(
                    data,
                    amount_field=amount_field,
                    date_field=date_field,
                    fiscal_start_month=self.fiscal_calendar.fy_start_month,
                )
                
                if len(quarterly_data) >= 4:
                    quarters = [q["quarter_label"] for q in quarterly_data]
                    amounts = [q["amount"] for q in quarterly_data]
                    
                    chart = self.chart_generator.quarterly_trend_chart(
                        quarters=quarters,
                        values=amounts,
                        title="Quarterly Trend Analysis",
                        ylabel="Amount ($)",
                        show_yoy_change=len(quarterly_data) >= 8,  # Need 2 years for YoY
                    )
                    charts.append(chart)
            except Exception as e:
                logger.debug(f"Could not generate quarterly chart: {e}")
        
        # Generate category breakdown chart
        if amount_field and category_field:
            category_totals: Dict[str, float] = {}
            for row in data:
                cat = str(row.get(category_field, 'Unknown'))
                amt = float(row.get(amount_field, 0) or 0)
                category_totals[cat] = category_totals.get(cat, 0) + amt
            
            sorted_cats = sorted(category_totals.items(), key=lambda x: abs(x[1]), reverse=True)[:10]
            
            if sorted_cats and self.chart_generator:
                chart = self.chart_generator.bar_chart(
                    categories=[c[0] for c in sorted_cats],
                    values=[c[1] for c in sorted_cats],
                    title=f"Amount by {category_field}",
                    ylabel="Amount ($)",
                    horizontal=True,
                )
                charts.append(chart)
                
                if len(sorted_cats) >= 3:
                    pie = self.chart_generator.pie_chart(
                        categories=[c[0] for c in sorted_cats],
                        values=[abs(c[1]) for c in sorted_cats],
                        title=f"Distribution by {category_field}",
                    )
                    charts.append(pie)
        
        # Generate trend chart if date field exists
        if amount_field and date_field:
            date_totals: Dict[str, float] = {}
            for row in data:
                date_val = str(row.get(date_field, ''))[:10]
                if date_val:
                    amt = float(row.get(amount_field, 0) or 0)
                    date_totals[date_val] = date_totals.get(date_val, 0) + amt
            
            if len(date_totals) >= 3 and self.chart_generator:
                sorted_dates = sorted(date_totals.items())
                chart = self.chart_generator.line_chart(
                    x_values=[d[0] for d in sorted_dates],
                    y_values=[d[1] for d in sorted_dates],
                    title="Amount Over Time",
                    xlabel="Date",
                    ylabel="Amount ($)",
                    fill_area=True,
                )
                charts.append(chart)
        
        context.charts = charts
        logger.info(f"Generated {len(charts)} charts")
        
        return context
    
    def _generate_analysis(self, context: AnalysisContext, max_iterations: int) -> AnalysisContext:
        """Phase 4: Generate analysis with reflection pattern."""
        logger.info("Phase 4: Generating analysis with reflection")
        
        calc_summary = "\n".join([
            f"- {c.metric_name}: {c.formatted_value} ({c.interpretation_guide})"
            for c in context.calculations[:20]
        ])
        
        sample_rows = context.working_data[:10]
        sample_data = json.dumps(sample_rows, indent=2, default=str)
        
        # Build explicit time context from parsed fiscal period
        time_context_parts = []
        
        # Add fiscal period details if available
        if context.parsed_query and context.parsed_query.time_period:
            tp = context.parsed_query.time_period
            time_context_parts.append(f"Fiscal Period: {tp.period_name}")
            time_context_parts.append(f"Date Range: {tp.start_date.strftime('%B %d, %Y')} through {tp.end_date.strftime('%B %d, %Y')}")
            time_context_parts.append(f"Fiscal Year: FY{tp.fiscal_year}")
            
            # Add fiscal year explanation (Feb start means FY named after ending year)
            if self.fiscal_calendar.fy_start_month == 2:
                fy_start_year = tp.fiscal_year - 1
                time_context_parts.append(
                    f"Note: FY{tp.fiscal_year} runs from February {fy_start_year} through January {tp.fiscal_year} "
                    f"(our fiscal year starts in February)"
                )
        
        # Also get actual transaction date range from data for reference
        date_range = "Not available"
        for col in context.raw_data.column_names:
            if 'date' in col.lower():
                dates = [row.get(col) for row in context.working_data if row.get(col)]
                if dates:
                    date_range = f"{min(dates)} to {max(dates)}"
                    time_context_parts.append(f"Transaction dates in data: {date_range}")
                break
        
        # Combine into full time context
        full_time_context = "\n".join(time_context_parts) if time_context_parts else date_range
        
        category_breakdown = ""
        category_calcs = [c for c in context.calculations if 'Total' in c.metric_name]
        if category_calcs:
            category_breakdown = "\n".join([
                f"- {c.metric_name}: {c.formatted_value}"
                for c in category_calcs[:10]
            ])
        
        # Build conversation context if available
        conversation_context = ""
        if context.session and context.session.context.has_context():
            conversation_context = f"\n## Previous Conversation Context\n{context.session.context.to_prompt_context()}\n"
        
        # Add filter summary to query context
        query_context = context.query
        if context.filter_summary:
            query_context += f"\n\n(Data filtered: {context.filter_summary})"
        
        # Add parsed query info
        parsed_info = ""
        if context.parsed_query:
            p = context.parsed_query
            parsed_info = f"\n## Detected Analysis Parameters\n"
            parsed_info += f"- Intent: {p.intent.value}\n"
            if p.time_period:
                parsed_info += f"- Time Period: {p.time_period.period_name} ({p.time_period.start_date} to {p.time_period.end_date})\n"
            if p.comparison_type:
                parsed_info += f"- Comparison: {p.comparison_type.value}\n"
            if p.departments:
                parsed_info += f"- Departments: {', '.join(p.departments)}\n"
            if p.accounts:
                parsed_info += f"- Accounts: {', '.join(p.accounts)}\n"
        
        # Get data interpretation context from configuration
        data_context_info = self.data_context.get_llm_context_summary()
        
        # Prepare statistical context
        statistical_context = context.statistical_context if context.statistical_context else ""
        if statistical_context:
            statistical_context = f"\n## Statistical Analysis Results\n{statistical_context}\n"
        
        # Use prompt manager for versioned prompts
        try:
            analysis_prompt = self.prompt_manager.get_prompt("financial_analysis")
            user_prompt = analysis_prompt.format(
            query=query_context,
                data_summary=f"- Total rows: {len(context.working_data)}\n- Date range: {date_range}\n- Columns available: {', '.join(context.raw_data.column_names)}",
            calculations=calc_summary or "No calculations available",
                time_context=full_time_context,
                filter_summary=f"Filtered data: {len(context.working_data)} rows",
                conversation_context=conversation_context + parsed_info + data_context_info,
                statistical_context=statistical_context,
            )
            system_prompt = analysis_prompt.system_prompt
        except FileNotFoundError as e:
            # Fallback to inline prompts if prompt manager fails
            logger.warning(f"Prompt manager failed: {e}. Using inline prompts.")
        except Exception as e:
            # Catch other errors (e.g., missing variables, YAML parsing errors)
            logger.warning(f"Prompt manager error: {e}. Using inline prompts.")
            user_prompt = f"""Analyze the following financial data and provide a professional analysis.

## User Query
{query_context}

## Data Summary
- Total rows: {len(context.working_data)}
- Date range: {date_range}
- Columns available: {', '.join(context.raw_data.column_names)}

## Pre-Calculated Metrics
{calc_summary or "No calculations available"}

## Sample Data (first 10 rows)
{sample_data}

## Data by Category (if applicable)
{category_breakdown or "No category breakdown available"}

{statistical_context}

{data_context_info}
{conversation_context}
{parsed_info}"""
            system_prompt = """You are a senior financial analyst with expertise in interpreting 
NetSuite financial data. You provide accurate, insightful analysis based strictly on 
the data provided.

## Core Principles
1. **Data-Grounded**: Every claim must reference specific data points
2. **Calculated Precision**: Use the provided calculation results - do not recalculate
3. **Actionable Insights**: Provide clear, specific recommendations
4. **Professional Tone**: Write for a CFO-level audience

## Analysis Structure
1. Executive Summary (2-3 sentences)
2. Key Findings (with specific numbers)
3. Trend Analysis (if applicable)
4. Recommendations (specific, actionable)

## Formatting for Slack
- Use *bold* for emphasis (Slack format)
- Use bullet points for lists
- Keep paragraphs concise
- Include specific dollar amounts and percentages"""
        
        response = self.router.generate_with_system(
            system_prompt=system_prompt,
            user_message=user_prompt,
        )
        
        analysis = response.content
        context.iteration_count = 1
        
        if max_iterations > 1:
            analysis, scores = self.evaluator.reflect_and_improve(
                analysis, max_iterations=max_iterations
            )
            context.iteration_count = len(scores)
            logger.info(f"Reflection scores: {scores}")
        
        context.analysis_text = analysis
        return context
    
    def _evaluate_analysis(self, context: AnalysisContext) -> AnalysisContext:
        """Phase 5: Final evaluation."""
        logger.info("Phase 5: Evaluating analysis")
        
        expected_values = {}  # Would come from Golden Dataset in production
        
        evaluation = self.evaluator.evaluate_analysis(
            analysis=context.analysis_text,
            calculations=context.calculations,
            expected_values=expected_values,
            data_summary=json.dumps(context.data_summary, indent=2, default=str),
        )
        
        context.evaluation = evaluation
        logger.info(
            f"Evaluation complete: accuracy={evaluation.objective_accuracy:.2%}, "
            f"qualitative={evaluation.average_qualitative_score:.1f}/10, "
            f"passes={evaluation.passes_threshold}"
        )
        
        return context
    
    def _build_response(self, context: AnalysisContext) -> AgentResponse:
        """Build the final response."""
        return AgentResponse(
            analysis=context.analysis_text,
            calculations=[c.to_dict() for c in context.calculations],
            charts=context.charts,
            evaluation_summary={
                "passes_threshold": context.evaluation.passes_threshold if context.evaluation else None,
                "objective_accuracy": context.evaluation.objective_accuracy if context.evaluation else None,
                "qualitative_score": context.evaluation.average_qualitative_score if context.evaluation else None,
                "suggestions": context.evaluation.improvement_suggestions if context.evaluation else [],
            },
            metadata={
                "query": context.query,
                "data_rows": context.raw_data.row_count,
                "filtered_rows": len(context.working_data),
                "iteration_count": context.iteration_count,
                "model_used": self.router.config.model_name,
                "generated_at": datetime.utcnow().isoformat(),
                "session_id": context.session.session_id if context.session else None,
                "parsed_intent": context.parsed_query.intent.value if context.parsed_query else None,
                "filter_summary": context.filter_summary,
            },
            trace_id=context.trace_id,
        )

def get_financial_analyst() -> FinancialAnalystAgent:
    """Get a configured Financial Analyst Agent."""
    return FinancialAnalystAgent()
