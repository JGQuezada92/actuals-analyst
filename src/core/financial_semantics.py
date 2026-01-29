"""
Financial Semantics Module

Provides semantic mapping between natural language financial terms and their
technical filters. This module ensures that terms like "revenue" correctly map
to account-based filters (accounts starting with "4") rather than department
filters (Sales department).

Key Concepts:
- Account-based terms: Filter on account number prefixes (revenue, expenses, COGS)
- Ambiguous terms: Require user disambiguation (e.g., "sales" could be either)
- Transaction type terms: Filter on transaction types (journals, invoices)
- Compound account terms: Filter on BOTH account number AND name

IMPORTANT: Department names are NOT in this dictionary.
All department resolution is handled by the DynamicRegistry which
discovers departments automatically from NetSuite data. This ensures:
1. No manual maintenance when org structure changes
2. Proper disambiguation for similar names (Product Marketing vs Product Management)
3. Exact matching instead of substring matching
"""
import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class SemanticCategory(Enum):
    """Category of a semantic term."""
    ACCOUNT = "account"                    # Filter on account NUMBER (prefix, exact)
    ACCOUNT_NAME = "account_name"          # Filter on account NAME (contains)
    COMPOUND_ACCOUNT = "compound_account"  # Filter on BOTH account number AND name
    DEPARTMENT = "department"
    TRANSACTION_TYPE = "transaction_type"
    SUBSIDIARY = "subsidiary"
    AMBIGUOUS = "ambiguous"


class FilterType(Enum):
    """Type of filter to apply."""
    PREFIX = "prefix"
    EXACT = "exact"
    CONTAINS = "contains"
    IN_LIST = "in_list"


@dataclass
class SemanticTerm:
    """
    Represents a semantic mapping between a natural language term and its technical filter.
    
    Attributes:
        term: The natural language term (e.g., "revenue", "marketing")
        category: The semantic category (account, department, transaction_type, ambiguous)
        filter_type: How to apply the filter (prefix, exact, contains, in_list)
        filter_values: The actual filter values to apply
        disambiguation_required: True if the term needs user clarification
        disambiguation_options: Options to present if disambiguation is needed
        description: Human-readable explanation of what this term means
        
        For COMPOUND_ACCOUNT category (filters on BOTH account number AND name):
        secondary_filter_type: How to filter the account name
        secondary_filter_values: Values for account name filter
    """
    term: str
    category: SemanticCategory
    filter_type: FilterType
    filter_values: List[str]
    disambiguation_required: bool = False
    disambiguation_options: Optional[List[Dict[str, Any]]] = None
    description: str = ""
    # For compound filters (account number + account name)
    secondary_filter_type: Optional[FilterType] = None
    secondary_filter_values: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "term": self.term,
            "category": self.category.value,
            "filter_type": self.filter_type.value,
            "filter_values": self.filter_values,
            "disambiguation_required": self.disambiguation_required,
            "disambiguation_options": self.disambiguation_options,
            "description": self.description,
        }
        if self.secondary_filter_type and self.secondary_filter_values:
            result["secondary_filter_type"] = self.secondary_filter_type.value
            result["secondary_filter_values"] = self.secondary_filter_values
        return result


# =============================================================================
# FINANCIAL SEMANTICS DICTIONARY
# =============================================================================
# This is the central mapping of financial terms to their technical filters.
# Each entry maps a natural language term to its proper interpretation.
#
# ARCHITECTURE:
# - ACCOUNT terms: Filter on account NUMBER prefixes (revenue→"4", expenses→"5")
# - COMPOUND_ACCOUNT terms: Filter on BOTH account number AND name
# - TRANSACTION_TYPE terms: Filter on transaction types
# - SUBSIDIARY terms: Filter on subsidiary names
# - AMBIGUOUS terms: Require user disambiguation (e.g., "sales")
#
# IMPORTANT: Department names are NOT in this dictionary.
# All department resolution is handled by the DynamicRegistry which
# discovers departments automatically from NetSuite data. This ensures:
# 1. No manual maintenance when org structure changes
# 2. Proper disambiguation for similar names (Product Marketing vs Product Management)
# 3. Exact matching instead of substring matching
#
# =============================================================================
# CORE FINANCIAL SEMANTICS (STATIC)
# =============================================================================
# These mappings represent fundamental accounting concepts that NEVER change:
# - Account type prefixes (revenue = 4, expenses = 5-8, etc.)
# - Financial statement classifications
# - Core accounting terms
#
# IMPORTANT: Account names and subsidiary names should NOT be hardcoded here.
# They are dynamically discovered by the DynamicRegistry
# from actual NetSuite data. This ensures the system stays up-to-date when
# organizational structures change.
#
# What SHOULD be here:
# - "revenue" -> account prefix "4"
# - "expenses" -> account prefix "5,6,7,8"
# - "cogs" -> account prefix "51"
# - etc.
#
# What should NOT be here:
# - "marketing" -> department filter (handled by DynamicRegistry)
# - "GPS" -> department filter (handled by DynamicRegistry)
# - "Phenom People Inc" -> subsidiary filter (handled by DynamicRegistry)
# =============================================================================

