"""
Financial Calculation Tools

CRITICAL FRAMEWORK PRINCIPLE: LLMs interpret, tools compute.

All numerical calculations are performed by deterministic code,
ensuring consistent results regardless of which LLM model is used.
The LLM's role is to interpret and explain these results.
"""
import math
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple, Union
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class MetricType(Enum):
    """Categories of financial metrics."""
    LIQUIDITY = "liquidity"
    PROFITABILITY = "profitability"
    EFFICIENCY = "efficiency"
    LEVERAGE = "leverage"
    CASH_FLOW = "cash_flow"
    TREND = "trend"
    VARIANCE = "variance"
    CORRELATION = "correlation"
    REGRESSION = "regression"
    VOLATILITY = "volatility"
    SEASONALITY = "seasonality"

@dataclass
class CalculationResult:
    """Container for a calculated metric with metadata."""
    metric_name: str
    value: float
    formatted_value: str
    metric_type: MetricType
    inputs: Dict[str, float]
    formula: str
    interpretation_guide: str  # Guidance for LLM interpretation
    confidence: float = 1.0  # 1.0 for deterministic calculations
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "formatted_value": self.formatted_value,
            "metric_type": self.metric_type.value,
            "inputs": self.inputs,
            "formula": self.formula,
            "interpretation_guide": self.interpretation_guide,
            "confidence": self.confidence,
        }

