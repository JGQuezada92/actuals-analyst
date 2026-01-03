"""
Budget vs Actual Support

Provides budget data retrieval and variance analysis capabilities.
Supports comparing actual financial results against budgeted amounts.

Key Features:
- Budget data retrieval (via SuiteQL or RESTlet)
- Budget-to-actual matching by account, department, and period
- Variance calculation (dollar and percentage)
- Favorable/unfavorable classification
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import date
from collections import defaultdict
from enum import Enum

from src.core.fiscal_calendar import FiscalPeriod, get_fiscal_calendar

logger = logging.getLogger(__name__)


class VarianceType(Enum):
    """Classification of variance."""
    FAVORABLE = "favorable"
    UNFAVORABLE = "unfavorable"
    NEUTRAL = "neutral"


@dataclass
class BudgetLine:
    """A single budget line item."""
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    subsidiary_id: Optional[str] = None
    subsidiary_name: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    period_name: Optional[str] = None
    budget_amount: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "account_name": self.account_name,
            "account_number": self.account_number,
            "department_id": self.department_id,
            "department_name": self.department_name,
            "subsidiary_id": self.subsidiary_id,
            "subsidiary_name": self.subsidiary_name,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "period_name": self.period_name,
            "budget_amount": self.budget_amount,
        }


@dataclass
class VarianceResult:
    """Result of a budget vs actual comparison."""
    dimension_key: str  # e.g., "Marketing:6100" (department:account)
    dimension_label: str  # Human-readable label
    
    budget_amount: float
    actual_amount: float
    variance_amount: float
    variance_percent: float
    variance_type: VarianceType
    
    # Breakdown dimensions
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    department_name: Optional[str] = None
    subsidiary_name: Optional[str] = None
    period_name: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension_key": self.dimension_key,
            "dimension_label": self.dimension_label,
            "budget_amount": self.budget_amount,
            "actual_amount": self.actual_amount,
            "variance_amount": self.variance_amount,
            "variance_percent": self.variance_percent,
            "variance_type": self.variance_type.value,
            "account_name": self.account_name,
            "account_number": self.account_number,
            "department_name": self.department_name,
            "subsidiary_name": self.subsidiary_name,
            "period_name": self.period_name,
        }


@dataclass
class BudgetVsActualReport:
    """Complete budget vs actual report."""
    period: FiscalPeriod
    variances: List[VarianceResult]
    total_budget: float
    total_actual: float
    total_variance: float
    total_variance_percent: float
    total_variance_type: VarianceType
    
    # Summary statistics
    favorable_count: int = 0
    unfavorable_count: int = 0
    largest_favorable: Optional[VarianceResult] = None
    largest_unfavorable: Optional[VarianceResult] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "period": self.period.to_dict(),
            "variances": [v.to_dict() for v in self.variances],
            "total_budget": self.total_budget,
            "total_actual": self.total_actual,
            "total_variance": self.total_variance,
            "total_variance_percent": self.total_variance_percent,
            "total_variance_type": self.total_variance_type.value,
            "favorable_count": self.favorable_count,
            "unfavorable_count": self.unfavorable_count,
            "largest_favorable": self.largest_favorable.to_dict() if self.largest_favorable else None,
            "largest_unfavorable": self.largest_unfavorable.to_dict() if self.largest_unfavorable else None,
        }


class BudgetRetriever:
    """
    Retrieves and processes budget data from NetSuite.
    
    Budget data in NetSuite can come from:
    1. Budget records (Budget table)
    2. Budget saved search
    3. Custom SuiteQL query
    """
    
    # SuiteQL query template for budget data
    BUDGET_QUERY_TEMPLATE = """
        SELECT
            Budget.ID AS budget_id,
            BUILTIN.DF(Budget.Account) AS account_name,
            Account.AccountNumber AS account_number,
            BUILTIN.DF(Budget.Department) AS department_name,
            BUILTIN.DF(Budget.Subsidiary) AS subsidiary_name,
            AccountingPeriod.PeriodName AS period_name,
            AccountingPeriod.StartDate AS period_start,
            AccountingPeriod.EndDate AS period_end,
            Budget.Amount AS budget_amount
        FROM
            Budget
        INNER JOIN
            Account ON Account.ID = Budget.Account
        INNER JOIN
            AccountingPeriod ON AccountingPeriod.ID = Budget.AccountingPeriod
        WHERE
            AccountingPeriod.StartDate >= '{start_date}'
            AND AccountingPeriod.EndDate <= '{end_date}'
            {additional_filters}
        ORDER BY
            department_name, account_number
    """
    
    def __init__(self, netsuite_client=None):
        """
        Initialize budget retriever.
        
        Args:
            netsuite_client: Optional NetSuite client for API calls
        """
        self._client = netsuite_client
        self.fiscal_calendar = get_fiscal_calendar()
    
    @property
    def client(self):
        """Lazy-load NetSuite client."""
        if self._client is None:
            from src.tools.netsuite_client import get_netsuite_client
            self._client = get_netsuite_client()
        return self._client
    
    def get_budget_data(
        self,
        period: FiscalPeriod,
        departments: List[str] = None,
        account_prefixes: List[str] = None,
    ) -> List[BudgetLine]:
        """
        Retrieve budget data for the specified period.
        
        Args:
            period: The fiscal period to retrieve budget for
            departments: Optional list of departments to filter
            account_prefixes: Optional list of account number prefixes
        
        Returns:
            List of BudgetLine objects
        """
        # Build additional filters
        filters = []
        
        if departments:
            dept_list = ", ".join(f"'{d}'" for d in departments)
            filters.append(f"AND BUILTIN.DF(Budget.Department) IN ({dept_list})")
        
        if account_prefixes:
            prefix_conditions = []
            for prefix in account_prefixes:
                prefix_conditions.append(f"Account.AccountNumber LIKE '{prefix}%'")
            filters.append(f"AND ({' OR '.join(prefix_conditions)})")
        
        # Build query
        query = self.BUDGET_QUERY_TEMPLATE.format(
            start_date=period.start_date.isoformat(),
            end_date=period.end_date.isoformat(),
            additional_filters=" ".join(filters),
        )
        
        try:
            # Execute query via SuiteQL
            result = self.client.execute_suiteql(query)
            
            if not result or not result.get("items"):
                logger.warning(f"No budget data found for {period.period_name}")
                return []
            
            # Convert to BudgetLine objects
            budget_lines = []
            for row in result["items"]:
                budget_lines.append(BudgetLine(
                    account_name=row.get("account_name"),
                    account_number=row.get("account_number"),
                    department_name=row.get("department_name"),
                    subsidiary_name=row.get("subsidiary_name"),
                    period_name=row.get("period_name"),
                    period_start=date.fromisoformat(row["period_start"]) if row.get("period_start") else None,
                    period_end=date.fromisoformat(row["period_end"]) if row.get("period_end") else None,
                    budget_amount=float(row.get("budget_amount", 0) or 0),
                ))
            
            logger.info(f"Retrieved {len(budget_lines)} budget lines for {period.period_name}")
            return budget_lines
            
        except Exception as e:
            logger.error(f"Failed to retrieve budget data: {e}")
            return []


class VarianceAnalyzer:
    """
    Analyzes variance between budget and actual amounts.
    
    Handles:
    - Matching budget to actuals by dimension
    - Calculating dollar and percentage variance
    - Classifying favorable vs unfavorable
    """
    
    # Account types where positive variance is unfavorable (expenses)
    EXPENSE_PREFIXES = ["5", "6", "7", "8"]
    
    def __init__(self):
        self.fiscal_calendar = get_fiscal_calendar()
    
    def analyze(
        self,
        budget_data: List[BudgetLine],
        actual_data: List[Dict[str, Any]],
        group_by: str = "department",
    ) -> BudgetVsActualReport:
        """
        Perform budget vs actual variance analysis.
        
        Args:
            budget_data: List of budget lines
            actual_data: List of actual transaction data
            group_by: Dimension to group by ("department", "account", "both")
        
        Returns:
            BudgetVsActualReport with variance details
        """
        # Aggregate budget by dimension
        budget_by_dim = self._aggregate_budget(budget_data, group_by)
        
        # Aggregate actuals by dimension
        actual_by_dim = self._aggregate_actuals(actual_data, group_by)
        
        # Calculate variances
        variances = []
        all_dimensions = set(budget_by_dim.keys()) | set(actual_by_dim.keys())
        
        for dim_key in sorted(all_dimensions):
            budget_info = budget_by_dim.get(dim_key, {"amount": 0, "label": dim_key})
            actual_info = actual_by_dim.get(dim_key, {"amount": 0, "label": dim_key})
            
            budget_amt = budget_info["amount"]
            actual_amt = actual_info["amount"]
            variance_amt = actual_amt - budget_amt
            variance_pct = (variance_amt / budget_amt * 100) if budget_amt != 0 else 0
            
            # Determine if favorable or unfavorable
            variance_type = self._classify_variance(
                variance_amt,
                dim_key,
                budget_info.get("account_number"),
            )
            
            variances.append(VarianceResult(
                dimension_key=dim_key,
                dimension_label=budget_info.get("label", actual_info.get("label", dim_key)),
                budget_amount=budget_amt,
                actual_amount=actual_amt,
                variance_amount=variance_amt,
                variance_percent=variance_pct,
                variance_type=variance_type,
                account_name=budget_info.get("account_name") or actual_info.get("account_name"),
                account_number=budget_info.get("account_number") or actual_info.get("account_number"),
                department_name=budget_info.get("department_name") or actual_info.get("department_name"),
            ))
        
        # Calculate totals
        total_budget = sum(v.budget_amount for v in variances)
        total_actual = sum(v.actual_amount for v in variances)
        total_variance = total_actual - total_budget
        total_variance_pct = (total_variance / total_budget * 100) if total_budget != 0 else 0
        
        # Classify total variance (assuming expenses context)
        total_variance_type = VarianceType.FAVORABLE if total_variance < 0 else VarianceType.UNFAVORABLE
        
        # Calculate statistics
        favorable = [v for v in variances if v.variance_type == VarianceType.FAVORABLE]
        unfavorable = [v for v in variances if v.variance_type == VarianceType.UNFAVORABLE]
        
        largest_favorable = max(favorable, key=lambda v: abs(v.variance_amount)) if favorable else None
        largest_unfavorable = max(unfavorable, key=lambda v: abs(v.variance_amount)) if unfavorable else None
        
        # Build period from first budget line
        period = self.fiscal_calendar.get_current_fiscal_year()
        if budget_data and budget_data[0].period_start:
            period = FiscalPeriod(
                start_date=budget_data[0].period_start,
                end_date=budget_data[0].period_end or budget_data[0].period_start,
                period_name=budget_data[0].period_name or "Budget Period",
                fiscal_year=self.fiscal_calendar.get_fiscal_year_for_date(budget_data[0].period_start),
            )
        
        return BudgetVsActualReport(
            period=period,
            variances=variances,
            total_budget=total_budget,
            total_actual=total_actual,
            total_variance=total_variance,
            total_variance_percent=total_variance_pct,
            total_variance_type=total_variance_type,
            favorable_count=len(favorable),
            unfavorable_count=len(unfavorable),
            largest_favorable=largest_favorable,
            largest_unfavorable=largest_unfavorable,
        )
    
    def _aggregate_budget(
        self,
        budget_data: List[BudgetLine],
        group_by: str,
    ) -> Dict[str, Dict[str, Any]]:
        """Aggregate budget data by dimension."""
        aggregated = defaultdict(lambda: {"amount": 0, "label": ""})
        
        for line in budget_data:
            if group_by == "department":
                dim_key = line.department_name or "Unknown"
                label = dim_key
            elif group_by == "account":
                dim_key = line.account_number or "Unknown"
                label = line.account_name or dim_key
            else:  # both
                dim_key = f"{line.department_name or 'Unknown'}:{line.account_number or 'Unknown'}"
                label = f"{line.department_name or 'Unknown'} - {line.account_name or 'Unknown'}"
            
            aggregated[dim_key]["amount"] += line.budget_amount
            aggregated[dim_key]["label"] = label
            aggregated[dim_key]["account_name"] = line.account_name
            aggregated[dim_key]["account_number"] = line.account_number
            aggregated[dim_key]["department_name"] = line.department_name
        
        return dict(aggregated)
    
    def _aggregate_actuals(
        self,
        actual_data: List[Dict[str, Any]],
        group_by: str,
    ) -> Dict[str, Dict[str, Any]]:
        """Aggregate actual data by dimension."""
        aggregated = defaultdict(lambda: {"amount": 0, "label": ""})
        
        # Field name detection
        dept_field = None
        account_field = None
        account_num_field = None
        amount_field = None
        
        if actual_data:
            sample = actual_data[0]
            for key in sample.keys():
                key_lower = key.lower()
                if "department" in key_lower and not dept_field:
                    dept_field = key
                elif "account" in key_lower and "number" in key_lower:
                    account_num_field = key
                elif "account" in key_lower and not account_field:
                    account_field = key
                elif "amount" in key_lower and not amount_field:
                    amount_field = key
        
        for row in actual_data:
            dept = str(row.get(dept_field, "Unknown") or "Unknown")
            account_num = str(row.get(account_num_field, "Unknown") or "Unknown")
            account_name = str(row.get(account_field, "Unknown") or "Unknown")
            amount = float(row.get(amount_field, 0) or 0)
            
            if group_by == "department":
                dim_key = dept
                label = dept
            elif group_by == "account":
                dim_key = account_num
                label = account_name
            else:  # both
                dim_key = f"{dept}:{account_num}"
                label = f"{dept} - {account_name}"
            
            aggregated[dim_key]["amount"] += amount
            aggregated[dim_key]["label"] = label
            aggregated[dim_key]["account_name"] = account_name
            aggregated[dim_key]["account_number"] = account_num
            aggregated[dim_key]["department_name"] = dept
        
        return dict(aggregated)
    
    def _classify_variance(
        self,
        variance_amount: float,
        dim_key: str,
        account_number: Optional[str],
    ) -> VarianceType:
        """
        Classify variance as favorable, unfavorable, or neutral.
        
        For revenue (prefix 4): positive variance is favorable
        For expenses (prefix 5-8): negative variance is favorable
        """
        if variance_amount == 0:
            return VarianceType.NEUTRAL
        
        # Check if this is an expense account
        is_expense = False
        if account_number:
            first_char = str(account_number)[0]
            is_expense = first_char in self.EXPENSE_PREFIXES
        
        if is_expense:
            # For expenses: spending less than budget is favorable
            return VarianceType.FAVORABLE if variance_amount < 0 else VarianceType.UNFAVORABLE
        else:
            # For revenue: earning more than budget is favorable
            return VarianceType.FAVORABLE if variance_amount > 0 else VarianceType.UNFAVORABLE


def format_variance_message(report: BudgetVsActualReport) -> str:
    """Format a user-friendly variance report message."""
    lines = [
        f"Budget vs Actual Report: {report.period.period_name}",
        "=" * 50,
        "",
        f"Total Budget: ${report.total_budget:,.2f}",
        f"Total Actual: ${report.total_actual:,.2f}",
        f"Total Variance: ${report.total_variance:,.2f} ({report.total_variance_percent:+.1f}%)",
        f"Overall: {report.total_variance_type.value.upper()}",
        "",
        f"Favorable items: {report.favorable_count}",
        f"Unfavorable items: {report.unfavorable_count}",
        "",
    ]
    
    if report.largest_unfavorable:
        lines.append(f"Largest unfavorable: {report.largest_unfavorable.dimension_label}")
        lines.append(f"  Variance: ${report.largest_unfavorable.variance_amount:,.2f}")
    
    if report.largest_favorable:
        lines.append(f"Largest favorable: {report.largest_favorable.dimension_label}")
        lines.append(f"  Variance: ${report.largest_favorable.variance_amount:,.2f}")
    
    return "\n".join(lines)


# Singleton instances
_budget_retriever: Optional[BudgetRetriever] = None
_variance_analyzer: Optional[VarianceAnalyzer] = None


def get_budget_retriever() -> BudgetRetriever:
    """Get the budget retriever instance."""
    global _budget_retriever
    if _budget_retriever is None:
        _budget_retriever = BudgetRetriever()
    return _budget_retriever


def get_variance_analyzer() -> VarianceAnalyzer:
    """Get the variance analyzer instance."""
    global _variance_analyzer
    if _variance_analyzer is None:
        _variance_analyzer = VarianceAnalyzer()
    return _variance_analyzer

