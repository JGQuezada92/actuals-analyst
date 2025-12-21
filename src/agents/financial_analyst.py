"""
Financial Analyst Agent

Implements the Accuracy-First Framework's agentic design patterns:
1. Tool Use Pattern: Calculations performed by deterministic code
2. Reflection Pattern: Self-critique and iterative refinement
3. Planning Pattern: Structured analysis approach

This agent analyzes NetSuite saved search data and produces
professional financial analysis with verified accuracy.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from src.core.model_router import get_router, Message, LLMResponse, ModelRouter
from src.tools.netsuite_client import NetSuiteDataRetriever, SavedSearchResult, get_data_retriever
from src.tools.calculator import FinancialCalculator, CalculationResult, get_calculator, MetricType
from src.tools.charts import ChartGenerator, ChartOutput, get_chart_generator
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
    calculations: List[CalculationResult] = field(default_factory=list)
    charts: List[ChartOutput] = field(default_factory=list)
    analysis_text: str = ""
    evaluation: Optional[EvaluationResult] = None
    iteration_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "data_row_count": self.raw_data.row_count,
            "data_columns": self.raw_data.column_names,
            "calculation_count": len(self.calculations),
            "chart_count": len(self.charts),
            "iteration_count": self.iteration_count,
            "passes_evaluation": self.evaluation.passes_threshold if self.evaluation else None,
        }

@dataclass
class AgentResponse:
    """Final response from the agent."""
    analysis: str
    calculations: List[Dict[str, Any]]
    charts: List[ChartOutput]
    evaluation_summary: Dict[str, Any]
    metadata: Dict[str, Any]
    
    @property
    def slack_formatted(self) -> str:
        """Format analysis for Slack."""
        return self.analysis
    
    @property
    def chart_files(self) -> List[str]:
        """Get list of chart file paths for Slack upload."""
        return [c.file_path for c in self.charts]

class FinancialAnalystAgent:
    """
    The main Financial Analyst Agent.
    
    Orchestrates data retrieval, calculations, analysis generation,
    and evaluation in a rigorous, accuracy-first workflow.
    """
    
    SYSTEM_PROMPT = """You are a senior financial analyst with expertise in interpreting 
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
- Include specific dollar amounts and percentages
"""

    ANALYSIS_PROMPT = """Analyze the following financial data and provide a professional analysis.

## User Query
{query}

## Data Summary
- Total rows: {row_count}
- Date range: {date_range}
- Columns available: {columns}

## Pre-Calculated Metrics
{calculations}

## Sample Data (first 10 rows)
{sample_data}

## Data by Category (if applicable)
{category_breakdown}

