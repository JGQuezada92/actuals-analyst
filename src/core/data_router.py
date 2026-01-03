"""
Smart Data Source Router

Intelligently routes queries to the optimal data source:
1. Pre-aggregated cache - Sub-second responses for common patterns
2. RESTlet full fetch - Complete data when needed (minutes)

Note: SuiteQL optimization has been removed due to accuracy issues
(SuiteQL uses transaction date instead of posting period for financial reporting).

This router analyzes the query and makes routing decisions based on:
- Query pattern matching (does it match a cached aggregation?)
- Data freshness requirements
- Estimated execution time
"""
import logging
from dataclasses import dataclass
from typing import Optional, Any, Union
from enum import Enum

from src.core.query_parser import ParsedQuery, QueryIntent
from src.core.fiscal_calendar import get_fiscal_calendar
from src.data.aggregation_cache import (
    AggregationCache, AggregatedData,
    get_aggregation_cache, get_aggregation_computer
)

logger = logging.getLogger(__name__)


class DataSource(Enum):
    """Available data sources in priority order."""
    PRE_AGGREGATED_CACHE = "cache"
    RESTLET_FULL = "restlet"


@dataclass
class RoutingDecision:
    """
    Result of the routing decision process.
    
    Contains the chosen data source, reasoning, and fallback options.
    """
    source: DataSource
    reason: str
    estimated_time_seconds: int
    fallback_source: Optional[DataSource] = None
    aggregation_type: Optional[str] = None  # If using cache, which aggregation
    
    def to_dict(self):
        return {
            "source": self.source.value,
            "reason": self.reason,
            "estimated_time_seconds": self.estimated_time_seconds,
            "fallback_source": self.fallback_source.value if self.fallback_source else None,
            "aggregation_type": self.aggregation_type,
        }


class DataRouter:
    """
    Routes queries to the optimal data source.
    
    Decision priority:
    1. Pre-aggregated cache (if query matches a cached pattern)
    2. RESTlet full fetch (for all queries requiring accurate financial data)
    
    Note: SuiteQL optimization removed - all queries use RESTlet for accuracy.
    """
    
    # Mapping of query patterns to aggregation types
    AGGREGATION_PATTERNS = {
        "ytd_by_department": {
            "intents": [QueryIntent.SUMMARY, QueryIntent.TOTAL, QueryIntent.BREAKDOWN],
            "requires_time_period": True,
            "group_by": "department",
        },
        "ytd_by_account_type": {
            "intents": [QueryIntent.SUMMARY, QueryIntent.TOTAL, QueryIntent.BREAKDOWN],
            "requires_time_period": True,
            "group_by": "account",
        },
        "monthly_trend": {
            "intents": [QueryIntent.TREND],
            "requires_time_period": True,
            "group_by": None,
        },
        "department_by_month": {
            "intents": [QueryIntent.TREND, QueryIntent.BREAKDOWN],
            "requires_time_period": True,
            "requires_department": True,
        },
        "top_accounts": {
            "intents": [QueryIntent.TOP_N],
            "requires_time_period": True,
        },
    }
    
    def __init__(self, aggregation_cache: AggregationCache = None):
        self.aggregation_cache = aggregation_cache or get_aggregation_cache()
        self.fiscal_calendar = get_fiscal_calendar()
    
    def route(self, parsed_query: ParsedQuery) -> RoutingDecision:
        """
        Determine the best data source for a query.
        
        Args:
            parsed_query: The parsed query to route
        
        Returns:
            RoutingDecision with the chosen source and reasoning
        """
        # Priority 1: Check if query matches a cached aggregation
        aggregation_match = self._match_aggregation_pattern(parsed_query)
        if aggregation_match:
            # Verify the cache actually has this data
            current_fy = self.fiscal_calendar.get_current_fiscal_year()
            cached = self.aggregation_cache.get(aggregation_match, current_fy.fiscal_year)
            
            if cached and not cached.is_stale:
                logger.info(f"Routing to cache: {aggregation_match}")
                return RoutingDecision(
                    source=DataSource.PRE_AGGREGATED_CACHE,
                    reason=f"Query matches pre-computed aggregation: {aggregation_match}",
                    estimated_time_seconds=1,
                    fallback_source=DataSource.RESTLET_FULL,
                    aggregation_type=aggregation_match,
                )
        
        # Always use RESTlet for accurate financial data (posting period dates)
        logger.info("Routing to RESTlet full fetch")
        return RoutingDecision(
            source=DataSource.RESTLET_FULL,
            reason="Complex query requires full dataset",
            estimated_time_seconds=300,  # ~5 minutes with parallel fetch
            fallback_source=None,
        )
    
    def _match_aggregation_pattern(self, parsed_query: ParsedQuery) -> Optional[str]:
        """
        Check if a query matches a cached aggregation pattern.
        
        Returns the aggregation type if matched, None otherwise.
        """
        # Check if we have a time period for current fiscal year
        if not parsed_query.time_period:
            return None
        
        current_fy = self.fiscal_calendar.get_current_fiscal_year()
        if parsed_query.time_period.fiscal_year != current_fy.fiscal_year:
            return None
        
        # Check each pattern
        for agg_type, pattern in self.AGGREGATION_PATTERNS.items():
            if parsed_query.intent not in pattern.get("intents", []):
                continue
            
            if pattern.get("requires_department") and not parsed_query.departments:
                continue
            
            if pattern.get("group_by"):
                query_group_by = parsed_query.group_by
                pattern_group_by = pattern["group_by"]
                
                # Handle list format
                if isinstance(query_group_by, list):
                    # Check if pattern's group_by is in the list
                    if pattern_group_by not in query_group_by:
                        # Check if query implies this grouping
                        if agg_type == "ytd_by_department" and not query_group_by:
                            # Default to department grouping for breakdowns
                            if parsed_query.intent == QueryIntent.BREAKDOWN:
                                return agg_type
                        continue
                elif query_group_by != pattern_group_by:
                    # Check if query implies this grouping
                    if agg_type == "ytd_by_department" and not query_group_by:
                        # Default to department grouping for breakdowns
                        if parsed_query.intent == QueryIntent.BREAKDOWN:
                            return agg_type
                    continue
            
            # Pattern matches
            return agg_type
        
        return None
    


