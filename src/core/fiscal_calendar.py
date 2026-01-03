"""
Fiscal Calendar Module

Provides fiscal year-aware date utilities for financial analysis.
Supports custom fiscal year start months (e.g., February for many companies).

Key Concepts:
- Fiscal Year (FY): A 12-month period named by its ENDING calendar year
- FY2026 with Feb start = Feb 1, 2025 - Jan 31, 2026
- FY2025 with Feb start = Feb 1, 2024 - Jan 31, 2025
- YTD = From fiscal year start to last COMPLETED month (not current date)
- Current Period = Current fiscal month
"""
import os
from datetime import date, datetime, timedelta
from dataclasses import dataclass
from typing import Tuple, Optional, List
from enum import Enum
import calendar

class PeriodType(Enum):
    """Types of time periods for analysis."""
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    YTD = "ytd"
    QTD = "qtd"
    MTD = "mtd"

@dataclass
class FiscalPeriod:
    """Represents a fiscal period with start and end dates."""
    start_date: date
    end_date: date
    period_name: str
    fiscal_year: int
    fiscal_quarter: Optional[int] = None
    fiscal_month: Optional[int] = None
    
    @property
    def days(self) -> int:
        """Number of days in the period."""
        return (self.end_date - self.start_date).days + 1
    
    def contains(self, d: date) -> bool:
        """Check if a date falls within this period."""
        return self.start_date <= d <= self.end_date
    
    def to_dict(self) -> dict:
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "period_name": self.period_name,
            "fiscal_year": self.fiscal_year,
            "fiscal_quarter": self.fiscal_quarter,
            "fiscal_month": self.fiscal_month,
            "days": self.days,
        }

