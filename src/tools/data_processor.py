"""
Data Processing Engine

Filtering and multi-dimensional aggregation for financial data.
Provides the data transformation layer between raw NetSuite data
and the calculation/analysis engines.

Uses configuration from data_dictionary.yaml for field mappings and parsing rules.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Tuple, Union
from datetime import date, datetime
from collections import defaultdict

from src.core.fiscal_calendar import FiscalPeriod, FiscalCalendar, get_fiscal_calendar
from src.core.data_context import DataContext, get_data_context, DepartmentInfo, AccountInfo

logger = logging.getLogger(__name__)

@dataclass
class FilterResult:
    """Result of a filtering operation."""
    data: List[Dict[str, Any]]
    original_count: int
    filtered_count: int
    filters_applied: List[str]
    
    @property
    def filter_summary(self) -> str:
        return f"Filtered {self.original_count} -> {self.filtered_count} rows ({len(self.filters_applied)} filters)"

@dataclass
class AggregationResult:
    """Result of an aggregation operation."""
    data: Dict[str, Any]              # Aggregated data
    dimensions: List[str]              # Dimensions used for grouping
    measures: List[str]                # Measures computed
    row_count: int                     # Number of groups
    
    def to_list(self) -> List[Dict[str, Any]]:
        """Convert to list of dicts for compatibility."""
        if isinstance(self.data, dict):
            result = []
            for key, value in self.data.items():
                if isinstance(value, dict):
                    row = {"_key": key, **value}
                else:
                    row = {"_key": key, "_value": value}
                result.append(row)
            return result
        return list(self.data)

class DataProcessor:
    """
    Processes and transforms financial data.
    
    Provides filtering, grouping, and aggregation capabilities
    while maintaining deterministic, reproducible results.
    
    Uses DataContext for field mappings and parsing rules from config.
    """
    
    # Common field name mappings for flexible matching
    # These are fallbacks; DataContext provides primary mappings
    FIELD_ALIASES = {
        # Account fields
        "account": ["account_name", "account", "acctname", "acct_name", "accountname"],
        "account_number": ["account_number", "acctnumber", "acct_number", "acctno"],
        
        # Department fields
        "department": ["department_name", "department", "dept", "dept_name", "deptname"],
        "department_number": ["formulatext", "department_number", "dept_number"],
        
        # Amount fields
        "amount": ["amount", "lineamount", "netamount", "total", "value", "amt"],
        "debit": ["debitamount", "debit", "dr"],
        "credit": ["creditamount", "credit", "cr"],
        
        # Date fields - primary is month_end_date per data dictionary
        "date": ["formuladate", "trandate", "date", "transaction_date", "tran_date", "postingdate"],
        "month_end_date": ["formuladate", "month_end_date"],
        "period": ["accountingPeriod_periodname", "periodname", "period_name", "postingperiod"],
        
        # Entity/Organization fields
        "subsidiary": ["subsidiarynohierarchy", "subsidiary", "subsidiary_name", "entity"],
        "vendor": ["vendor_entityid", "vendor", "vendorname", "vendor_name"],
        
        # Transaction fields
        "type": ["type", "type_text", "trantype", "transaction_type", "je_type"],
        "memo": ["memo", "description", "line_memo"],
        "document_number": ["tranid", "document_number", "doc_number", "docnum"],
        
        # Classification fields
        "class": ["class", "class_text", "classname", "class_name"],
        "parent_type": ["item_parent", "item_parent_text", "parent_type"],
        "sku": ["item_displayname", "sku", "sku_name"],
        
        # Amortization fields
        "amortization_schedule": ["amortizationSchedule_amortemplate", "amortization_schedule"],
        "amortization_number": ["amortizationSchedule_schedulenumber", "amortization_number"],
    }
    
    def __init__(self, fiscal_calendar: FiscalCalendar = None, data_context: DataContext = None):
        self.fiscal_calendar = fiscal_calendar or get_fiscal_calendar()
        self.data_context = data_context or get_data_context()
        
        # Update field aliases from data context
        self._update_field_aliases_from_context()
    
    def _update_field_aliases_from_context(self):
        """Update field aliases based on data context configuration."""
        # Ensure the primary date field from config is first in the list
        primary_date = self.data_context.get_primary_date_field()
        if primary_date and "date" in self.FIELD_ALIASES:
            if primary_date not in self.FIELD_ALIASES["date"]:
                self.FIELD_ALIASES["date"].insert(0, primary_date)
            elif self.FIELD_ALIASES["date"][0] != primary_date:
                self.FIELD_ALIASES["date"].remove(primary_date)
                self.FIELD_ALIASES["date"].insert(0, primary_date)
    
    def parse_department(self, raw_value: str) -> DepartmentInfo:
        """Parse a department value using the data context rules."""
        return self.data_context.parse_department(raw_value)
    
    def classify_account(self, account_number: str, account_name: str = "") -> AccountInfo:
        """Classify an account using the data context rules."""
        return self.data_context.classify_account(account_number, account_name)
    
    def find_field(self, data: List[Dict], field_type: str) -> Optional[str]:
        """
        Find the actual field name in data that matches a field type.
        
        Args:
            data: The data to search
            field_type: Logical field type (e.g., "department", "amount")
        
        Returns:
            The actual field name found, or None
        """
        if not data:
            return None
        
        sample = data[0]
        sample_keys_lower = {k.lower(): k for k in sample.keys()}
        
        aliases = self.FIELD_ALIASES.get(field_type, [field_type])
        
        for alias in aliases:
            if alias.lower() in sample_keys_lower:
                return sample_keys_lower[alias.lower()]
        
        return None
    
    def filter_by_department(
        self, 
        data: List[Dict], 
        department: str,
        field_name: str = None
    ) -> FilterResult:
        """
        Filter data to a specific department.
        
        Args:
            data: Raw data rows
            department: Department name to filter by
            field_name: Specific field to use (auto-detected if None)
        """
        field_name = field_name or self.find_field(data, "department")
        
        if not field_name:
            logger.warning("Could not find department field in data")
            return FilterResult(
                data=data,
                original_count=len(data),
                filtered_count=len(data),
                filters_applied=["department field not found"],
            )
        
        dept_lower = department.lower()
        filtered = [
            row for row in data
            if dept_lower in str(row.get(field_name, "")).lower()
        ]
        
        return FilterResult(
            data=filtered,
            original_count=len(data),
            filtered_count=len(filtered),
            filters_applied=[f"{field_name} contains '{department}'"],
        )
    
    def filter_by_date_range(
        self,
        data: List[Dict],
        start_date: date,
        end_date: date,
        field_name: str = None
    ) -> FilterResult:
        """
        Filter data to a date range.
        
        Args:
            data: Raw data rows
            start_date: Start of range (inclusive)
            end_date: End of range (inclusive)
            field_name: Date field to use (auto-detected if None)
        """
        field_name = field_name or self.find_field(data, "date")
        
        if not field_name:
            logger.warning("Could not find date field in data")
            return FilterResult(
                data=data,
                original_count=len(data),
                filtered_count=len(data),
                filters_applied=["date field not found"],
            )
        
        def parse_date(value: Any) -> Optional[date]:
            if isinstance(value, date):
                return value
            if isinstance(value, datetime):
                return value.date()
            if isinstance(value, str):
                value = value.strip()
                
                # Handle M/D/YYYY format (RESTlet format with single digit month/day)
                if '/' in value:
                    try:
                        parts = value.split('/')
                        if len(parts) == 3:
                            month = int(parts[0])
                            day = int(parts[1])
                            year = int(parts[2])
                            return date(year, month, day)
                    except (ValueError, IndexError):
                        pass
                
                # Handle ISO format YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
                if 'T' in value:
                    value = value.split('T')[0]
                
                # Try common formats
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"]:
                    try:
                        return datetime.strptime(value[:10], fmt).date()
                    except (ValueError, IndexError):
                        continue
            return None
        
        filtered = []
        for row in data:
            row_date = parse_date(row.get(field_name))
            if row_date and start_date <= row_date <= end_date:
                filtered.append(row)
        
        return FilterResult(
            data=filtered,
            original_count=len(data),
            filtered_count=len(filtered),
            filters_applied=[f"{field_name} between {start_date} and {end_date}"],
        )
    
    def filter_by_period(
        self,
        data: List[Dict],
        period: FiscalPeriod,
        field_name: str = None
    ) -> FilterResult:
        """Filter data to a fiscal period."""
        return self.filter_by_date_range(
            data, period.start_date, period.end_date, field_name
        )
    
    def filter_by_account(
        self,
        data: List[Dict],
        account_pattern: str,
        field_name: str = None
    ) -> FilterResult:
        """
        Filter data by account name or number.
        
        Args:
            data: Raw data rows
            account_pattern: Account name/number to match (supports partial match)
            field_name: Account field to use (auto-detected if None)
        """
        # Try account name first, then account number
        field_name = field_name or self.find_field(data, "account") or self.find_field(data, "account_number")
        
        if not field_name:
            logger.warning("Could not find account field in data")
            return FilterResult(
                data=data,
                original_count=len(data),
                filtered_count=len(data),
                filters_applied=["account field not found"],
            )
        
        pattern_lower = account_pattern.lower()
        filtered = [
            row for row in data
            if pattern_lower in str(row.get(field_name, "")).lower()
        ]
        
        return FilterResult(
            data=filtered,
            original_count=len(data),
            filtered_count=len(filtered),
            filters_applied=[f"{field_name} contains '{account_pattern}'"],
        )
    
    def filter_by_account_type(
        self,
        data: List[Dict],
        account_type_filter: Dict[str, Any],
        field_name: str = None
    ) -> FilterResult:
        """
        Filter data by account type using the semantic filter format.
        
        This is a key method for the financial semantics integration.
        It filters based on account number prefixes (e.g., "4" for revenue,
        "5,6,7,8" for expenses).
        
        Args:
            data: Raw data rows
            account_type_filter: Dict with filter_type and values
                Example: {"filter_type": "prefix", "values": ["4"]}
            field_name: Account number field to use (auto-detected if None)
        
        Returns:
            FilterResult with filtered data
        """
        if not account_type_filter:
            return FilterResult(
                data=data,
                original_count=len(data),
                filtered_count=len(data),
                filters_applied=[],
            )
        
        filter_type = account_type_filter.get("filter_type", "prefix")
        values = account_type_filter.get("values", [])
        
        if not values:
            return FilterResult(
                data=data,
                original_count=len(data),
                filtered_count=len(data),
                filters_applied=[],
            )
        
        # Try account number first (most reliable for prefix matching)
        field_name = field_name or self.find_field(data, "account_number") or self.find_field(data, "account")
        
        if not field_name:
            logger.warning("Could not find account number field in data")
            return FilterResult(
                data=data,
                original_count=len(data),
                filtered_count=len(data),
                filters_applied=["account_number field not found"],
            )
        
        # Get account name field for "Total" exclusion
        account_name_field = self.find_field(data, "account")
        
        def is_total_account(row: Dict) -> bool:
            """Check if account name contains 'Total' (summary/rollup account)."""
            if account_name_field:
                account_name = str(row.get(account_name_field, "")).lower()
                return "total" in account_name
            return False
        
        # Apply filter based on type
        if filter_type == "prefix":
            filtered = [
                row for row in data
                if any(
                    str(row.get(field_name, "")).startswith(prefix)
                    for prefix in values
                ) and not is_total_account(row)  # Exclude "Total" accounts
            ]
            filter_desc = f"account prefix in {values} (excluding 'Total' accounts)"
            
        elif filter_type == "exact":
            values_set = set(values)
            filtered = [
                row for row in data
                if str(row.get(field_name, "")) in values_set
                and not is_total_account(row)  # Exclude "Total" accounts
            ]
            filter_desc = f"account in {values} (excluding 'Total' accounts)"
            
        elif filter_type == "contains":
            filtered = [
                row for row in data
                if any(
                    val in str(row.get(field_name, ""))
                    for val in values
                ) and not is_total_account(row)  # Exclude "Total" accounts
            ]
            filter_desc = f"account contains {values} (excluding 'Total' accounts)"
            
        elif filter_type == "in_list":
            values_set = set(v.lower() for v in values)
            filtered = [
                row for row in data
                if str(row.get(field_name, "")).lower() in values_set
                and not is_total_account(row)  # Exclude "Total" accounts
            ]
            filter_desc = f"account in list {values} (excluding 'Total' accounts)"
            
        else:
            logger.warning(f"Unknown filter_type: {filter_type}")
            filtered = data
            filter_desc = f"unknown filter_type: {filter_type}"
        
        logger.info(f"Account type filter: {len(data)} -> {len(filtered)} rows ({filter_desc})")
        
        return FilterResult(
            data=filtered,
            original_count=len(data),
            filtered_count=len(filtered),
            filters_applied=[filter_desc],
        )
    
    def filter_by_account_name(
        self,
        data: List[Dict],
        account_name_filter: Dict[str, Any],
        field_name: str = None
    ) -> FilterResult:
        """
        Filter data by account NAME (not number) using the semantic filter format.
        
        This enables filtering accounts where the name contains specific text,
        such as "Sales & Marketing" or "Product Development".
        
        Args:
            data: Raw data rows
            account_name_filter: Dict with filter_type and values
                Example: {"filter_type": "contains", "values": ["Sales & Marketing"]}
            field_name: Account name field to use (auto-detected if None)
        
        Returns:
            FilterResult with filtered data
        """
        if not account_name_filter:
            return FilterResult(
                data=data,
                original_count=len(data),
                filtered_count=len(data),
                filters_applied=[],
            )
        
        filter_type = account_name_filter.get("filter_type", "contains")
        values = account_name_filter.get("values", [])
        
        if not values:
            return FilterResult(
                data=data,
                original_count=len(data),
                filtered_count=len(data),
                filters_applied=[],
            )
        
        # Use account name field
        field_name = field_name or self.find_field(data, "account")
        
        if not field_name:
            logger.warning("Could not find account name field in data")
            return FilterResult(
                data=data,
                original_count=len(data),
                filtered_count=len(data),
                filters_applied=["account_name field not found"],
            )
        
        # Apply filter based on type (usually "contains")
        if filter_type == "contains":
            # Match if account name contains ANY of the values
            filtered = [
                row for row in data
                if any(
                    val.lower() in str(row.get(field_name, "")).lower()
                    for val in values
                )
            ]
            filter_desc = f"account name contains {values}"
            
        elif filter_type == "exact":
            values_lower = set(v.lower() for v in values)
            filtered = [
                row for row in data
                if str(row.get(field_name, "")).lower() in values_lower
            ]
            filter_desc = f"account name exactly {values}"
            
        elif filter_type == "prefix":
            filtered = [
                row for row in data
                if any(
                    str(row.get(field_name, "")).lower().startswith(val.lower())
                    for val in values
                )
            ]
            filter_desc = f"account name starts with {values}"
            
        else:
            logger.warning(f"Unknown filter_type for account name: {filter_type}")
            filtered = data
            filter_desc = f"unknown filter_type: {filter_type}"
        
        logger.info(f"Account name filter: {len(data)} -> {len(filtered)} rows ({filter_desc})")
        
        return FilterResult(
            data=filtered,
            original_count=len(data),
            filtered_count=len(filtered),
            filters_applied=[filter_desc],
        )
    
    def filter_by_transaction_type(
        self,
        data: List[Dict],
        transaction_types: List[str],
        field_name: str = None
    ) -> FilterResult:
        """
        Filter data by transaction type(s).
        
        Args:
            data: Raw data rows
            transaction_types: List of transaction type codes (e.g., ["Journal", "VendBill"])
            field_name: Transaction type field to use (auto-detected if None)
        
        Returns:
            FilterResult with filtered data
        """
        if not transaction_types:
            return FilterResult(
                data=data,
                original_count=len(data),
                filtered_count=len(data),
                filters_applied=[],
            )
        
        field_name = field_name or self.find_field(data, "type")
        
        if not field_name:
            logger.warning("Could not find transaction type field in data")
            return FilterResult(
                data=data,
                original_count=len(data),
                filtered_count=len(data),
                filters_applied=["type field not found"],
            )
        
        types_lower = set(t.lower() for t in transaction_types)
        filtered = [
            row for row in data
            if str(row.get(field_name, "")).lower() in types_lower
        ]
        
        logger.info(f"Transaction type filter: {len(data)} -> {len(filtered)} rows (types: {transaction_types})")
        
        return FilterResult(
            data=filtered,
            original_count=len(data),
            filtered_count=len(filtered),
            filters_applied=[f"type in {transaction_types}"],
        )
    
    def apply_filters(
        self,
        data: List[Dict],
        departments: List[str] = None,
        accounts: List[str] = None,
        period: FiscalPeriod = None,
        custom_filters: List[Callable[[Dict], bool]] = None,
        account_type_filter: Dict[str, Any] = None,
        transaction_type_filter: List[str] = None,
    ) -> FilterResult:
        """
        Apply multiple filters to data.
        
        Args:
            data: Raw data rows
            departments: Department names to filter by (OR logic)
            accounts: Account patterns to filter by (OR logic)
            period: Fiscal period to filter by
            custom_filters: Additional custom filter functions
            account_type_filter: Semantic account type filter (NEW)
                Example: {"filter_type": "prefix", "values": ["4"]}
            transaction_type_filter: List of transaction types to include (NEW)
        """
        result = data
        all_filters = []
        original_count = len(data)
        
        # Apply period filter first (usually most restrictive)
        if period:
            filter_result = self.filter_by_period(result, period)
            result = filter_result.data
            all_filters.extend(filter_result.filters_applied)
        
        # Apply account type filter (NEW - from financial semantics)
        if account_type_filter:
            filter_result = self.filter_by_account_type(result, account_type_filter)
            result = filter_result.data
            all_filters.extend(filter_result.filters_applied)
        
        # Apply transaction type filter (NEW - from financial semantics)
        if transaction_type_filter:
            filter_result = self.filter_by_transaction_type(result, transaction_type_filter)
            result = filter_result.data
            all_filters.extend(filter_result.filters_applied)
        
        # Apply department filter (OR logic for multiple departments)
        if departments:
            dept_field = self.find_field(result, "department")
            if dept_field:
                dept_filtered = []
                for row in result:
                    row_dept = str(row.get(dept_field, "")).lower()
                    if any(d.lower() in row_dept for d in departments):
                        dept_filtered.append(row)
                result = dept_filtered
                all_filters.append(f"department in {departments}")
        
        # Apply account filter (OR logic for multiple accounts)
        if accounts:
            acct_field = self.find_field(result, "account") or self.find_field(result, "account_number")
            if acct_field:
                acct_filtered = []
                for row in result:
                    row_acct = str(row.get(acct_field, "")).lower()
                    if any(a.lower() in row_acct for a in accounts):
                        acct_filtered.append(row)
                result = acct_filtered
                all_filters.append(f"account in {accounts}")
        
        # Apply custom filters
        if custom_filters:
            for i, filter_func in enumerate(custom_filters):
                result = [row for row in result if filter_func(row)]
                all_filters.append(f"custom_filter_{i}")
        
        return FilterResult(
            data=result,
            original_count=original_count,
            filtered_count=len(result),
            filters_applied=all_filters,
        )
    
    def group_by_single(
        self,
        data: List[Dict],
        group_field: str,
        amount_field: str = None,
        aggregations: List[str] = None
    ) -> AggregationResult:
        """
        Group data by a single dimension and aggregate.
        
        Args:
            data: Data rows to group
            group_field: Field to group by
            amount_field: Amount field to aggregate (auto-detected if None)
            aggregations: Aggregation types ["sum", "count", "avg", "min", "max"]
        """
        amount_field = amount_field or self.find_field(data, "amount")
        aggregations = aggregations or ["sum", "count"]
        
        groups: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"values": [], "count": 0})
        
        for row in data:
            key = str(row.get(group_field, "Unknown"))
            amount = self._parse_amount(row.get(amount_field, 0))
            groups[key]["values"].append(amount)
            groups[key]["count"] += 1
        
        result = {}
        for key, group_data in groups.items():
            values = group_data["values"]
            agg_result = {"count": group_data["count"]}
            
            if "sum" in aggregations and values:
                agg_result["sum"] = sum(values)
            if "avg" in aggregations and values:
                agg_result["avg"] = sum(values) / len(values)
            if "min" in aggregations and values:
                agg_result["min"] = min(values)
            if "max" in aggregations and values:
                agg_result["max"] = max(values)
            
            result[key] = agg_result
        
        return AggregationResult(
            data=result,
            dimensions=[group_field],
            measures=aggregations,
            row_count=len(result),
        )
    
    def group_by_period(
        self,
        data: List[Dict],
        period_type: str = "month",
        amount_field: str = None,
        date_field: str = None
    ) -> AggregationResult:
        """
        Group data by time period.
        
        Args:
            data: Data rows to group
            period_type: "day", "week", "month", "quarter", "year"
            amount_field: Amount field to aggregate
            date_field: Date field to use
        """
        amount_field = amount_field or self.find_field(data, "amount")
        date_field = date_field or self.find_field(data, "date")
        
        if not date_field:
            logger.warning("Could not find date field for period grouping")
            return AggregationResult(
                data={},
                dimensions=["period"],
                measures=["sum", "count"],
                row_count=0,
            )
        
        groups: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"values": [], "count": 0})
        
        for row in data:
            row_date = self._parse_date(row.get(date_field))
            if not row_date:
                continue
            
            # Generate period key
            if period_type == "day":
                key = row_date.strftime("%Y-%m-%d")
            elif period_type == "week":
                key = row_date.strftime("%Y-W%W")
            elif period_type == "month":
                key = row_date.strftime("%Y-%m")
            elif period_type == "quarter":
                quarter = (row_date.month - 1) // 3 + 1
                key = f"{row_date.year}-Q{quarter}"
            elif period_type == "year":
                key = str(row_date.year)
            else:
                key = row_date.strftime("%Y-%m")
            
            amount = self._parse_amount(row.get(amount_field, 0))
            groups[key]["values"].append(amount)
            groups[key]["count"] += 1
        
        result = {}
        for key, group_data in sorted(groups.items()):
            values = group_data["values"]
            result[key] = {
                "sum": sum(values),
                "count": group_data["count"],
                "avg": sum(values) / len(values) if values else 0,
            }
        
        return AggregationResult(
            data=result,
            dimensions=["period"],
            measures=["sum", "count", "avg"],
            row_count=len(result),
        )
    
    def group_by_multiple(
        self,
        data: List[Dict],
        group_fields: List[str],
        amount_field: str = None,
        aggregations: List[str] = None,
        date_field: str = None
    ) -> AggregationResult:
        """
        Group data by multiple dimensions and aggregate.
        
        Example: group_fields=["account", "quarter"] creates nested structure:
        {
            "Account 5100": {
                "FY2026 Q1": {"sum": 1000, "count": 5},
                "FY2026 Q2": {"sum": 1500, "count": 7},
            },
            "Account 5200": {
                "FY2026 Q1": {"sum": 2000, "count": 10},
                "FY2026 Q2": {"sum": 2500, "count": 12},
            }
        }
        
        Args:
            data: Data rows to group
            group_fields: List of fields to group by (e.g., ["account", "quarter"])
            amount_field: Amount field to aggregate (auto-detected if None)
            aggregations: Aggregation types ["sum", "count", "avg", "min", "max"]
            date_field: Date field for period-based grouping (auto-detected if None)
        
        Returns:
            AggregationResult with nested dictionary structure
        """
        if not group_fields:
            logger.warning("No group fields provided for multi-dimensional grouping")
            return AggregationResult(
                data={},
                dimensions=[],
                measures=["sum", "count"],
                row_count=0,
            )
        
        amount_field = amount_field or self.find_field(data, "amount")
        aggregations = aggregations or ["sum", "count"]
        
        # Handle special case: time-based fields need date field
        time_fields = {"quarter", "month", "year", "day", "week"}
        has_time_field = any(field in time_fields for field in group_fields)
        if has_time_field and not date_field:
            date_field = self.find_field(data, "date")
        
        # Build composite keys from all grouping fields
        groups: Dict[Tuple, Dict[str, Any]] = defaultdict(lambda: {"values": [], "count": 0})
        
        for row in data:
            # Build composite key from all grouping fields
            key_parts = []
            for field in group_fields:
                if field == "quarter" and date_field:
                    # Extract quarter from date using fiscal calendar
                    row_date = self._parse_date(row.get(date_field))
                    if row_date:
                        quarter = (row_date.month - 1) // 3 + 1
                        try:
                            fiscal_year = self.fiscal_calendar.get_fiscal_year_for_date(row_date)
                            key_parts.append(f"FY{fiscal_year} Q{quarter}")
                        except Exception:
                            # Fallback to calendar year if fiscal calendar fails
                            key_parts.append(f"{row_date.year}-Q{quarter}")
                    else:
                        key_parts.append("Unknown")
                elif field == "month" and date_field:
                    # Extract month from date
                    row_date = self._parse_date(row.get(date_field))
                    if row_date:
                        try:
                            fiscal_year = self.fiscal_calendar.get_fiscal_year_for_date(row_date)
                            # Calculate fiscal month (1-12, where 1 = first month of FY)
                            fy_start_month = self.fiscal_calendar.fy_start_month
                            if row_date.month >= fy_start_month:
                                fiscal_month = row_date.month - fy_start_month + 1
                            else:
                                fiscal_month = row_date.month + (12 - fy_start_month) + 1
                            key_parts.append(f"FY{fiscal_year} M{fiscal_month:02d}")
                        except Exception:
                            # Fallback to calendar month
                            key_parts.append(row_date.strftime("%Y-%m"))
                    else:
                        key_parts.append("Unknown")
                elif field == "year" and date_field:
                    # Extract fiscal year from date
                    row_date = self._parse_date(row.get(date_field))
                    if row_date:
                        try:
                            fiscal_year = self.fiscal_calendar.get_fiscal_year_for_date(row_date)
                            key_parts.append(f"FY{fiscal_year}")
                        except Exception:
                            key_parts.append(str(row_date.year))
                    else:
                        key_parts.append("Unknown")
                else:
                    # Regular field grouping
                    field_name = self.find_field(data, field)
                    if field_name:
                        value = row.get(field_name)
                        if value is None:
                            key_parts.append("Unknown")
                        else:
                            key_parts.append(str(value))
                    else:
                        key_parts.append("Unknown")
            
            key = tuple(key_parts)
            amount = self._parse_amount(row.get(amount_field, 0))
            groups[key]["values"].append(amount)
            groups[key]["count"] += 1
        
        # Convert to nested dictionary structure
        result = {}
        for key_tuple, group_data in groups.items():
            values = group_data["values"]
            agg_result = {"count": group_data["count"]}
            
            if "sum" in aggregations and values:
                agg_result["sum"] = sum(values)
            if "avg" in aggregations and values:
                agg_result["avg"] = sum(values) / len(values) if values else 0
            if "min" in aggregations and values:
                agg_result["min"] = min(values)
            if "max" in aggregations and values:
                agg_result["max"] = max(values)
            
            # Build nested structure
            current = result
            for i, key_part in enumerate(key_tuple):
                if i == len(key_tuple) - 1:
                    # Last level - store aggregation result
                    current[key_part] = agg_result
                else:
                    # Intermediate level - create nested dict
                    if key_part not in current:
                        current[key_part] = {}
                    current = current[key_part]
        
        return AggregationResult(
            data=result,
            dimensions=group_fields,
            measures=aggregations,
            row_count=len(groups),
        )
    
    def pivot_by_dimensions(
        self,
        data: List[Dict],
        row_dimension: str,
        column_dimension: str,
        value_field: str = None,
        aggregation: str = "sum"
    ) -> Dict[str, Dict[str, float]]:
        """
        Create a pivot table with two dimensions.
        
        Args:
            data: Data rows
            row_dimension: Field for row headers
            column_dimension: Field for column headers
            value_field: Field to aggregate
            aggregation: "sum", "count", "avg"
        
        Returns:
            Nested dict: {row_key: {col_key: value}}
        """
        value_field = value_field or self.find_field(data, "amount")
        
        pivot: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        
        for row in data:
            row_key = str(row.get(row_dimension, "Unknown"))
            col_key = str(row.get(column_dimension, "Unknown"))
            value = self._parse_amount(row.get(value_field, 0))
            pivot[row_key][col_key].append(value)
        
        result = {}
        for row_key, cols in pivot.items():
            result[row_key] = {}
            for col_key, values in cols.items():
                if aggregation == "sum":
                    result[row_key][col_key] = sum(values)
                elif aggregation == "count":
                    result[row_key][col_key] = len(values)
                elif aggregation == "avg":
                    result[row_key][col_key] = sum(values) / len(values) if values else 0
                else:
                    result[row_key][col_key] = sum(values)
        
        return result
    
    def compare_periods(
        self,
        data: List[Dict],
        current_period: FiscalPeriod,
        prior_period: FiscalPeriod,
        group_by: Union[str, List[str]] = None,
        amount_field: str = None,
        date_field: str = None
    ) -> List[Dict[str, Any]]:
        """
        Compare two periods and calculate variance.
        
        Args:
            data: All data (will be filtered to periods)
            current_period: Current period to analyze
            prior_period: Prior period to compare against
            group_by: Optional dimension(s) to group by (str or List[str])
            amount_field: Amount field to aggregate
            date_field: Date field for filtering
        
        Returns:
            List of comparison records with variance
        """
        amount_field = amount_field or self.find_field(data, "amount")
        date_field = date_field or self.find_field(data, "date")
        
        # Filter to each period
        current_data = self.filter_by_period(data, current_period, date_field).data
        prior_data = self.filter_by_period(data, prior_period, date_field).data
        
        if group_by:
            # Normalize group_by to list
            if isinstance(group_by, str):
                group_by_list = [group_by]
            else:
                group_by_list = group_by if isinstance(group_by, list) else []
            
            if len(group_by_list) == 1:
                # Single dimension - use existing method
                current_grouped = self.group_by_single(current_data, group_by_list[0], amount_field)
                prior_grouped = self.group_by_single(prior_data, group_by_list[0], amount_field)
                
                all_keys = set(current_grouped.data.keys()) | set(prior_grouped.data.keys())
                
                results = []
                for key in sorted(all_keys):
                    current_sum = current_grouped.data.get(key, {}).get("sum", 0) or 0
                    prior_sum = prior_grouped.data.get(key, {}).get("sum", 0) or 0
                    
                    variance = current_sum - prior_sum
                    pct_change = (variance / abs(prior_sum)) if prior_sum != 0 else None
                    
                    results.append({
                        group_by_list[0]: key,
                        "current_period": current_period.period_name,
                        "current_amount": current_sum,
                        "prior_period": prior_period.period_name,
                        "prior_amount": prior_sum,
                        "variance": variance,
                        "variance_pct": pct_change,
                    })
                
                return results
            else:
                # Multiple dimensions - use multi-dimensional method
                current_grouped = self.group_by_multiple(
                    current_data, group_by_list, amount_field, date_field=date_field
                )
                prior_grouped = self.group_by_multiple(
                    prior_data, group_by_list, amount_field, date_field=date_field
                )
                
                # Flatten nested structure for comparison
                def flatten_nested(data_dict, prefix="", result=None):
                    """Flatten nested dictionary to list of records."""
                    if result is None:
                        result = []
                    
                    for key, value in data_dict.items():
                        current_key = f"{prefix}.{key}" if prefix else key
                        if isinstance(value, dict) and "sum" in value:
                            # Leaf node with aggregation
                            result.append({
                                "_key": current_key,
                                "_group_by": group_by_list,
                                "sum": value.get("sum", 0),
                                "count": value.get("count", 0),
                            })
                        elif isinstance(value, dict):
                            # Intermediate node
                            flatten_nested(value, current_key, result)
                    
                    return result
                
                current_flat = {r["_key"]: r for r in flatten_nested(current_grouped.data)}
                prior_flat = {r["_key"]: r for r in flatten_nested(prior_grouped.data)}
                
                all_keys = set(current_flat.keys()) | set(prior_flat.keys())
                
                results = []
                for key in sorted(all_keys):
                    current_sum = current_flat.get(key, {}).get("sum", 0) or 0
                    prior_sum = prior_flat.get(key, {}).get("sum", 0) or 0
                    
                    variance = current_sum - prior_sum
                    pct_change = (variance / abs(prior_sum)) if prior_sum != 0 else None
                    
                    results.append({
                        "_key": key,
                        "_group_by": group_by_list,
                        "current_period": current_period.period_name,
                        "current_amount": current_sum,
                        "prior_period": prior_period.period_name,
                        "prior_amount": prior_sum,
                        "variance": variance,
                        "variance_pct": pct_change,
                    })
                
                return results
        else:
            # Total comparison
            current_total = sum(self._parse_amount(r.get(amount_field, 0)) for r in current_data)
            prior_total = sum(self._parse_amount(r.get(amount_field, 0)) for r in prior_data)
            
            variance = current_total - prior_total
            pct_change = (variance / abs(prior_total)) if prior_total != 0 else None
            
            return [{
                "category": "Total",
                "current_period": current_period.period_name,
                "current_amount": current_total,
                "prior_period": prior_period.period_name,
                "prior_amount": prior_total,
                "variance": variance,
                "variance_pct": pct_change,
            }]
    
    def _parse_amount(self, value: Any) -> float:
        """Parse a value as a float amount."""
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # Remove currency symbols, commas, parentheses for negative
            cleaned = re.sub(r"[$,]", "", value)
            if cleaned.startswith("(") and cleaned.endswith(")"):
                cleaned = "-" + cleaned[1:-1]
            try:
                return float(cleaned)
            except ValueError:
                return 0.0
        return 0.0
    
    def _parse_date(self, value: Any) -> Optional[date]:
        """Parse a value as a date."""
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            value = value.strip()
            # Try various date formats
            formats = [
                "%Y-%m-%d",           # 2024-01-15
                "%m/%d/%Y",           # 01/15/2024
                "%d/%m/%Y",           # 15/01/2024
                "%Y/%m/%d",           # 2024/01/15
                "%m-%d-%Y",           # 01-15-2024
                "%d-%m-%Y",           # 15-01-2024
                "%Y-%m-%dT%H:%M:%S",  # 2024-01-15T00:00:00
                "%m/%d/%Y %H:%M:%S",  # 01/15/2024 12:00:00
                "%Y-%m-%d %H:%M:%S",  # 2024-01-15 12:00:00
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(value[:len(value)].split('.')[0], fmt).date()
                except (ValueError, IndexError):
                    continue
            # Try just the date portion if there's a time component
            if 'T' in value or ' ' in value:
                date_part = value.split('T')[0].split(' ')[0]
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
                    try:
                        return datetime.strptime(date_part, fmt).date()
                    except (ValueError, IndexError):
                        continue
        return None

# Singleton instance
_data_processor: Optional[DataProcessor] = None

def get_data_processor() -> DataProcessor:
    """Get the configured data processor instance."""
    global _data_processor
    if _data_processor is None:
        _data_processor = DataProcessor()
    return _data_processor

