"""
Pre-Aggregated Data Layer

Provides cached, pre-computed aggregations for common query patterns.
This enables sub-second response times for frequent queries like:
- YTD revenue by department
- Monthly expense trends
- Top accounts by spending

Aggregations are refreshed daily and stored in the file system.
"""
import os
import json
import logging
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class AggregatedData:
    """
    Container for pre-computed aggregated data.
    
    Stores aggregated metrics with metadata about when they were computed
    and from how much source data.
    """
    aggregation_type: str
    computed_at: datetime
    fiscal_year: int
    data: Dict[str, Any]
    row_count: int  # Number of source rows used
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "aggregation_type": self.aggregation_type,
            "computed_at": self.computed_at.isoformat(),
            "fiscal_year": self.fiscal_year,
            "data": self.data,
            "row_count": self.row_count,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'AggregatedData':
        return cls(
            aggregation_type=d["aggregation_type"],
            computed_at=datetime.fromisoformat(d["computed_at"]),
            fiscal_year=d["fiscal_year"],
            data=d["data"],
            row_count=d["row_count"],
        )
    
    @property
    def age_hours(self) -> float:
        """Get the age of this aggregation in hours."""
        return (datetime.now() - self.computed_at).total_seconds() / 3600
    
    @property
    def is_stale(self) -> bool:
        """Check if this aggregation is stale (>24 hours old)."""
        max_age_hours = float(os.getenv("AGGREGATION_MAX_AGE_HOURS", "24"))
        return self.age_hours > max_age_hours


