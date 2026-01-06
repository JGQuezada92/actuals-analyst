"""
Test script to demonstrate monthly expense calculation logic.
This shows how the agent calculates monthly totals for comparison.
"""
import json
from datetime import datetime, date
from src.tools.data_processor import get_data_processor
from src.tools.calculator import get_calculator

# Mock data simulating SDR department expenses for current fiscal year
# Fiscal year starts in February (FY2025: Feb 2025 - Jan 2026)
mock_data = [
    # February 2025
    {"formuladate": "2025-02-15", "amount": 350000, "department": "SDR", "account": "5100 - Salaries"},
    {"formuladate": "2025-02-20", "amount": 45000, "department": "SDR", "account": "5200 - Software"},
    {"formuladate": "2025-02-28", "amount": 12000, "department": "SDR", "account": "5300 - Travel"},
    
    # March 2025
    {"formuladate": "2025-03-10", "amount": 350000, "department": "SDR", "account": "5100 - Salaries"},
    {"formuladate": "2025-03-15", "amount": 45000, "department": "SDR", "account": "5200 - Software"},
    {"formuladate": "2025-03-25", "amount": 15000, "department": "SDR", "account": "5300 - Travel"},
    
    # April 2025
    {"formuladate": "2025-04-05", "amount": 360000, "department": "SDR", "account": "5100 - Salaries"},
    {"formuladate": "2025-04-12", "amount": 48000, "department": "SDR", "account": "5200 - Software"},
    {"formuladate": "2025-04-20", "amount": 18000, "department": "SDR", "account": "5300 - Travel"},
    
    # May 2025
    {"formuladate": "2025-05-08", "amount": 360000, "department": "SDR", "account": "5100 - Salaries"},
    {"formuladate": "2025-05-15", "amount": 48000, "department": "SDR", "account": "5200 - Software"},
    {"formuladate": "2025-05-22", "amount": 20000, "department": "SDR", "account": "5300 - Travel"},
    
    # June 2025
    {"formuladate": "2025-06-10", "amount": 370000, "department": "SDR", "account": "5100 - Salaries"},
    {"formuladate": "2025-06-18", "amount": 50000, "department": "SDR", "account": "5200 - Software"},
    {"formuladate": "2025-06-25", "amount": 22000, "department": "SDR", "account": "5300 - Travel"},
    
    # July 2025
    {"formuladate": "2025-07-12", "amount": 370000, "department": "SDR", "account": "5100 - Salaries"},
    {"formuladate": "2025-07-20", "amount": 50000, "department": "SDR", "account": "5200 - Software"},
    {"formuladate": "2025-07-28", "amount": 25000, "department": "SDR", "account": "5300 - Travel"},
    
    # August 2025
    {"formuladate": "2025-08-05", "amount": 380000, "department": "SDR", "account": "5100 - Salaries"},
    {"formuladate": "2025-08-15", "amount": 52000, "department": "SDR", "account": "5200 - Software"},
    {"formuladate": "2025-08-22", "amount": 28000, "department": "SDR", "account": "5300 - Travel"},
    
    # September 2025
    {"formuladate": "2025-09-10", "amount": 380000, "department": "SDR", "account": "5100 - Salaries"},
    {"formuladate": "2025-09-18", "amount": 52000, "department": "SDR", "account": "5200 - Software"},
    {"formuladate": "2025-09-25", "amount": 30000, "department": "SDR", "account": "5300 - Travel"},
    
    # October 2025
    {"formuladate": "2025-10-08", "amount": 390000, "department": "SDR", "account": "5100 - Salaries"},
    {"formuladate": "2025-10-15", "amount": 54000, "department": "SDR", "account": "5200 - Software"},
    {"formuladate": "2025-10-22", "amount": 32000, "department": "SDR", "account": "5300 - Travel"},
    
    # November 2025
    {"formuladate": "2025-11-10", "amount": 390000, "department": "SDR", "account": "5100 - Salaries"},
    {"formuladate": "2025-11-18", "amount": 54000, "department": "SDR", "account": "5200 - Software"},
    {"formuladate": "2025-11-25", "amount": 35000, "department": "SDR", "account": "5300 - Travel"},
    
    # December 2025
    {"formuladate": "2025-12-08", "amount": 400000, "department": "SDR", "account": "5100 - Salaries"},
    {"formuladate": "2025-12-15", "amount": 56000, "department": "SDR", "account": "5200 - Software"},
    {"formuladate": "2025-12-22", "amount": 38000, "department": "SDR", "account": "5300 - Travel"},
    
    # January 2026
    {"formuladate": "2026-01-10", "amount": 400000, "department": "SDR", "account": "5100 - Salaries"},
    {"formuladate": "2026-01-18", "amount": 56000, "department": "SDR", "account": "5200 - Software"},
    {"formuladate": "2026-01-25", "amount": 40000, "department": "SDR", "account": "5300 - Travel"},
]