Provide a comprehensive analysis following the structure in your instructions.
Remember: Use the pre-calculated metrics exactly as provided - do not recalculate.
"""
    
    def __init__(
        self,
        data_retriever: Optional[NetSuiteDataRetriever] = None,
        calculator: Optional[FinancialCalculator] = None,
        chart_generator: Optional[ChartGenerator] = None,
        evaluator: Optional[EvaluationHarness] = None,
        router: Optional[ModelRouter] = None,
    ):
        self.data_retriever = data_retriever or get_data_retriever()
        self.calculator = calculator or get_calculator()
        self.chart_generator = chart_generator or get_chart_generator()
        self.evaluator = evaluator or get_evaluation_harness()
        self.router = router or get_router()
        self.config = get_config()
    
    async def analyze(
        self,
        query: str,
        search_id: Optional[str] = None,
        include_charts: bool = True,
        max_iterations: int = 3,
    ) -> AgentResponse:
        """
        Main analysis entry point.
        
        Args:
            query: User's analysis question
            search_id: NetSuite saved search ID (uses default if None)
            include_charts: Whether to generate visualizations
            max_iterations: Max reflection iterations for quality
        
        Returns:
            Complete AgentResponse with analysis, charts, and evaluation
        """
        logger.info(f"Starting analysis for query: {query[:100]}...")
        
        # Phase 1: Data Retrieval
        context = await self._retrieve_data(query, search_id)
        
        # Phase 2: Deterministic Calculations
        context = self._perform_calculations(context)
        
        # Phase 3: Chart Generation
        if include_charts:
            context = self._generate_charts(context)
        
        # Phase 4: Analysis Generation with Reflection
        context = self._generate_analysis(context, max_iterations)
        
        # Phase 5: Final Evaluation
        context = self._evaluate_analysis(context)
        
        return self._build_response(context)
    
    def analyze_sync(
        self,
        query: str,
        search_id: Optional[str] = None,
        include_charts: bool = True,
        max_iterations: int = 3,
    ) -> AgentResponse:
        """Synchronous version of analyze for non-async contexts."""
        import asyncio
        return asyncio.run(self.analyze(query, search_id, include_charts, max_iterations))
    
    async def _retrieve_data(self, query: str, search_id: Optional[str]) -> AnalysisContext:
        """Phase 1: Retrieve data from NetSuite."""
        logger.info("Phase 1: Retrieving data from NetSuite")
        
        result = self.data_retriever.get_saved_search_data(search_id)
        summary = self.data_retriever.get_data_summary(result)
        
        logger.info(f"Retrieved {result.row_count} rows with columns: {result.column_names}")
        
        return AnalysisContext(
            query=query,
            raw_data=result,
            data_summary=summary,
        )
    
    def _perform_calculations(self, context: AnalysisContext) -> AnalysisContext:
        """Phase 2: Perform deterministic calculations."""
        logger.info("Phase 2: Performing deterministic calculations")
        
        calculations = []
        data = context.raw_data.data
        columns = [c.lower() for c in context.raw_data.column_names]
        
        # Auto-detect and calculate relevant metrics based on available columns
        category_fields = ['type', 'account', 'department', 'class', 'location', 'category']
        amount_fields = ['amount', 'total', 'value', 'balance', 'credit', 'debit']
        
        # Find amount field
        amount_field = None
        for col in context.raw_data.column_names:
            if col.lower() in amount_fields or 'amount' in col.lower():
                amount_field = col
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
            
            # Sum by category if available
            for cat_col in context.raw_data.column_names:
                if cat_col.lower() in category_fields or 'type' in cat_col.lower():
                    category_sums = self.calculator.sum_by_category(data, amount_field, cat_col)
                    calculations.extend(category_sums.values())
                    break
            
            # Trend analysis if date field exists
            date_fields = ['date', 'trandate', 'created', 'posted']
            for col in context.raw_data.column_names:
                if col.lower() in date_fields or 'date' in col.lower():
                    trend = self.calculator.time_series_trend(data, amount_field, col)
                    calculations.append(trend)
                    break
        
        context.calculations = calculations
        logger.info(f"Completed {len(calculations)} calculations")
        
        return context
    
    def _generate_charts(self, context: AnalysisContext) -> AnalysisContext:
        """Phase 3: Generate visualizations."""
        logger.info("Phase 3: Generating charts")
        
        charts = []
        data = context.raw_data.data
        
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
            if 'date' in col_lower:
                date_field = col
        
        # Generate category breakdown chart
        if amount_field and category_field:
            category_totals: Dict[str, float] = {}
            for row in data:
                cat = str(row.get(category_field, 'Unknown'))
                amt = float(row.get(amount_field, 0) or 0)
                category_totals[cat] = category_totals.get(cat, 0) + amt
            
            sorted_cats = sorted(category_totals.items(), key=lambda x: abs(x[1]), reverse=True)[:10]
            
            if sorted_cats:
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
            
            if len(date_totals) >= 3:
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
        
        sample_rows = context.raw_data.data[:10]
        sample_data = json.dumps(sample_rows, indent=2, default=str)
        
        date_range = "Not available"
        for col in context.raw_data.column_names:
            if 'date' in col.lower():
                dates = [row.get(col) for row in context.raw_data.data if row.get(col)]
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
        
        prompt = self.ANALYSIS_PROMPT.format(
            query=context.query,
            row_count=context.raw_data.row_count,
            date_range=date_range,
            columns=", ".join(context.raw_data.column_names),
            calculations=calc_summary or "No calculations available",
            sample_data=sample_data,
            category_breakdown=category_breakdown or "No category breakdown available",
        )
        
        response = self.router.generate_with_system(
            system_prompt=self.SYSTEM_PROMPT,
            user_message=prompt,
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
                "iteration_count": context.iteration_count,
                "model_used": self.router.config.model_name,
                "generated_at": datetime.utcnow().isoformat(),
            },
        )

def get_financial_analyst() -> FinancialAnalystAgent:
    """Get a configured Financial Analyst Agent."""
    return FinancialAnalystAgent()
