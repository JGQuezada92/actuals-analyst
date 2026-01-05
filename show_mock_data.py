"""Show the actual mock data generated for a query."""
import os
import json
from datetime import datetime

# Enable mock data mode
os.environ['USE_MOCK_DATA'] = 'true'

from src.tools.netsuite_client import get_data_retriever
from src.core.query_parser import get_query_parser
from src.tools.calculator import get_calculator
from src.tools.data_processor import get_data_processor
from src.core.fiscal_calendar import get_fiscal_calendar

def show_mock_data_for_query(query: str):
    """Show mock data, calculations, and what gets sent to LLM."""
    
    print("=" * 80)
    print(f"QUERY: {query}")
    print("=" * 80)
    
    # Parse query
    parser = get_query_parser()
    parsed = parser.parse(query)
    
    print(f"\nParsed Query:")
    print(f"  Intent: {parsed.intent.value}")
    print(f"  Departments: {parsed.departments}")
    print(f"  Time Period: {parsed.time_period.period_name if parsed.time_period else 'None'}")
    if parsed.time_period:
        print(f"    Start: {parsed.time_period.start_date}")
        print(f"    End: {parsed.time_period.end_date}")
    
    # Get mock data
    retriever = get_data_retriever()
    result = retriever.get_saved_search_data(parsed_query=parsed)
    
    print(f"\n{'=' * 80}")
    print(f"MOCK DATA GENERATED: {len(result.data)} transactions")
    print("=" * 80)
    
    # Show first 20 rows
    print(f"\nFirst 20 Transactions:")
    print("-" * 80)
    for i, row in enumerate(result.data[:20], 1):
        print(f"\nTransaction {i}:")
        print(f"  Department: {row.get('department_name', 'N/A')}")
        print(f"  Account: {row.get('account_name', 'N/A')}")
        print(f"  Account Number: {row.get('account_number', 'N/A')}")
        print(f"  Amount: ${row.get('amount', '0.00')}")
        print(f"  Period: {row.get('accountingPeriod_periodname', 'N/A')}")
        print(f"  Date: {row.get('trandate', 'N/A')}")
        print(f"  Type: {row.get('type', 'N/A')}")
        print(f"  Memo: {row.get('memo', 'N/A')}")
    
    # Show summary statistics
    print(f"\n{'=' * 80}")
    print("DATA SUMMARY")
    print("=" * 80)
    
    # Count by department
    dept_counts = {}
    for row in result.data:
        dept = row.get('department_name', 'Unknown')
        dept_counts[dept] = dept_counts.get(dept, 0) + 1
    
    print(f"\nTransactions by Department:")
    for dept, count in sorted(dept_counts.items()):
        print(f"  {dept}: {count} transactions")
    
    # Count by period
    period_counts = {}
    for row in result.data:
        period = row.get('accountingPeriod_periodname', 'Unknown')
        period_counts[period] = period_counts.get(period, 0) + 1
    
    print(f"\nTransactions by Period:")
    for period, count in sorted(period_counts.items()):
        print(f"  {period}: {count} transactions")
    
    # Sum amounts
    total_amount = 0.0
    amounts_by_type = {}
    amounts_by_period = {}
    
    for row in result.data:
        try:
            amount = float(row.get('amount', 0) or 0)
            total_amount += amount
            
            trans_type = row.get('type', 'Unknown')
            amounts_by_type[trans_type] = amounts_by_type.get(trans_type, 0) + amount
            
            period = row.get('accountingPeriod_periodname', 'Unknown')
            amounts_by_period[period] = amounts_by_period.get(period, 0) + amount
        except (ValueError, TypeError):
            pass
    
    print(f"\nTotal Amount: ${total_amount:,.2f}")
    
    print(f"\nAmounts by Transaction Type:")
    for trans_type, amount in sorted(amounts_by_type.items(), key=lambda x: abs(x[1]), reverse=True):
        pct = (amount / total_amount * 100) if total_amount != 0 else 0
        print(f"  {trans_type}: ${amount:,.2f} ({pct:.2f}%)")
    
    print(f"\nAmounts by Period:")
    for period, amount in sorted(amounts_by_period.items()):
        print(f"  {period}: ${amount:,.2f}")
    
    # Perform calculations
    print(f"\n{'=' * 80}")
    print("CALCULATIONS PERFORMED")
    print("=" * 80)
    
    processor = get_data_processor()
    calculator = get_calculator()
    
    # Filter data
    filtered_result = processor.filter_by_period(
        result.data,
        parsed.time_period,
    )
    
    filtered_data = filtered_result.data  # FilterResult has 'data' attribute
    
    print(f"\nAfter Period Filter: {len(filtered_data)} transactions")
    
    # Manual calculations
    print(f"\nManual Calculations:")
    total = sum(float(row.get('amount', 0) or 0) for row in filtered_data)
    print(f"  Total Amount: ${total:,.2f}")
    
    # Calculate by transaction type
    by_type = {}
    for row in filtered_data:
        trans_type = row.get('type', 'Unknown')
        if trans_type not in by_type:
            by_type[trans_type] = []
        by_type[trans_type].append(row)
    
    print(f"\n  Totals by Transaction Type:")
    for trans_type, type_rows in sorted(by_type.items()):
        type_total = sum(float(row.get('amount', 0) or 0) for row in type_rows)
        pct = (type_total / total * 100) if total != 0 else 0
        print(f"    {trans_type}: ${type_total:,.2f} ({pct:.2f}%)")
    
    # Show what gets sent to LLM
    print(f"\n{'=' * 80}")
    print("DATA SENT TO LLM (First 10 rows)")
    print("=" * 80)
    
    sample_data = filtered_data[:10]
    sample_json = json.dumps(sample_data, indent=2, default=str)
    
    print(f"\nSample Data (JSON format):")
    print(sample_json[:2000])  # First 2000 chars
    if len(sample_json) > 2000:
        print(f"\n... (truncated, showing first 2000 characters of {len(sample_json)} total)")
    
    print(f"\n{'=' * 80}")
    print("VERIFICATION")
    print("=" * 80)
    
    # Manual calculation verification
    print(f"\nManual Verification:")
    print(f"  Total transactions: {len(result.data)}")
    print(f"  Total amount (sum): ${total_amount:,.2f}")
    print(f"  Average per transaction: ${total_amount/len(result.data):,.2f}" if result.data else "  N/A")
    
    # Compare with filtered data total
    filtered_total = sum(float(row.get('amount', 0) or 0) for row in filtered_data)
    print(f"\n  Filtered data total: ${filtered_total:,.2f}")
    print(f"  Original data total: ${total_amount:,.2f}")
    print(f"  Match: {'YES' if abs(filtered_total - total_amount) < 0.01 else 'NO'}")

if __name__ == "__main__":
    query = "what is the total YTD expense for SDR?"
    show_mock_data_for_query(query)