def main():
    print("=" * 80)
    print("MONTHLY EXPENSE CALCULATION DEMONSTRATION")
    print("Query: 'what is the total monthly expense for the SDR department for the current fiscal year?'")
    print("=" * 80)
    print()
    
    processor = get_data_processor()
    calculator = get_calculator()
    
    # Step 1: Group by month
    print("STEP 1: Grouping transactions by month")
    print("-" * 80)
    monthly_breakdown = processor.group_by_period(
        data=mock_data,
        period_type="month",
        amount_field="amount",
        date_field="formuladate"
    )
    
    print(f"Found {len(monthly_breakdown.data)} months with data")
    print()
    
    # Step 2: Display monthly totals
    print("STEP 2: Monthly Totals")
    print("-" * 80)
    monthly_totals = []
    for month_key in sorted(monthly_breakdown.data.keys()):
        month_data = monthly_breakdown.data[month_key]
        month_total = month_data.get("sum", 0)
        month_count = month_data.get("count", 0)
        
        # Format month name
        try:
            year, month_num = month_key.split("-")
            month_name = datetime(int(year), int(month_num), 1).strftime("%B %Y")
        except:
            month_name = month_key
        
        monthly_totals.append({
            "month": month_name,
            "month_key": month_key,
            "total": month_total,
            "count": month_count
        })
        
        print(f"{month_name:20} | ${month_total:>12,.2f} | {month_count:>3} transactions")
    
    print()
    print("-" * 80)
    
    # Step 3: Calculate grand total
    grand_total = sum(m["total"] for m in monthly_totals)
    print(f"{'TOTAL (FY2025 YTD)':20} | ${grand_total:>12,.2f} | {len(mock_data):>3} transactions")
    print()
    
    # Step 4: Show calculation details
    print("STEP 3: Calculation Details")
    print("-" * 80)
    print("Formula: Sum of 'amount' field grouped by month (YYYY-MM)")
    print("Date Field: formuladate (month-end date)")
    print("Amount Field: amount")
    print()
    print("For each month:")
    print("  1. Extract year-month from formuladate (e.g., '2025-02')")
    print("  2. Sum all amounts for transactions in that month")
    print("  3. Count transactions per month")
    print()
    
    # Step 5: Show breakdown by account type
    print("STEP 4: Breakdown by Account Type")
    print("-" * 80)
    account_totals = calculator.sum_by_category(mock_data, "amount", "account")
    for account, calc_result in account_totals.items():
        print(f"{account:30} | ${calc_result.value:>12,.2f}")
    print()
    
    # Step 6: Show average monthly expense
    avg_monthly = grand_total / len(monthly_totals) if monthly_totals else 0
    print("STEP 5: Summary Statistics")
    print("-" * 80)
    print(f"Average Monthly Expense: ${avg_monthly:,.2f}")
    print(f"Highest Month: {max(monthly_totals, key=lambda x: x['total'])['month']} (${max(monthly_totals, key=lambda x: x['total'])['total']:,.2f})")
    print(f"Lowest Month:  {min(monthly_totals, key=lambda x: x['total'])['month']} (${min(monthly_totals, key=lambda x: x['total'])['total']:,.2f})")
    print()
    
    print("=" * 80)
    print("This is how the agent calculates monthly expenses.")
    print("The actual calculation uses the same logic with real NetSuite data.")
    print("=" * 80)

if __name__ == "__main__":
    main()