class AggregationCache:
    """
    File-based cache for pre-computed aggregations.
    
    Stores aggregations as JSON files, organized by type and fiscal year.
    """
    
    def __init__(self, cache_dir: str = ".cache/aggregations"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_path(self, aggregation_type: str, fiscal_year: int) -> Path:
        """Get the cache file path for an aggregation."""
        return self.cache_dir / f"{aggregation_type}_{fiscal_year}.json"
    
    def get(self, aggregation_type: str, fiscal_year: int) -> Optional[AggregatedData]:
        """
        Get a cached aggregation if it exists and is not stale.
        
        Args:
            aggregation_type: Type of aggregation (e.g., "ytd_by_department")
            fiscal_year: Fiscal year the aggregation covers
        
        Returns:
            AggregatedData if found and not stale, None otherwise
        """
        cache_path = self._get_cache_path(aggregation_type, fiscal_year)
        
        if not cache_path.exists():
            logger.debug(f"Aggregation cache miss: {aggregation_type}_{fiscal_year}")
            return None
        
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
            
            aggregation = AggregatedData.from_dict(data)
            
            # Check if stale
            if aggregation.is_stale:
                logger.info(f"Aggregation stale ({aggregation.age_hours:.1f}h old): {aggregation_type}")
                return None
            
            logger.info(f"Aggregation cache hit: {aggregation_type}_{fiscal_year}")
            return aggregation
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to read aggregation cache: {e}")
            return None
    
    def set(self, aggregation: AggregatedData) -> None:
        """
        Store an aggregation in the cache.
        
        Args:
            aggregation: The aggregated data to cache
        """
        cache_path = self._get_cache_path(aggregation.aggregation_type, aggregation.fiscal_year)
        
        try:
            with open(cache_path, 'w') as f:
                json.dump(aggregation.to_dict(), f, indent=2)
            
            logger.info(
                f"Cached aggregation: {aggregation.aggregation_type}_{aggregation.fiscal_year} "
                f"({aggregation.row_count} rows)"
            )
        except IOError as e:
            logger.error(f"Failed to write aggregation cache: {e}")
    
    def invalidate(self, aggregation_type: str, fiscal_year: int) -> bool:
        """Invalidate a specific aggregation."""
        cache_path = self._get_cache_path(aggregation_type, fiscal_year)
        if cache_path.exists():
            cache_path.unlink()
            logger.info(f"Invalidated aggregation: {aggregation_type}_{fiscal_year}")
            return True
        return False
    
    def clear_all(self) -> int:
        """Clear all cached aggregations."""
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
            count += 1
        logger.info(f"Cleared {count} aggregation cache entries")
        return count
    
    def list_cached(self) -> List[Dict[str, Any]]:
        """List all cached aggregations with metadata."""
        cached = []
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                agg = AggregatedData.from_dict(data)
                cached.append({
                    "aggregation_type": agg.aggregation_type,
                    "fiscal_year": agg.fiscal_year,
                    "computed_at": agg.computed_at.isoformat(),
                    "age_hours": agg.age_hours,
                    "is_stale": agg.is_stale,
                    "row_count": agg.row_count,
                })
            except Exception:
                pass
        return cached


class AggregationComputer:
    """
    Computes aggregations from raw financial data.
    
    Provides methods to compute various pre-defined aggregations
    that can be cached for fast retrieval.
    """
    
    # Account type prefixes for classification
    ACCOUNT_TYPE_MAP = {
        "1": "Assets",
        "2": "Liabilities",
        "3": "Equity",
        "4": "Revenue",
        "5": "COGS",
        "6": "Operating Expenses",
        "7": "Operating Expenses",
        "8": "Other Income/Expense",
    }
    
    def __init__(self, data_processor=None):
        from src.tools.data_processor import get_data_processor
        self.data_processor = data_processor or get_data_processor()
    
    def _get_account_type(self, account_number: str) -> str:
        """Classify an account by its number prefix."""
        if not account_number:
            return "Unknown"
        first_char = str(account_number)[0]
        return self.ACCOUNT_TYPE_MAP.get(first_char, "Other")
    
    def _find_field(self, data: List[Dict], field_type: str) -> Optional[str]:
        """Find the actual field name in data."""
        return self.data_processor.find_field(data, field_type)
    
    def compute_ytd_by_department(
        self,
        raw_data: List[Dict],
        fiscal_year: int,
    ) -> AggregatedData:
        """
        Pre-compute YTD totals by department.
        
        Returns aggregation like:
        {
            "Marketing": 1500000.00,
            "R&D": 2300000.00,
            "G&A": 800000.00,
        }
        """
        totals = defaultdict(float)
        
        dept_field = self._find_field(raw_data, "department")
        amount_field = self._find_field(raw_data, "amount")
        
        if not dept_field or not amount_field:
            logger.warning("Cannot compute ytd_by_department: missing fields")
            return AggregatedData(
                aggregation_type="ytd_by_department",
                computed_at=datetime.now(),
                fiscal_year=fiscal_year,
                data={},
                row_count=0,
            )
        
        for row in raw_data:
            dept = str(row.get(dept_field, "Unknown") or "Unknown")
            # Extract just the department name (handle hierarchies like "Parent : Child")
            if " : " in dept:
                dept = dept.split(" : ")[-1].strip()
            amount = float(row.get(amount_field, 0) or 0)
            totals[dept] += amount
        
        return AggregatedData(
            aggregation_type="ytd_by_department",
            computed_at=datetime.now(),
            fiscal_year=fiscal_year,
            data=dict(totals),
            row_count=len(raw_data),
        )
    
    def compute_ytd_by_account_type(
        self,
        raw_data: List[Dict],
        fiscal_year: int,
    ) -> AggregatedData:
        """
        Pre-compute YTD totals by account type.
        
        Returns aggregation like:
        {
            "Revenue": 5000000.00,
            "COGS": 2000000.00,
            "Operating Expenses": 1500000.00,
        }
        """
        totals = defaultdict(float)
        
        account_field = self._find_field(raw_data, "account_number")
        amount_field = self._find_field(raw_data, "amount")
        
        if not amount_field:
            logger.warning("Cannot compute ytd_by_account_type: missing amount field")
            return AggregatedData(
                aggregation_type="ytd_by_account_type",
                computed_at=datetime.now(),
                fiscal_year=fiscal_year,
                data={},
                row_count=0,
            )
        
        for row in raw_data:
            acct_num = str(row.get(account_field, "") or "")
            account_type = self._get_account_type(acct_num)
            amount = float(row.get(amount_field, 0) or 0)
            totals[account_type] += amount
        
        return AggregatedData(
            aggregation_type="ytd_by_account_type",
            computed_at=datetime.now(),
            fiscal_year=fiscal_year,
            data=dict(totals),
            row_count=len(raw_data),
        )
    
    def compute_monthly_trend(
        self,
        raw_data: List[Dict],
        fiscal_year: int,
    ) -> AggregatedData:
        """
        Pre-compute monthly totals for trend analysis.
        
        Returns aggregation like:
        {
            "2025-02": {"Revenue": 400000, "Expenses": 300000},
            "2025-03": {"Revenue": 450000, "Expenses": 320000},
        }
        """
        monthly = defaultdict(lambda: defaultdict(float))
        
        date_field = self._find_field(raw_data, "date")
        account_field = self._find_field(raw_data, "account_number")
        amount_field = self._find_field(raw_data, "amount")
        
        if not date_field or not amount_field:
            logger.warning("Cannot compute monthly_trend: missing fields")
            return AggregatedData(
                aggregation_type="monthly_trend",
                computed_at=datetime.now(),
                fiscal_year=fiscal_year,
                data={},
                row_count=0,
            )
        
        for row in raw_data:
            date_val = str(row.get(date_field, "") or "")[:7]  # YYYY-MM
            if not date_val or len(date_val) < 7:
                continue
            
            acct_num = str(row.get(account_field, "") or "")
            account_type = self._get_account_type(acct_num)
            amount = float(row.get(amount_field, 0) or 0)
            
            monthly[date_val][account_type] += amount
        
        # Convert defaultdicts to regular dicts for JSON serialization
        result = {month: dict(types) for month, types in monthly.items()}
        
        return AggregatedData(
            aggregation_type="monthly_trend",
            computed_at=datetime.now(),
            fiscal_year=fiscal_year,
            data=result,
            row_count=len(raw_data),
        )
    
    def compute_department_by_month(
        self,
        raw_data: List[Dict],
        fiscal_year: int,
    ) -> AggregatedData:
        """
        Pre-compute department totals by month.
        
        Returns aggregation like:
        {
            "2025-02": {"Marketing": 100000, "R&D": 200000},
            "2025-03": {"Marketing": 110000, "R&D": 210000},
        }
        """
        monthly_dept = defaultdict(lambda: defaultdict(float))
        
        date_field = self._find_field(raw_data, "date")
        dept_field = self._find_field(raw_data, "department")
        amount_field = self._find_field(raw_data, "amount")
        
        if not date_field or not dept_field or not amount_field:
            logger.warning("Cannot compute department_by_month: missing fields")
            return AggregatedData(
                aggregation_type="department_by_month",
                computed_at=datetime.now(),
                fiscal_year=fiscal_year,
                data={},
                row_count=0,
            )
        
        for row in raw_data:
            date_val = str(row.get(date_field, "") or "")[:7]  # YYYY-MM
            if not date_val or len(date_val) < 7:
                continue
            
            dept = str(row.get(dept_field, "Unknown") or "Unknown")
            if " : " in dept:
                dept = dept.split(" : ")[-1].strip()
            amount = float(row.get(amount_field, 0) or 0)
            
            monthly_dept[date_val][dept] += amount
        
        result = {month: dict(depts) for month, depts in monthly_dept.items()}
        
        return AggregatedData(
            aggregation_type="department_by_month",
            computed_at=datetime.now(),
            fiscal_year=fiscal_year,
            data=result,
            row_count=len(raw_data),
        )
    
    def compute_top_accounts(
        self,
        raw_data: List[Dict],
        fiscal_year: int,
        top_n: int = 20,
    ) -> AggregatedData:
        """
        Pre-compute top accounts by spending.
        
        Returns aggregation like:
        {
            "accounts": [
                {"account": "Salaries", "amount": 1500000},
                {"account": "Software", "amount": 500000},
            ]
        }
        """
        account_totals = defaultdict(float)
        
        account_field = self._find_field(raw_data, "account")
        amount_field = self._find_field(raw_data, "amount")
        
        if not account_field or not amount_field:
            logger.warning("Cannot compute top_accounts: missing fields")
            return AggregatedData(
                aggregation_type="top_accounts",
                computed_at=datetime.now(),
                fiscal_year=fiscal_year,
                data={"accounts": []},
                row_count=0,
            )
        
        for row in raw_data:
            account = str(row.get(account_field, "Unknown") or "Unknown")
            amount = float(row.get(amount_field, 0) or 0)
            account_totals[account] += amount
        
        # Sort by absolute amount (for expenses, which are often negative)
        sorted_accounts = sorted(
            account_totals.items(),
            key=lambda x: abs(x[1]),
            reverse=True
        )[:top_n]
        
        accounts_list = [{"account": k, "amount": v} for k, v in sorted_accounts]
        
        return AggregatedData(
            aggregation_type="top_accounts",
            computed_at=datetime.now(),
            fiscal_year=fiscal_year,
            data={"accounts": accounts_list},
            row_count=len(raw_data),
        )


def refresh_aggregation_cache():
    """
    Refresh all pre-computed aggregations.
    
    This should be run daily (e.g., via cron or scheduled task) to keep
    the aggregation cache up to date.
    """
    from src.tools.netsuite_client import get_data_retriever
    from src.core.fiscal_calendar import get_fiscal_calendar
    from src.core.query_parser import ParsedQuery, QueryIntent
    
    logger.info("Starting aggregation cache refresh...")
    
    retriever = get_data_retriever()
    computer = AggregationComputer()
    cache = AggregationCache()
    fiscal_cal = get_fiscal_calendar()
    
    # Get current fiscal year
    current_fy = fiscal_cal.get_current_fiscal_year()
    ytd_range = fiscal_cal.get_ytd_range()
    
    logger.info(f"Fetching YTD data for FY{current_fy.fiscal_year}...")
    
    # Fetch YTD data
    parsed = ParsedQuery(
        original_query="cache_refresh",
        intent=QueryIntent.SUMMARY,
        time_period=ytd_range,
    )
    
    result = retriever.get_saved_search_data(
        parsed_query=parsed,
        bypass_cache=True,
        use_suiteql_optimization=False,  # SuiteQL removed - always use RESTlet
    )
    
    logger.info(f"Fetched {result.row_count} rows for aggregation")
    
    # Compute and cache all aggregations
    aggregations = [
        computer.compute_ytd_by_department(result.data, current_fy.fiscal_year),
        computer.compute_ytd_by_account_type(result.data, current_fy.fiscal_year),
        computer.compute_monthly_trend(result.data, current_fy.fiscal_year),
        computer.compute_department_by_month(result.data, current_fy.fiscal_year),
        computer.compute_top_accounts(result.data, current_fy.fiscal_year),
    ]
    
    for agg in aggregations:
        cache.set(agg)
        logger.info(f"Cached {agg.aggregation_type}: {len(agg.data)} entries from {agg.row_count} rows")
    
    logger.info(f"Aggregation cache refresh complete: {len(aggregations)} aggregations cached")
    return aggregations


# Singleton instances
_cache: Optional[AggregationCache] = None
_computer: Optional[AggregationComputer] = None


def get_aggregation_cache() -> AggregationCache:
    """Get the aggregation cache instance."""
    global _cache
    if _cache is None:
        _cache = AggregationCache()
    return _cache


def get_aggregation_computer() -> AggregationComputer:
    """Get the aggregation computer instance."""
    global _computer
    if _computer is None:
        _computer = AggregationComputer()
    return _computer