class SmartDataRetriever:
    """
    High-level data retrieval with intelligent source routing.
    
    Combines the router, cache, and NetSuite client to provide
    transparent data access with automatic optimization.
    """
    
    def __init__(
        self,
        router: DataRouter = None,
        aggregation_cache: AggregationCache = None,
        data_retriever=None,
    ):
        self.router = router or DataRouter()
        self.aggregation_cache = aggregation_cache or get_aggregation_cache()
        
        # Lazy import to avoid circular dependency
        self._data_retriever = data_retriever
    
    @property
    def data_retriever(self):
        if self._data_retriever is None:
            from src.tools.netsuite_client import get_data_retriever
            self._data_retriever = get_data_retriever()
        return self._data_retriever
    
    def get_data(
        self,
        parsed_query: ParsedQuery,
        bypass_cache: bool = False,
    ) -> Union[AggregatedData, Any]:
        """
        Get data for a query using the optimal source.
        
        Args:
            parsed_query: The parsed query
            bypass_cache: If True, skip pre-aggregated cache
        
        Returns:
            Either AggregatedData (from cache) or SavedSearchResult (from API)
        """
        decision = self.router.route(parsed_query)
        logger.info(f"Data routing: {decision.source.value} - {decision.reason}")
        
        try:
            if decision.source == DataSource.PRE_AGGREGATED_CACHE and not bypass_cache:
                return self._get_from_cache(parsed_query, decision)
            
            else:
                return self._get_via_restlet(parsed_query)
                
        except Exception as e:
            if decision.fallback_source:
                logger.warning(f"Primary source failed ({e}), falling back to {decision.fallback_source.value}")
                return self._get_from_source(decision.fallback_source, parsed_query)
            raise
    
    def _get_from_cache(
        self,
        parsed_query: ParsedQuery,
        decision: RoutingDecision,
    ) -> AggregatedData:
        """Get data from pre-aggregated cache."""
        current_fy = self.router.fiscal_calendar.get_current_fiscal_year()
        cached = self.aggregation_cache.get(decision.aggregation_type, current_fy.fiscal_year)
        
        if cached:
            logger.info(f"Cache hit: {decision.aggregation_type} ({cached.row_count} rows)")
            return cached
        
        # Cache miss - fall back
        raise ValueError("Cache miss after routing decision")
    
    def _get_via_restlet(self, parsed_query: ParsedQuery):
        """Get data via RESTlet full fetch."""
        return self.data_retriever.get_saved_search_data(
            parsed_query=parsed_query,
            use_suiteql_optimization=False,
        )
    
    def _get_from_source(self, source: DataSource, parsed_query: ParsedQuery):
        """Get data from a specific source."""
        if source == DataSource.RESTLET_FULL:
            return self._get_via_restlet(parsed_query)
        else:
            raise ValueError(f"Cannot fall back to {source}")


# Singleton instances
_router: Optional[DataRouter] = None
_smart_retriever: Optional[SmartDataRetriever] = None


def get_data_router() -> DataRouter:
    """Get the data router instance."""
    global _router
    if _router is None:
        _router = DataRouter()
    return _router


def get_smart_data_retriever() -> SmartDataRetriever:
    """Get the smart data retriever instance."""
    global _smart_retriever
    if _smart_retriever is None:
        _smart_retriever = SmartDataRetriever()
    return _smart_retriever

