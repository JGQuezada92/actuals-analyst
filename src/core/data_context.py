"""
Data Context Loader

Loads and caches data interpretation rules from configuration files.
Provides helper functions for parsing NetSuite data according to defined rules.

This module enables configuration-driven data interpretation without hardcoding
rules in the codebase. Update config/data_dictionary.yaml to change parsing rules.
"""
import os
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from functools import lru_cache

logger = logging.getLogger(__name__)

# Find config directory
def _get_config_dir() -> Path:
    """Get the config directory path."""
    # Try relative to this file
    src_core = Path(__file__).parent
    project_root = src_core.parent.parent
    config_dir = project_root / "config"
    
    if config_dir.exists():
        return config_dir
    
    # Try current working directory
    cwd_config = Path.cwd() / "config"
    if cwd_config.exists():
        return cwd_config
    
    raise FileNotFoundError(f"Config directory not found. Tried: {config_dir}, {cwd_config}")


@dataclass
class DepartmentInfo:
    """Parsed department information."""
    raw_value: str
    cost_category: str
    department_name: str
    
    def __str__(self) -> str:
        return f"{self.department_name} ({self.cost_category})"


@dataclass
class AccountInfo:
    """Parsed account information."""
    account_number: str
    account_name: str
    statement_type: str  # "income_statement" or "balance_sheet"
    cost_category: Optional[str] = None
    subcategory: Optional[str] = None
    
    @property
    def is_income_statement(self) -> bool:
        return self.statement_type == "income_statement"
    
    @property
    def is_balance_sheet(self) -> bool:
        return self.statement_type == "balance_sheet"


