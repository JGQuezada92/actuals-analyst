"""
Query Understanding Engine

Hybrid approach: keyword extraction + LLM parsing for complex queries.
Extracts intent, filters, time ranges, and comparison types from user queries.

Enhanced with financial semantics for proper term resolution:
- "revenue" → account filter (prefix "4"), not Sales department
- "sales" → ambiguous, requires disambiguation
- "marketing expenses" → department filter + account filter
"""
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from datetime import date
from enum import Enum

from src.core.fiscal_calendar import FiscalCalendar, FiscalPeriod, PeriodType, get_fiscal_calendar
from src.core.financial_semantics import (
    resolve_financial_terms,
    resolve_financial_terms_with_ranges,
    needs_disambiguation,
    build_disambiguation_message,
    is_account_term,
    is_department_term,
    is_subsidiary_term,
    get_subsidiary_filter,
    is_consolidated_query,
    SemanticCategory,
    SemanticTerm,
)

# Dynamic registry import (optional - gracefully handles if not available)
try:
    from src.core.dynamic_registry import get_dynamic_registry, EntityType, RegistryMatch
    DYNAMIC_REGISTRY_AVAILABLE = True
except ImportError:
    DYNAMIC_REGISTRY_AVAILABLE = False
    logger.debug("Dynamic registry not available")

logger = logging.getLogger(__name__)

class QueryIntent(Enum):
    """Primary intent of the user query."""
    SUMMARY = "summary"           # General overview/summary
    TOTAL = "total"               # Sum/total of amounts
    TREND = "trend"               # Trend over time
    COMPARISON = "comparison"     # Compare periods/categories
    VARIANCE = "variance"         # Variance analysis
    BREAKDOWN = "breakdown"       # Breakdown by category
    TOP_N = "top_n"               # Top/bottom N items
    DETAIL = "detail"             # Detailed line items
    RATIO = "ratio"               # Ratio/percentage analysis

class ComparisonType(Enum):
    """Type of comparison requested."""
    MONTH_OVER_MONTH = "mom"
    YEAR_OVER_YEAR = "yoy"
    QUARTER_OVER_QUARTER = "qoq"
    BUDGET_VS_ACTUAL = "bva"
    PRIOR_PERIOD = "prior"
    CUSTOM = "custom"

@dataclass
class ParsedFilter:
    """A filter extracted from the query."""
    field: str              # Field to filter on (department, account, etc.)
    operator: str           # eq, contains, in, gt, lt, between
    value: Any              # Filter value(s)
    original_text: str      # Original text that produced this filter

@dataclass
class ParsedQuery:
    """Structured representation of a parsed user query."""
    original_query: str
    intent: QueryIntent
    
    # Time filters
    time_period: Optional[FiscalPeriod] = None
    comparison_period: Optional[FiscalPeriod] = None
    comparison_type: Optional[ComparisonType] = None
    
    # Entity filters
    departments: List[str] = field(default_factory=list)
    accounts: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    subsidiaries: List[str] = field(default_factory=list)
    is_consolidated: bool = False  # True for consolidated (all subsidiaries) queries
    
    # Semantic filters (NEW - from financial_semantics module)
    account_type_filter: Optional[Dict[str, Any]] = None  # {"filter_type": "prefix", "values": ["4"]}
    account_name_filter: Optional[Dict[str, Any]] = None  # {"filter_type": "contains", "values": ["Sales & Marketing"]}
    transaction_type_filter: Optional[List[str]] = None   # ["Journal", "VendBill"]
    
    # Disambiguation (NEW - for ambiguous terms like "sales")
    requires_disambiguation: bool = False
    disambiguation_message: Optional[str] = None
    ambiguous_terms: List[str] = field(default_factory=list)
    
    # Resolved semantic terms for reference
    semantic_terms: List[Dict[str, Any]] = field(default_factory=list)
    
    # Additional parameters
    top_n: Optional[int] = None
    group_by: Optional[List[str]] = field(default_factory=list)
    sort_by: Optional[str] = None
    sort_ascending: bool = False
    
    # Raw filters for custom processing
    filters: List[ParsedFilter] = field(default_factory=list)
    
    # Confidence and metadata
    confidence: float = 1.0
    used_llm_fallback: bool = False
    parsing_notes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_query": self.original_query,
            "intent": self.intent.value,
            "time_period": self.time_period.to_dict() if self.time_period else None,
            "comparison_period": self.comparison_period.to_dict() if self.comparison_period else None,
            "comparison_type": self.comparison_type.value if self.comparison_type else None,
            "departments": self.departments,
            "accounts": self.accounts,
            "classes": self.classes,
            "subsidiaries": self.subsidiaries,
            "is_consolidated": self.is_consolidated,
            "account_type_filter": self.account_type_filter,
            "account_name_filter": self.account_name_filter,  # NEW
            "transaction_type_filter": self.transaction_type_filter,
            "requires_disambiguation": self.requires_disambiguation,
            "disambiguation_message": self.disambiguation_message,
            "ambiguous_terms": self.ambiguous_terms,
            "top_n": self.top_n,
            "group_by": self.group_by if isinstance(self.group_by, list) else ([self.group_by] if self.group_by else []),
            "confidence": self.confidence,
            "used_llm_fallback": self.used_llm_fallback,
        }