class FiscalCalendar:
    """
    Fiscal calendar with configurable fiscal year start.
    
    Usage:
        cal = FiscalCalendar(fiscal_year_start_month=2)  # Feb start
        fy = cal.get_current_fiscal_year()
        ytd = cal.get_ytd_range()
    """
    
    def __init__(self, fiscal_year_start_month: int = None):
        """
        Initialize fiscal calendar.
        
        Args:
            fiscal_year_start_month: Month number (1-12) when fiscal year starts.
                                    Defaults to FISCAL_YEAR_START_MONTH env var or 2 (February).
        """
        if fiscal_year_start_month is None:
            fiscal_year_start_month = int(os.getenv("FISCAL_YEAR_START_MONTH", "2"))
        
        if not 1 <= fiscal_year_start_month <= 12:
            raise ValueError(f"Fiscal year start month must be 1-12, got {fiscal_year_start_month}")
        
        self.fy_start_month = fiscal_year_start_month
    
    def get_fiscal_year_for_date(self, d: date) -> int:
        """
        Determine which fiscal year a date belongs to.
        
        Fiscal year is NAMED after the ENDING calendar year.
        
        For FY starting in Feb (fiscal year ends in January of following year):
        - Jan 15, 2025 → FY2025 (ends Jan 31, 2025)
        - Feb 15, 2025 → FY2026 (ends Jan 31, 2026)
        - Dec 15, 2025 → FY2026 (ends Jan 31, 2026)
        """
        if d.month >= self.fy_start_month:
            # We're in months Feb-Dec, so FY ends next calendar year
            return d.year + 1
        else:
            # We're in Jan (or before FY start), FY ends this calendar year
            return d.year
    
    def get_fiscal_year_range(self, fiscal_year: int) -> FiscalPeriod:
        """
        Get the start and end dates for a fiscal year.
        
        Fiscal year is NAMED after the ENDING calendar year.
        
        Args:
            fiscal_year: The fiscal year number (e.g., 2026)
                        FY2026 = Feb 1, 2025 → Jan 31, 2026
        
        Returns:
            FiscalPeriod with start and end dates
        """
        # FY is named after the ending year
        # FY2026 starts Feb 2025 (one year before the ending year)
        if self.fy_start_month == 1:
            # Special case: FY starts in January = calendar year
            start = date(fiscal_year, 1, 1)
            end = date(fiscal_year, 12, 31)
        else:
            # FY starts in prior calendar year, ends in the fiscal_year
            start_year = fiscal_year - 1
            start = date(start_year, self.fy_start_month, 1)
            
            # End is last day of month before FY start in the fiscal_year
            end_month = self.fy_start_month - 1
            last_day = calendar.monthrange(fiscal_year, end_month)[1]
            end = date(fiscal_year, end_month, last_day)
        
        return FiscalPeriod(
            start_date=start,
            end_date=end,
            period_name=f"FY{fiscal_year}",
            fiscal_year=fiscal_year,
        )
    
    def get_current_fiscal_year(self) -> FiscalPeriod:
        """Get the current fiscal year period."""
        current_fy = self.get_fiscal_year_for_date(date.today())
        return self.get_fiscal_year_range(current_fy)
    
    def get_prior_fiscal_year(self) -> FiscalPeriod:
        """Get the previous fiscal year period."""
        current_fy = self.get_fiscal_year_for_date(date.today())
        return self.get_fiscal_year_range(current_fy - 1)
    
    def get_ytd_range(self, as_of: date = None) -> FiscalPeriod:
        """
        Get Year-To-Date range from fiscal year start to LAST COMPLETED MONTH.
        
        YTD always ends at the last day of the most recently completed month,
        not the current date (since current month is not yet closed).
        
        Args:
            as_of: Reference date (defaults to today). YTD ends at the last
                   completed month before or on this date.
        
        Example (if today is Dec 30, 2025):
            - Current FY = FY2026 (Feb 2025 - Jan 2026)
            - YTD = Feb 1, 2025 to Nov 30, 2025 (Dec not yet complete)
        """
        as_of = as_of or date.today()
        
        # Get last completed month end
        # First day of current month, minus 1 day = last day of prior month
        first_of_current_month = date(as_of.year, as_of.month, 1)
        last_completed_month_end = first_of_current_month - timedelta(days=1)
        
        # Get the fiscal year for the last completed month
        fy = self.get_fiscal_year_for_date(last_completed_month_end)
        fy_range = self.get_fiscal_year_range(fy)
        
        # If the last completed month is before the FY start, 
        # we need to go back to the prior FY
        if last_completed_month_end < fy_range.start_date:
            fy = fy - 1
            fy_range = self.get_fiscal_year_range(fy)
        
        return FiscalPeriod(
            start_date=fy_range.start_date,
            end_date=last_completed_month_end,
            period_name=f"FY{fy} YTD",
            fiscal_year=fy,
        )
    
    def get_fiscal_quarter(self, d: date) -> int:
        """
        Get the fiscal quarter (1-4) for a date.
        
        Quarter 1 starts at fiscal year start month.
        """
        month_in_fy = (d.month - self.fy_start_month) % 12
        return (month_in_fy // 3) + 1
    
    def get_fiscal_quarter_range(self, fiscal_year: int, quarter: int) -> FiscalPeriod:
        """
        Get the date range for a specific fiscal quarter.
        
        Args:
            fiscal_year: The fiscal year (named after ending year)
            quarter: Fiscal quarter 1-4
        
        Example: FY2026 Q1 = Feb-Apr 2025, FY2026 Q4 = Nov 2025 - Jan 2026
        """
        if not 1 <= quarter <= 4:
            raise ValueError(f"Quarter must be 1-4, got {quarter}")
        
        # Calculate start month of the quarter
        quarter_offset = (quarter - 1) * 3
        start_month = ((self.fy_start_month - 1 + quarter_offset) % 12) + 1
        
        # Determine year for start month
        # FY is named after ending year, so FY2026 starts in calendar year 2025
        fy_start_year = fiscal_year - 1 if self.fy_start_month > 1 else fiscal_year
        
        if start_month >= self.fy_start_month:
            start_year = fy_start_year
        else:
            start_year = fy_start_year + 1
        
        start = date(start_year, start_month, 1)
        
        # End is 3 months later minus 1 day
        end_month = ((start_month - 1 + 2) % 12) + 1
        end_year = start_year if end_month >= start_month else start_year + 1
        last_day = calendar.monthrange(end_year, end_month)[1]
        end = date(end_year, end_month, last_day)
        
        return FiscalPeriod(
            start_date=start,
            end_date=end,
            period_name=f"FY{fiscal_year} Q{quarter}",
            fiscal_year=fiscal_year,
            fiscal_quarter=quarter,
        )
    
    def get_current_quarter(self) -> FiscalPeriod:
        """Get the current fiscal quarter."""
        today = date.today()
        fy = self.get_fiscal_year_for_date(today)
        q = self.get_fiscal_quarter(today)
        return self.get_fiscal_quarter_range(fy, q)
    
    def get_fiscal_month_range(self, fiscal_year: int, fiscal_month: int) -> FiscalPeriod:
        """
        Get date range for a fiscal month.
        
        Args:
            fiscal_year: The fiscal year (named after ending year)
                        FY2026 = Feb 2025 - Jan 2026
            fiscal_month: Fiscal month 1-12 (1 = first month of FY, e.g., Feb for Feb-start FY)
        
        Example: FY2026 P1 = February 2025, FY2026 P12 = January 2026
        """
        if not 1 <= fiscal_month <= 12:
            raise ValueError(f"Fiscal month must be 1-12, got {fiscal_month}")
        
        # Convert fiscal month to calendar month
        calendar_month = ((self.fy_start_month - 1 + fiscal_month - 1) % 12) + 1
        
        # Determine calendar year
        # FY is named after ending year, so FY2026 starts in calendar year 2025
        fy_start_year = fiscal_year - 1 if self.fy_start_month > 1 else fiscal_year
        
        if calendar_month >= self.fy_start_month:
            calendar_year = fy_start_year
        else:
            calendar_year = fy_start_year + 1
        
        start = date(calendar_year, calendar_month, 1)
        last_day = calendar.monthrange(calendar_year, calendar_month)[1]
        end = date(calendar_year, calendar_month, last_day)
        
        return FiscalPeriod(
            start_date=start,
            end_date=end,
            period_name=f"FY{fiscal_year} P{fiscal_month}",
            fiscal_year=fiscal_year,
            fiscal_month=fiscal_month,
        )
    
    def get_current_month(self) -> FiscalPeriod:
        """Get the current calendar month as a period."""
        today = date.today()
        start = date(today.year, today.month, 1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        end = date(today.year, today.month, last_day)
        
        return FiscalPeriod(
            start_date=start,
            end_date=end,
            period_name=today.strftime("%B %Y"),
            fiscal_year=self.get_fiscal_year_for_date(today),
        )
    
    def get_prior_month(self) -> FiscalPeriod:
        """Get the previous calendar month as a period."""
        today = date.today()
        first_of_this_month = date(today.year, today.month, 1)
        last_of_prior = first_of_this_month - timedelta(days=1)
        start = date(last_of_prior.year, last_of_prior.month, 1)
        
        return FiscalPeriod(
            start_date=start,
            end_date=last_of_prior,
            period_name=start.strftime("%B %Y"),
            fiscal_year=self.get_fiscal_year_for_date(start),
        )
    
    def get_same_period_prior_year(self, period: FiscalPeriod) -> FiscalPeriod:
        """Get the same period from the prior year for comparison."""
        prior_start = date(period.start_date.year - 1, period.start_date.month, period.start_date.day)
        prior_end = date(period.end_date.year - 1, period.end_date.month, 
                        min(period.end_date.day, calendar.monthrange(period.end_date.year - 1, period.end_date.month)[1]))
        
        return FiscalPeriod(
            start_date=prior_start,
            end_date=prior_end,
            period_name=f"{period.period_name} (Prior Year)",
            fiscal_year=period.fiscal_year - 1,
            fiscal_quarter=period.fiscal_quarter,
            fiscal_month=period.fiscal_month,
        )
    
    def get_trailing_months(self, n: int, as_of: date = None) -> FiscalPeriod:
        """
        Get a trailing N months period ending on the specified date.
        
        Args:
            n: Number of trailing months (e.g., 12 for TTM)
            as_of: End date for the period (defaults to end of last complete month)
        
        Returns:
            FiscalPeriod covering the trailing N months
        """
        if as_of is None:
            # Default to end of last complete month
            today = date.today()
            first_of_month = date(today.year, today.month, 1)
            as_of = first_of_month - timedelta(days=1)
        
        # Calculate start date (n months before as_of, start of that month)
        end_date = as_of
        
        # Go back n months
        target_month = as_of.month - n
        target_year = as_of.year
        
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        
        start_date = date(target_year, target_month, 1)
        
        # Adjust start to be the first of the following month for clean N-month range
        if n == 12:
            period_name = "Trailing 12 Months (TTM)"
        elif n == 3:
            period_name = "Trailing 3 Months"
        elif n == 6:
            period_name = "Trailing 6 Months"
        else:
            period_name = f"Trailing {n} Months"
        
        return FiscalPeriod(
            start_date=start_date,
            end_date=end_date,
            period_name=period_name,
            fiscal_year=self.get_fiscal_year_for_date(end_date),
        )
    
    def get_trailing_quarters(self, n: int, as_of: date = None) -> FiscalPeriod:
        """
        Get a trailing N quarters period ending on the specified date.
        
        Args:
            n: Number of trailing quarters
            as_of: End date for the period (defaults to end of last complete quarter)
        
        Returns:
            FiscalPeriod covering the trailing N quarters
        """
        if as_of is None:
            # Default to end of last complete quarter
            today = date.today()
            current_q = self.get_current_quarter()
            # Use day before current quarter start
            as_of = current_q.start_date - timedelta(days=1)
        
        # Each quarter is 3 months
        return self.get_trailing_months(n * 3, as_of)
    
    def get_ttm(self, as_of: date = None) -> FiscalPeriod:
        """
        Get Trailing Twelve Months period.
        
        Convenience wrapper for get_trailing_months(12).
        """
        return self.get_trailing_months(12, as_of)
    
    def parse_period_string(self, period_str: str, reference_date: date = None) -> Optional[FiscalPeriod]:
        """
        Parse a period string into a FiscalPeriod.
        
        Supported formats:
        - "YTD" - Year to date
        - "current month" / "this month"
        - "last month" / "prior month"
        - "Q1", "Q2", etc.
        - "FY2024", "FY25"
        - "January 2024", "Jan 2024"
        - "TTM" / "trailing 12 months" / "last 12 months"
        - "trailing 3 months" / "last 3 months"
        """
        reference_date = reference_date or date.today()
        period_str = period_str.strip().lower()
        
        # YTD
        if period_str in ["ytd", "year to date", "year-to-date"]:
            return self.get_ytd_range(reference_date)
        
        # Current month
        if period_str in ["current month", "this month", "mtd"]:
            return self.get_current_month()
        
        # Prior month
        if period_str in ["last month", "prior month", "previous month"]:
            return self.get_prior_month()
        
        # TTM / Trailing 12 months
        if period_str in ["ttm", "trailing 12 months", "last 12 months", "trailing twelve months", "t12m"]:
            return self.get_trailing_months(12)
        
        # Trailing N months patterns
        import re
        trailing_match = re.match(r"(?:trailing|last)\s+(\d+)\s+months?", period_str)
        if trailing_match:
            months = int(trailing_match.group(1))
            return self.get_trailing_months(months)
        
        # Trailing N quarters patterns
        trailing_q_match = re.match(r"(?:trailing|last)\s+(\d+)\s+quarters?", period_str)
        if trailing_q_match:
            quarters = int(trailing_q_match.group(1))
            return self.get_trailing_quarters(quarters)
        
        # Quarter patterns
        q_match = re.match(r"q(\d)", period_str)
        if q_match:
            quarter = int(q_match.group(1))
            fy = self.get_fiscal_year_for_date(reference_date)
            return self.get_fiscal_quarter_range(fy, quarter)
        
        # Fiscal year patterns
        fy_match = re.match(r"fy\s*(\d{2,4})", period_str)
        if fy_match:
            year = int(fy_match.group(1))
            if year < 100:
                year += 2000
            return self.get_fiscal_year_range(year)
        
        return None

# Singleton instance
_fiscal_calendar: Optional[FiscalCalendar] = None

def get_fiscal_calendar() -> FiscalCalendar:
    """Get the configured fiscal calendar instance."""
    global _fiscal_calendar
    if _fiscal_calendar is None:
        _fiscal_calendar = FiscalCalendar()
    return _fiscal_calendar

def reset_fiscal_calendar():
    """Reset the fiscal calendar (useful for testing)."""
    global _fiscal_calendar
    _fiscal_calendar = None

