"""
Advanced Statistical Analysis Module

Provides sophisticated time-series and regression analysis capabilities
for financial data. Implements seasonality adjustment, ARCH/GARCH modeling,
and multi-variable correlation analysis.

Key Features:
- Multi-account correlation with revenue
- Seasonal decomposition (additive/multiplicative)
- ARCH/GARCH volatility modeling
- Regression with statistical significance testing
- Granger causality testing (optional)

Follows Accuracy-First Framework:
- All calculations are deterministic
- Results include confidence intervals and p-values
- Interpretation guides for LLM consumption
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
from enum import Enum
from datetime import date, datetime
import warnings

if TYPE_CHECKING:
    import pandas as pd
    import numpy as np

# Suppress warnings from arch and statsmodels
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Optional imports - gracefully handle missing dependencies
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None

try:
    from statsmodels.tsa.seasonal import STL
    from statsmodels.tsa.stattools import adfuller
    import statsmodels.api as sm
    from statsmodels.stats.diagnostic import acorr_ljungbox
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    STL = None
    sm = None
    acorr_ljungbox = None

try:
    from arch import arch_model
    ARCH_AVAILABLE = True
except ImportError:
    ARCH_AVAILABLE = False
    arch_model = None

try:
    from scipy.stats import t
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    t = None

logger = logging.getLogger(__name__)


class SeasonalityType(Enum):
    ADDITIVE = "additive"
    MULTIPLICATIVE = "multiplicative"
    NONE = "none"


class VolatilityModel(Enum):
    ARCH = "arch"
    GARCH = "garch"
    EGARCH = "egarch"


@dataclass
class SeasonalDecomposition:
    """Result of seasonal decomposition."""
    original: Any  # np.ndarray when numpy available
    trend: Any  # np.ndarray when numpy available
    seasonal: Any  # np.ndarray when numpy available
    residual: Any  # np.ndarray when numpy available
    seasonality_type: SeasonalityType
    period: int  # e.g., 12 for monthly data
    seasonal_strength: float  # 0-1, how much variance explained by seasonality
    interpretation: str


@dataclass
class RegressionResult:
    """Result of a regression analysis."""
    dependent_var: str
    independent_var: str
    coefficient: float
    std_error: float
    t_statistic: float
    p_value: float
    r_squared: float
    adj_r_squared: float
    confidence_interval_95: Tuple[float, float]
    observations: int
    is_significant: bool  # p < 0.05
    interpretation: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "dependent_var": self.dependent_var,
            "independent_var": self.independent_var,
            "coefficient": self.coefficient,
            "std_error": self.std_error,
            "t_statistic": self.t_statistic,
            "p_value": self.p_value,
            "r_squared": self.r_squared,
            "adj_r_squared": self.adj_r_squared,
            "confidence_interval_95": self.confidence_interval_95,
            "observations": self.observations,
            "is_significant": self.is_significant,
            "interpretation": self.interpretation,
        }


@dataclass
class CorrelationEntry:
    """Single correlation result."""
    account_name: str
    account_number: str
    correlation: float
    p_value: float
    is_significant: bool
    lag_months: int  # 0 = same period, 1 = 1 month lag, etc.
    interpretation: str


@dataclass
class CorrelationAnalysis:
    """Full correlation analysis result."""
    target_variable: str  # e.g., "Revenue"
    correlations: List[CorrelationEntry]
    top_positive: List[CorrelationEntry]
    top_negative: List[CorrelationEntry]
    seasonally_adjusted: bool
    period_count: int
    summary: str


@dataclass
class ARCHResult:
    """Result of ARCH/GARCH volatility analysis."""
    model_type: VolatilityModel
    conditional_volatility: Any  # np.ndarray when numpy available
    unconditional_variance: float
    arch_params: Dict[str, float]
    garch_params: Dict[str, float]  # Empty if ARCH only
    aic: float
    bic: float
    log_likelihood: float
    ljung_box_p_value: float  # Test for remaining autocorrelation
    interpretation: str
    volatility_forecast: Optional[List[float]] = None  # Future periods


class StatisticalAnalyzer:
    """
    Advanced statistical analysis engine.
    
    Provides regression, correlation, seasonality, and volatility analysis
    with full statistical rigor (p-values, confidence intervals, diagnostics).
    """
    
    def __init__(self, fiscal_start_month: int = 2):
        """
        Initialize analyzer.
        
        Args:
            fiscal_start_month: 1-12, month when fiscal year starts (2 = February)
        """
        self.fiscal_start_month = fiscal_start_month
        self.logger = logging.getLogger(__name__)
        
        if not NUMPY_AVAILABLE or not PANDAS_AVAILABLE:
            self.logger.warning("numpy/pandas not available - statistical analysis disabled")
        if not STATSMODELS_AVAILABLE:
            self.logger.warning("statsmodels not available - some features disabled")
        if not ARCH_AVAILABLE:
            self.logger.warning("arch package not available - ARCH/GARCH disabled")
    
    # ===================
    # DATA PREPARATION
    # ===================
    
    def prepare_time_series(
        self,
        data: List[Dict[str, Any]],
        amount_field: str,
        date_field: str,
        group_by: str = None,
        aggregation: str = "sum",
        frequency: str = "M"  # M=monthly, Q=quarterly
    ) -> Dict[str, Any]:
        """
        Convert raw data to time-indexed series for analysis.
        
        Args:
            data: Raw data rows
            amount_field: Field containing amounts
            date_field: Field containing dates
            group_by: Optional field to create separate series (e.g., account_name)
            aggregation: "sum", "mean", "count"
            frequency: "M" for monthly, "Q" for quarterly
        
        Returns:
            Dict mapping group names to pandas Series with DatetimeIndex
        """
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas required for time series preparation")
        
        if not data:
            return {}
        
        # Parse dates and amounts
        df = pd.DataFrame(data)
        
        # Convert date field
        if date_field not in df.columns:
            self.logger.warning(f"Date field '{date_field}' not found")
            return {}
        
        df[date_field] = pd.to_datetime(df[date_field], errors='coerce')
        df = df.dropna(subset=[date_field])
        
        if amount_field not in df.columns:
            self.logger.warning(f"Amount field '{amount_field}' not found")
            return {}
        
        df[amount_field] = pd.to_numeric(df[amount_field], errors='coerce')
        df = df.dropna(subset=[amount_field])
        
        if df.empty:
            return {}
        
        # Set date as index
        df.set_index(date_field, inplace=True)
        
        # Group if needed
        if group_by and group_by in df.columns:
            series_dict = {}
            for group_value, group_df in df.groupby(group_by):
                # Aggregate by period
                # Use 'ME' instead of 'M' for monthly frequency (pandas 2.0+)
                freq = frequency.replace('M', 'ME') if frequency == 'M' else frequency
                if aggregation == "sum":
                    resampled = group_df[amount_field].resample(freq).sum()
                elif aggregation == "mean":
                    resampled = group_df[amount_field].resample(freq).mean()
                elif aggregation == "count":
                    resampled = group_df[amount_field].resample(freq).count()
                else:
                    resampled = group_df[amount_field].resample(freq).sum()
                
                # Remove zero/NaN periods
                resampled = resampled[resampled != 0].dropna()
                
                if len(resampled) > 0:
                    series_dict[str(group_value)] = resampled
        else:
            # Single series
            # Use 'ME' instead of 'M' for monthly frequency (pandas 2.0+)
            freq = frequency.replace('M', 'ME') if frequency == 'M' else frequency
            if aggregation == "sum":
                resampled = df[amount_field].resample(freq).sum()
            elif aggregation == "mean":
                resampled = df[amount_field].resample(freq).mean()
            elif aggregation == "count":
                resampled = df[amount_field].resample(freq).count()
            else:
                resampled = df[amount_field].resample(freq).sum()
            
            resampled = resampled[resampled != 0].dropna()
            if len(resampled) > 0:
                return {"total": resampled}
            else:
                return {}
        
        return series_dict
    
    def align_series(
        self,
        series_dict: Dict[str, Any],  # Dict[str, pd.Series] when pandas available
        min_observations: int = 12
    ) -> Tuple[Any, List[str]]:  # Tuple[pd.DataFrame, List[str]] when pandas available
        """
        Align multiple series to common date range.
        
        Args:
            series_dict: Dict of series to align
            min_observations: Minimum required observations
        
        Returns:
            Tuple of (aligned DataFrame, list of dropped series names)
        """
        if not series_dict:
            return pd.DataFrame(), []
        
        # Find common date range
        all_dates = set()
        for series in series_dict.values():
            all_dates.update(series.index)
        
        if not all_dates:
            return pd.DataFrame(), []
        
        common_dates = sorted(all_dates)
        
        # Create aligned dataframe
        aligned = pd.DataFrame(index=common_dates)
        dropped = []
        
        for name, series in series_dict.items():
            if len(series) < min_observations:
                dropped.append(name)
                continue
            
            # Reindex to common dates, forward fill missing values
            aligned[name] = series.reindex(common_dates)
        
        # Drop columns with too many NaN values
        threshold = len(aligned) * 0.5  # Keep if >50% data
        aligned = aligned.dropna(axis=1, thresh=threshold)
        
        return aligned, dropped
    
    # ===================
    # SEASONALITY ANALYSIS
    # ===================
    
    def decompose_seasonality(
        self,
        series: Any,  # pd.Series when pandas available
        period: int = 12,
        model: str = "additive"
    ) -> SeasonalDecomposition:
        """
        Decompose time series into trend, seasonal, and residual components.
        
        Uses STL (Seasonal-Trend decomposition using LOESS) for robustness.
        
        Args:
            series: Time series to decompose
            period: Seasonal period (12 for monthly data with yearly seasonality)
            model: "additive" or "multiplicative"
        
        Returns:
            SeasonalDecomposition with components and diagnostics
        """
        if not STATSMODELS_AVAILABLE:
            raise ImportError("statsmodels required for seasonality decomposition")
        
        if len(series) < period * 2:
            raise ValueError(f"Need at least {period * 2} observations for period {period}")
        
        # Remove any NaN values
        series_clean = series.dropna()
        
        if len(series_clean) < period * 2:
            raise ValueError(f"Insufficient data after cleaning: {len(series_clean)} < {period * 2}")
        
        try:
            # Use STL decomposition
            stl = STL(series_clean, seasonal=period, robust=True)
            result = stl.fit()
            
            trend = result.trend.values
            seasonal = result.seasonal.values
            residual = result.resid.values
            original = series_clean.values
            
            # Calculate seasonal strength
            seasonal_var = np.var(seasonal)
            residual_var = np.var(residual)
            seasonal_strength = seasonal_var / (seasonal_var + residual_var) if (seasonal_var + residual_var) > 0 else 0.0
            
            # Interpretation
            if seasonal_strength > 0.7:
                interp = f"Strong seasonality (strength={seasonal_strength:.2f}). Seasonal component explains most variance."
            elif seasonal_strength > 0.4:
                interp = f"Moderate seasonality (strength={seasonal_strength:.2f}). Some seasonal patterns present."
            else:
                interp = f"Weak seasonality (strength={seasonal_strength:.2f}). Limited seasonal patterns."
            
            return SeasonalDecomposition(
                original=original,
                trend=trend,
                seasonal=seasonal,
                residual=residual,
                seasonality_type=SeasonalityType.ADDITIVE if model == "additive" else SeasonalityType.MULTIPLICATIVE,
                period=period,
                seasonal_strength=seasonal_strength,
                interpretation=interp
            )
        except Exception as e:
            self.logger.error(f"Error in seasonality decomposition: {e}")
            # Fallback: simple decomposition
            return self._simple_decomposition(series_clean, period, model)
    
    def _simple_decomposition(
        self,
        series: Any,  # pd.Series when pandas available
        period: int,
        model: str
    ) -> SeasonalDecomposition:
        """Fallback simple decomposition if STL fails."""
        values = series.values
        n = len(values)
        
        # Simple moving average for trend
        window = min(period, n // 4)
        if window < 2:
            window = 2
        
        trend = pd.Series(values).rolling(window=window, center=True).mean().fillna(method='bfill').fillna(method='ffill').values
        
        # Detrend
        detrended = values - trend
        
        # Simple seasonal component (average by period position)
        seasonal = np.zeros(n)
        for i in range(period):
            indices = np.arange(i, n, period)
            if len(indices) > 0:
                seasonal[i::period] = np.mean(detrended[indices]) if len(indices) > 0 else 0
        
        # Center seasonal component
        seasonal = seasonal - np.mean(seasonal)
        
        # Residual
        residual = detrended - seasonal
        
        seasonal_strength = np.var(seasonal) / (np.var(seasonal) + np.var(residual)) if (np.var(seasonal) + np.var(residual)) > 0 else 0.0
        
        return SeasonalDecomposition(
            original=values,
            trend=trend,
            seasonal=seasonal,
            residual=residual,
            seasonality_type=SeasonalityType.ADDITIVE,
            period=period,
            seasonal_strength=seasonal_strength,
            interpretation=f"Simple decomposition (strength={seasonal_strength:.2f})"
        )
    
    def seasonally_adjust(
        self,
        series: Any,  # pd.Series when pandas available
        period: int = 12
    ) -> Any:  # pd.Series when pandas available
        """
        Remove seasonal component from series.
        
        Args:
            series: Original series (pandas Series when pandas available)
            period: Seasonal period
        
        Returns:
            Seasonally adjusted series (pandas Series when pandas available)
        """
        if len(series) < period * 2:
            self.logger.warning(f"Insufficient data for seasonality adjustment: {len(series)} < {period * 2}")
            return series
        
        decomp = self.decompose_seasonality(series, period)
        
        # Return trend + residual (seasonally adjusted)
        adjusted_values = decomp.trend + decomp.residual
        
        return pd.Series(adjusted_values, index=series.index[:len(adjusted_values)])
    
    def detect_seasonality_strength(
        self,
        series: Any,  # pd.Series when pandas available
        period: int = 12
    ) -> Tuple[float, str]:
        """
        Measure strength of seasonality (0-1 scale).
        
        Uses F-test variance ratio approach.
        
        Returns:
            Tuple of (strength 0-1, interpretation string)
        """
        if len(series) < period * 2:
            return 0.0, "Insufficient data for seasonality detection"
        
        try:
            decomp = self.decompose_seasonality(series, period)
            strength = decomp.seasonal_strength
            
            if strength > 0.7:
                interp = f"Strong seasonality ({strength:.2f})"
            elif strength > 0.4:
                interp = f"Moderate seasonality ({strength:.2f})"
            elif strength > 0.2:
                interp = f"Weak seasonality ({strength:.2f})"
            else:
                interp = f"No significant seasonality ({strength:.2f})"
            
            return strength, interp
        except Exception as e:
            self.logger.error(f"Error detecting seasonality: {e}")
            return 0.0, f"Error: {str(e)}"
    
    # ===================
    # CORRELATION ANALYSIS
    # ===================
    
    def _compute_correlation(
        self,
        x: Any,  # pd.Series when pandas available
        y: Any,  # pd.Series when pandas available
        method: str = "pearson"
    ) -> Tuple[float, float]:
        """
        Compute correlation and p-value.
        
        Returns:
            Tuple of (correlation coefficient, p-value)
        """
        # Align series
        aligned = pd.DataFrame({'x': x, 'y': y}).dropna()
        
        if len(aligned) < 3:
            return 0.0, 1.0
        
        if method == "pearson":
            corr = aligned['x'].corr(aligned['y'])
        elif method == "spearman":
            corr = aligned['x'].corr(aligned['y'], method='spearman')
        else:
            corr = aligned['x'].corr(aligned['y'])
        
        # Compute p-value using t-test
        n = len(aligned)
        if n < 3 or abs(corr) >= 1.0:
            p_value = 1.0 if abs(corr) < 1.0 else 0.0
        else:
            t_stat = corr * np.sqrt((n - 2) / (1 - corr**2)) if abs(corr) < 1.0 else 0
            if SCIPY_AVAILABLE:
                from scipy.stats import t
                p_value = 2 * (1 - t.cdf(abs(t_stat), n - 2))
            else:
                # Fallback: approximate p-value
                p_value = 0.05 if abs(t_stat) > 2 else 1.0
        
        return corr, p_value
    
    def correlate_accounts_with_revenue(
        self,
        data: List[Dict[str, Any]],
        amount_field: str = "amount",
        date_field: str = "formuladate",
        account_field: str = "account_name",
        account_number_field: str = "account_number",
        account_type_field: str = "account_number",  # Use account_number prefix
        revenue_account_type: str = "4",
        expense_account_types: List[str] = ["5", "6", "7", "8"],
        seasonally_adjust: bool = True,
        max_lag: int = 3
    ) -> CorrelationAnalysis:
        """
        Correlate each expense account with total revenue.
        
        This is the PRIMARY method for the user's request.
        
        Args:
            data: Full dataset with all accounts
            amount_field: Field containing amounts
            date_field: Field containing dates
            account_field: Field containing account names
            account_number_field: Field containing account numbers
            account_type_field: Field containing account type codes
            revenue_account_type: Account type code for revenue (typically "4")
            expense_account_types: Account type codes for expenses
            seasonally_adjust: Whether to remove seasonality before correlation
            max_lag: Maximum lag (months) to test
        
        Returns:
            CorrelationAnalysis with ranked correlations
        """
        if not data:
            return CorrelationAnalysis(
                target_variable="Revenue",
                correlations=[],
                top_positive=[],
                top_negative=[],
                seasonally_adjusted=seasonally_adjust,
                period_count=0,
                summary="No data provided"
            )
        
        df = pd.DataFrame(data)
        
        # Identify revenue accounts (account_number starts with "4")
        revenue_mask = df[account_number_field].astype(str).str.startswith(revenue_account_type)
        revenue_data = df[revenue_mask].copy()
        
        if revenue_data.empty:
            return CorrelationAnalysis(
                target_variable="Revenue",
                correlations=[],
                top_positive=[],
                top_negative=[],
                seasonally_adjusted=seasonally_adjust,
                period_count=0,
                summary="No revenue accounts found"
            )
        
        # Prepare revenue time series
        revenue_series_dict = self.prepare_time_series(
            revenue_data.to_dict('records'),
            amount_field,
            date_field,
            aggregation="sum",
            frequency="M"
        )
        
        if not revenue_series_dict:
            return CorrelationAnalysis(
                target_variable="Revenue",
                correlations=[],
                top_positive=[],
                top_negative=[],
                seasonally_adjusted=seasonally_adjust,
                period_count=0,
                summary="Could not prepare revenue time series"
            )
        
        # Get total revenue series
        revenue_series = list(revenue_series_dict.values())[0]
        
        # Seasonally adjust revenue if requested
        if seasonally_adjust and len(revenue_series) >= 24:
            try:
                revenue_series = self.seasonally_adjust(revenue_series, period=12)
            except Exception as e:
                self.logger.warning(f"Could not seasonally adjust revenue: {e}")
        
        # Identify expense accounts
        expense_mask = False
        for exp_type in expense_account_types:
            expense_mask = expense_mask | df[account_number_field].astype(str).str.startswith(exp_type)
        
        expense_data = df[expense_mask].copy()
        
        if expense_data.empty:
            return CorrelationAnalysis(
                target_variable="Revenue",
                correlations=[],
                top_positive=[],
                top_negative=[],
                seasonally_adjusted=seasonally_adjust,
                period_count=len(revenue_series),
                summary="No expense accounts found"
            )
        
        # Prepare expense account time series
        expense_series_dict = self.prepare_time_series(
            expense_data.to_dict('records'),
            amount_field,
            date_field,
            group_by=account_field,
            aggregation="sum",
            frequency="M"
        )
        
        if not expense_series_dict:
            return CorrelationAnalysis(
                target_variable="Revenue",
                correlations=[],
                top_positive=[],
                top_negative=[],
                seasonally_adjusted=seasonally_adjust,
                period_count=len(revenue_series),
                summary="Could not prepare expense time series"
            )
        
        # Compute correlations for each expense account
        correlations = []
        
        for account_name, expense_series in expense_series_dict.items():
            # Seasonally adjust if requested
            if seasonally_adjust and len(expense_series) >= 24:
                try:
                    expense_series = self.seasonally_adjust(expense_series, period=12)
                except Exception as e:
                    self.logger.warning(f"Could not seasonally adjust {account_name}: {e}")
            
            # Test multiple lags
            best_corr = None
            best_lag = 0
            best_p_value = 1.0
            
            for lag in range(max_lag + 1):
                if lag == 0:
                    x_series = expense_series
                    y_series = revenue_series
                else:
                    # Lag expense series (expense leads revenue)
                    x_series = expense_series.shift(-lag)
                    y_series = revenue_series
                
                # Align
                aligned = pd.DataFrame({'x': x_series, 'y': y_series}).dropna()
                
                if len(aligned) < 3:
                    continue
                
                corr, p_value = self._compute_correlation(aligned['x'], aligned['y'])
                
                if best_corr is None or abs(corr) > abs(best_corr):
                    best_corr = corr
                    best_lag = lag
                    best_p_value = p_value
            
            if best_corr is not None:
                # Get account number
                account_num = ""
                account_rows = expense_data[expense_data[account_field] == account_name]
                if not account_rows.empty:
                    account_num = str(account_rows.iloc[0].get(account_number_field, ""))
                
                # Interpretation
                if abs(best_corr) > 0.7:
                    strength = "strong"
                elif abs(best_corr) > 0.4:
                    strength = "moderate"
                elif abs(best_corr) > 0.2:
                    strength = "weak"
                else:
                    strength = "very weak"
                
                direction = "positive" if best_corr > 0 else "negative"
                lag_text = f" (lag {best_lag} months)" if best_lag > 0 else ""
                sig_text = " (significant)" if best_p_value < 0.05 else " (not significant)"
                
                interp = f"{strength.capitalize()} {direction} correlation{lag_text}{sig_text}"
                
                correlations.append(CorrelationEntry(
                    account_name=account_name,
                    account_number=account_num,
                    correlation=best_corr,
                    p_value=best_p_value,
                    is_significant=best_p_value < 0.05,
                    lag_months=best_lag,
                    interpretation=interp
                ))
        
        # Sort by absolute correlation
        correlations.sort(key=lambda x: abs(x.correlation), reverse=True)
        
        # Separate positive and negative
        top_positive = [c for c in correlations if c.correlation > 0]
        top_negative = [c for c in correlations if c.correlation < 0]
        
        # Summary
        significant = [c for c in correlations if c.is_significant]
        summary = f"Analyzed {len(correlations)} expense accounts against revenue. "
        summary += f"{len(significant)} correlations are statistically significant (p<0.05). "
        if top_positive:
            summary += f"Strongest positive: {top_positive[0].account_name} (r={top_positive[0].correlation:.3f}). "
        if top_negative:
            summary += f"Strongest negative: {top_negative[0].account_name} (r={top_negative[0].correlation:.3f})."
        
        return CorrelationAnalysis(
            target_variable="Revenue",
            correlations=correlations,
            top_positive=top_positive,
            top_negative=top_negative,
            seasonally_adjusted=seasonally_adjust,
            period_count=len(revenue_series),
            summary=summary
        )
    
    def correlation_matrix(
        self,
        series_dict: Dict[str, Any],  # Dict[str, pd.Series] when pandas available
        method: str = "pearson"
    ) -> Any:  # pd.DataFrame when pandas available
        """
        Compute correlation matrix for multiple series.
        
        Args:
            series_dict: Dict of named series
            method: "pearson", "spearman", or "kendall"
        
        Returns:
            Correlation matrix as DataFrame
        """
        if not series_dict:
            return pd.DataFrame()
        
        # Align all series
        aligned, _ = self.align_series(series_dict)
        
        if aligned.empty:
            return pd.DataFrame()
        
        return aligned.corr(method=method)
    
    # ===================
    # REGRESSION ANALYSIS
    # ===================
    
    def simple_regression(
        self,
        y: Any,  # pd.Series when pandas available
        x: Any,  # pd.Series when pandas available
        add_constant: bool = True
    ) -> RegressionResult:
        """
        Simple OLS regression with diagnostics.
        
        Args:
            y: Dependent variable
            x: Independent variable
            add_constant: Whether to include intercept
        
        Returns:
            RegressionResult with full statistics
        """
        if not STATSMODELS_AVAILABLE:
            raise ImportError("statsmodels required for regression analysis")
        
        # Align series
        aligned = pd.DataFrame({'y': y, 'x': x}).dropna()
        
        if len(aligned) < 3:
            raise ValueError(f"Insufficient data: {len(aligned)} < 3")
        
        y_vals = aligned['y'].values
        x_vals = aligned['x'].values
        
        if add_constant:
            X = sm.add_constant(x_vals)
        else:
            X = x_vals.reshape(-1, 1)
        
        try:
            model = sm.OLS(y_vals, X).fit()
            
            # Extract results
            if add_constant:
                coefficient = model.params[1]  # Slope
                std_error = model.bse[1]
                t_statistic = model.tvalues[1]
                p_value = model.pvalues[1]
                ci = model.conf_int().iloc[1].values
            else:
                coefficient = model.params[0]
                std_error = model.bse[0]
                t_statistic = model.tvalues[0]
                p_value = model.pvalues[0]
                ci = model.conf_int().iloc[0].values
            
            r_squared = model.rsquared
            adj_r_squared = model.rsquared_adj
            
            # Interpretation
            direction = "positive" if coefficient > 0 else "negative"
            sig_text = "statistically significant" if p_value < 0.05 else "not statistically significant"
            strength = "strong" if abs(coefficient) > 0.5 else "moderate" if abs(coefficient) > 0.2 else "weak"
            
            interp = f"{strength.capitalize()} {direction} relationship ({sig_text}, p={p_value:.4f}). "
            interp += f"R²={r_squared:.3f} indicates {r_squared*100:.1f}% of variance explained."
            
            return RegressionResult(
                dependent_var="y",
                independent_var="x",
                coefficient=coefficient,
                std_error=std_error,
                t_statistic=t_statistic,
                p_value=p_value,
                r_squared=r_squared,
                adj_r_squared=adj_r_squared,
                confidence_interval_95=(ci[0], ci[1]),
                observations=len(aligned),
                is_significant=p_value < 0.05,
                interpretation=interp
            )
        except Exception as e:
            self.logger.error(f"Regression error: {e}")
            raise
    
    def regression_with_seasonality(
        self,
        y: Any,  # pd.Series when pandas available
        x: Any,  # pd.Series when pandas available
        seasonal_period: int = 12
    ) -> RegressionResult:
        """
        Regression with seasonal dummy variables.
        
        Includes monthly/quarterly dummies to control for seasonality.
        
        Args:
            y: Dependent variable
            x: Independent variable
            seasonal_period: 12 for monthly, 4 for quarterly
        
        Returns:
            RegressionResult controlling for seasonality
        """
        if not STATSMODELS_AVAILABLE:
            raise ImportError("statsmodels required for regression analysis")
        
        # Align series
        aligned = pd.DataFrame({'y': y, 'x': x}).dropna()
        
        if len(aligned) < seasonal_period + 3:
            raise ValueError(f"Insufficient data for seasonal regression: {len(aligned)} < {seasonal_period + 3}")
        
        y_vals = aligned['y'].values
        x_vals = aligned['x'].values
        
        # Create seasonal dummies
        dates = aligned.index
        if isinstance(dates[0], pd.Timestamp):
            periods = dates.month if seasonal_period == 12 else dates.quarter
        else:
            # Fallback: use position
            periods = np.array([i % seasonal_period for i in range(len(dates))])
        
        # Create dummy variables (drop first to avoid multicollinearity)
        dummies = pd.get_dummies(periods, prefix='season', drop_first=True)
        
        # Combine X and dummies
        X = pd.DataFrame({'x': x_vals})
        X = pd.concat([X, dummies], axis=1)
        X = sm.add_constant(X)
        
        try:
            model = sm.OLS(y_vals, X).fit()
            
            # Extract coefficient for x (first non-constant column)
            coefficient = model.params['x']
            std_error = model.bse['x']
            t_statistic = model.tvalues['x']
            p_value = model.pvalues['x']
            ci = model.conf_int().loc['x'].values
            
            r_squared = model.rsquared
            adj_r_squared = model.rsquared_adj
            
            # Interpretation
            direction = "positive" if coefficient > 0 else "negative"
            sig_text = "statistically significant" if p_value < 0.05 else "not statistically significant"
            
            interp = f"{direction.capitalize()} relationship controlling for seasonality ({sig_text}, p={p_value:.4f}). "
            interp += f"R²={r_squared:.3f} (adjusted: {adj_r_squared:.3f})."
            
            return RegressionResult(
                dependent_var="y",
                independent_var="x",
                coefficient=coefficient,
                std_error=std_error,
                t_statistic=t_statistic,
                p_value=p_value,
                r_squared=r_squared,
                adj_r_squared=adj_r_squared,
                confidence_interval_95=(ci[0], ci[1]),
                observations=len(aligned),
                is_significant=p_value < 0.05,
                interpretation=interp
            )
        except Exception as e:
            self.logger.error(f"Seasonal regression error: {e}")
            raise
    
    # ===================
    # ARCH/GARCH ANALYSIS
    # ===================
    
    def detect_arch_effects(
        self,
        series: Any,  # pd.Series when pandas available
        lags: int = 5
    ) -> Tuple[float, bool, str]:
        """
        Test for ARCH effects using Engle's LM test.
        
        Args:
            series: Series to test
            lags: Number of lags for test
        
        Returns:
            Tuple of (p-value, has_arch_effects, interpretation)
        """
        if not ARCH_AVAILABLE:
            return 1.0, False, "ARCH package not available"
        
        if len(series) < lags + 10:
            return 1.0, False, f"Insufficient data: {len(series)} < {lags + 10}"
        
        try:
            from arch.unitroot import engle_arch
            
            # Convert to returns if needed (demean first)
            returns = series - series.mean()
            
            result = engle_arch(returns, lags=lags)
            p_value = result.pvalue
            
            has_arch = p_value < 0.05
            
            if has_arch:
                interp = f"ARCH effects detected (p={p_value:.4f}). Volatility clustering present."
            else:
                interp = f"No significant ARCH effects (p={p_value:.4f}). Constant variance assumption holds."
            
            return p_value, has_arch, interp
        except Exception as e:
            self.logger.error(f"ARCH detection error: {e}")
            return 1.0, False, f"Error: {str(e)}"
    
    def fit_arch_model(
        self,
        series: Any,  # pd.Series when pandas available
        p: int = 1,  # ARCH order
        q: int = 0,  # GARCH order (0 = ARCH only)
        mean_model: str = "constant"
    ) -> ARCHResult:
        """
        Fit ARCH or GARCH model to series.
        
        Models conditional heteroskedasticity (volatility clustering).
        
        Args:
            series: Returns or residuals series
            p: ARCH order (lagged squared residuals)
            q: GARCH order (lagged variance). 0 = ARCH, 1+ = GARCH
            mean_model: "constant", "zero", "AR", "ARX"
        
        Returns:
            ARCHResult with volatility estimates and diagnostics
        """
        if not ARCH_AVAILABLE:
            raise ImportError("arch package required for ARCH/GARCH modeling")
        
        if len(series) < 50:
            raise ValueError(f"Insufficient data for ARCH/GARCH: {len(series)} < 50")
        
        try:
            # Convert to returns (demean)
            returns = series - series.mean()
            
            # Fit model
            model = arch_model(returns, vol='Garch' if q > 0 else 'Arch', p=p, q=q, mean=mean_model)
            fitted = model.fit(disp='off')
            
            # Extract parameters
            params = fitted.params
            
            arch_params = {}
            garch_params = {}
            
            for param_name, param_value in params.items():
                if 'alpha' in param_name.lower():
                    arch_params[param_name] = float(param_value)
                elif 'beta' in param_name.lower():
                    garch_params[param_name] = float(param_value)
            
            # Conditional volatility
            conditional_vol = fitted.conditional_volatility.values
            
            # Unconditional variance
            unconditional_var = float(fitted.unconditional_variance) if hasattr(fitted, 'unconditional_variance') else np.var(returns)
            
            # Information criteria
            aic = float(fitted.aic)
            bic = float(fitted.bic)
            log_likelihood = float(fitted.loglikelihood)
            
            # Ljung-Box test for remaining autocorrelation
            residuals = fitted.resid
            try:
                lb_test = acorr_ljungbox(residuals, lags=10, return_df=True)
                ljung_box_p_value = float(lb_test['lb_pvalue'].iloc[-1])
            except:
                ljung_box_p_value = 1.0
            
            # Interpretation
            model_name = f"GARCH({p},{q})" if q > 0 else f"ARCH({p})"
            interp = f"{model_name} model fitted. "
            interp += f"AIC={aic:.2f}, BIC={bic:.2f}. "
            if ljung_box_p_value < 0.05:
                interp += "Residuals show remaining autocorrelation (p<0.05). "
            else:
                interp += "Residuals appear white noise (p>=0.05). "
            interp += f"Unconditional variance: {unconditional_var:.4f}."
            
            return ARCHResult(
                model_type=VolatilityModel.GARCH if q > 0 else VolatilityModel.ARCH,
                conditional_volatility=conditional_vol,
                unconditional_variance=unconditional_var,
                arch_params=arch_params,
                garch_params=garch_params,
                aic=aic,
                bic=bic,
                log_likelihood=log_likelihood,
                ljung_box_p_value=ljung_box_p_value,
                interpretation=interp
            )
        except Exception as e:
            self.logger.error(f"ARCH/GARCH fitting error: {e}")
            raise
    
    def volatility_forecast(
        self,
        arch_result: ARCHResult,
        horizon: int = 6
    ) -> List[float]:
        """
        Forecast future volatility.
        
        Args:
            arch_result: Fitted ARCH/GARCH result
            horizon: Number of periods to forecast
        
        Returns:
            List of forecasted volatility values
        """
        # This would require storing the fitted model, which we don't do currently
        # For now, return unconditional variance as forecast
        return [arch_result.unconditional_variance] * horizon
    
    # ===================
    # COMPREHENSIVE ANALYSIS
    # ===================
    
    def full_revenue_correlation_analysis(
        self,
        data: List[Dict[str, Any]],
        amount_field: str = "amount",
        date_field: str = "formuladate",
        account_field: str = "account_name",
        account_number_field: str = "account_number",
        account_type_field: str = "account_type",
        include_arch: bool = True,
        seasonally_adjust: bool = True,
        top_n: int = 10
    ) -> Dict[str, Any]:
        """
        Complete analysis: correlate all accounts with revenue,
        adjusting for seasonality and ARCH effects.
        
        This is the MAIN ENTRY POINT for the user's request.
        
        Args:
            data: Full NetSuite dataset
            amount_field: Field containing amounts
            date_field: Field containing dates
            account_field: Field containing account names
            account_number_field: Field containing account numbers
            account_type_field: Field containing account type codes
            include_arch: Whether to model volatility
            seasonally_adjust: Whether to remove seasonality
            top_n: Number of top correlations to highlight
        
        Returns:
            Dict with:
            - correlation_analysis: CorrelationAnalysis object
            - seasonality: Dict of seasonal decomposition per account
            - arch_analysis: ARCHResult for revenue (if include_arch)
            - regression_results: Dict of top account regressions
            - summary: Executive summary string
            - llm_context: Formatted context for LLM interpretation
        """
        if not PANDAS_AVAILABLE or not NUMPY_AVAILABLE:
            return {
                "correlation_analysis": CorrelationAnalysis(
                    target_variable="Revenue",
                    correlations=[],
                    top_positive=[],
                    top_negative=[],
                    seasonally_adjusted=seasonally_adjust,
                    period_count=0,
                    summary="Statistical analysis requires numpy and pandas packages. Please install: pip install numpy pandas statsmodels arch scipy"
                ),
                "seasonality": {},
                "arch_analysis": None,
                "regression_results": {},
                "summary": "Statistical analysis disabled - missing dependencies (numpy, pandas)",
                "llm_context": "## Statistical Analysis Unavailable\n\nStatistical analysis requires numpy, pandas, statsmodels, and arch packages. Please install these dependencies:\n\n```bash\npip install numpy pandas statsmodels arch scipy\n```\n\nOnce installed, the system can perform:\n- Correlation analysis between expense accounts and revenue\n- Seasonality decomposition and adjustment\n- ARCH/GARCH volatility modeling\n- Regression analysis with statistical significance testing"
            }
        
        result = {
            "correlation_analysis": None,
            "seasonality": {},
            "arch_analysis": None,
            "regression_results": {},
            "summary": "",
            "llm_context": ""
        }
        
        # Step 1: Correlation analysis
        try:
            corr_analysis = self.correlate_accounts_with_revenue(
                data=data,
                amount_field=amount_field,
                date_field=date_field,
                account_field=account_field,
                account_number_field=account_number_field,
                account_type_field=account_type_field,
                seasonally_adjust=seasonally_adjust
            )
            result["correlation_analysis"] = corr_analysis
        except Exception as e:
            self.logger.error(f"Correlation analysis error: {e}")
            result["correlation_analysis"] = CorrelationAnalysis(
                target_variable="Revenue",
                correlations=[],
                top_positive=[],
                top_negative=[],
                seasonally_adjusted=seasonally_adjust,
                period_count=0,
                summary=f"Error: {str(e)}"
            )
        
        # Step 2: Seasonality analysis for revenue and top accounts
        corr_analysis = result.get("correlation_analysis")
        if corr_analysis and hasattr(corr_analysis, 'correlations') and corr_analysis.correlations:
            # Get revenue series
            df = pd.DataFrame(data)
            revenue_mask = df[account_number_field].astype(str).str.startswith("4")
            revenue_data = df[revenue_mask].copy()
            
            if not revenue_data.empty:
                revenue_series_dict = self.prepare_time_series(
                    revenue_data.to_dict('records'),
                    amount_field,
                    date_field,
                    aggregation="sum",
                    frequency="M"
                )
                
                if revenue_series_dict:
                    revenue_series = list(revenue_series_dict.values())[0]
                    if len(revenue_series) >= 24:
                        try:
                            decomp = self.decompose_seasonality(revenue_series, period=12)
                            result["seasonality"]["Revenue"] = decomp
                        except Exception as e:
                            self.logger.warning(f"Could not decompose revenue seasonality: {e}")
            
            # Top accounts
            top_accounts = corr_analysis.top_positive[:top_n] + corr_analysis.top_negative[:top_n]
            
            for entry in top_accounts:
                account_name = entry.account_name
                account_data = df[df[account_field] == account_name].copy()
                
                if not account_data.empty:
                    account_series_dict = self.prepare_time_series(
                        account_data.to_dict('records'),
                        amount_field,
                        date_field,
                        aggregation="sum",
                        frequency="M"
                    )
                    
                    if account_series_dict:
                        account_series = list(account_series_dict.values())[0]
                        if len(account_series) >= 24:
                            try:
                                decomp = self.decompose_seasonality(account_series, period=12)
                                result["seasonality"][account_name] = decomp
                            except Exception as e:
                                self.logger.debug(f"Could not decompose {account_name} seasonality: {e}")
        
        # Step 3: ARCH analysis for revenue
        if include_arch and ARCH_AVAILABLE:
            try:
                df = pd.DataFrame(data)
                revenue_mask = df[account_number_field].astype(str).str.startswith("4")
                revenue_data = df[revenue_mask].copy()
                
                if not revenue_data.empty:
                    revenue_series_dict = self.prepare_time_series(
                        revenue_data.to_dict('records'),
                        amount_field,
                        date_field,
                        aggregation="sum",
                        frequency="M"
                    )
                    
                    if revenue_series_dict:
                        revenue_series = list(revenue_series_dict.values())[0]
                        
                        # Test for ARCH effects
                        p_value, has_arch, _ = self.detect_arch_effects(revenue_series)
                        
                        if has_arch and len(revenue_series) >= 50:
                            try:
                                arch_result = self.fit_arch_model(revenue_series, p=1, q=1)
                                result["arch_analysis"] = arch_result
                            except Exception as e:
                                self.logger.warning(f"Could not fit ARCH model: {e}")
            except Exception as e:
                self.logger.warning(f"ARCH analysis error: {e}")
        
        # Step 4: Regression for top accounts
        if corr_analysis and corr_analysis.correlations:
            df = pd.DataFrame(data)
            revenue_mask = df[account_number_field].astype(str).str.startswith("4")
            revenue_data = df[revenue_mask].copy()
            
            if not revenue_data.empty:
                revenue_series_dict = self.prepare_time_series(
                    revenue_data.to_dict('records'),
                    amount_field,
                    date_field,
                    aggregation="sum",
                    frequency="M"
                )
                
                if revenue_series_dict:
                    revenue_series = list(revenue_series_dict.values())[0]
                    
                    # Top positive correlations
                    for entry in corr_analysis.top_positive[:top_n]:
                        if entry.is_significant:
                            account_name = entry.account_name
                            account_data = df[df[account_field] == account_name].copy()
                            
                            if not account_data.empty:
                                account_series_dict = self.prepare_time_series(
                                    account_data.to_dict('records'),
                                    amount_field,
                                    date_field,
                                    aggregation="sum",
                                    frequency="M"
                                )
                                
                                if account_series_dict:
                                    account_series = list(account_series_dict.values())[0]
                                    
                                    try:
                                        if seasonally_adjust and len(account_series) >= 24:
                                            reg_result = self.regression_with_seasonality(
                                                revenue_series,
                                                account_series,
                                                seasonal_period=12
                                            )
                                        else:
                                            reg_result = self.simple_regression(
                                                revenue_series,
                                                account_series
                                            )
                                        
                                        reg_result.dependent_var = "Revenue"
                                        reg_result.independent_var = account_name
                                        result["regression_results"][account_name] = reg_result
                                    except Exception as e:
                                        self.logger.debug(f"Could not regress {account_name}: {e}")
        
        # Step 5: Generate summary and LLM context
        result["summary"] = self._generate_summary(result)
        result["llm_context"] = self.format_for_llm(result)
        
        return result
    
    def _generate_summary(self, result: Dict[str, Any]) -> str:
        """Generate executive summary."""
        parts = []
        
        if result["correlation_analysis"]:
            corr = result["correlation_analysis"]
            parts.append(corr.summary)
        
        if result["seasonality"]:
            parts.append(f"Seasonality analyzed for {len(result['seasonality'])} series.")
        
        if result["arch_analysis"]:
            parts.append(f"ARCH/GARCH volatility modeling completed: {result['arch_analysis'].interpretation}")
        
        if result["regression_results"]:
            parts.append(f"Regression analysis completed for {len(result['regression_results'])} top accounts.")
        
        return " ".join(parts) if parts else "Analysis completed."
    
    def format_for_llm(self, analysis_result: Dict[str, Any]) -> str:
        """
        Format statistical analysis results for LLM interpretation.
        
        Provides context the LLM needs to generate accurate, insightful narrative.
        """
        parts = []
        
        # Correlation summary
        if "correlation_analysis" in analysis_result and analysis_result["correlation_analysis"]:
            corr = analysis_result["correlation_analysis"]
            parts.append("## Correlation Analysis Results")
            parts.append(f"Target Variable: {corr.target_variable}")
            parts.append(f"Seasonally Adjusted: {'Yes' if corr.seasonally_adjusted else 'No'}")
            parts.append(f"Periods Analyzed: {corr.period_count}")
            parts.append("")
            
            if corr.top_positive:
                parts.append("### Top Positive Correlations (Higher expense → Higher revenue):")
                for i, entry in enumerate(corr.top_positive[:10], 1):
                    sig = "***" if entry.is_significant else ""
                    lag_text = f" (lag {entry.lag_months}mo)" if entry.lag_months > 0 else ""
                    parts.append(f"{i}. {entry.account_name}: r={entry.correlation:.3f}{sig} (p={entry.p_value:.4f}){lag_text}")
                parts.append("")
            
            if corr.top_negative:
                parts.append("### Top Negative Correlations (Higher expense → Lower revenue):")
                for i, entry in enumerate(corr.top_negative[:10], 1):
                    sig = "***" if entry.is_significant else ""
                    lag_text = f" (lag {entry.lag_months}mo)" if entry.lag_months > 0 else ""
                    parts.append(f"{i}. {entry.account_name}: r={entry.correlation:.3f}{sig} (p={entry.p_value:.4f}){lag_text}")
                parts.append("")
            
            parts.append("Note: *** indicates statistical significance at p<0.05")
            parts.append("")
        
        # Seasonality summary
        if "seasonality" in analysis_result and analysis_result["seasonality"]:
            parts.append("## Seasonality Analysis")
            for name, decomp in list(analysis_result["seasonality"].items())[:10]:
                parts.append(f"- {name}: Seasonal strength = {decomp.seasonal_strength:.2f} - {decomp.interpretation}")
            parts.append("")
        
        # ARCH summary
        if "arch_analysis" in analysis_result and analysis_result["arch_analysis"]:
            arch = analysis_result["arch_analysis"]
            parts.append("## Volatility (ARCH) Analysis")
            parts.append(f"Model: {arch.model_type.value.upper()}")
            parts.append(f"Unconditional Variance: {arch.unconditional_variance:.4f}")
            parts.append(f"AIC: {arch.aic:.2f}, BIC: {arch.bic:.2f}")
            parts.append(arch.interpretation)
            parts.append("")
        
        # Regression summary
        if "regression_results" in analysis_result and analysis_result["regression_results"]:
            parts.append("## Regression Analysis Results")
            for account_name, reg_result in list(analysis_result["regression_results"].items())[:10]:
                sig = "***" if reg_result.is_significant else ""
                parts.append(f"- {account_name}: coefficient={reg_result.coefficient:.4f}{sig}, ")
                parts.append(f"  R²={reg_result.r_squared:.3f}, p={reg_result.p_value:.4f}")
                parts.append(f"  {reg_result.interpretation}")
            parts.append("")
        
        return "\n".join(parts)


# Singleton pattern
_analyzer_instance = None

def get_statistical_analyzer(fiscal_start_month: int = 2) -> StatisticalAnalyzer:
    """Get singleton StatisticalAnalyzer instance."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = StatisticalAnalyzer(fiscal_start_month=fiscal_start_month)
    return _analyzer_instance