FINANCIAL_SEMANTICS: Dict[str, SemanticTerm] = {
    # -------------------------------------------------------------------------
    # ACCOUNT-BASED TERMS (filter on account number prefix)
    # -------------------------------------------------------------------------
    
    # Revenue accounts (4xxx)
    "revenue": SemanticTerm(
        term="revenue",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["4"],
        description="Revenue/income accounts (account numbers starting with 4)",
    ),
    "sales revenue": SemanticTerm(
        term="sales revenue",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["4"],
        description="Sales revenue accounts (account numbers starting with 4)",
    ),
    "income": SemanticTerm(
        term="income",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["4"],
        description="Income accounts (account numbers starting with 4)",
    ),
    "revenues": SemanticTerm(
        term="revenues",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["4"],
        description="Revenue accounts (account numbers starting with 4)",
    ),
    
    # Operating Expenses (5xxx) - Parent category
    "operating expenses": SemanticTerm(
        term="operating expenses",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["5"],
        description="Operating expense accounts (account numbers starting with 5)",
    ),
    "opex": SemanticTerm(
        term="opex",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["5"],
        description="Operating expense accounts (account numbers starting with 5)",
    ),
    "operating costs": SemanticTerm(
        term="operating costs",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["5"],
        description="Operating expense accounts (account numbers starting with 5)",
    ),
    
    # Cost of Goods Sold (51xxx)
    # Cost of Sales/COGS - AMBIGUOUS (could mean accounts OR departments)
    "cogs": SemanticTerm(
        term="cogs",
        category=SemanticCategory.AMBIGUOUS,
        filter_type=FilterType.PREFIX,
        filter_values=[],
        disambiguation_required=True,
        disambiguation_options=[
            {
                "label": "COGS Accounts (51xxx account numbers)",
                "category": "account",
                "filter_type": "prefix",
                "filter_values": ["51"],
                "description": "Filter by Cost of Goods Sold accounts (account numbers starting with 51)",
            },
            {
                "label": "Cost of Sales Departments (COS org structure)",
                "category": "department",
                "filter_type": "contains",
                "filter_values": ["Cost of Sales"],
                "description": "Filter by Cost of Sales department hierarchy",
            },
        ],
        description="COGS could mean account category (51xxx) or Cost of Sales departments",
    ),
    "cost of goods sold": SemanticTerm(
        term="cost of goods sold",
        category=SemanticCategory.AMBIGUOUS,
        filter_type=FilterType.PREFIX,
        filter_values=[],
        disambiguation_required=True,
        disambiguation_options=[
            {
                "label": "COGS Accounts (51xxx account numbers)",
                "category": "account",
                "filter_type": "prefix",
                "filter_values": ["51"],
                "description": "Filter by COGS accounts (account numbers starting with 51)",
            },
            {
                "label": "Cost of Sales Departments",
                "category": "department",
                "filter_type": "contains",
                "filter_values": ["Cost of Sales"],
                "description": "Filter by Cost of Sales department hierarchy",
            },
        ],
        description="COGS could mean account category or Cost of Sales departments",
    ),
    "cost of sales": SemanticTerm(
        term="cost of sales",
        category=SemanticCategory.AMBIGUOUS,
        filter_type=FilterType.PREFIX,
        filter_values=[],
        disambiguation_required=True,
        disambiguation_options=[
            {
                "label": "Cost of Sales Accounts (51xxx)",
                "category": "account",
                "filter_type": "prefix",
                "filter_values": ["51"],
                "description": "Filter by Cost of Sales accounts (account numbers starting with 51)",
            },
            {
                "label": "Cost of Sales Departments",
                "category": "department",
                "filter_type": "contains",
                "filter_values": ["Cost of Sales"],
                "description": "Filter by Cost of Sales department hierarchy",
            },
        ],
        description="Cost of Sales could mean account category or department hierarchy",
    ),
    "cos": SemanticTerm(
        term="cos",
        category=SemanticCategory.AMBIGUOUS,
        filter_type=FilterType.PREFIX,
        filter_values=[],
        disambiguation_required=True,
        disambiguation_options=[
            {
                "label": "COS Accounts (51xxx account numbers)",
                "category": "account",
                "filter_type": "prefix",
                "filter_values": ["51"],
                "description": "Filter by Cost of Sales accounts (account numbers starting with 51)",
            },
            {
                "label": "Cost of Sales Departments",
                "category": "department",
                "filter_type": "contains",
                "filter_values": ["Cost of Sales"],
                "description": "Filter by Cost of Sales department hierarchy",
            },
        ],
        description="COS could mean account category or Cost of Sales departments",
    ),
    
    # R&D/Product Development - AMBIGUOUS (could mean accounts OR departments)
    "r&d": SemanticTerm(
        term="r&d",
        category=SemanticCategory.AMBIGUOUS,
        filter_type=FilterType.PREFIX,  # Default, will be overridden
        filter_values=[],
        disambiguation_required=True,
        disambiguation_options=[
            {
                "label": "R&D Accounts (52xxx account numbers)",
                "category": "account",
                "filter_type": "prefix",
                "filter_values": ["52"],
                "description": "Filter by R&D expense accounts (account numbers starting with 52)",
            },
            {
                "label": "R&D Departments (R&D org structure)",
                "category": "department",
                "filter_type": "contains",
                "filter_values": ["R&D"],
                "description": "Filter by R&D department hierarchy (R&D Parent and all sub-departments)",
            },
            {
                "label": "Both (R&D accounts AND R&D departments)",
                "category": "both",
                "filter_type": "prefix",
                "filter_values": ["52"],
                "department_filter": ["R&D"],
                "description": "Filter by both R&D accounts (52xxx) AND R&D departments",
            },
        ],
        description="R&D could mean account category (52xxx) or department hierarchy",
    ),
    "research and development": SemanticTerm(
        term="research and development",
        category=SemanticCategory.AMBIGUOUS,
        filter_type=FilterType.PREFIX,
        filter_values=[],
        disambiguation_required=True,
        disambiguation_options=[
            {
                "label": "R&D Accounts (52xxx account numbers)",
                "category": "account",
                "filter_type": "prefix",
                "filter_values": ["52"],
                "description": "Filter by R&D expense accounts (account numbers starting with 52)",
            },
            {
                "label": "R&D Departments (R&D org structure)",
                "category": "department",
                "filter_type": "contains",
                "filter_values": ["R&D"],
                "description": "Filter by R&D department hierarchy",
            },
        ],
        description="R&D could mean account category or department hierarchy",
    ),
    "research & development": SemanticTerm(
        term="research & development",
        category=SemanticCategory.AMBIGUOUS,
        filter_type=FilterType.PREFIX,
        filter_values=[],
        disambiguation_required=True,
        disambiguation_options=[
            {
                "label": "R&D Accounts (52xxx account numbers)",
                "category": "account",
                "filter_type": "prefix",
                "filter_values": ["52"],
                "description": "Filter by R&D expense accounts (account numbers starting with 52)",
            },
            {
                "label": "R&D Departments (R&D org structure)",
                "category": "department",
                "filter_type": "contains",
                "filter_values": ["R&D"],
                "description": "Filter by R&D department hierarchy",
            },
        ],
        description="R&D could mean account category or department hierarchy",
    ),
    # Note: "product development" is left as account-only since it's more specific to accounts
    
    # Sales & Marketing (53xxx)
    "sales and marketing": SemanticTerm(
        term="sales and marketing",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["53"],
        description="Sales & Marketing accounts (account numbers starting with 53)",
    ),
    "sales & marketing": SemanticTerm(
        term="sales & marketing",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["53"],
        description="Sales & Marketing accounts (account numbers starting with 53)",
    ),
    "s&m": SemanticTerm(
        term="s&m",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["53"],
        description="Sales & Marketing accounts (account numbers starting with 53)",
    ),
    
    # General & Administrative - AMBIGUOUS (could mean accounts OR departments)
    "g&a": SemanticTerm(
        term="g&a",
        category=SemanticCategory.AMBIGUOUS,
        filter_type=FilterType.PREFIX,
        filter_values=[],
        disambiguation_required=True,
        disambiguation_options=[
            {
                "label": "G&A Accounts (59xxx account numbers)",
                "category": "account",
                "filter_type": "prefix",
                "filter_values": ["59"],
                "description": "Filter by G&A expense accounts (account numbers starting with 59)",
            },
            {
                "label": "G&A Departments (G&A org structure)",
                "category": "department",
                "filter_type": "contains",
                "filter_values": ["G&A"],
                "description": "Filter by G&A department hierarchy (G&A Parent and all sub-departments)",
            },
            {
                "label": "Both (G&A accounts AND G&A departments)",
                "category": "both",
                "filter_type": "prefix",
                "filter_values": ["59"],
                "department_filter": ["G&A"],
                "description": "Filter by both G&A accounts (59xxx) AND G&A departments",
            },
        ],
        description="G&A could mean account category (59xxx) or department hierarchy",
    ),
    "general and administrative": SemanticTerm(
        term="general and administrative",
        category=SemanticCategory.AMBIGUOUS,
        filter_type=FilterType.PREFIX,
        filter_values=[],
        disambiguation_required=True,
        disambiguation_options=[
            {
                "label": "G&A Accounts (59xxx account numbers)",
                "category": "account",
                "filter_type": "prefix",
                "filter_values": ["59"],
                "description": "Filter by G&A expense accounts (account numbers starting with 59)",
            },
            {
                "label": "G&A Departments (G&A org structure)",
                "category": "department",
                "filter_type": "contains",
                "filter_values": ["G&A"],
                "description": "Filter by G&A department hierarchy",
            },
        ],
        description="G&A could mean account category or department hierarchy",
    ),
    "general & administrative": SemanticTerm(
        term="general & administrative",
        category=SemanticCategory.AMBIGUOUS,
        filter_type=FilterType.PREFIX,
        filter_values=[],
        disambiguation_required=True,
        disambiguation_options=[
            {
                "label": "G&A Accounts (59xxx account numbers)",
                "category": "account",
                "filter_type": "prefix",
                "filter_values": ["59"],
                "description": "Filter by G&A expense accounts (account numbers starting with 59)",
            },
            {
                "label": "G&A Departments (G&A org structure)",
                "category": "department",
                "filter_type": "contains",
                "filter_values": ["G&A"],
                "description": "Filter by G&A department hierarchy",
            },
        ],
        description="G&A could mean account category or department hierarchy",
    ),
    
    # Depreciation & Amortization (598xx)
    "depreciation": SemanticTerm(
        term="depreciation",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["598"],
        description="Depreciation accounts (account numbers starting with 598)",
    ),
    "amortization": SemanticTerm(
        term="amortization",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["598"],
        description="Amortization accounts (account numbers starting with 598)",
    ),
    "depreciation and amortization": SemanticTerm(
        term="depreciation and amortization",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["598"],
        description="Depreciation & Amortization accounts (account numbers starting with 598)",
    ),
    "depreciation & amortization": SemanticTerm(
        term="depreciation & amortization",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["598"],
        description="Depreciation & Amortization accounts (account numbers starting with 598)",
    ),
    "d&a": SemanticTerm(
        term="d&a",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["598"],
        description="Depreciation & Amortization accounts (account numbers starting with 598)",
    ),
    
    # Interest (6xxx)
    "interest": SemanticTerm(
        term="interest",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["6"],
        description="Interest related accounts (account numbers starting with 6 - expense or income)",
    ),
    "interest expense": SemanticTerm(
        term="interest expense",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["6"],
        description="Interest expense accounts (account numbers starting with 6)",
    ),
    "interest income": SemanticTerm(
        term="interest income",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["6"],
        description="Interest income accounts (account numbers starting with 6)",
    ),
    
    # Income Tax & Other (7xxx, 8xxx)
    "income tax": SemanticTerm(
        term="income tax",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["7", "8"],
        description="Income Tax accounts (account numbers starting with 7 or 8)",
    ),
    "other expenses": SemanticTerm(
        term="other expenses",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["7", "8"],
        description="Other expense accounts (account numbers starting with 7 or 8)",
    ),
    "other income": SemanticTerm(
        term="other income",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["7", "8"],
        description="Other income accounts (account numbers starting with 7 or 8)",
    ),
    
    # Standard Expenses (5xxx) - Default when user says "expense" or "expenses"
    # Users must explicitly say "all expenses", "interest", "income tax", etc. for 6,7,8
    "expenses": SemanticTerm(
        term="expenses",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["5"],
        description="Operating expense accounts (account numbers starting with 5)",
    ),
    "expense": SemanticTerm(
        term="expense",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["5"],
        description="Operating expense accounts (account numbers starting with 5)",
    ),
    "spend": SemanticTerm(
        term="spend",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["5"],
        description="Operating expense accounts (account numbers starting with 5)",
    ),
    "spending": SemanticTerm(
        term="spending",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["5"],
        description="Operating expense accounts (account numbers starting with 5)",
    ),
    "costs": SemanticTerm(
        term="costs",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["5"],
        description="Operating expense accounts (account numbers starting with 5)",
    ),
    # Explicit "all expenses" for when user wants 5,6,7,8
    "all expenses": SemanticTerm(
        term="all expenses",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["5", "6", "7", "8"],
        description="All expense accounts (account numbers starting with 5, 6, 7, or 8)",
    ),
    "all expense": SemanticTerm(
        term="all expense",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["5", "6", "7", "8"],
        description="All expense accounts (account numbers starting with 5, 6, 7, or 8)",
    ),
    
    # -------------------------------------------------------------------------
    # EXPENSE CATEGORY TERMS (filter on account NAME contains)
    # These terms filter accounts by name, not by account number prefix
    # -------------------------------------------------------------------------
    
    # Payroll & Compensation
    "salary": SemanticTerm(
        term="salary",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Salary", "Salaries"],
        description="Salary expense accounts (account names containing 'Salary')",
    ),
    "salaries": SemanticTerm(
        term="salaries",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Salary", "Salaries"],
        description="Salary expense accounts (account names containing 'Salary')",
    ),
    "payroll": SemanticTerm(
        term="payroll",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Payroll"],
        description="Payroll expense accounts (account names containing 'Payroll')",
    ),
    "compensation": SemanticTerm(
        term="compensation",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Compensation"],
        description="Compensation expense accounts (account names containing 'Compensation')",
    ),
    "benefits": SemanticTerm(
        term="benefits",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Benefits", "Benefit"],
        description="Employee benefits expense accounts (account names containing 'Benefits')",
    ),
    "employee benefits": SemanticTerm(
        term="employee benefits",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Benefits", "Benefit"],
        description="Employee benefits expense accounts (account names containing 'Benefits')",
    ),
    
    # Facilities & Operations
    "rent": SemanticTerm(
        term="rent",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Rent", "Lease"],
        description="Rent/lease expense accounts (account names containing 'Rent' or 'Lease')",
    ),
    "rent expense": SemanticTerm(
        term="rent expense",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Rent", "Lease"],
        description="Rent/lease expense accounts (account names containing 'Rent' or 'Lease')",
    ),
    "utilities": SemanticTerm(
        term="utilities",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Utilities", "Utility"],
        description="Utilities expense accounts (account names containing 'Utilities')",
    ),
    "utilities expense": SemanticTerm(
        term="utilities expense",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Utilities", "Utility"],
        description="Utilities expense accounts (account names containing 'Utilities')",
    ),
    
    # Technology & Software
    "software": SemanticTerm(
        term="software",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Software", "SaaS", "Subscription"],
        description="Software expense accounts (account names containing 'Software', 'SaaS', or 'Subscription')",
    ),
    "software expense": SemanticTerm(
        term="software expense",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Software", "SaaS", "Subscription"],
        description="Software expense accounts (account names containing 'Software', 'SaaS', or 'Subscription')",
    ),
    "saas": SemanticTerm(
        term="saas",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["SaaS", "Software", "Subscription"],
        description="SaaS/software subscription expense accounts",
    ),
    "subscriptions": SemanticTerm(
        term="subscriptions",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Subscription", "SaaS", "Software"],
        description="Software subscription expense accounts",
    ),
    
    # Travel & Entertainment
    "travel": SemanticTerm(
        term="travel",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Travel", "T&E"],
        description="Travel expense accounts (account names containing 'Travel' or 'T&E')",
    ),
    "travel expense": SemanticTerm(
        term="travel expense",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Travel", "T&E"],
        description="Travel expense accounts (account names containing 'Travel' or 'T&E')",
    ),
    "travel and entertainment": SemanticTerm(
        term="travel and entertainment",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Travel", "T&E", "Entertainment"],
        description="Travel and entertainment expense accounts",
    ),
    "t&e": SemanticTerm(
        term="t&e",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["T&E", "Travel", "Entertainment"],
        description="Travel and entertainment expense accounts",
    ),
    
    # Insurance & Professional Services
    "insurance": SemanticTerm(
        term="insurance",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Insurance"],
        description="Insurance expense accounts (account names containing 'Insurance')",
    ),
    "professional services": SemanticTerm(
        term="professional services",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Professional Services", "Consulting", "Legal"],
        description="Professional services expense accounts (account names containing 'Professional Services', 'Consulting', or 'Legal')",
    ),
    "consulting": SemanticTerm(
        term="consulting",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Consulting", "Professional Services"],
        description="Consulting expense accounts",
    ),
    "legal": SemanticTerm(
        term="legal",
        category=SemanticCategory.ACCOUNT_NAME,
        filter_type=FilterType.CONTAINS,
        filter_values=["Legal", "Professional Services"],
        description="Legal expense accounts",
    ),
    
    # Balance Sheet - Assets (1xxx)
    "assets": SemanticTerm(
        term="assets",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["1"],
        description="Asset accounts (account numbers starting with 1)",
    ),
    "asset": SemanticTerm(
        term="asset",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["1"],
        description="Asset accounts (account numbers starting with 1)",
    ),
    
    # Balance Sheet - Liabilities (2xxx)
    "liabilities": SemanticTerm(
        term="liabilities",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["2"],
        description="Liability accounts (account numbers starting with 2)",
    ),
    "liability": SemanticTerm(
        term="liability",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["2"],
        description="Liability accounts (account numbers starting with 2)",
    ),
    
    # Balance Sheet - Equity (3xxx)
    "equity": SemanticTerm(
        term="equity",
        category=SemanticCategory.ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["3"],
        description="Equity accounts (account numbers starting with 3)",
    ),
    
    # -------------------------------------------------------------------------
    # COMPOUND ACCOUNT TERMS (filter on BOTH account number AND name)
    # These terms require filtering by account number prefix AND account name contains
    # -------------------------------------------------------------------------
    
    # Sales & Marketing Costs (53xxx accounts with "Sales & Marketing" in name)
    "sales and marketing cost": SemanticTerm(
        term="sales and marketing cost",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["53"],  # Account number starts with 53
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Sales & Marketing"],  # Account name contains
        description="Sales & Marketing expense accounts (53xxx with 'Sales & Marketing' in name)",
    ),
    "sales and marketing costs": SemanticTerm(
        term="sales and marketing costs",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["53"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Sales & Marketing"],
        description="Sales & Marketing expense accounts (53xxx with 'Sales & Marketing' in name)",
    ),
    "sales & marketing cost": SemanticTerm(
        term="sales & marketing cost",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["53"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Sales & Marketing"],
        description="Sales & Marketing expense accounts (53xxx with 'Sales & Marketing' in name)",
    ),
    "sales & marketing costs": SemanticTerm(
        term="sales & marketing costs",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["53"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Sales & Marketing"],
        description="Sales & Marketing expense accounts (53xxx with 'Sales & Marketing' in name)",
    ),
    "s&m cost": SemanticTerm(
        term="s&m cost",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["53"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Sales & Marketing"],
        description="Sales & Marketing expense accounts (53xxx with 'Sales & Marketing' in name)",
    ),
    "s&m costs": SemanticTerm(
        term="s&m costs",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["53"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Sales & Marketing"],
        description="Sales & Marketing expense accounts (53xxx with 'Sales & Marketing' in name)",
    ),
    "s&m spend": SemanticTerm(
        term="s&m spend",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["53"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Sales & Marketing"],
        description="Sales & Marketing expense accounts (53xxx with 'Sales & Marketing' in name)",
    ),
    "s&m spending": SemanticTerm(
        term="s&m spending",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["53"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Sales & Marketing"],
        description="Sales & Marketing expense accounts (53xxx with 'Sales & Marketing' in name)",
    ),
    "sales and marketing expense": SemanticTerm(
        term="sales and marketing expense",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["53"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Sales & Marketing"],
        description="Sales & Marketing expense accounts (53xxx with 'Sales & Marketing' in name)",
    ),
    "sales and marketing expenses": SemanticTerm(
        term="sales and marketing expenses",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["53"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Sales & Marketing"],
        description="Sales & Marketing expense accounts (53xxx with 'Sales & Marketing' in name)",
    ),
    "sales & marketing expense": SemanticTerm(
        term="sales & marketing expense",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["53"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Sales & Marketing"],
        description="Sales & Marketing expense accounts (53xxx with 'Sales & Marketing' in name)",
    ),
    "sales & marketing expenses": SemanticTerm(
        term="sales & marketing expenses",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["53"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Sales & Marketing"],
        description="Sales & Marketing expense accounts (53xxx with 'Sales & Marketing' in name)",
    ),
    
    # R&D / Product Development Costs (52xxx accounts with "Product Development" or "R&D" in name)
    "product development cost": SemanticTerm(
        term="product development cost",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["52"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Product Development"],
        description="Product Development expense accounts (52xxx with 'Product Development' in name)",
    ),
    "product development costs": SemanticTerm(
        term="product development costs",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["52"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Product Development"],
        description="Product Development expense accounts (52xxx with 'Product Development' in name)",
    ),
    "r&d cost": SemanticTerm(
        term="r&d cost",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["52"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Product Development", "R&D", "Research"],
        description="R&D/Product Development expense accounts (52xxx)",
    ),
    "r&d costs": SemanticTerm(
        term="r&d costs",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["52"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Product Development", "R&D", "Research"],
        description="R&D/Product Development expense accounts (52xxx)",
    ),
    
    # G&A Costs (59xxx accounts with "G&A" or "General" in name)
    "g&a cost": SemanticTerm(
        term="g&a cost",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["59"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["G&A", "General & Administrative", "General and Administrative"],
        description="G&A expense accounts (59xxx)",
    ),
    "g&a costs": SemanticTerm(
        term="g&a costs",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["59"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["G&A", "General & Administrative", "General and Administrative"],
        description="G&A expense accounts",
    ),
    "general and administrative cost": SemanticTerm(
        term="general and administrative cost",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["59"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["G&A", "General & Administrative", "General and Administrative"],
        description="G&A expense accounts",
    ),
    "general and administrative costs": SemanticTerm(
        term="general and administrative costs",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["59"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["G&A", "General & Administrative", "General and Administrative"],
        description="G&A expense accounts",
    ),
    
    # Cost of Sales Costs (5xxx accounts with "Cost of Sales" in name)  
    "cost of sales cost": SemanticTerm(
        term="cost of sales cost",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["5"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Cost of Sales"],
        description="Cost of Sales expense accounts (5xxx with 'Cost of Sales' in name)",
    ),
    "cost of sales costs": SemanticTerm(
        term="cost of sales costs",
        category=SemanticCategory.COMPOUND_ACCOUNT,
        filter_type=FilterType.PREFIX,
        filter_values=["5"],
        secondary_filter_type=FilterType.CONTAINS,
        secondary_filter_values=["Cost of Sales"],
        description="Cost of Sales expense accounts (5xxx with 'Cost of Sales' in name)",
    ),
    
    # -------------------------------------------------------------------------
    # DEPARTMENT-BASED TERMS REMOVED
    # -------------------------------------------------------------------------
    # All department resolution is now handled by the DynamicRegistry which
    # discovers departments automatically from NetSuite data. This ensures:
    # 1. No manual maintenance when org structure changes
    # 2. Proper disambiguation for similar names (Product Marketing vs Product Management)
    # 3. Exact matching instead of substring matching
    #
    # The following department terms were removed:
    # - "sales department", "sales team", "marketing", "marketing department", "mktg"
    # - "engineering", "finance", "finance department", "accounting"
    # - "hr", "human resources", "information technology", "customer success"
    # - "product", "operations", "legal", "sdr", "sales development", "gcc"
    # - DEPARTMENT-type entries for "r&d", "research and development", "g&a", "general and administrative"
    #
    # NOTE: ACCOUNT-type entries for "r&d", "g&a", etc. are KEPT (they filter on account number prefixes)
    # -------------------------------------------------------------------------
    
    # -------------------------------------------------------------------------
    # AMBIGUOUS TERMS (require user disambiguation)
    # -------------------------------------------------------------------------
    
    "sales": SemanticTerm(
        term="sales",
        category=SemanticCategory.AMBIGUOUS,
        filter_type=FilterType.PREFIX,  # Default, will be overridden
        filter_values=[],
        disambiguation_required=True,
        disambiguation_options=[
            {
                "label": "Sales Revenue (income from sales)",
                "category": "account",
                "filter_type": "prefix",
                "filter_values": ["4"],
                "description": "Revenue accounts (account numbers starting with 4)",
            },
            {
                "label": "Sales Department (team spending)",
                "category": "department",
                "filter_type": "contains",
                "filter_values": ["Sales"],
                "description": "Spending by the Sales department",
            },
        ],
        description="Ambiguous: could mean sales revenue or sales department",
    ),
    
    # -------------------------------------------------------------------------
    # TRANSACTION TYPE TERMS (filter on transaction type)
    # -------------------------------------------------------------------------
    
    "journal entries": SemanticTerm(
        term="journal entries",
        category=SemanticCategory.TRANSACTION_TYPE,
        filter_type=FilterType.IN_LIST,
        filter_values=["Journal"],
        description="Journal entry transactions",
    ),
    "journals": SemanticTerm(
        term="journals",
        category=SemanticCategory.TRANSACTION_TYPE,
        filter_type=FilterType.IN_LIST,
        filter_values=["Journal"],
        description="Journal entry transactions",
    ),
    "journal entry": SemanticTerm(
        term="journal entry",
        category=SemanticCategory.TRANSACTION_TYPE,
        filter_type=FilterType.IN_LIST,
        filter_values=["Journal"],
        description="Journal entry transactions",
    ),
    "invoices": SemanticTerm(
        term="invoices",
        category=SemanticCategory.TRANSACTION_TYPE,
        filter_type=FilterType.IN_LIST,
        filter_values=["CustInvc"],
        description="Customer invoice transactions",
    ),
    "customer invoices": SemanticTerm(
        term="customer invoices",
        category=SemanticCategory.TRANSACTION_TYPE,
        filter_type=FilterType.IN_LIST,
        filter_values=["CustInvc"],
        description="Customer invoice transactions",
    ),
    "bills": SemanticTerm(
        term="bills",
        category=SemanticCategory.TRANSACTION_TYPE,
        filter_type=FilterType.IN_LIST,
        filter_values=["VendBill"],
        description="Vendor bill transactions",
    ),
    "vendor bills": SemanticTerm(
        term="vendor bills",
        category=SemanticCategory.TRANSACTION_TYPE,
        filter_type=FilterType.IN_LIST,
        filter_values=["VendBill"],
        description="Vendor bill transactions",
    ),
    "payments": SemanticTerm(
        term="payments",
        category=SemanticCategory.TRANSACTION_TYPE,
        filter_type=FilterType.IN_LIST,
        filter_values=["CustPymt", "VendPymt"],
        description="Customer and vendor payment transactions",
    ),
    "expense reports": SemanticTerm(
        term="expense reports",
        category=SemanticCategory.TRANSACTION_TYPE,
        filter_type=FilterType.IN_LIST,
        filter_values=["ExpRept"],
        description="Employee expense report transactions",
    ),
    
    # -------------------------------------------------------------------------
    # SUBSIDIARY TERMS (filter on subsidiary name)
    # -------------------------------------------------------------------------
    
    "us": SemanticTerm(
        term="us",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.CONTAINS,
        filter_values=["US", "United States", "USA", "America"],
        description="US subsidiary",
    ),
    "us subsidiary": SemanticTerm(
        term="us subsidiary",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.CONTAINS,
        filter_values=["US", "United States", "USA", "America"],
        description="US subsidiary",
    ),
    "united states": SemanticTerm(
        term="united states",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.CONTAINS,
        filter_values=["US", "United States", "USA", "America"],
        description="United States subsidiary",
    ),
    "uk": SemanticTerm(
        term="uk",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.CONTAINS,
        filter_values=["UK", "United Kingdom", "Britain", "GB"],
        description="UK subsidiary",
    ),
    "uk subsidiary": SemanticTerm(
        term="uk subsidiary",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.CONTAINS,
        filter_values=["UK", "United Kingdom", "Britain", "GB"],
        description="UK subsidiary",
    ),
    "united kingdom": SemanticTerm(
        term="united kingdom",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.CONTAINS,
        filter_values=["UK", "United Kingdom", "Britain", "GB"],
        description="United Kingdom subsidiary",
    ),
    "europe": SemanticTerm(
        term="europe",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.CONTAINS,
        filter_values=["Europe", "EU", "EMEA"],
        description="Europe/EMEA subsidiary",
    ),
    "emea": SemanticTerm(
        term="emea",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.CONTAINS,
        filter_values=["EMEA", "Europe"],
        description="EMEA region subsidiary",
    ),
    "apac": SemanticTerm(
        term="apac",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.CONTAINS,
        filter_values=["APAC", "Asia Pacific", "Asia"],
        description="Asia Pacific subsidiary",
    ),
    "asia pacific": SemanticTerm(
        term="asia pacific",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.CONTAINS,
        filter_values=["APAC", "Asia Pacific", "Asia"],
        description="Asia Pacific subsidiary",
    ),
    "canada": SemanticTerm(
        term="canada",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.CONTAINS,
        filter_values=["Canada", "CA", "Canadian"],
        description="Canada subsidiary",
    ),
    "australia": SemanticTerm(
        term="australia",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.CONTAINS,
        filter_values=["Australia", "AU", "Australian"],
        description="Australia subsidiary",
    ),
    "germany": SemanticTerm(
        term="germany",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.CONTAINS,
        filter_values=["Germany", "DE", "German"],
        description="Germany subsidiary",
    ),
    "france": SemanticTerm(
        term="france",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.CONTAINS,
        filter_values=["France", "FR", "French"],
        description="France subsidiary",
    ),
    "consolidated": SemanticTerm(
        term="consolidated",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.EXACT,
        filter_values=["*"],  # Special value meaning "all subsidiaries combined"
        description="Consolidated (all subsidiaries combined)",
    ),
    "parent company": SemanticTerm(
        term="parent company",
        category=SemanticCategory.SUBSIDIARY,
        filter_type=FilterType.CONTAINS,
        filter_values=["Parent", "HQ", "Headquarters", "Corporate"],
        description="Parent company / Headquarters",
    ),
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _normalize_term(term: str) -> str:
    """
    Normalize a term for lookup by converting to lowercase and handling plurals.
    
    Args:
        term: The raw term to normalize
        
    Returns:
        Normalized term for dictionary lookup
    """
    term = term.lower().strip()
    
    # Handle common variations
    replacements = {
        "and": "&",
        " & ": " and ",
    }
    
    for old, new in replacements.items():
        if old in term and new not in term:
            # Only replace if the alternate form exists in dictionary
            alt_term = term.replace(old, new)
            if alt_term in FINANCIAL_SEMANTICS:
                term = alt_term
    
    return term


def get_semantic_term(term: str) -> Optional[SemanticTerm]:
    """
    Look up a semantic term in the dictionary.
    
    Handles case-insensitive matching and common variations.
    
    Args:
        term: The natural language term to look up
        
    Returns:
        SemanticTerm if found, None otherwise
    """
    normalized = _normalize_term(term)
    
    # Direct lookup
    if normalized in FINANCIAL_SEMANTICS:
        return FINANCIAL_SEMANTICS[normalized]
    
    # Try without trailing 's' (handle plurals)
    if normalized.endswith('s') and normalized[:-1] in FINANCIAL_SEMANTICS:
        return FINANCIAL_SEMANTICS[normalized[:-1]]
    
    # Try with trailing 's' (handle singulars)
    if normalized + 's' in FINANCIAL_SEMANTICS:
        return FINANCIAL_SEMANTICS[normalized + 's']
    
    return None


def resolve_financial_terms(query: str) -> List[SemanticTerm]:
    """
    Extract all financial terms from a query and resolve them to SemanticTerms.
    
    This function scans the query for known financial terms and returns
    their semantic interpretations. Longer matches take precedence over
    shorter ones (e.g., "sales department" beats "sales").
    
    Args:
        query: The user's natural language query
        
    Returns:
        List of resolved SemanticTerms found in the query
    """
    terms, _ = resolve_financial_terms_with_ranges(query)
    return terms


def resolve_financial_terms_with_ranges(query: str) -> Tuple[List[SemanticTerm], List[Tuple[int, int]]]:
    """
    Extract all financial terms from a query and return both terms and matched ranges.
    
    This is useful for downstream processing that needs to know which parts of the
    query have been claimed by semantic term matching (e.g., to avoid extracting
    "marketing" as a department when it's part of "sales and marketing cost").
    
    Args:
        query: The user's natural language query
        
    Returns:
        Tuple of (resolved_terms, matched_ranges)
        - resolved_terms: List of resolved SemanticTerms found in the query
        - matched_ranges: List of (start, end) tuples indicating matched character positions
    """
    query_lower = query.lower()
    resolved_terms = []
    matched_ranges = []  # Track matched character ranges to avoid overlaps
    
    # Sort terms by length (descending) to prefer longer matches
    sorted_terms = sorted(FINANCIAL_SEMANTICS.keys(), key=len, reverse=True)
    
    for term in sorted_terms:
        # Use word boundary matching
        pattern = r'\b' + re.escape(term) + r'\b'
        
        for match in re.finditer(pattern, query_lower):
            start, end = match.span()
            
            # Check if this range overlaps with an already matched range
            overlaps = False
            for matched_start, matched_end in matched_ranges:
                if not (end <= matched_start or start >= matched_end):
                    overlaps = True
                    break
            
            if not overlaps:
                semantic_term = FINANCIAL_SEMANTICS[term]
                if semantic_term not in resolved_terms:
                    resolved_terms.append(semantic_term)
                    matched_ranges.append((start, end))
    
    logger.debug(f"Resolved {len(resolved_terms)} financial terms from query: {[t.term for t in resolved_terms]}")
    return resolved_terms, matched_ranges


def needs_disambiguation(terms: List[SemanticTerm]) -> List[SemanticTerm]:
    """
    Filter terms that require user disambiguation.
    
    Args:
        terms: List of resolved SemanticTerms
        
    Returns:
        List of terms that have disambiguation_required=True
    """
    return [t for t in terms if t.disambiguation_required]


def build_disambiguation_message(terms: List[SemanticTerm]) -> str:
    """
    Build a user-friendly message asking for disambiguation.
    
    Args:
        terms: List of ambiguous SemanticTerms
        
    Returns:
        Formatted message with options for the user
    """
    if not terms:
        return ""
    
    messages = []
    
    for term in terms:
        if term.disambiguation_options:
            msg_parts = [f'The term "{term.term}" could mean:\n']
            
            for i, option in enumerate(term.disambiguation_options, 1):
                msg_parts.append(f"  {i}. {option['label']}")
                if option.get('description'):
                    msg_parts.append(f"     ({option['description']})")
                msg_parts.append("")
            
            msg_parts.append("Please specify which one you mean, or rephrase your question.")
            messages.append("\n".join(msg_parts))
    
    return "\n\n".join(messages)


def apply_disambiguation_choice(term: SemanticTerm, choice_index: int) -> Optional[SemanticTerm]:
    """
    Apply a user's disambiguation choice to create a resolved SemanticTerm.
    
    Args:
        term: The ambiguous SemanticTerm
        choice_index: Zero-based index of the user's choice
        
    Returns:
        A new SemanticTerm with the disambiguated values, or None if invalid
    """
    if not term.disambiguation_options:
        return None
    
    if choice_index < 0 or choice_index >= len(term.disambiguation_options):
        return None
    
    option = term.disambiguation_options[choice_index]
    
    return SemanticTerm(
        term=term.term,
        category=SemanticCategory(option["category"]),
        filter_type=FilterType(option["filter_type"]),
        filter_values=option["filter_values"],
        disambiguation_required=False,
        disambiguation_options=None,
        description=option.get("description", ""),
    )


def get_account_filter_for_term(term: str) -> Optional[Dict[str, Any]]:
    """
    Convenience function to get account filter for a term if applicable.
    
    Args:
        term: The natural language term
        
    Returns:
        Dict with filter_type and values if term is account-based, None otherwise
    """
    semantic_term = get_semantic_term(term)
    
    if semantic_term and semantic_term.category == SemanticCategory.ACCOUNT:
        return {
            "filter_type": semantic_term.filter_type.value,
            "values": semantic_term.filter_values,
        }
    
    return None


def get_department_filter_for_term(term: str) -> Optional[List[str]]:
    """
    Convenience function to get department filter for a term if applicable.
    
    Args:
        term: The natural language term
        
    Returns:
        List of department names if term is department-based, None otherwise
    """
    semantic_term = get_semantic_term(term)
    
    if semantic_term and semantic_term.category == SemanticCategory.DEPARTMENT:
        return semantic_term.filter_values
    
    return None


def is_account_term(term: str) -> bool:
    """Check if a term refers to account types (not departments)."""
    semantic_term = get_semantic_term(term)
    return semantic_term is not None and semantic_term.category == SemanticCategory.ACCOUNT


def is_department_term(term: str) -> bool:
    """Check if a term refers to departments."""
    semantic_term = get_semantic_term(term)
    return semantic_term is not None and semantic_term.category == SemanticCategory.DEPARTMENT


def is_ambiguous_term(term: str) -> bool:
    """Check if a term is ambiguous and requires disambiguation."""
    semantic_term = get_semantic_term(term)
    return semantic_term is not None and semantic_term.category == SemanticCategory.AMBIGUOUS


def is_subsidiary_term(term: str) -> bool:
    """Check if a term refers to subsidiaries."""
    semantic_term = get_semantic_term(term)
    return semantic_term is not None and semantic_term.category == SemanticCategory.SUBSIDIARY


def get_subsidiary_filter_for_term(term: str) -> Optional[List[str]]:
    """
    Convenience function to get subsidiary filter for a term if applicable.
    
    Args:
        term: The natural language term
        
    Returns:
        List of subsidiary names if term is subsidiary-based, None otherwise
    """
    semantic_term = get_semantic_term(term)
    
    if semantic_term and semantic_term.category == SemanticCategory.SUBSIDIARY:
        return semantic_term.filter_values
    
    return None


def get_subsidiary_filter(terms: List[SemanticTerm]) -> List[str]:
    """
    Extract subsidiary filter values from a list of semantic terms.
    
    Args:
        terms: List of resolved SemanticTerms
        
    Returns:
        List of subsidiary names to filter on
    """
    subsidiaries = []
    for term in terms:
        if term.category == SemanticCategory.SUBSIDIARY:
            subsidiaries.extend(term.filter_values)
    return list(set(subsidiaries))


def is_consolidated_query(terms: List[SemanticTerm]) -> bool:
    """
    Check if this is a consolidated query (all subsidiaries combined).
    
    Args:
        terms: List of resolved SemanticTerms
        
    Returns:
        True if the query asks for consolidated results
    """
    for term in terms:
        if term.category == SemanticCategory.SUBSIDIARY and "*" in term.filter_values:
            return True
    return False

