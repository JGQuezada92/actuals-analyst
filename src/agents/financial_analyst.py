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
from src.core.memory import Session, SessionManager, get_session_manager
from src.core.data_context import DataContext, get_data_context
from src.core.financial_semantics import apply_disambiguation_choice, get_semantic_term
from src.core.query_cost_estimator import QueryCostEstimator, QueryCostEstimate, get_query_cost_estimator
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
            if session is None and session_id:
                session = self.session_manager.get_session(session_id)
            if session is None:
                session = self.session_manager.create_session()
            
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
                    parsed_query = self._apply_disambiguation(parsed_query, disambiguation_choice)
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
                context = self._generate_analysis(context, max_iterations)
                if span:
                    span.attributes["iteration_count"] = context.iteration_count
            
            # Phase 5: Final Evaluation
            with tracer.start_span("phase_5_evaluation", SpanKind.EVALUATION) as span:
                context = self._evaluate_analysis(context)
                if span and context.evaluation:
                    span.attributes["evaluation_score"] = context.evaluation.average_qualitative_score
                    span.attributes["passed_threshold"] = context.evaluation.passes_threshold
                    tracer.record_evaluation(
                        score=context.evaluation.average_qualitative_score,
                        passed=context.evaluation.passes_threshold
                    )
            
            # Update session with this conversation
            self._update_session(context)
            
            return self._build_response(context)
    
    def _apply_disambiguation(
        self,
        parsed_query: ParsedQuery,
        choices: Dict[str, int],
    ) -> ParsedQuery:
        """
        Apply user's disambiguation choices to update the parsed query.
        
        Args:
            parsed_query: The original parsed query with ambiguous terms
            choices: Dict mapping term -> choice index (1-based for user-friendly display)
        
        Returns:
            Updated ParsedQuery with resolved semantic filters
        """
        from src.core.financial_semantics import SemanticCategory
        
        resolved_terms = set()
        unresolved_terms = []
        
        for term, choice_index in choices.items():
            # Check if this is a department disambiguation from registry
            if term in parsed_query.department_disambiguation_options:
                options = parsed_query.department_disambiguation_options[term]
                # Convert 1-based user choice to 0-based index
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
                        parsed_query.account_type_filter = {
                            "filter_type": resolved.filter_type.value,
                            "values": resolved.filter_values,
                        }
                    elif resolved.category == SemanticCategory.DEPARTMENT:
                        parsed_query.departments.extend(resolved.filter_values)
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
    
    def _build_disambiguation_response(
        self,
        query: str,
        parsed_query: ParsedQuery,
        session: Optional[Session],
    ) -> AgentResponse:
        """
        Build a response asking for clarification on ambiguous terms.
        """
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
        if parsed.departments:
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
        
        context.filtered_data = data
        context.filter_summary = f"Filtered {context.raw_data.row_count} -> {len(data)} rows"
        
        if filters_applied:
            context.filter_summary += f" ({', '.join(filters_applied)})"
        
        return context
    
    def _update_session(self, context: AnalysisContext):
        """Update the session with this conversation turn."""
        if not context.session:
            return
        
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
        
        date_range = "Not available"
        for col in context.raw_data.column_names:
            if 'date' in col.lower():
                dates = [row.get(col) for row in context.working_data if row.get(col)]
                if dates:
                    date_range = f"{min(dates)} to {max(dates)}"
                break
        
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
                time_context=date_range,
                filter_summary=f"Filtered data: {len(context.working_data)} rows",
                conversation_context=conversation_context + parsed_info + data_context_info,
                statistical_context=statistical_context,
            )
            system_prompt = analysis_prompt.system_prompt
        except FileNotFoundError:
            # Fallback to inline prompts if prompt manager fails
            logger.warning("Prompt manager failed, using inline prompts")
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