class QueryParser:
    """
    Parses user queries to extract structured information.
    
    Uses a hybrid approach:
    1. Keyword extraction for common patterns (fast, deterministic)
    2. LLM fallback for complex/ambiguous queries (accurate, slower)
    """
    
    # Common department name patterns
    # Updated to match NetSuite saved search department names
    # NOTE: Account-based terms are now handled by financial_semantics module
    # REMOVED: "revenue" (this is an account type, not a department!)
    # REMOVED: "cost of sales", "cogs" (these are handled as account types)
    DEPARTMENT_PATTERNS = [
        # Cost of Sales department team (specific team patterns)
        r"\b(GCC|customer centric engineering)\b",
        
        # G&A departments
        r"\b(G&A|general\s*(?:and|&)\s*admin(?:istrative)?)\b",
        r"\b(finance|accounting|FP&A)\b",
        r"(?<![a-z])\bIT\b(?![a-z])|\binformation\s+technology\b|\btech\s+ops\b",  # Fixed: IT must be uppercase standalone word, not "it"
        r"\b(HR|human resources|people ops)\b",
        r"\b(legal|compliance)\b",
        
        # R&D departments
        r"\b(R&D|research\s*(?:and|&)\s*development)\b",
        r"\b(engineering|eng)\b",
        
        # Sales & Marketing
        # NOTE: "sales" alone is now handled as ambiguous in financial_semantics
        # Only match explicit department references
        r"\b(sales\s+(?:department|team))\b",
        r"\b(SDR|sales development|sales dev)\b",
        r"\b(marketing|mktg)\b",
        r"\b(commercial)\b",
        
        # Other departments
        r"\b(customer success|CS|support)\b",
        r"\b(product|PM)\b",
        r"\b(operations|ops)\b",
    ]
    
    # Time period patterns
    TIME_PATTERNS = {
        "ytd": r"\b(YTD|year[\s-]to[\s-]date)\b",
        "mtd": r"\b(MTD|month[\s-]to[\s-]date)\b",
        "qtd": r"\b(QTD|quarter[\s-]to[\s-]date)\b",
        "current_month": r"\b(this month|current month|this period)\b",
        "last_month": r"\b(last month|prior month|previous month)\b",
        "current_quarter": r"\b(this quarter|current quarter|Q[1-4]\s*(?:FY)?\d{0,4})\b",
        "last_quarter": r"\b(last quarter|prior quarter|previous quarter)\b",
        "current_year": r"\b(this year|current year|FY\s*\d{2,4})\b",
        "last_year": r"\b(last year|prior year|previous year)\b",
        # Trailing period patterns (TTM, trailing N months)
        "ttm": r"\b(TTM|T12M|trailing\s*12\s*months?|trailing\s*twelve\s*months?|last\s*12\s*months?)\b",
        "trailing_3": r"\b(trailing\s*3\s*months?|last\s*3\s*months?|past\s*3\s*months?)\b",
        "trailing_6": r"\b(trailing\s*6\s*months?|last\s*6\s*months?|past\s*6\s*months?)\b",
        "trailing_n": r"\btrailing\s*(\d+)\s*months?\b",
    }
    
    # Comparison patterns
    COMPARISON_PATTERNS = {
        ComparisonType.MONTH_OVER_MONTH: r"\b(mom|month[\s-]over[\s-]month|vs\.?\s*last month|compared?\s*to\s*last month)\b",
        ComparisonType.YEAR_OVER_YEAR: r"\b(yoy|year[\s-]over[\s-]year|vs\.?\s*last year|compared?\s*to\s*(?:last|prior|same\s*period\s*last)\s*year)\b",
        ComparisonType.QUARTER_OVER_QUARTER: r"\b(qoq|quarter[\s-]over[\s-]quarter|vs\.?\s*last quarter)\b",
        ComparisonType.BUDGET_VS_ACTUAL: r"\b(budget\s*vs\.?\s*actual|actual\s*vs\.?\s*budget|variance\s*to\s*budget)\b",
        ComparisonType.PRIOR_PERIOD: r"\b(vs\.?\s*prior|compared?\s*to\s*prior|variance)\b",
    }
    
    # Intent patterns
    INTENT_PATTERNS = {
        QueryIntent.TREND: r"\b(trend|over\s*time|growth|trajectory|progression|historically)\b",
        QueryIntent.VARIANCE: r"\b(variance|difference|change|deviation|vs\.?|compared?)\b",
        QueryIntent.BREAKDOWN: r"\b(breakdown|by\s+(?:department|account|category|type)|split|composition)\b",
        QueryIntent.TOP_N: r"\b(top\s*\d+|bottom\s*\d+|largest|smallest|highest|lowest)\b",
        QueryIntent.TOTAL: r"\b(total|sum|aggregate|overall|grand)\b",
        QueryIntent.RATIO: r"\b(ratio|percent(?:age)?|proportion|relative\s*to|as\s*(?:a\s*)?%)\b",
        QueryIntent.SUMMARY: r"\b(summary|summarize|overview|snapshot|highlights?)\b",
    }
    
    def __init__(self, fiscal_calendar: FiscalCalendar = None, llm_router = None):
        """
        Initialize the query parser.
        
        Args:
            fiscal_calendar: Fiscal calendar for date calculations
            llm_router: Optional LLM router for fallback parsing
        """
        self.fiscal_calendar = fiscal_calendar or get_fiscal_calendar()
        self.llm_router = llm_router
        # NEW: Add dynamic registry
        if DYNAMIC_REGISTRY_AVAILABLE:
            self.dynamic_registry = get_dynamic_registry()
        else:
            self.dynamic_registry = None
    
    def parse(self, query: str, context: Dict[str, Any] = None) -> ParsedQuery:
        """
        Parse a user query into structured form.
        
        Args:
            query: The user's natural language query
            context: Optional context from conversation history
        
        Returns:
            ParsedQuery with extracted information
        """
        query_lower = query.lower().strip()
        notes = []
        
        # NEW: Extract semantic filters FIRST (this determines what is an account vs department)
        semantic_result = self._extract_semantic_filters(query)
        
        # Extract intent
        intent = self._extract_intent(query_lower)
        notes.append(f"Detected intent: {intent.value}")
        
        # Extract time period
        time_period = self._extract_time_period(query_lower)
        if time_period:
            notes.append(f"Time period: {time_period.period_name}")
        
        # Extract comparison
        comparison_type, comparison_period = self._extract_comparison(query_lower, time_period)
        if comparison_type:
            notes.append(f"Comparison: {comparison_type.value}")
        
        # Extract departments (now aware of account-based terms and compound terms to exclude)
        semantic_matched_ranges = semantic_result.get("matched_ranges", [])
        departments, dept_clarification = self._extract_departments(query, semantic_matched_ranges)
        
        # Merge semantic department filters (avoid duplicates, case-insensitive)
        if semantic_result.get("departments"):
            existing_lower = [d.lower() for d in departments]
            for dept in semantic_result["departments"]:
                if dept.lower() not in existing_lower:
                    departments.append(dept)
                    existing_lower.append(dept.lower())
        
        if departments:
            notes.append(f"Departments: {departments}")
        
        # Extract accounts
        accounts = self._extract_accounts(query)
        if accounts:
            notes.append(f"Accounts: {accounts}")
        
        # Extract top N
        top_n = self._extract_top_n(query_lower)
        if top_n:
            notes.append(f"Top N: {top_n}")
        
        # Extract group by
        group_by = self._extract_group_by(query_lower)
        if group_by:
            notes.append(f"Group by: {', '.join(group_by)}")
        
        # Get semantic filter results
        account_type_filter = semantic_result.get("account_type_filter")
        account_name_filter = semantic_result.get("account_name_filter")  # NEW
        transaction_type_filter = semantic_result.get("transaction_type_filter")
        requires_disambiguation = semantic_result.get("requires_disambiguation", False)
        disambiguation_message = semantic_result.get("disambiguation_message")
        ambiguous_terms = semantic_result.get("ambiguous_terms", [])
        semantic_terms = semantic_result.get("semantic_terms", [])
        is_consolidated = semantic_result.get("is_consolidated", False)
        
        # NEW: Add dynamic clarification if needed (from department extraction)
        if dept_clarification and not requires_disambiguation:
            requires_disambiguation = True
            disambiguation_message = dept_clarification["message"]
            ambiguous_terms = [dept_clarification["term"]]
        
        # Extract subsidiaries from semantic filters
        subsidiaries = semantic_result.get("subsidiaries", [])
        
        if account_type_filter:
            notes.append(f"Account type filter: {account_type_filter}")
        if account_name_filter:
            notes.append(f"Account name filter: {account_name_filter}")
        if transaction_type_filter:
            notes.append(f"Transaction type filter: {transaction_type_filter}")
        if subsidiaries:
            notes.append(f"Subsidiaries: {subsidiaries}")
        if is_consolidated:
            notes.append("Consolidated query (all subsidiaries)")
        if requires_disambiguation:
            notes.append(f"Disambiguation required for: {ambiguous_terms}")
        
        # Calculate confidence based on extraction success
        confidence = self._calculate_confidence(
            intent, time_period, departments, accounts, query_lower,
            has_semantic_filters=bool(account_type_filter or transaction_type_filter),
            requires_disambiguation=requires_disambiguation,
        )
        
        # Use LLM fallback for low confidence (but not if disambiguation is needed)
        used_llm = False
        if confidence < 0.5 and self.llm_router and not requires_disambiguation:
            llm_result = self._llm_parse_fallback(query, context)
            if llm_result:
                # Merge LLM results
                intent = llm_result.get("intent", intent)
                departments = llm_result.get("departments", departments) or departments
                accounts = llm_result.get("accounts", accounts) or accounts
                used_llm = True
                notes.append("Used LLM fallback for parsing")
                confidence = max(confidence, 0.7)
        
        return ParsedQuery(
            original_query=query,
            intent=intent,
            time_period=time_period,
            comparison_period=comparison_period,
            comparison_type=comparison_type,
            departments=departments,
            accounts=accounts,
            subsidiaries=subsidiaries,
            is_consolidated=is_consolidated,
            account_type_filter=account_type_filter,
            account_name_filter=account_name_filter,  # NEW
            transaction_type_filter=transaction_type_filter,
            requires_disambiguation=requires_disambiguation,
            disambiguation_message=disambiguation_message,
            ambiguous_terms=ambiguous_terms,
            semantic_terms=semantic_terms,
            top_n=top_n,
            group_by=group_by,
            confidence=confidence,
            used_llm_fallback=used_llm,
            parsing_notes=notes,
        )
    
    def _extract_semantic_filters(self, query: str) -> Dict[str, Any]:
        """
        Extract semantic filters from the query using the financial_semantics module.
        
        This method resolves financial terms to their proper categories:
        - Account-based terms (revenue, expenses) -> account_type_filter
        - Department-based terms (marketing, engineering) -> departments
        - Transaction type terms (journals, invoices) -> transaction_type_filter
        - Subsidiary terms (US, UK, EMEA) -> subsidiaries
        - Ambiguous terms (sales) -> requires disambiguation
        
        Returns:
            Dict with extracted filters and disambiguation info
        """
        result = {
            "account_type_filter": None,
            "account_name_filter": None,  # NEW: For account name contains filtering
            "departments": [],
            "subsidiaries": [],
            "transaction_type_filter": None,
            "is_consolidated": False,
            "requires_disambiguation": False,
            "disambiguation_message": None,
            "ambiguous_terms": [],
            "semantic_terms": [],
            "matched_ranges": [],  # Character ranges claimed by compound terms
        }
        
        # Resolve all financial terms in the query (with ranges for overlap detection)
        resolved_terms, matched_ranges = resolve_financial_terms_with_ranges(query)
        result["matched_ranges"] = matched_ranges
        
        if not resolved_terms:
            return result
        
        # Store resolved terms for reference
        result["semantic_terms"] = [t.to_dict() for t in resolved_terms]
        
        # Check for ambiguous terms first
        ambiguous = needs_disambiguation(resolved_terms)
        if ambiguous:
            result["requires_disambiguation"] = True
            result["ambiguous_terms"] = [t.term for t in ambiguous]
            result["disambiguation_message"] = build_disambiguation_message(ambiguous)
            logger.info(f"Query contains ambiguous terms: {result['ambiguous_terms']}")
            # Don't process other filters if disambiguation is needed
            return result
        
        # Check for consolidated query (all subsidiaries combined)
        result["is_consolidated"] = is_consolidated_query(resolved_terms)
        
        # Process each resolved term
        account_prefixes = []
        account_name_values = []
        transaction_types = []
        subsidiaries = []
        
        for term in resolved_terms:
            if term.category == SemanticCategory.ACCOUNT:
                # Merge account prefixes
                for prefix in term.filter_values:
                    if prefix not in account_prefixes:
                        account_prefixes.append(prefix)
                logger.debug(f"Semantic: '{term.term}' -> account filter {term.filter_values}")
            
            elif term.category == SemanticCategory.COMPOUND_ACCOUNT:
                # Handle compound filter (account number prefix + account name contains)
                # Primary filter: account number prefix
                for prefix in term.filter_values:
                    if prefix not in account_prefixes:
                        account_prefixes.append(prefix)
                # Secondary filter: account name contains
                if term.secondary_filter_values:
                    for name_val in term.secondary_filter_values:
                        if name_val not in account_name_values:
                            account_name_values.append(name_val)
                logger.debug(
                    f"Semantic: '{term.term}' -> compound filter: "
                    f"number prefix {term.filter_values}, name contains {term.secondary_filter_values}"
                )
            
            elif term.category == SemanticCategory.ACCOUNT_NAME:
                # Account name filter only
                for name_val in term.filter_values:
                    if name_val not in account_name_values:
                        account_name_values.append(name_val)
                logger.debug(f"Semantic: '{term.term}' -> account name filter {term.filter_values}")
                
            elif term.category == SemanticCategory.DEPARTMENT:
                # Add to departments list
                for dept in term.filter_values:
                    if dept not in result["departments"]:
                        result["departments"].append(dept)
                logger.debug(f"Semantic: '{term.term}' -> department filter {term.filter_values}")
                
            elif term.category == SemanticCategory.TRANSACTION_TYPE:
                # Merge transaction types
                for ttype in term.filter_values:
                    if ttype not in transaction_types:
                        transaction_types.append(ttype)
                logger.debug(f"Semantic: '{term.term}' -> transaction type {term.filter_values}")
            
            elif term.category == SemanticCategory.SUBSIDIARY:
                # Add to subsidiaries list (skip consolidated marker)
                for sub in term.filter_values:
                    if sub != "*" and sub not in subsidiaries:
                        subsidiaries.append(sub)
                logger.debug(f"Semantic: '{term.term}' -> subsidiary filter {term.filter_values}")
        
        # Build filter objects
        if account_prefixes:
            result["account_type_filter"] = {
                "filter_type": "prefix",
                "values": account_prefixes,
            }
        
        if account_name_values:
            result["account_name_filter"] = {
                "filter_type": "contains",
                "values": account_name_values,
            }
        
        if transaction_types:
            result["transaction_type_filter"] = transaction_types
        
        if subsidiaries:
            result["subsidiaries"] = subsidiaries
        
        return result
    
    def _extract_intent(self, query: str) -> QueryIntent:
        """Extract the primary intent from the query."""
        for intent, pattern in self.INTENT_PATTERNS.items():
            if re.search(pattern, query, re.IGNORECASE):
                return intent
        
        # Default to summary if no specific intent detected
        return QueryIntent.SUMMARY
    
    def _extract_time_period(self, query: str) -> Optional[FiscalPeriod]:
        """Extract time period from the query."""
        # IMPORTANT: Check specific quarter patterns FIRST before generic patterns
        # This ensures "Q1 in FY 2026" is parsed correctly, not as "FY 2026" + "Q1"
        
        # Try month range pattern FIRST (e.g., "February through December 2025", "Feb to Dec 2025", "March - November 2025")
        # Pattern: Month (through|to|-|–) Month Year
        month_range_pattern = r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*(?:through|to|-|–)\s*(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*(\d{4})\b"
        
        month_range_match = re.search(month_range_pattern, query, re.IGNORECASE)
        if month_range_match:
            start_month_str = month_range_match.group(1)
            end_month_str = month_range_match.group(2)
            year = int(month_range_match.group(3))
            
            # Convert month names to numbers
            month_map = {
                'jan': 1, 'january': 1,
                'feb': 2, 'february': 2,
                'mar': 3, 'march': 3,
                'apr': 4, 'april': 4,
                'may': 5,
                'jun': 6, 'june': 6,
                'jul': 7, 'july': 7,
                'aug': 8, 'august': 8,
                'sep': 9, 'september': 9,
                'oct': 10, 'october': 10,
                'nov': 11, 'november': 11,
                'dec': 12, 'december': 12,
            }
            
            start_month = month_map.get(start_month_str.lower()[:3], 1)
            end_month = month_map.get(end_month_str.lower()[:3], 12)
            
            # Create date range
            from calendar import monthrange
            start_date = date(year, start_month, 1)
            _, last_day = monthrange(year, end_month)
            end_date = date(year, end_month, last_day)
            
            # Determine fiscal year
            fiscal_year = self.fiscal_calendar.get_fiscal_year_for_date(start_date)
            
            # Create period name
            start_month_short = start_month_str[:3].title()
            end_month_short = end_month_str[:3].title()
            period_name = f"{start_month_short}-{end_month_short} {year}"
            
            result = FiscalPeriod(
                start_date=start_date,
                end_date=end_date,
                period_name=period_name,
                fiscal_year=fiscal_year,
            )
            
            logger.info(f"Extracted time period: {result.period_name} ({result.start_date} to {result.end_date})")
            return result
        
        # Try specific quarter with fiscal year (e.g., "Q1 FY2026", "Q1 in FY 2026", "Q1 2026")
        # Pattern: Q1 (optional: "in") FY 2026 or Q1 FY2026 or Q1 2026
        q_match = re.search(r"\bQ([1-4])(?:\s+in\s+)?(?:FY\s*)?(\d{2,4})\b", query, re.IGNORECASE)
        if q_match:
            quarter = int(q_match.group(1))
            year_str = q_match.group(2)
            if year_str:
                year = int(year_str)
                if year < 100:
                    year += 2000
                return self.fiscal_calendar.get_fiscal_quarter_range(year, quarter)
        
        # Try quarter without year (e.g., "Q1", "Q3") - use current fiscal year
        q_match = re.search(r"\bQ([1-4])(?!\s*(?:FY|in)\s*\d)\b", query, re.IGNORECASE)
        if q_match:
            quarter = int(q_match.group(1))
            year = self.fiscal_calendar.get_fiscal_year_for_date(date.today())
            return self.fiscal_calendar.get_fiscal_quarter_range(year, quarter)
        
        # Try to parse specific fiscal year (e.g., "FY2024", "FY25")
        # Only match if no quarter was found
        fy_match = re.search(r"\bFY\s*(\d{2,4})\b", query, re.IGNORECASE)
        if fy_match:
            year = int(fy_match.group(1))
            if year < 100:
                year += 2000
            return self.fiscal_calendar.get_fiscal_year_range(year)
        
        # Try to parse "YYYY fiscal year" format (e.g., "2026 fiscal year", "2025 fiscal year")
        # Pattern: 4-digit year followed by "fiscal year"
        fy_year_match = re.search(r"\b(\d{4})\s+fiscal\s+year\b", query, re.IGNORECASE)
        if fy_year_match:
            year = int(fy_year_match.group(1))
            result = self.fiscal_calendar.get_fiscal_year_range(year)
            logger.info(f"Extracted time period: {result.period_name} ({result.start_date} to {result.end_date})")
            return result
        
        # Check generic patterns (YTD, current month, etc.)
        for period_type, pattern in self.TIME_PATTERNS.items():
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                if period_type == "ytd":
                    return self.fiscal_calendar.get_ytd_range()
                elif period_type == "current_month":
                    return self.fiscal_calendar.get_current_month()
                elif period_type == "last_month":
                    return self.fiscal_calendar.get_prior_month()
                elif period_type == "current_quarter":
                    return self.fiscal_calendar.get_current_quarter()
                elif period_type == "current_year":
                    return self.fiscal_calendar.get_current_fiscal_year()
                elif period_type == "last_year":
                    return self.fiscal_calendar.get_prior_fiscal_year()
                # Trailing period patterns
                elif period_type == "ttm":
                    return self.fiscal_calendar.get_trailing_months(12)
                elif period_type == "trailing_3":
                    return self.fiscal_calendar.get_trailing_months(3)
                elif period_type == "trailing_6":
                    return self.fiscal_calendar.get_trailing_months(6)
                elif period_type == "trailing_n":
                    # Extract the number from the matched group
                    n = int(match.group(1))
                    return self.fiscal_calendar.get_trailing_months(n)
        
        # Look for relative time expressions
        months_match = re.search(r"\b(?:last|past)\s+(\d+)\s+months?\b", query, re.IGNORECASE)
        if months_match:
            num_months = int(months_match.group(1))
            return self.fiscal_calendar.get_trailing_months(num_months)
        
        # Log if no time period was extracted
        logger.warning(f"No time period extracted from query: {query[:100]}")
        return None
    
    def _extract_comparison(self, query: str, time_period: Optional[FiscalPeriod]) -> Tuple[Optional[ComparisonType], Optional[FiscalPeriod]]:
        """Extract comparison type and comparison period."""
        for comp_type, pattern in self.COMPARISON_PATTERNS.items():
            if re.search(pattern, query, re.IGNORECASE):
                comparison_period = None
                
                if time_period and comp_type == ComparisonType.PRIOR_PERIOD:
                    comparison_period = self.fiscal_calendar.get_same_period_prior_year(time_period)
                elif comp_type == ComparisonType.MONTH_OVER_MONTH:
                    comparison_period = self.fiscal_calendar.get_prior_month()
                elif comp_type == ComparisonType.YEAR_OVER_YEAR:
                    if time_period:
                        comparison_period = self.fiscal_calendar.get_same_period_prior_year(time_period)
                    else:
                        comparison_period = self.fiscal_calendar.get_prior_fiscal_year()
                
                return comp_type, comparison_period
        
        return None, None
    
    def _extract_departments(
        self, 
        query: str, 
        semantic_matched_ranges: List[Tuple[int, int]] = None
    ) -> Tuple[List[str], Optional[Dict]]:
        """
        Extract department names from the query.
        
        Uses a tiered approach:
        1. Static patterns (for well-known patterns like "sales department")
        2. Dynamic registry (for data-discovered departments)
        
        Args:
            query: The user's query
            semantic_matched_ranges: Character ranges already claimed by semantic terms
        
        Returns:
            Tuple of (departments_list, clarification_info)
        """
        departments = []
        clarification_needed = None
        query_lower = query.lower()
        
        # Step 1: Try static patterns first (existing logic)
        for pattern in self.DEPARTMENT_PATTERNS:
            for match in re.finditer(pattern, query, re.IGNORECASE):
                dept = match.group().strip()
                start, end = match.span()
                
                # Special check: "IT" pattern should only match uppercase "IT", not lowercase "it"
                if pattern.startswith("(?<![a-z])\\bIT\\b") or "\\bIT\\b" in pattern:
                    # Check if the actual matched text is uppercase "IT"
                    actual_text = query[start:end]
                    if actual_text.lower() == "it" and actual_text != "IT":
                        # Skip lowercase "it" - it's a pronoun, not IT department
                        logger.debug(f"Skipping lowercase 'it' at position {start}:{end} - pronoun, not IT department")
                        continue
                
                # Check if this match overlaps with a compound semantic term
                if semantic_matched_ranges:
                    overlaps = False
                    for matched_start, matched_end in semantic_matched_ranges:
                        if not (end <= matched_start or start >= matched_end):
                            overlaps = True
                            logger.debug(
                                f"Skipping department '{dept}' - overlaps with compound term at {matched_start}:{matched_end}"
                            )
                            break
                    if overlaps:
                        continue
                
                # Normalize department name (returns None if it's an account term)
                dept_normalized = self._normalize_department(dept)
                if dept_normalized and dept_normalized not in departments:
                    departments.append(dept_normalized)
        
        # Step 2: Try dynamic registry for potential department terms not matched by patterns
        if self.dynamic_registry and not self.dynamic_registry.is_empty():
            potential_terms = self._extract_potential_entity_terms(query, semantic_matched_ranges)
            
            for term in potential_terms:
                # Skip if already matched by static patterns
                if any(term.lower() in d.lower() for d in departments):
                    continue
                
                # Check dynamic registry
                resolved, clarification = self._resolve_entity_dynamic(term, EntityType.DEPARTMENT)
                
                if resolved:
                    for dept in resolved:
                        if dept not in departments:
                            departments.append(dept)
                elif clarification:
                    # Multiple matches found - need clarification
                    clarification_needed = clarification
                    # Don't add to departments yet - wait for user response
        
        return departments, clarification_needed
    
    def _resolve_entity_dynamic(
        self, 
        term: str, 
        entity_type: EntityType
    ) -> Tuple[Optional[List[str]], Optional[Dict]]:
        """
        Resolve an entity term using the dynamic registry.
        
        Args:
            term: The term to resolve (e.g., "GPS", "Sales NA")
            entity_type: The type of entity to look for
        
        Returns:
            Tuple of (resolved_values, clarification_info)
            - resolved_values: List of canonical names if resolved, None if not found
            - clarification_info: Dict with clarification details if needed, None otherwise
        """
        if not self.dynamic_registry or self.dynamic_registry.is_empty():
            # Registry not yet built - will be populated on first data fetch
            logger.debug(f"Dynamic registry is empty, cannot resolve '{term}'")
            return None, None
        
        match = self.dynamic_registry.lookup(term, entity_type)
        
        if match.is_empty:
            # Term not found in registry
            return None, None
        
        if match.is_exact:
            # Single confident match - return the canonical name
            return [match.best_match.canonical_name], None
        
        if match.needs_clarification:
            # Multiple matches - need user clarification
            clarification = {
                "term": term,
                "type": entity_type.value,
                "options": match.clarification_options[:10],
                "message": self._build_clarification_message(term, entity_type, match),
            }
            return None, clarification
        
        # Lower confidence but single match - use it
        if match.best_match:
            return [match.best_match.canonical_name], None
        
        return None, None
    
    def _build_clarification_message(
        self, 
        term: str, 
        entity_type: EntityType, 
        match: RegistryMatch
    ) -> str:
        """Build a user-friendly clarification message."""
        type_name = {
            EntityType.DEPARTMENT: "department",
            EntityType.ACCOUNT: "account",
            EntityType.ACCOUNT_NUMBER: "account number",
            EntityType.SUBSIDIARY: "subsidiary",
            EntityType.TRANSACTION_TYPE: "transaction type",
        }.get(entity_type, "entity")
        
        options_str = "\n".join(
            f"  {i+1}. {opt}" 
            for i, opt in enumerate(match.clarification_options[:10])
        )
        
        return (
            f'"{term}" matches multiple {type_name}s:\n'
            f'{options_str}\n\n'
            f'Which one did you mean? You can also say "all" for a consolidated view.'
        )
    
    def _extract_potential_entity_terms(
        self, 
        query: str, 
        semantic_matched_ranges: List[Tuple[int, int]] = None
    ) -> List[str]:
        """
        Extract words/phrases that might be entity names (departments, accounts, etc.).
        
        Filters out common stop words, time periods, and financial terms that are
        already handled by the semantic system.
        """
        query_lower = query.lower()
        
        # Words to exclude (handled elsewhere or too common)
        stop_words = {
            # Common query words
            "what", "are", "the", "show", "me", "give", "provide", "list", "get",
            "for", "by", "in", "of", "and", "or", "to", "from", "with", "about",
            "how", "much", "many", "which", "where", "when", "why", "can", "could",
            
            # Financial terms (handled by semantic system)
            "expenses", "expense", "revenue", "revenues", "cost", "costs", "spend",
            "spending", "income", "total", "sum", "breakdown", "analysis", "report",
            "budget", "actual", "variance", "profit", "loss", "margin",
            
            # Time terms (handled by fiscal calendar)
            "ytd", "mtd", "qtd", "ttm", "trailing", "months", "month", "quarters",
            "quarter", "year", "years", "current", "last", "prior", "previous",
            "this", "that", "today", "yesterday", "week", "weekly", "monthly",
            "quarterly", "annually", "fy", "fiscal",
            
            # Account type terms
            "accounts", "account", "assets", "liabilities", "equity",
            "operating", "cogs", "opex",
        }
        
        # Extract words
        words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9\-&]+\b', query_lower)
        potential_terms = []
        
        for word in words:
            if word not in stop_words and len(word) > 1:
                # Check if word is within a semantic matched range
                if semantic_matched_ranges:
                    word_start = query_lower.find(word)
                    if word_start >= 0:
                        in_range = False
                        for start, end in semantic_matched_ranges:
                            if start <= word_start < end:
                                in_range = True
                                break
                        if in_range:
                            continue
                
                potential_terms.append(word)
        
        # Also try two-word phrases (bigrams) for things like "Sales NA", "Product Management"
        words_list = query_lower.split()
        for i in range(len(words_list) - 1):
            w1, w2 = words_list[i], words_list[i + 1]
            if w1 not in stop_words and w2 not in stop_words:
                phrase = f"{w1} {w2}"
                if phrase not in potential_terms:
                    potential_terms.append(phrase)
        
        # Try three-word phrases for things like "GPS North America"
        for i in range(len(words_list) - 2):
            w1, w2, w3 = words_list[i], words_list[i + 1], words_list[i + 2]
            if w1 not in stop_words and w3 not in stop_words:
                phrase = f"{w1} {w2} {w3}"
                if phrase not in potential_terms:
                    potential_terms.append(phrase)
        
        return potential_terms
    
    def _normalize_department(self, dept: str) -> Optional[str]:
        """
        Normalize department name to match NetSuite department hierarchy.
        
        IMPORTANT: This method now checks if a term is an account-based term
        using the financial_semantics module. Account-based terms like "revenue"
        should NOT be mapped to departments.
        
        Returns None if the term is actually an account-based term.
        """
        dept_lower = dept.lower().strip()
        
        # CRITICAL FIX: Check if this term is actually an account-based term
        # Terms like "revenue", "expenses", "cogs" should NOT become department filters
        if is_account_term(dept_lower):
            logger.debug(f"Term '{dept}' is account-based, not a department")
            return None
        
        # Map user-friendly names to NetSuite department patterns
        # These will be used for partial matching against department_name field
        # NOTE: Removed "revenue" -> "Sales" mapping - revenue is an account type!
        mappings = {
            # Cost of Sales hierarchy (department, not account type "cost of sales")
            "gcc": "GCC",
            "customer centric engineering": "GCC",
            
            # G&A hierarchy
            "g&a": "G&A",
            "general and administrative": "G&A",
            "general & administrative": "G&A",
            "finance": "Finance",
            "accounting": "Finance",
            "fp&a": "Finance",
            "it": "IT",
            "information technology": "IT",
            "tech ops": "IT",
            "hr": "HR",
            "human resources": "HR",
            "people ops": "HR",
            "legal": "Legal",
            "compliance": "Legal",
            
            # R&D hierarchy
            "r&d": "R&D",
            "research and development": "R&D",
            "research & development": "R&D",
            "engineering": "Engineering",
            "eng": "Engineering",
            
            # Sales & Marketing
            # NOTE: "sales" alone is ambiguous - handled by financial_semantics
            # Only explicit department references go here
            "sales department": "Sales",
            "sales team": "Sales",
            "commercial": "Sales",
            "sdr": "SDR",
            "sales development": "SDR",
            "sales dev": "SDR",
            "marketing": "Marketing",
            "mktg": "Marketing",
            
            # Other
            "customer success": "Customer Success",
            "cs": "Customer Success",
            "support": "Support",
            "product": "Product",
            "pm": "Product",
            "operations": "Operations",
            "ops": "Operations",
        }
        
        return mappings.get(dept_lower, dept)
    
    def _extract_accounts(self, query: str) -> List[str]:
        """Extract account names or numbers from the query."""
        accounts = []
        
        # Look for account numbers (e.g., "account 6100", "acct 123456")
        acct_num_match = re.findall(r"\b(?:account|acct)\.?\s*#?\s*(\d{4,6})\b", query, re.IGNORECASE)
        accounts.extend(acct_num_match)
        
        # Common account name patterns - more specific to avoid false positives
        # Note: Generic terms like "spend", "expense" are NOT accounts - they describe what we're analyzing
        account_patterns = [
            r"\b(accounts?\s*payable|A/?P)\b",
            r"\b(accounts?\s*receivable|A/?R)\b",
            r"\b(payroll|salaries|wages)\b",
            r"\b(rent\s+expense|lease\s+expense)\b",
            r"\b(travel\s+(?:and\s+)?(?:entertainment|expense)|T&E\s+expense)\b",
            r"\b(software\s+(?:expense|subscriptions?)|SaaS\s+subscriptions?)\b",
            r"\b(professional\s*services?\s+expense|consulting\s+(?:fees?|expense))\b",
            r"\b(deferred\s*revenue)\b",
            r"\b(cost\s+of\s+(?:goods\s+)?sales?|COGS)\b",
        ]
        
        for pattern in account_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                acct = match if isinstance(match, str) else match[0]
                if acct.lower() not in [a.lower() for a in accounts]:
                    accounts.append(acct)
        
        return accounts
    
    def _extract_top_n(self, query: str) -> Optional[int]:
        """Extract top N value from query."""
        match = re.search(r"\b(?:top|bottom)\s*(\d+)\b", query, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None
    
    def _extract_group_by(self, query: str) -> List[str]:
        """Extract ALL grouping dimensions from query."""
        # Find all instances of "by <dimension>" in the query
        # This handles commas, "and", and other separators naturally
        dimension_map = {
            "department": ["department", "departments"],
            "account": ["account", "accounts"],
            "month": ["month", "months"],
            "quarter": ["quarter", "quarters"],
            "vendor": ["vendor", "vendors"],
            "customer": ["customer", "customers"],
            "class": ["class", "classes"],
            "location": ["location", "locations"],
            "subsidiary": ["subsidiary", "subsidiaries"],
        }
        
        groups = []
        query_lower = query.lower()
        
        # Find all "by <word>" patterns
        by_pattern = r"by\s+(\w+)"
        matches = re.findall(by_pattern, query_lower)
        
        # Map matched words to dimension types
        for match in matches:
            for dim_type, variants in dimension_map.items():
                if match in variants:
                    if dim_type not in groups:
                        groups.append(dim_type)
                    break
        
        return groups
    
    def _calculate_confidence(
        self,
        intent: QueryIntent,
        time_period: Optional[FiscalPeriod],
        departments: List[str],
        accounts: List[str],
        query: str,
        has_semantic_filters: bool = False,
        requires_disambiguation: bool = False,
    ) -> float:
        """
        Calculate confidence score for the parsing.
        
        Args:
            intent: Detected query intent
            time_period: Extracted time period
            departments: Extracted departments
            accounts: Extracted accounts
            query: The original query string
            has_semantic_filters: Whether semantic filters were extracted
            requires_disambiguation: Whether disambiguation is needed
        """
        confidence = 0.5  # Base confidence
        
        # Boost for detected time period
        if time_period:
            confidence += 0.15
        
        # Boost for detected departments
        if departments:
            confidence += 0.15
        
        # Boost for detected accounts
        if accounts:
            confidence += 0.1
        
        # Boost for specific intent (not just default summary)
        if intent != QueryIntent.SUMMARY:
            confidence += 0.1
        
        # NEW: Boost for successfully resolved semantic filters
        if has_semantic_filters:
            confidence += 0.15
        
        # NEW: Reduce confidence if disambiguation is needed
        if requires_disambiguation:
            confidence -= 0.3
        
        # Reduce for very short or very long queries (likely unclear)
        word_count = len(query.split())
        if word_count < 3:
            confidence -= 0.2
        elif word_count > 30:
            confidence -= 0.1
        
        return min(max(confidence, 0.0), 1.0)
    
    def _llm_parse_fallback(self, query: str, context: Dict[str, Any] = None) -> Optional[Dict]:
        """Use LLM to parse complex queries. Returns None if LLM not available."""
        if not self.llm_router:
            return None
        
        try:
            prompt = f"""Parse this financial analysis query and extract structured information.

Query: "{query}"

Extract the following (respond in JSON):
- intent: one of [summary, total, trend, comparison, variance, breakdown, top_n, detail, ratio]
- departments: list of department names mentioned (e.g., ["Marketing", "SDR"])
- accounts: list of account names or types mentioned
- time_period: description of time period (e.g., "YTD", "last month", "Q1 2024")
- comparison_type: if comparing, what type (e.g., "month_over_month", "year_over_year")
- group_by: dimension to group by if mentioned
- top_n: number if requesting top/bottom N

Respond ONLY with valid JSON, no markdown or explanation."""

            response = self.llm_router.generate_with_system(
                system_prompt="You are a query parser. Respond only with valid JSON.",
                user_message=prompt,
                temperature=0.1,
            )
            
            import json
            return json.loads(response.content)
        except Exception as e:
            logger.warning(f"LLM parsing fallback failed: {e}")
            return None

# Singleton instance
_query_parser: Optional[QueryParser] = None

def get_query_parser(llm_router = None) -> QueryParser:
    """Get the configured query parser instance."""
    global _query_parser
    if _query_parser is None:
        _query_parser = QueryParser(llm_router=llm_router)
    return _query_parser

