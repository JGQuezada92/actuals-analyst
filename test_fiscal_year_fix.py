"""Test script to verify fiscal year calculation fix."""
from datetime import date
from src.tools.calculator import get_calculator
from src.core.fiscal_calendar import get_fiscal_calendar

print("=" * 80)
print("FISCAL YEAR CALCULATION FIX VERIFICATION")
print("=" * 80)
print()

calc = get_calculator()
fiscal_cal = get_fiscal_calendar()

# Test dates
test_dates = [
    date(2026, 1, 6),   # January 6, 2026 (should be FY2026)
    date(2026, 2, 15),  # February 15, 2026 (should be FY2027)
    date(2025, 12, 31), # December 31, 2025 (should be FY2026)
]

print("Testing fiscal year calculation:")
print("-" * 80)

for test_date in test_dates:
    # Using fiscal calendar (correct method)
    fiscal_cal_fy = fiscal_cal.get_fiscal_year_for_date(test_date)
    fiscal_cal_range = fiscal_cal.get_fiscal_year_range(fiscal_cal_fy)
    
    # Using calculator ytd_total (should match)
    result = calc.ytd_total(
        [],
        'amount',
        'date',
        fiscal_start_month=2,
        as_of_date=test_date
    )
    
    # Extract fiscal year from metric name (e.g., "FY2026 YTD Total")
    calc_fy = int(result.metric_name.replace("FY", "").replace(" YTD Total", ""))
    
    print(f"Date: {test_date}")
    print(f"  Fiscal Calendar FY: {fiscal_cal_fy} ({fiscal_cal_range.period_name})")
    print(f"  Calculator FY: {calc_fy} ({result.metric_name})")
    print(f"  FY Start: {result.inputs['fy_start']}")
    print(f"  Match: {'OK' if fiscal_cal_fy == calc_fy else 'MISMATCH!'}")
    print()

print("=" * 80)
print("Current Fiscal Year (from fiscal calendar):")
current_fy = fiscal_cal.get_current_fiscal_year()
print(f"  {current_fy.period_name}: {current_fy.start_date} to {current_fy.end_date}")
print("=" * 80)