class FinancialCalculator:
    """
    Deterministic financial calculations.
    
    Every method includes:
    1. The calculation formula
    2. Input validation
    3. Interpretation guidance for the LLM
    """
    
    @staticmethod
    def _safe_divide(numerator: float, denominator: float) -> Optional[float]:
        """Safe division with zero handling."""
        if denominator == 0:
            return None
        return numerator / denominator
    
    @staticmethod
    def _format_currency(value: float) -> str:
        """Format as currency."""
        if value >= 1_000_000:
            return f"${value/1_000_000:,.2f}M"
        elif value >= 1_000:
            return f"${value/1_000:,.2f}K"
        else:
            return f"${value:,.2f}"
    
    @staticmethod
    def _format_percentage(value: float) -> str:
        """Format as percentage."""
        return f"{value * 100:.2f}%"
    
    @staticmethod
    def _format_ratio(value: float) -> str:
        """Format as ratio."""
        return f"{value:.2f}x"
    
    # ==================== LIQUIDITY RATIOS ====================
    
    def current_ratio(
        self, 
        current_assets: float, 
        current_liabilities: float
    ) -> CalculationResult:
        """Calculate current ratio (liquidity measure)."""
        value = self._safe_divide(current_assets, current_liabilities)
        
        if value is None:
            return CalculationResult(
                metric_name="Current Ratio",
                value=float('inf'),
                formatted_value="N/A (no liabilities)",
                metric_type=MetricType.LIQUIDITY,
                inputs={"current_assets": current_assets, "current_liabilities": current_liabilities},
                formula="Current Assets / Current Liabilities",
                interpretation_guide="Cannot calculate - no current liabilities.",
                confidence=0.0,
            )
        
        return CalculationResult(
            metric_name="Current Ratio",
            value=value,
            formatted_value=self._format_ratio(value),
            metric_type=MetricType.LIQUIDITY,
            inputs={"current_assets": current_assets, "current_liabilities": current_liabilities},
            formula="Current Assets / Current Liabilities",
            interpretation_guide=(
                f"A ratio of {value:.2f}x means the company has ${value:.2f} in current assets "
                f"for every $1.00 of current liabilities. "
                f"Generally, >1.0x indicates ability to cover short-term obligations. "
                f"Industry context matters: 1.5-2.0x often considered healthy for most industries."
            ),
        )
    
    def quick_ratio(
        self,
        current_assets: float,
        inventory: float,
        current_liabilities: float
    ) -> CalculationResult:
        """Calculate quick ratio (acid-test ratio)."""
        numerator = current_assets - inventory
        value = self._safe_divide(numerator, current_liabilities)
        
        if value is None:
            return CalculationResult(
                metric_name="Quick Ratio",
                value=float('inf'),
                formatted_value="N/A",
                metric_type=MetricType.LIQUIDITY,
                inputs={"current_assets": current_assets, "inventory": inventory, "current_liabilities": current_liabilities},
                formula="(Current Assets - Inventory) / Current Liabilities",
                interpretation_guide="Cannot calculate - no current liabilities.",
                confidence=0.0,
            )
        
        return CalculationResult(
            metric_name="Quick Ratio",
            value=value,
            formatted_value=self._format_ratio(value),
            metric_type=MetricType.LIQUIDITY,
            inputs={"current_assets": current_assets, "inventory": inventory, "current_liabilities": current_liabilities},
            formula="(Current Assets - Inventory) / Current Liabilities",
            interpretation_guide=(
                f"Quick ratio of {value:.2f}x excludes inventory (less liquid). "
                f"This is a more conservative liquidity measure. "
                f">1.0x generally indicates good short-term liquidity without relying on inventory sales."
            ),
        )
    
    # ==================== PROFITABILITY RATIOS ====================
    
    def gross_margin(self, revenue: float, cogs: float) -> CalculationResult:
        """Calculate gross profit margin."""
        gross_profit = revenue - cogs
        value = self._safe_divide(gross_profit, revenue)
        
        if value is None:
            return CalculationResult(
                metric_name="Gross Margin",
                value=0.0,
                formatted_value="N/A",
                metric_type=MetricType.PROFITABILITY,
                inputs={"revenue": revenue, "cogs": cogs},
                formula="(Revenue - COGS) / Revenue",
                interpretation_guide="Cannot calculate - no revenue.",
                confidence=0.0,
            )
        
        return CalculationResult(
            metric_name="Gross Margin",
            value=value,
            formatted_value=self._format_percentage(value),
            metric_type=MetricType.PROFITABILITY,
            inputs={"revenue": revenue, "cogs": cogs, "gross_profit": gross_profit},
            formula="(Revenue - COGS) / Revenue",
            interpretation_guide=(
                f"Gross margin of {value*100:.1f}% means the company retains "
                f"${value*100:.0f} cents of every dollar after direct costs. "
                f"Higher margins indicate pricing power or efficient production. "
                f"Compare to industry benchmarks for meaningful analysis."
            ),
        )
    
    def operating_margin(self, operating_income: float, revenue: float) -> CalculationResult:
        """Calculate operating profit margin."""
        value = self._safe_divide(operating_income, revenue)
        
        if value is None:
            return CalculationResult(
                metric_name="Operating Margin",
                value=0.0,
                formatted_value="N/A",
                metric_type=MetricType.PROFITABILITY,
                inputs={"operating_income": operating_income, "revenue": revenue},
                formula="Operating Income / Revenue",
                interpretation_guide="Cannot calculate - no revenue.",
                confidence=0.0,
            )
        
        return CalculationResult(
            metric_name="Operating Margin",
            value=value,
            formatted_value=self._format_percentage(value),
            metric_type=MetricType.PROFITABILITY,
            inputs={"operating_income": operating_income, "revenue": revenue},
            formula="Operating Income / Revenue",
            interpretation_guide=(
                f"Operating margin of {value*100:.1f}% reflects profit after all operating expenses. "
                f"This is a key measure of operational efficiency. "
                f"Negative values indicate operating losses."
            ),
        )
    
    def net_margin(self, net_income: float, revenue: float) -> CalculationResult:
        """Calculate net profit margin."""
        value = self._safe_divide(net_income, revenue)
        
        if value is None:
            return CalculationResult(
                metric_name="Net Margin",
                value=0.0,
                formatted_value="N/A",
                metric_type=MetricType.PROFITABILITY,
                inputs={"net_income": net_income, "revenue": revenue},
                formula="Net Income / Revenue",
                interpretation_guide="Cannot calculate - no revenue.",
                confidence=0.0,
            )
        
        return CalculationResult(
            metric_name="Net Margin",
            value=value,
            formatted_value=self._format_percentage(value),
            metric_type=MetricType.PROFITABILITY,
            inputs={"net_income": net_income, "revenue": revenue},
            formula="Net Income / Revenue",
            interpretation_guide=(
                f"Net margin of {value*100:.1f}% is the bottom-line profitability. "
                f"This is what remains after all expenses, interest, and taxes. "
                f"Widely varies by industry - compare to sector peers."
            ),
        )
    
    # ==================== VARIANCE ANALYSIS ====================
    
    def variance(
        self,
        actual: float,
        budget: float,
        metric_name: str = "Value"
    ) -> CalculationResult:
        """Calculate variance between actual and budgeted values."""
        absolute_variance = actual - budget
        pct_variance = self._safe_divide(absolute_variance, abs(budget)) if budget != 0 else None
        
        favorable = absolute_variance > 0  # Assumes higher is better (flip for expenses)
        
        return CalculationResult(
            metric_name=f"{metric_name} Variance",
            value=absolute_variance,
            formatted_value=f"{self._format_currency(absolute_variance)} ({self._format_percentage(pct_variance) if pct_variance else 'N/A'})",
            metric_type=MetricType.VARIANCE,
            inputs={"actual": actual, "budget": budget},
            formula="Actual - Budget",
            interpretation_guide=(
                f"{'Favorable' if favorable else 'Unfavorable'} variance of {self._format_currency(abs(absolute_variance))}. "
                f"Actual {metric_name} was {self._format_percentage(abs(pct_variance)) if pct_variance else 'significantly'} "
                f"{'above' if favorable else 'below'} budget. "
                f"Investigate root causes for significant variances (typically >5-10%)."
            ),
        )
    
    def period_over_period_change(
        self,
        current_value: float,
        prior_value: float,
        metric_name: str = "Value",
        period_label: str = "Period"
    ) -> CalculationResult:
        """Calculate period-over-period change."""
        absolute_change = current_value - prior_value
        pct_change = self._safe_divide(absolute_change, abs(prior_value)) if prior_value != 0 else None
        
        direction = "increased" if absolute_change > 0 else "decreased"
        
        return CalculationResult(
            metric_name=f"{metric_name} {period_label} Change",
            value=pct_change if pct_change is not None else 0,
            formatted_value=self._format_percentage(pct_change) if pct_change else "N/A",
            metric_type=MetricType.TREND,
            inputs={"current_value": current_value, "prior_value": prior_value},
            formula="(Current - Prior) / |Prior|",
            interpretation_guide=(
                f"{metric_name} {direction} by {self._format_currency(abs(absolute_change))} "
                f"({self._format_percentage(abs(pct_change)) if pct_change else 'significantly'}) "
                f"compared to prior {period_label.lower()}. "
                f"Consider seasonality and one-time factors when interpreting."
            ),
        )
    
    # ==================== AGGREGATION FUNCTIONS ====================
    
    def sum_by_category(
        self,
        data: List[Dict[str, Any]],
        amount_field: str,
        category_field: str
    ) -> Dict[str, CalculationResult]:
        """Sum amounts by category."""
        totals: Dict[str, float] = {}
        
        for row in data:
            category = str(row.get(category_field, "Unknown"))
            amount = float(row.get(amount_field, 0) or 0)
            totals[category] = totals.get(category, 0) + amount
        
        results = {}
        grand_total = sum(totals.values())
        
        for category, total in sorted(totals.items(), key=lambda x: x[1], reverse=True):
            pct_of_total = self._safe_divide(total, grand_total) or 0
            
            results[category] = CalculationResult(
                metric_name=f"{category} Total",
                value=total,
                formatted_value=self._format_currency(total),
                metric_type=MetricType.CASH_FLOW,
                inputs={"category": category, "grand_total": grand_total},
                formula=f"Sum of {amount_field} where {category_field} = '{category}'",
                interpretation_guide=(
                    f"{category} represents {self._format_percentage(pct_of_total)} of total. "
                    f"This is {self._format_currency(total)} out of {self._format_currency(grand_total)} total."
                ),
            )
        
        return results
    
    def time_series_trend(
        self,
        data: List[Dict[str, Any]],
        amount_field: str,
        date_field: str
    ) -> CalculationResult:
        """Calculate trend direction and strength from time series data."""
        # Sort by date and extract values
        sorted_data = sorted(data, key=lambda x: str(x.get(date_field, '')))
        values = [float(row.get(amount_field, 0) or 0) for row in sorted_data]
        
        if len(values) < 2:
            return CalculationResult(
                metric_name="Trend Analysis",
                value=0,
                formatted_value="Insufficient data",
                metric_type=MetricType.TREND,
                inputs={"data_points": len(values)},
                formula="Linear regression slope",
                interpretation_guide="Need at least 2 data points for trend analysis.",
                confidence=0.0,
            )
        
        # Simple linear regression
        n = len(values)
        x_values = list(range(n))
        x_mean = sum(x_values) / n
        y_mean = sum(values) / n
        
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values))
        denominator = sum((x - x_mean) ** 2 for x in x_values)
        
        slope = self._safe_divide(numerator, denominator) or 0
        
        # Calculate R-squared for confidence
        y_pred = [y_mean + slope * (x - x_mean) for x in x_values]
        ss_res = sum((y - yp) ** 2 for y, yp in zip(values, y_pred))
        ss_tot = sum((y - y_mean) ** 2 for y in values)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        
        trend_direction = "upward" if slope > 0 else "downward" if slope < 0 else "flat"
        trend_strength = "strong" if abs(r_squared) > 0.7 else "moderate" if abs(r_squared) > 0.4 else "weak"
        
        return CalculationResult(
            metric_name="Trend Analysis",
            value=slope,
            formatted_value=f"{trend_direction.capitalize()} trend ({self._format_currency(slope)}/period)",
            metric_type=MetricType.TREND,
            inputs={"data_points": n, "r_squared": r_squared, "first_value": values[0], "last_value": values[-1]},
            formula="Linear regression slope (OLS)",
            interpretation_guide=(
                f"Data shows a {trend_strength} {trend_direction} trend. "
                f"Average change of {self._format_currency(abs(slope))} per period. "
                f"R² of {r_squared:.2f} indicates the trend explains {r_squared*100:.0f}% of variance. "
                f"Values ranged from {self._format_currency(min(values))} to {self._format_currency(max(values))}."
            ),
            confidence=abs(r_squared),
        )
    
    # ==================== FISCAL-AWARE CALCULATIONS ====================
    
    def ytd_total(
        self,
        data: List[Dict[str, Any]],
        amount_field: str,
        date_field: str,
        fiscal_start_month: int = 2,
        as_of_date: 'date' = None,
        category_field: str = None
    ) -> CalculationResult:
        """
        Calculate Year-To-Date total respecting fiscal calendar.
        
        Args:
            data: Transaction data
            amount_field: Field containing amounts
            date_field: Field containing dates
            fiscal_start_month: Month when fiscal year starts (1-12)
            as_of_date: End date for YTD (defaults to today)
            category_field: Optional field to filter by
        """
        from datetime import date as date_type, datetime
        
        as_of_date = as_of_date or date_type.today()
        
        # Calculate fiscal year start
        if as_of_date.month >= fiscal_start_month:
            fy_start = date_type(as_of_date.year, fiscal_start_month, 1)
        else:
            fy_start = date_type(as_of_date.year - 1, fiscal_start_month, 1)
        
        # Calculate fiscal year (named after ENDING calendar year, not starting year)
        # For Feb-start: FY2026 = Feb 2025 - Jan 2026
        # If as_of_date is Jan 2026, fiscal_year should be 2026 (not 2025)
        if as_of_date.month >= fiscal_start_month:
            # We're in months Feb-Dec, so FY ends next calendar year
            fiscal_year = as_of_date.year + 1
        else:
            # We're in Jan (or before FY start), FY ends this calendar year
            fiscal_year = as_of_date.year
        
        # Parse and filter data
        ytd_total = 0.0
        record_count = 0
        
        for row in data:
            row_date = row.get(date_field)
            
            # Parse date
            if isinstance(row_date, str):
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
                    try:
                        row_date = datetime.strptime(row_date[:10], fmt).date()
                        break
                    except ValueError:
                        continue
            elif isinstance(row_date, datetime):
                row_date = row_date.date()
            
            if not isinstance(row_date, date_type):
                continue
            
            # Check if within YTD range
            if fy_start <= row_date <= as_of_date:
                amount = float(row.get(amount_field, 0) or 0)
                ytd_total += amount
                record_count += 1
        
        return CalculationResult(
            metric_name=f"FY{fiscal_year} YTD Total",
            value=ytd_total,
            formatted_value=self._format_currency(ytd_total),
            metric_type=MetricType.CASH_FLOW,
            inputs={
                "fy_start": fy_start.isoformat(),
                "as_of_date": as_of_date.isoformat(),
                "record_count": record_count,
            },
            formula=f"Sum of {amount_field} from {fy_start} to {as_of_date}",
            interpretation_guide=(
                f"Year-to-date total for FY{fiscal_year} is {self._format_currency(ytd_total)}. "
                f"This covers {record_count} transactions from {fy_start.strftime('%b %d, %Y')} "
                f"through {as_of_date.strftime('%b %d, %Y')}."
            ),
        )
    
    def period_variance_by_category(
        self,
        current_data: List[Dict[str, Any]],
        prior_data: List[Dict[str, Any]],
        amount_field: str,
        category_field: str,
        current_period_name: str = "Current",
        prior_period_name: str = "Prior"
    ) -> List[CalculationResult]:
        """
        Calculate variance for each category between two periods.
        
        Returns a list of CalculationResults, one per category.
        """
        # Sum by category for each period
        current_by_cat: Dict[str, float] = {}
        prior_by_cat: Dict[str, float] = {}
        
        for row in current_data:
            cat = str(row.get(category_field, "Unknown"))
            amt = float(row.get(amount_field, 0) or 0)
            current_by_cat[cat] = current_by_cat.get(cat, 0) + amt
        
        for row in prior_data:
            cat = str(row.get(category_field, "Unknown"))
            amt = float(row.get(amount_field, 0) or 0)
            prior_by_cat[cat] = prior_by_cat.get(cat, 0) + amt
        
        all_categories = set(current_by_cat.keys()) | set(prior_by_cat.keys())
        
        results = []
        for cat in sorted(all_categories):
            current_val = current_by_cat.get(cat, 0)
            prior_val = prior_by_cat.get(cat, 0)
            
            variance = current_val - prior_val
            pct_variance = self._safe_divide(variance, abs(prior_val)) if prior_val != 0 else None
            
            favorable = variance < 0  # For expenses, lower is better
            direction = "decreased" if variance < 0 else "increased"
            
            results.append(CalculationResult(
                metric_name=f"{cat} Variance",
                value=variance,
                formatted_value=(
                    f"{self._format_currency(variance)} "
                    f"({self._format_percentage(pct_variance) if pct_variance is not None else 'N/A'})"
                ),
                metric_type=MetricType.VARIANCE,
                inputs={
                    "category": cat,
                    f"{current_period_name}_amount": current_val,
                    f"{prior_period_name}_amount": prior_val,
                },
                formula=f"{current_period_name} - {prior_period_name}",
                interpretation_guide=(
                    f"{cat} {direction} by {self._format_currency(abs(variance))} "
                    f"from {self._format_currency(prior_val)} to {self._format_currency(current_val)}. "
                    f"{'Favorable' if favorable else 'Unfavorable'} variance for expense tracking."
                ),
            ))
        
        return results
    
    def ratio_over_time(
        self,
        data: List[Dict[str, Any]],
        numerator_field: str,
        denominator_field: str,
        date_field: str,
        period_type: str = "month",
        ratio_name: str = "Ratio"
    ) -> CalculationResult:
        """
        Calculate a ratio trend over time (e.g., Marketing Spend / Revenue by month).
        
        Args:
            data: Transaction data
            numerator_field: Field for numerator (or category filter value)
            denominator_field: Field for denominator (or category filter value)
            date_field: Date field for grouping
            period_type: Grouping period ("month", "quarter", "year")
            ratio_name: Name for the ratio metric
        """
        from datetime import datetime
        from collections import defaultdict
        
        # Group by period
        periods: Dict[str, Dict[str, float]] = defaultdict(lambda: {"numerator": 0, "denominator": 0})
        
        for row in data:
            row_date = row.get(date_field)
            
            # Parse date
            if isinstance(row_date, str):
                for fmt in ["%Y-%m-%d", "%m/%d/%Y"]:
                    try:
                        row_date = datetime.strptime(row_date[:10], fmt).date()
                        break
                    except ValueError:
                        continue
            elif isinstance(row_date, datetime):
                row_date = row_date.date()
            
            if not hasattr(row_date, 'strftime'):
                continue
            
            # Generate period key
            if period_type == "month":
                period_key = row_date.strftime("%Y-%m")
            elif period_type == "quarter":
                q = (row_date.month - 1) // 3 + 1
                period_key = f"{row_date.year}-Q{q}"
            else:
                period_key = str(row_date.year)
            
            # Aggregate (assumes fields are actual amounts, not categories)
            num_val = float(row.get(numerator_field, 0) or 0)
            den_val = float(row.get(denominator_field, 0) or 0)
            
            periods[period_key]["numerator"] += num_val
            periods[period_key]["denominator"] += den_val
        
        # Calculate ratios
        ratios = []
        for period_key in sorted(periods.keys()):
            num = periods[period_key]["numerator"]
            den = periods[period_key]["denominator"]
            ratio = self._safe_divide(num, den)
            if ratio is not None:
                ratios.append((period_key, ratio))
        
        if len(ratios) < 2:
            return CalculationResult(
                metric_name=f"{ratio_name} Trend",
                value=0,
                formatted_value="Insufficient data",
                metric_type=MetricType.TREND,
                inputs={"periods": len(ratios)},
                formula=f"{numerator_field} / {denominator_field}",
                interpretation_guide="Not enough data points for trend analysis.",
                confidence=0.0,
            )
        
        # Calculate trend
        first_ratio = ratios[0][1]
        last_ratio = ratios[-1][1]
        avg_ratio = sum(r[1] for r in ratios) / len(ratios)
        change = last_ratio - first_ratio
        
        direction = "increased" if change > 0 else "decreased"
        
        return CalculationResult(
            metric_name=f"{ratio_name} Trend",
            value=avg_ratio,
            formatted_value=self._format_percentage(avg_ratio),
            metric_type=MetricType.TREND,
            inputs={
                "first_period": ratios[0][0],
                "first_ratio": first_ratio,
                "last_period": ratios[-1][0],
                "last_ratio": last_ratio,
                "period_count": len(ratios),
            },
            formula=f"{numerator_field} / {denominator_field} by {period_type}",
            interpretation_guide=(
                f"The {ratio_name.lower()} {direction} from {self._format_percentage(first_ratio)} "
                f"to {self._format_percentage(last_ratio)} over {len(ratios)} periods. "
                f"Average ratio: {self._format_percentage(avg_ratio)}."
            ),
        )
    
    def comparative_summary(
        self,
        current_total: float,
        prior_total: float,
        current_period_name: str,
        prior_period_name: str,
        metric_name: str = "Amount"
    ) -> CalculationResult:
        """
        Create a summary comparison between two period totals.
        """
        variance = current_total - prior_total
        pct_change = self._safe_divide(variance, abs(prior_total))
        
        direction = "increased" if variance > 0 else "decreased"
        favorable = variance < 0  # Assuming expense context
        
        return CalculationResult(
            metric_name=f"{metric_name} Comparison",
            value=variance,
            formatted_value=(
                f"{self._format_currency(current_total)} vs {self._format_currency(prior_total)} "
                f"({'+' if variance > 0 else ''}{self._format_percentage(pct_change) if pct_change else 'N/A'})"
            ),
            metric_type=MetricType.VARIANCE,
            inputs={
                current_period_name: current_total,
                prior_period_name: prior_total,
            },
            formula=f"{current_period_name} - {prior_period_name}",
            interpretation_guide=(
                f"{metric_name} {direction} by {self._format_currency(abs(variance))} "
                f"({self._format_percentage(abs(pct_change)) if pct_change else 'N/A'}) "
                f"from {prior_period_name} to {current_period_name}. "
                f"{'Favorable' if favorable else 'Unfavorable'} for expense management."
            ),
        )

# Singleton calculator instance
_calculator = FinancialCalculator()

def get_calculator() -> FinancialCalculator:
    """Get the financial calculator instance."""
    return _calculator
