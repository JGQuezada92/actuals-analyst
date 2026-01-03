"""
Query Decomposition Engine

Breaks complex queries into executable sub-queries (components) that can be
processed in dependency order. This enables handling of queries like:
- "Compare Marketing and R&D spend by quarter YoY showing top 5 accounts"
- "Monthly revenue trend vs same period last year"

Each component represents a discrete operation (data fetch, aggregation, 
comparison, ranking) that produces a result used by dependent components.
"""
import logging
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union
from enum import Enum
from collections import defaultdict

from src.core.query_parser import ParsedQuery, QueryIntent, ComparisonType
from src.core.fiscal_calendar import FiscalPeriod, get_fiscal_calendar

logger = logging.getLogger(__name__)


class QueryComponentType(Enum):
    """Types of query components."""
    DATA_FETCH = "data_fetch"
    AGGREGATION = "aggregation"
    COMPARISON = "comparison"
    RANKING = "ranking"
    CALCULATION = "calculation"
    FILTER = "filter"


@dataclass
class QueryComponent:
    """
    A single component in a decomposed query.
    
    Represents one discrete operation in the query execution pipeline.
    """
    component_id: str
    component_type: QueryComponentType
    description: str
    dependencies: List[str] = field(default_factory=list)  # IDs of components this depends on
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "component_id": self.component_id,
            "component_type": self.component_type.value,
            "description": self.description,
            "dependencies": self.dependencies,
            "parameters": self.parameters,
        }


@dataclass
class DecomposedQuery:
    """
    A query broken down into executable components.
    
    Components are ordered by dependencies so they can be executed sequentially,
    with each component having access to its dependencies' results.
    """
    original_query: str
    parsed_query: ParsedQuery
    components: List[QueryComponent]
    execution_order: List[str]  # Component IDs in execution order
    estimated_complexity: str  # "simple", "moderate", "complex"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_query": self.original_query,
            "components": [c.to_dict() for c in self.components],
            "execution_order": self.execution_order,
            "estimated_complexity": self.estimated_complexity,
        }
    
    def get_component(self, component_id: str) -> Optional[QueryComponent]:
        """Get a component by ID."""
        for c in self.components:
            if c.component_id == component_id:
                return c
        return None