class DataContext:
    """
    Loads and provides access to data interpretation rules.
    
    Usage:
        context = DataContext()
        date_field = context.get_primary_date_field()
        dept_info = context.parse_department("G&A (Parent) : Finance")
        acct_info = context.classify_account("601010")
    """
    
    def __init__(self, config_dir: Path = None):
        """
        Initialize the data context.
        
        Args:
            config_dir: Path to config directory (auto-detected if None)
        """
        self.config_dir = config_dir or _get_config_dir()
        self._config: Dict[str, Any] = {}
        self._context_md: str = ""
        self._load_config()
    
    def _load_config(self):
        """Load configuration from YAML file."""
        yaml_path = self.config_dir / "data_dictionary.yaml"
        md_path = self.config_dir / "analysis_context.md"
        
        # Load YAML config
        if yaml_path.exists():
            try:
                import yaml
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f) or {}
                logger.info(f"Loaded data dictionary from {yaml_path}")
            except ImportError:
                logger.warning("PyYAML not installed. Using fallback config.")
                self._config = self._get_fallback_config()
            except Exception as e:
                logger.error(f"Failed to load data dictionary: {e}")
                self._config = self._get_fallback_config()
        else:
            logger.warning(f"Data dictionary not found at {yaml_path}. Using fallback.")
            self._config = self._get_fallback_config()
        
        # Load markdown context
        if md_path.exists():
            try:
                with open(md_path, 'r', encoding='utf-8') as f:
                    self._context_md = f.read()
                logger.info(f"Loaded analysis context from {md_path}")
            except Exception as e:
                logger.error(f"Failed to load analysis context: {e}")
                self._context_md = self._get_fallback_context()
        else:
            self._context_md = self._get_fallback_context()
    
    def _get_fallback_config(self) -> Dict[str, Any]:
        """Return fallback configuration if YAML can't be loaded."""
        return {
            "date_fields": {
                "period_field": "accountingPeriod_periodname",  # Primary for period filtering
                "primary": "trandate",  # Fallback for date-range filtering
                "fallback": "formuladate",
            },
            "department_hierarchy": {
                "field": "department_name",
                "separator": " : ",
            },
            "account_classification": {
                "number_field": "account_number",
                "name_field": "account_name",
                "income_statement": {"prefixes": ["4", "5", "6", "7", "8"]},
                "balance_sheet": {"prefixes": ["1", "2", "3"]},
            },
            "amount_fields": {
                "primary": "amount",
                "debit": "debitamount",
                "credit": "creditamount",
            },
            "fiscal_calendar": {
                "start_month": 2,
            },
        }
    
    def _get_fallback_context(self) -> str:
        """Return fallback context if markdown can't be loaded."""
        return """
## Data Interpretation

- Use Month-End Date for date filtering
- Department names: "Cost Category : Department Name"
- Account numbers 4-8 = Income Statement, 1-3 = Balance Sheet
- Fiscal year starts in February
"""
    
    # =========================================================================
    # DATE FIELDS
    # =========================================================================
    
    def get_primary_date_field(self) -> str:
        """
        Get the primary date field name to use for filtering.
        
        Note: For period-based filtering (matching export file), use get_period_field() instead.
        This method returns the date field for date-range filtering (fallback only).
        """
        return self._config.get("date_fields", {}).get("primary", "trandate")
    
    def get_fallback_date_field(self) -> str:
        """Get the fallback date field if primary is not available."""
        return self._config.get("date_fields", {}).get("fallback", "trandate")
    
    def get_period_field(self) -> str:
        """
        Get the accounting period field name for period-based filtering.
        
        This is the PRIMARY field for date filtering and matches the export file's
        "Month-End Date (Text Format)" filter. Use this for filtering by period names
        (e.g., "Jan 2024", "Feb 2024") rather than date ranges.
        """
        return self._config.get("date_fields", {}).get("period_field", "accountingPeriod_periodname")
    
    def get_date_fields(self) -> List[str]:
        """
        Get all date-related fields in order of preference.
        
        Note: For period-based filtering, use get_period_field() instead.
        This method returns date fields for date-range filtering (fallback only).
        """
        df = self._config.get("date_fields", {})
        return [
            df.get("period_field", "accountingPeriod_periodname"),  # Primary for period filtering
            df.get("primary", "trandate"),  # Fallback for date-range filtering
            df.get("fallback", "formuladate"),
        ]
    
    # =========================================================================
    # DEPARTMENT PARSING
    # =========================================================================
    
    def get_department_field(self) -> str:
        """Get the department field name."""
        return self._config.get("department_hierarchy", {}).get("field", "department_name")
    
    def get_department_separator(self) -> str:
        """Get the separator used in department hierarchy."""
        return self._config.get("department_hierarchy", {}).get("separator", " : ")
    
    def parse_department(self, raw_value: str) -> DepartmentInfo:
        """
        Parse a department value into cost category and department name.
        
        Args:
            raw_value: Raw department string like "G&A (Parent) : Finance"
        
        Returns:
            DepartmentInfo with parsed components
        """
        if not raw_value:
            return DepartmentInfo(
                raw_value="",
                cost_category="Unknown",
                department_name="Unknown",
            )
        
        separator = self.get_department_separator()
        parts = raw_value.split(separator)
        
        if len(parts) >= 2:
            cost_category = parts[0].strip()
            department_name = parts[1].strip()
            
            # Clean up "(Parent)" suffix from cost category
            cost_category = re.sub(r'\s*\(Parent\)\s*$', '', cost_category)
            
            # Also clean up "(Parent)" from department name if present
            department_name = re.sub(r'\s*\(Parent\)\s*$', '', department_name)
        else:
            # No separator found, use as-is
            cost_category = re.sub(r'\s*\(Parent\)\s*$', '', raw_value.strip())
            department_name = cost_category
        
        return DepartmentInfo(
            raw_value=raw_value,
            cost_category=cost_category,
            department_name=department_name,
        )
    
    def get_cost_categories(self) -> List[Dict[str, str]]:
        """Get the list of known cost categories."""
        return self._config.get("department_hierarchy", {}).get("cost_categories", [])
    
    # =========================================================================
    # ACCOUNT CLASSIFICATION
    # =========================================================================
    
    def get_account_number_field(self) -> str:
        """Get the account number field name."""
        return self._config.get("account_classification", {}).get("number_field", "account_number")
    
    def get_account_name_field(self) -> str:
        """Get the account name field name."""
        return self._config.get("account_classification", {}).get("name_field", "account_name")
    
    def classify_account(self, account_number: str, account_name: str = "") -> AccountInfo:
        """
        Classify an account as income statement or balance sheet.
        Supports 1-digit, 2-digit, and 3-digit prefix classification.
        
        Args:
            account_number: The account number (e.g., "531010", "598010")
            account_name: Optional account name for additional parsing
        
        Returns:
            AccountInfo with classification
        """
        account_number = str(account_number).strip()
        
        if not account_number:
            return AccountInfo(
                account_number="",
                account_name=account_name,
                statement_type="unknown",
            )
        
        first_digit = account_number[0]
        acct_class = self._config.get("account_classification", {})
        
        # Check income statement prefixes
        is_prefixes = acct_class.get("income_statement", {}).get("prefixes", ["4", "5", "6", "7", "8"])
        if first_digit in is_prefixes:
            statement_type = "income_statement"
            
            # Find subcategory - check 3-digit, then 2-digit, then 1-digit prefixes
            subcategory = None
            
            # Check for 3-digit prefix first (e.g., 598)
            if len(account_number) >= 3:
                three_digit = account_number[:3]
                for subcat in acct_class.get("income_statement", {}).get("subcategories", []):
                    # Check nested subcategories for 3-digit match
                    nested_subs = subcat.get("subcategories", [])
                    for nested_sub in nested_subs:
                        if nested_sub.get("prefix") == three_digit:
                            subcategory = nested_sub.get("name")
                            break
                    if subcategory:
                        break
            
            # Check for 2-digit prefix if no 3-digit match (e.g., 51, 52, 53, 59)
            if not subcategory and len(account_number) >= 2:
                two_digit = account_number[:2]
                for subcat in acct_class.get("income_statement", {}).get("subcategories", []):
                    nested_subs = subcat.get("subcategories", [])
                    for nested_sub in nested_subs:
                        if nested_sub.get("prefix") == two_digit:
                            subcategory = nested_sub.get("name")
                            break
                    if subcategory:
                        break
            
            # Fall back to 1-digit prefix if no 2-digit or 3-digit match
            if not subcategory:
                for subcat in acct_class.get("income_statement", {}).get("subcategories", []):
                    if subcat.get("prefix") == first_digit:
                        subcategory = subcat.get("name")
                        break
        else:
            # Check balance sheet prefixes
            bs_prefixes = acct_class.get("balance_sheet", {}).get("prefixes", ["1", "2", "3"])
            if first_digit in bs_prefixes:
                statement_type = "balance_sheet"
                
                # Find subcategory
                subcategory = None
                for subcat in acct_class.get("balance_sheet", {}).get("subcategories", []):
                    if subcat.get("prefix") == first_digit:
                        subcategory = subcat.get("name")
                        break
            else:
                statement_type = "unknown"
                subcategory = None
        
        # Parse cost category from account name
        cost_category = None
        if account_name:
            separator = self._config.get("account_hierarchy", {}).get("separator", " : ")
            parts = account_name.split(separator)
            if parts:
                cost_category = parts[0].strip()
        
        return AccountInfo(
            account_number=account_number,
            account_name=account_name,
            statement_type=statement_type,
            cost_category=cost_category,
            subcategory=subcategory,
        )
    
    def is_income_statement_account(self, account_number: str) -> bool:
        """Check if an account is an income statement account."""
        info = self.classify_account(account_number)
        return info.is_income_statement
    
    def is_balance_sheet_account(self, account_number: str) -> bool:
        """Check if an account is a balance sheet account."""
        info = self.classify_account(account_number)
        return info.is_balance_sheet
    
    # =========================================================================
    # AMOUNT FIELDS
    # =========================================================================
    
    def get_amount_field(self) -> str:
        """Get the primary amount field name."""
        return self._config.get("amount_fields", {}).get("primary", "amount")
    
    def get_debit_field(self) -> str:
        """Get the debit amount field name."""
        return self._config.get("amount_fields", {}).get("debit", "debitamount")
    
    def get_credit_field(self) -> str:
        """Get the credit amount field name."""
        return self._config.get("amount_fields", {}).get("credit", "creditamount")
    
    # =========================================================================
    # FISCAL CALENDAR
    # =========================================================================
    
    def get_fiscal_year_start_month(self) -> int:
        """Get the month when fiscal year starts (1-12)."""
        return self._config.get("fiscal_calendar", {}).get("start_month", 2)
    
    # =========================================================================
    # LLM CONTEXT
    # =========================================================================
    
    def get_llm_context(self) -> str:
        """
        Get the full context markdown for inclusion in LLM prompts.
        
        Returns:
            Markdown string with data interpretation rules
        """
        return self._context_md
    
    def get_llm_context_summary(self) -> str:
        """
        Get a shorter summary of key interpretation rules.
        
        Returns:
            Condensed context for token-limited prompts
        """
        return f"""## Data Interpretation Rules

**Dates**: Use Month-End Date (formuladate) for all date filtering.

**Departments**: Format is "Cost Category : Department Name"
- G&A = Administrative overhead
- Cost of Sales = Direct delivery costs
- R&D = Engineering/product costs

**Accounts**: 
- Numbers starting with 4-8 = Income Statement (P&L)
  - 4xxx = Revenue
  - 5xxx = Operating Expenses (parent)
    - 51xxx = Cost of Goods Sold/Cost of Sales
    - 52xxx = R&D/Product Development
    - 53xxx = Sales & Marketing/S&M
    - 59xxx = General & Administrative/G&A
    - 598xx = Depreciation & Amortization (within G&A)
  - 6xxx = Interest (expense or income)
  - 7xxx, 8xxx = Income Tax, Other Expense and Other Income
- Numbers starting with 1-3 = Balance Sheet

**Fiscal Year**: Starts in February (FY2025 = Feb 2025 - Jan 2026)
"""
    
    def get_field_mappings(self) -> Dict[str, str]:
        """
        Get a dictionary of logical field names to actual field names.
        
        Returns:
            Dict mapping logical names to actual column names
        """
        return {
            "date": self.get_primary_date_field(),
            "date_fallback": self.get_fallback_date_field(),
            "period": self.get_period_field(),
            "department": self.get_department_field(),
            "account_number": self.get_account_number_field(),
            "account_name": self.get_account_name_field(),
            "amount": self.get_amount_field(),
            "debit": self.get_debit_field(),
            "credit": self.get_credit_field(),
        }


# Singleton instance
_data_context: Optional[DataContext] = None

def get_data_context() -> DataContext:
    """Get the configured data context instance."""
    global _data_context
    if _data_context is None:
        _data_context = DataContext()
    return _data_context

def reset_data_context():
    """Reset the data context (useful for testing or reloading config)."""
    global _data_context
    _data_context = None

