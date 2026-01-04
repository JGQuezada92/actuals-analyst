"""
NetSuite Filter Builder

Converts ParsedQuery objects into NetSuite RESTlet filter parameters.
This enables server-side filtering to dramatically reduce data transfer.

The key insight: Instead of fetching 391,000 rows and filtering in Python,
we send filter parameters to NetSuite and only fetch the matching rows.

Uses accountingPeriod_periodname for date filtering (e.g., "Jan 2024", "Feb 2024")
to match the export file's "Month-End Date (Text Format)" filter.
"""
import os
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from datetime import date
import calendar

if TYPE_CHECKING:
    from src.core.query_parser import ParsedQuery
    from src.core.fiscal_calendar import FiscalPeriod

logger = logging.getLogger(__name__)


@dataclass
class NetSuiteFilterParams:
    """
    Container for filter parameters to send to the NetSuite RESTlet.
    
    These parameters are added to the RESTlet URL query string and
    processed server-side to filter data before pagination.
    
    Uses accountingPeriod_periodname for date filtering (e.g., "Jan 2024", "Feb 2024")
    to match the export file's "Month-End Date (Text Format)" filter.
    """
    period_names: Optional[List[str]] = None  # Accounting period names (e.g., ["Jan 2024", "Feb 2024"])
    start_date: Optional[str] = None  # MM/DD/YYYY format (fallback if period_names not provided)
    end_date: Optional[str] = None    # MM/DD/YYYY format (fallback if period_names not provided)
    date_field: str = "trandate"   # Date field for fallback date filtering (default: trandate)
    departments: List[str] = None
    account_prefixes: List[str] = None
    account_name: Optional[str] = None
    transaction_types: List[str] = None
    subsidiary: Optional[str] = None
    exclude_totals: bool = True
    
    def __post_init__(self):
        if self.departments is None:
            self.departments = []
        if self.account_prefixes is None:
            self.account_prefixes = []
        if self.transaction_types is None:
            self.transaction_types = []
    
    def to_query_params(self) -> Dict[str, str]:
        """
        Convert to URL query parameters for the RESTlet.
        
        NOTE: period_names are NOT sent to RESTlet because server-side period filtering
        doesn't work reliably. Period filtering is applied client-side instead.
        
        Returns:
            Dict of parameter name to value, ready for URL encoding
        """
        params = {}
        
        # DO NOT send period_names to RESTlet - server-side filtering doesn't work
        # Period filtering will be applied client-side using accountingPeriod_periodname
        # Only use date range as fallback if period_names not available
        if self.period_names:
            # Skip sending periodNames to RESTlet - will filter client-side
            logger.debug(f"Skipping periodNames server-side filter (will filter client-side): {self.period_names}")
        elif self.start_date and self.end_date:
            # Fallback: use date range if period names not available
            params["startDate"] = self.start_date
            params["endDate"] = self.end_date
            params["dateField"] = self.date_field
        
        if self.departments:
            params["department"] = ",".join(self.departments)
        
        if self.account_prefixes:
            params["accountPrefix"] = ",".join(self.account_prefixes)
        
        if self.account_name:
            params["accountName"] = self.account_name
        
        if self.transaction_types:
            params["transactionType"] = ",".join(self.transaction_types)
        
        if self.subsidiary:
            params["subsidiary"] = self.subsidiary
        
        if self.exclude_totals:
            params["excludeTotals"] = "true"
        
        return params
    
    def has_filters(self) -> bool:
        """Check if any filters are set."""
        return bool(
            self.period_names or
            (self.start_date and self.end_date) or
            self.departments or
            self.account_prefixes or
            self.account_name or
            self.transaction_types or
            self.subsidiary
        )
    
    def describe(self) -> str:
        """Return human-readable description of filters."""
        parts = []
        
        if self.period_names:
            parts.append(f"Accounting Periods: {', '.join(self.period_names)}")
        elif self.start_date and self.end_date:
            parts.append(f"Date: {self.start_date} to {self.end_date}")
        
        if self.departments:
            parts.append(f"Departments: {', '.join(self.departments)}")
        
        if self.account_prefixes:
            parts.append(f"Account prefixes: {', '.join(self.account_prefixes)}")
        
        if self.account_name:
            parts.append(f"Account name contains: {self.account_name}")
        
        if self.transaction_types:
            parts.append(f"Transaction types: {', '.join(self.transaction_types)}")
        
        if self.subsidiary:
            parts.append(f"Subsidiary: {self.subsidiary}")
        
        return "; ".join(parts) if parts else "No filters"


