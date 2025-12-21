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

# Singleton calculator instance
_calculator = FinancialCalculator()

def get_calculator() -> FinancialCalculator:
    """Get the financial calculator instance."""
    return _calculator
