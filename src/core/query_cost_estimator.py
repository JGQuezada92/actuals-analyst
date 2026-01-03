"""
Query Cost Estimator

Estimates the cost (time, resources) of a query and warns users before
expensive queries. Provides optimization suggestions to help users
refine their queries for faster results.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.query_parser import ParsedQuery

logger = logging.getLogger(__name__)


@dataclass
class QueryCostEstimate:
    """
    Estimated cost/complexity of a query.
    
    Used to warn users before expensive queries and suggest optimizations.
    """
    estimated_rows: int
    estimated_time_seconds: int
    complexity: str  # "low", "medium", "high", "very_high"
    optimization_suggestions: List[str] = field(default_factory=list)
    should_warn_user: bool = False
    
    def to_dict(self):
        return {
            "estimated_rows": self.estimated_rows,
            "estimated_time_seconds": self.estimated_time_seconds,
            "estimated_time_formatted": self._format_time(self.estimated_time_seconds),
            "complexity": self.complexity,
            "optimization_suggestions": self.optimization_suggestions,
            "should_warn_user": self.should_warn_user,
        }
    
    @staticmethod
    def _format_time(seconds: int) -> str:
        """Format seconds into a human-readable string."""
        if seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            if remaining_seconds == 0:
                return f"{minutes} minute{'s' if minutes > 1 else ''}"
            return f"{minutes} minute{'s' if minutes > 1 else ''} {remaining_seconds}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours} hour{'s' if hours > 1 else ''} {minutes}m"


class QueryCostEstimator:
    """
    Estimates the cost of executing a query.
    
    Based on historical data patterns:
    - ~391,000 total rows in typical saved search
    - ~16,000 rows per month
    - ~1.5 seconds per 1000 rows for parallel RESTlet fetch
    """
    
    # Historical data for estimation
    TOTAL_ROWS_ESTIMATE = 200000
    ROWS_PER_MONTH = 16000
    
    # Time estimates (all queries use RESTlet with parallel fetch)
    SECONDS_PER_1000_ROWS_PARALLEL = 1.5
    
    # Thresholds
    HIGH_COMPLEXITY_ROWS = 50000
    VERY_HIGH_COMPLEXITY_ROWS = 150000
    WARN_THRESHOLD_SECONDS = 60  # Warn if estimated time > 1 minute
    
    def estimate(self, parsed_query: 'ParsedQuery') -> QueryCostEstimate:
        """
        Estimate the cost of a parsed query.
        
        Args:
            parsed_query: The parsed query to estimate
        
        Returns:
            QueryCostEstimate with estimated time, rows, and suggestions
        """
        # Estimate row count based on filters
        estimated_rows = self._estimate_row_count(parsed_query)
        
        # Estimate time (all queries use RESTlet with parallel fetch)
        estimated_time = self._estimate_time(estimated_rows)
        
        # Categorize complexity
        complexity = self._categorize_complexity(estimated_rows)
        
        # Generate optimization suggestions
        suggestions = self._generate_suggestions(parsed_query, complexity)
        
        # Determine if we should warn the user
        should_warn = (
            complexity in ["high", "very_high"] or
            estimated_time > self.WARN_THRESHOLD_SECONDS
        )
        
        estimate = QueryCostEstimate(
            estimated_rows=estimated_rows,
            estimated_time_seconds=estimated_time,
            complexity=complexity,
            optimization_suggestions=suggestions,
            should_warn_user=should_warn,
        )
        
        logger.info(
            f"Query cost estimate: {estimated_rows:,} rows, {estimated_time}s, "
            f"complexity={complexity}"
        )
        
        return estimate
    
    def _estimate_row_count(self, parsed_query: 'ParsedQuery') -> int:
        """
        Estimate the number of rows a query will return.
        
        Uses filter information to narrow down the estimate.
        """
        rows = self.TOTAL_ROWS_ESTIMATE
        
        # Time period filter (most significant reduction)
        if parsed_query.time_period:
            days = parsed_query.time_period.days
            months = max(days / 30.0, 0.5)  # At least half month
            rows = int(self.ROWS_PER_MONTH * months)
            logger.debug(f"Time filter: {months:.1f} months -> {rows} rows")
        
        # Department filter
        if parsed_query.departments:
            # Assume each department is ~15% of total data
            dept_factor = min(0.15 * len(parsed_query.departments), 0.6)
            rows = int(rows * dept_factor)
            logger.debug(f"Department filter: {parsed_query.departments} -> {rows} rows")
        
        # Account type filter
        if parsed_query.account_type_filter:
            values = parsed_query.account_type_filter.get("values", [])
            # Assume each account prefix is ~20% of data
            account_factor = min(0.2 * len(values), 0.8)
            rows = int(rows * account_factor)
            logger.debug(f"Account filter: {values} -> {rows} rows")
        
        # Transaction type filter
        if parsed_query.transaction_type_filter:
            # Assume each transaction type is ~10% of data
            type_factor = min(0.1 * len(parsed_query.transaction_type_filter), 0.5)
            rows = int(rows * type_factor)
            logger.debug(f"Transaction type filter: {parsed_query.transaction_type_filter} -> {rows} rows")
        
        return max(rows, 100)  # Minimum estimate
    
    def _estimate_time(self, estimated_rows: int) -> int:
        """
        Estimate execution time in seconds.
        
        All queries use RESTlet with parallel fetch.
        """
        # Use parallel RESTlet fetch rate
        seconds = (estimated_rows / 1000) * self.SECONDS_PER_1000_ROWS_PARALLEL
        
        # Add overhead for parsing, filtering, etc.
        seconds += 2  # Base overhead
        
        return max(int(seconds), 1)
    
    def _categorize_complexity(self, estimated_rows: int) -> str:
        """Categorize query complexity based on estimated rows."""
        if estimated_rows < 10000:
            return "low"
        elif estimated_rows < self.HIGH_COMPLEXITY_ROWS:
            return "medium"
        elif estimated_rows < self.VERY_HIGH_COMPLEXITY_ROWS:
            return "high"
        else:
            return "very_high"
    
    def _generate_suggestions(
        self,
        parsed_query: 'ParsedQuery',
        complexity: str,
    ) -> List[str]:
        """
        Generate optimization suggestions based on the query.
        
        Suggestions help users refine their query for faster results.
        """
        suggestions = []
        
        # Check for missing filters
        if not parsed_query.time_period:
            suggestions.append(
                "Add a time period (e.g., 'YTD', 'last month', 'Q3') to reduce data volume significantly"
            )
        
        if not parsed_query.departments:
            suggestions.append(
                "Specify a department (e.g., 'Marketing', 'R&D') to narrow results"
            )
        
        if not parsed_query.account_type_filter:
            suggestions.append(
                "Be specific about what you're looking for (e.g., 'revenue' vs 'expenses') "
                "to filter by account type"
            )
        
        # Suggest breaking up complex queries
        if complexity in ["high", "very_high"]:
            suggestions.append(
                "Consider breaking this into smaller queries (e.g., by quarter or department)"
            )
        
        # If we have suggestions but query could be refined
        if parsed_query.time_period and not parsed_query.departments:
            if complexity in ["medium", "high"]:
                suggestions.append(
                    "Adding a department filter would make this query much faster"
                )
        
        return suggestions
    
    def format_user_warning(self, estimate: QueryCostEstimate) -> str:
        """
        Format a user-friendly warning message about query cost.
        
        Returns:
            Formatted warning message for display to user
        """
        time_str = estimate._format_time(estimate.estimated_time_seconds)
        
        msg = f"[!] This query may take approximately *{time_str}*.\n"
        msg += f"Estimated data volume: {estimate.estimated_rows:,} rows\n"
        
        # All queries use RESTlet for accurate financial data
        if False:  # SuiteQL removed
            msg += "[+] Using optimized database filtering\n"
        else:
            msg += "[!] Requires full data fetch (no filters applied)\n"
        
        if estimate.optimization_suggestions:
            msg += "\n*To speed this up, you could:*\n"
            for suggestion in estimate.optimization_suggestions:
                msg += f"- {suggestion}\n"
        
        return msg


# Singleton instance
_estimator: Optional[QueryCostEstimator] = None


def get_query_cost_estimator() -> QueryCostEstimator:
    """Get the query cost estimator instance."""
    global _estimator
    if _estimator is None:
        _estimator = QueryCostEstimator()
    return _estimator