class NetSuiteFilterBuilder:
    """
    Builds NetSuite filter parameters from ParsedQuery objects.
    
    This class translates the semantic query understanding (ParsedQuery)
    into concrete NetSuite filter parameters that the RESTlet can apply.
    
    Uses accountingPeriod_periodname for date filtering (e.g., "Jan 2024", "Feb 2024")
    to match the export file's "Month-End Date (Text Format)" filter.
    
    Usage:
        builder = NetSuiteFilterBuilder()
        filter_params = builder.build_from_parsed_query(parsed_query)
        query_params = filter_params.to_query_params()
    """
    
    # Date format expected by NetSuite
    NETSUITE_DATE_FORMAT = "%m/%d/%Y"
    
    # Month abbreviations for period name formatting
    MONTH_ABBREVIATIONS = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    ]
    
    def __init__(self, date_field: str = "trandate"):
        """
        Initialize the filter builder.
        
        Args:
            date_field: The date field to use for fallback date filtering
                       (only used if period names cannot be generated).
                       Default: "trandate" (Accounting Posting Date).
        """
        self.date_field = date_field
    
    def build_from_parsed_query(self, parsed_query: 'ParsedQuery') -> NetSuiteFilterParams:
        """
        Build filter parameters from a ParsedQuery.
        
        Args:
            parsed_query: The parsed query with extracted filters
        
        Returns:
            NetSuiteFilterParams ready to send to the RESTlet
        """
        params = NetSuiteFilterParams(date_field=self.date_field)
        
        # Extract accounting period names from time period
        if parsed_query.time_period:
            period_names = self._date_range_to_period_names(
                parsed_query.time_period.start_date,
                parsed_query.time_period.end_date
            )
            if period_names:
                params.period_names = period_names
                logger.debug(
                    f"Accounting period filter: {', '.join(period_names)} "
                    f"({parsed_query.time_period.period_name})"
                )
            else:
                # Fallback to date range if period names cannot be generated
                params.start_date = self._format_date(parsed_query.time_period.start_date)
                params.end_date = self._format_date(parsed_query.time_period.end_date)
                logger.debug(
                    f"Date filter (fallback): {params.start_date} to {params.end_date} "
                    f"({parsed_query.time_period.period_name})"
                )
        
        # Extract departments
        if parsed_query.departments:
            params.departments = list(parsed_query.departments)
            logger.debug(f"Department filter: {params.departments}")
        
        # Extract account type filter (prefixes)
        if parsed_query.account_type_filter:
            filter_type = parsed_query.account_type_filter.get("filter_type", "prefix")
            values = parsed_query.account_type_filter.get("values", [])
            
            if filter_type == "prefix" and values:
                params.account_prefixes = list(values)
                logger.debug(f"Account prefix filter: {params.account_prefixes}")
        
        # Extract account name filter
        if parsed_query.account_name_filter:
            values = parsed_query.account_name_filter.get("values", [])
            if values:
                # Use the first value for server-side filtering
                # Multiple values would need OR logic which is complex server-side
                params.account_name = values[0]
                logger.debug(f"Account name filter: {params.account_name}")
        
        # Extract transaction type filter
        if parsed_query.transaction_type_filter:
            params.transaction_types = list(parsed_query.transaction_type_filter)
            logger.debug(f"Transaction type filter: {params.transaction_types}")
        
        # Extract subsidiary filter
        if parsed_query.subsidiaries:
            # Use first subsidiary for server-side filter
            params.subsidiary = parsed_query.subsidiaries[0]
            logger.debug(f"Subsidiary filter: {params.subsidiary}")
        
        # Always exclude totals to prevent double-counting
        params.exclude_totals = True
        
        logger.info(f"Built server-side filters: {params.describe()}")
        
        return params
    
    def build_from_components(
        self,
        time_period: 'FiscalPeriod' = None,
        departments: List[str] = None,
        account_prefixes: List[str] = None,
        account_name: str = None,
        transaction_types: List[str] = None,
        subsidiary: str = None,
    ) -> NetSuiteFilterParams:
        """
        Build filter parameters from individual components.
        
        Useful when you don't have a ParsedQuery but have the filter values.
        """
        params = NetSuiteFilterParams(date_field=self.date_field)
        
        if time_period:
            period_names = self._date_range_to_period_names(
                time_period.start_date,
                time_period.end_date
            )
            if period_names:
                params.period_names = period_names
            else:
                # Fallback to date range
                params.start_date = self._format_date(time_period.start_date)
                params.end_date = self._format_date(time_period.end_date)
        
        if departments:
            params.departments = list(departments)
        
        if account_prefixes:
            params.account_prefixes = list(account_prefixes)
        
        if account_name:
            params.account_name = account_name
        
        if transaction_types:
            params.transaction_types = list(transaction_types)
        
        if subsidiary:
            params.subsidiary = subsidiary
        
        return params
    
    def _format_date(self, d: date) -> str:
        """Format a date for NetSuite."""
        return d.strftime(self.NETSUITE_DATE_FORMAT)
    
    def _date_range_to_period_names(self, start_date: date, end_date: date) -> List[str]:
        """
        Convert a date range to accounting period names.
        
        Period names are in format "MMM YYYY" (e.g., "Jan 2024", "Feb 2024").
        This matches the accountingPeriod_periodname field in NetSuite.
        
        Args:
            start_date: Start date of the range
            end_date: End date of the range
        
        Returns:
            List of period names covering the date range, or empty list if conversion fails
        """
        try:
            period_names = []
            current = date(start_date.year, start_date.month, 1)
            end = date(end_date.year, end_date.month, 1)
            
            while current <= end:
                month_abbr = self.MONTH_ABBREVIATIONS[current.month - 1]
                period_name = f"{month_abbr} {current.year}"
                period_names.append(period_name)
                
                # Move to next month
                if current.month == 12:
                    current = date(current.year + 1, 1, 1)
                else:
                    current = date(current.year, current.month + 1, 1)
            
            logger.debug(
                f"Converted date range {start_date} to {end_date} "
                f"to periods: {', '.join(period_names)}"
            )
            return period_names
            
        except Exception as e:
            logger.warning(f"Failed to convert date range to period names: {e}")
            return []


# Factory function
def get_filter_builder(date_field: Optional[str] = None) -> NetSuiteFilterBuilder:
    """
    Get a configured filter builder.
    
    Args:
        date_field: Optional date field override for fallback date filtering.
                   If not provided, reads from NETSUITE_FILTER_DATE_FIELD environment
                   variable (default: "trandate").
                   Note: Primary filtering uses accountingPeriod_periodname.
    """
    if date_field is None:
        date_field = os.getenv("NETSUITE_FILTER_DATE_FIELD", "trandate")
    return NetSuiteFilterBuilder(date_field=date_field)