class QueryDecomposer:
    """
    Decomposes complex queries into executable components.
    
    Analyzes the parsed query to identify:
    - Data fetches required (main period, comparison period)
    - Aggregations needed (by department, by account, by month)
    - Comparisons (YoY, MoM, vs budget)
    - Rankings (top N)
    - Calculations (percentages, variances)
    """
    
    def __init__(self):
        self.fiscal_calendar = get_fiscal_calendar()
    
    def decompose(self, query: str, parsed_query: ParsedQuery) -> DecomposedQuery:
        """
        Decompose a query into executable components.
        
        Args:
            query: The original query string
            parsed_query: The parsed query structure
        
        Returns:
            DecomposedQuery with ordered components
        """
        components = []
        
        # Step 1: Always start with primary data fetch
        primary_fetch = self._create_data_fetch_component(
            parsed_query,
            component_id="fetch_primary",
            description="Fetch primary data",
            period=parsed_query.time_period,
        )
        components.append(primary_fetch)
        
        # Step 2: Add comparison period fetch if needed
        if parsed_query.comparison_type and parsed_query.comparison_period:
            comparison_fetch = self._create_data_fetch_component(
                parsed_query,
                component_id="fetch_comparison",
                description=f"Fetch comparison data ({parsed_query.comparison_type.value})",
                period=parsed_query.comparison_period,
            )
            components.append(comparison_fetch)
        
        # Step 3: Add aggregation if grouping is requested
        if parsed_query.group_by or parsed_query.intent == QueryIntent.BREAKDOWN:
            group_by = parsed_query.group_by or [self._infer_group_by(parsed_query)]
            # Ensure it's a list for backward compatibility
            if isinstance(group_by, str):
                group_by = [group_by]
            elif not isinstance(group_by, list):
                group_by = []
            
            agg_component = self._create_aggregation_component(
                parsed_query,
                group_by=group_by,
                dependencies=["fetch_primary"],
            )
            components.append(agg_component)
            
            # If comparison, also aggregate comparison data
            if parsed_query.comparison_type and parsed_query.comparison_period:
                comp_agg = self._create_aggregation_component(
                    parsed_query,
                    group_by=group_by,
                    component_id="aggregate_comparison",
                    dependencies=["fetch_comparison"],
                    description=f"Aggregate comparison data by {', '.join(group_by) if isinstance(group_by, list) else group_by}",
                )
                components.append(comp_agg)
        
        # Step 4: Add comparison calculation if needed
        if parsed_query.comparison_type and parsed_query.comparison_period:
            comparison_deps = ["fetch_primary", "fetch_comparison"]
            
            # If we have aggregations, depend on those instead
            if parsed_query.group_by or parsed_query.intent == QueryIntent.BREAKDOWN:
                comparison_deps = ["aggregate_primary", "aggregate_comparison"]
            
            comp_component = self._create_comparison_component(
                parsed_query,
                dependencies=comparison_deps,
            )
            components.append(comp_component)
        
        # Step 5: Add ranking if top N is requested
        if parsed_query.top_n:
            # Depend on the latest component
            last_component = components[-1].component_id
            ranking_component = self._create_ranking_component(
                parsed_query,
                dependencies=[last_component],
            )
            components.append(ranking_component)
        
        # Step 6: Determine execution order via topological sort
        execution_order = self._topological_sort(components)
        
        # Step 7: Estimate complexity
        complexity = self._estimate_complexity(components)
        
        logger.info(
            f"Decomposed query into {len(components)} components: "
            f"{[c.component_type.value for c in components]}, complexity={complexity}"
        )
        
        return DecomposedQuery(
            original_query=query,
            parsed_query=parsed_query,
            components=components,
            execution_order=execution_order,
            estimated_complexity=complexity,
        )
    
    def _create_data_fetch_component(
        self,
        parsed_query: ParsedQuery,
        component_id: str,
        description: str,
        period: Optional[FiscalPeriod],
    ) -> QueryComponent:
        """Create a data fetch component."""
        return QueryComponent(
            component_id=component_id,
            component_type=QueryComponentType.DATA_FETCH,
            description=description,
            dependencies=[],  # Data fetches have no dependencies
            parameters={
                "time_period": period.to_dict() if period else None,
                "departments": parsed_query.departments,
                "account_type_filter": parsed_query.account_type_filter,
                "transaction_type_filter": parsed_query.transaction_type_filter,
                "subsidiaries": parsed_query.subsidiaries,
            },
        )
    
    def _create_aggregation_component(
        self,
        parsed_query: ParsedQuery,
        group_by: Union[str, List[str]],
        dependencies: List[str],
        component_id: str = "aggregate_primary",
        description: str = None,
    ) -> QueryComponent:
        """Create an aggregation component."""
        # Normalize group_by to list
        if isinstance(group_by, str):
            group_by_list = [group_by]
        else:
            group_by_list = group_by if isinstance(group_by, list) else []
        
        group_by_display = ", ".join(group_by_list) if group_by_list else "none"
        return QueryComponent(
            component_id=component_id,
            component_type=QueryComponentType.AGGREGATION,
            description=description or f"Aggregate data by {group_by_display}",
            dependencies=dependencies,
            parameters={
                "group_by": group_by_list,
                "metrics": ["sum", "count"],
            },
        )
    
    def _create_comparison_component(
        self,
        parsed_query: ParsedQuery,
        dependencies: List[str],
    ) -> QueryComponent:
        """Create a comparison component."""
        return QueryComponent(
            component_id="compare",
            component_type=QueryComponentType.COMPARISON,
            description=f"Compare {parsed_query.comparison_type.value}",
            dependencies=dependencies,
            parameters={
                "comparison_type": parsed_query.comparison_type.value,
                "current_period": parsed_query.time_period.period_name if parsed_query.time_period else None,
                "prior_period": parsed_query.comparison_period.period_name if parsed_query.comparison_period else None,
                "calculate_variance": True,
                "calculate_percentage": True,
            },
        )
    
    def _create_ranking_component(
        self,
        parsed_query: ParsedQuery,
        dependencies: List[str],
    ) -> QueryComponent:
        """Create a ranking component."""
        return QueryComponent(
            component_id="rank",
            component_type=QueryComponentType.RANKING,
            description=f"Select top {parsed_query.top_n}",
            dependencies=dependencies,
            parameters={
                "top_n": parsed_query.top_n,
                "sort_by": parsed_query.sort_by or "amount",
                "ascending": parsed_query.sort_ascending,
            },
        )
    
    def _infer_group_by(self, parsed_query: ParsedQuery) -> str:
        """Infer grouping dimension from query context."""
        # If departments mentioned, group by department
        if parsed_query.departments:
            return "account"
        
        # If account filter, group by department
        if parsed_query.account_type_filter:
            return "department"
        
        # Default to department for breakdown
        return "department"
    
    def _topological_sort(self, components: List[QueryComponent]) -> List[str]:
        """
        Sort components in dependency order (topological sort).
        
        Returns component IDs in the order they should be executed.
        """
        # Build dependency graph
        in_degree = {c.component_id: 0 for c in components}
        graph = defaultdict(list)
        
        for c in components:
            for dep in c.dependencies:
                graph[dep].append(c.component_id)
                in_degree[c.component_id] += 1
        
        # Kahn's algorithm
        queue = [cid for cid, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            cid = queue.pop(0)
            result.append(cid)
            
            for neighbor in graph[cid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        if len(result) != len(components):
            # Cycle detected, fall back to simple ordering
            logger.warning("Cycle detected in component dependencies")
            return [c.component_id for c in components]
        
        return result
    
    def _estimate_complexity(self, components: List[QueryComponent]) -> str:
        """Estimate query complexity based on components."""
        num_components = len(components)
        
        # Count component types
        has_comparison = any(c.component_type == QueryComponentType.COMPARISON for c in components)
        has_aggregation = any(c.component_type == QueryComponentType.AGGREGATION for c in components)
        has_ranking = any(c.component_type == QueryComponentType.RANKING for c in components)
        num_fetches = sum(1 for c in components if c.component_type == QueryComponentType.DATA_FETCH)
        
        if num_components <= 2 and num_fetches == 1:
            return "simple"
        elif has_comparison or num_fetches > 1 or (has_aggregation and has_ranking):
            return "complex"
        else:
            return "moderate"


class QueryExecutor:
    """
    Executes decomposed queries component by component.
    
    Manages the execution flow, passing results between components
    based on their dependencies.
    """
    
    def __init__(self, data_retriever=None, data_processor=None, calculator=None):
        from src.tools.netsuite_client import get_data_retriever
        from src.tools.data_processor import get_data_processor
        from src.tools.calculator import get_calculator
        
        self.data_retriever = data_retriever or get_data_retriever()
        self.data_processor = data_processor or get_data_processor()
        self.calculator = calculator or get_calculator()
    
    def execute(self, decomposed: DecomposedQuery) -> Dict[str, Any]:
        """
        Execute a decomposed query.
        
        Args:
            decomposed: The decomposed query with ordered components
        
        Returns:
            Dict mapping component IDs to their results
        """
        results = {}
        
        for component_id in decomposed.execution_order:
            component = decomposed.get_component(component_id)
            if not component:
                logger.warning(f"Component {component_id} not found")
                continue
            
            # Gather dependency results
            dep_results = {
                dep_id: results.get(dep_id)
                for dep_id in component.dependencies
            }
            
            # Execute component
            logger.info(f"Executing component: {component_id} ({component.component_type.value})")
            result = self._execute_component(component, dep_results, decomposed.parsed_query)
            results[component_id] = result
        
        return results
    
    def _execute_component(
        self,
        component: QueryComponent,
        dep_results: Dict[str, Any],
        parsed_query: ParsedQuery,
    ) -> Any:
        """Execute a single component."""
        if component.component_type == QueryComponentType.DATA_FETCH:
            return self._execute_data_fetch(component, parsed_query)
        
        elif component.component_type == QueryComponentType.AGGREGATION:
            return self._execute_aggregation(component, dep_results)
        
        elif component.component_type == QueryComponentType.COMPARISON:
            return self._execute_comparison(component, dep_results)
        
        elif component.component_type == QueryComponentType.RANKING:
            return self._execute_ranking(component, dep_results)
        
        elif component.component_type == QueryComponentType.CALCULATION:
            return self._execute_calculation(component, dep_results)
        
        else:
            logger.warning(f"Unknown component type: {component.component_type}")
            return None
    
    def _execute_data_fetch(
        self,
        component: QueryComponent,
        parsed_query: ParsedQuery,
    ) -> List[Dict[str, Any]]:
        """Execute a data fetch component."""
        params = component.parameters
        
        # Create a modified parsed query for this fetch
        from src.core.fiscal_calendar import FiscalPeriod
        from datetime import date
        
        time_period = None
        if params.get("time_period"):
            tp = params["time_period"]
            time_period = FiscalPeriod(
                start_date=date.fromisoformat(tp["start_date"]) if isinstance(tp["start_date"], str) else tp["start_date"],
                end_date=date.fromisoformat(tp["end_date"]) if isinstance(tp["end_date"], str) else tp["end_date"],
                period_name=tp.get("period_name", ""),
                fiscal_year=tp.get("fiscal_year"),
            )
        
        # Create fetch query
        fetch_query = ParsedQuery(
            original_query=parsed_query.original_query,
            intent=parsed_query.intent,
            time_period=time_period,
            departments=params.get("departments", []),
            account_type_filter=params.get("account_type_filter"),
            transaction_type_filter=params.get("transaction_type_filter"),
            subsidiaries=params.get("subsidiaries", []),
        )
        
        result = self.data_retriever.get_saved_search_data(
            parsed_query=fetch_query,
            use_suiteql_optimization=False,  # SuiteQL removed - always use RESTlet
        )
        
        return result.data
    
    def _execute_aggregation(
        self,
        component: QueryComponent,
        dep_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute an aggregation component."""
        params = component.parameters
        group_by = params.get("group_by", ["department"])
        
        # Normalize to list format
        if isinstance(group_by, str):
            group_by_list = [group_by]
        else:
            group_by_list = group_by if isinstance(group_by, list) else ["department"]
        
        # Get data from dependency
        data = list(dep_results.values())[0] if dep_results else []
        
        if not data:
            return {}
        
        amount_field = self.data_processor.find_field(data, "amount")
        if not amount_field:
            logger.warning("Could not find amount field for aggregation")
            return {}
        
        # Handle multiple grouping dimensions
        if len(group_by_list) == 1:
            # Single dimension - use existing method for backward compatibility
            group_field = self.data_processor.find_field(data, group_by_list[0])
            if not group_field:
                logger.warning(f"Could not find field for aggregation: {group_by_list[0]}")
                return {}
            
            totals = defaultdict(float)
            for row in data:
                key = str(row.get(group_field, "Unknown"))
                amount = float(row.get(amount_field, 0) or 0)
                totals[key] += amount
            
            return dict(totals)
        else:
            # Multiple dimensions - use new multi-dimensional method
            result = self.data_processor.group_by_multiple(
                data=data,
                group_fields=group_by_list,
                amount_field=amount_field,
                aggregations=["sum", "count"]
            )
            return result.data
    
    def _execute_comparison(
        self,
        component: QueryComponent,
        dep_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a comparison component."""
        params = component.parameters
        
        # Get the two datasets to compare
        results = list(dep_results.values())
        if len(results) < 2:
            logger.warning("Comparison requires two datasets")
            return {}
        
        current_data = results[0]
        prior_data = results[1]
        
        # If data is already aggregated (dicts), compare directly
        if isinstance(current_data, dict) and isinstance(prior_data, dict):
            comparison = {}
            all_keys = set(current_data.keys()) | set(prior_data.keys())
            
            for key in all_keys:
                current_val = current_data.get(key, 0)
                prior_val = prior_data.get(key, 0)
                variance = current_val - prior_val
                pct_change = (variance / prior_val * 100) if prior_val != 0 else 0
                
                comparison[key] = {
                    "current": current_val,
                    "prior": prior_val,
                    "variance": variance,
                    "pct_change": pct_change,
                }
            
            return comparison
        
        # For raw data lists, calculate totals first
        current_total = sum(float(r.get("amount", 0) or 0) for r in current_data) if current_data else 0
        prior_total = sum(float(r.get("amount", 0) or 0) for r in prior_data) if prior_data else 0
        variance = current_total - prior_total
        pct_change = (variance / prior_total * 100) if prior_total != 0 else 0
        
        return {
            "current_total": current_total,
            "prior_total": prior_total,
            "variance": variance,
            "pct_change": pct_change,
            "current_period": params.get("current_period"),
            "prior_period": params.get("prior_period"),
        }
    
    def _execute_ranking(
        self,
        component: QueryComponent,
        dep_results: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Execute a ranking component."""
        params = component.parameters
        top_n = params.get("top_n", 10)
        ascending = params.get("ascending", False)
        
        # Get data from dependency
        data = list(dep_results.values())[0] if dep_results else {}
        
        if isinstance(data, dict):
            # Data is aggregated - convert to list and sort
            items = [{"name": k, "amount": v} for k, v in data.items()]
            sorted_items = sorted(items, key=lambda x: x["amount"], reverse=not ascending)
            return sorted_items[:top_n]
        
        elif isinstance(data, list):
            # Data is raw list
            amount_field = self.data_processor.find_field(data, "amount") if data else "amount"
            sorted_data = sorted(
                data,
                key=lambda x: float(x.get(amount_field, 0) or 0),
                reverse=not ascending
            )
            return sorted_data[:top_n]
        
        return []
    
    def _execute_calculation(
        self,
        component: QueryComponent,
        dep_results: Dict[str, Any],
    ) -> Any:
        """Execute a calculation component."""
        # Placeholder for custom calculations
        return dep_results


# Singleton instances
_decomposer: Optional[QueryDecomposer] = None
_executor: Optional[QueryExecutor] = None


def get_query_decomposer() -> QueryDecomposer:
    """Get the query decomposer instance."""
    global _decomposer
    if _decomposer is None:
        _decomposer = QueryDecomposer()
    return _decomposer


def get_query_executor() -> QueryExecutor:
    """Get the query executor instance."""
    global _executor
    if _executor is None:
        _executor = QueryExecutor()
    return _executor

