"""Test to compare data with and without account prefix filters."""
import os
os.environ.setdefault('USE_MOCK_DATA', 'false')

from src.core.query_parser import get_query_parser
from src.core.netsuite_filter_builder import get_filter_builder
from src.tools.netsuite_client import NetSuiteDataRetriever

# Test 1: All expenses (no account prefix filter)
print("=" * 80)
print("TEST 1: ALL EXPENSES FOR SDR DEPARTMENT (NO ACCOUNT PREFIX FILTER)")
print("=" * 80)

query1 = "what is the total expense for the SDR department for the current fiscal year?"
parser = get_query_parser()
parsed1 = parser.parse(query1)

print(f"\nParsed Filters:")
print(f"  Account Type Filter: {parsed1.account_type_filter}")
print(f"  Departments: {parsed1.departments}")
print(f"  Time Period: {parsed1.time_period.period_name if parsed1.time_period else None}")

retriever = NetSuiteDataRetriever(use_cache=False)
result1 = retriever.get_saved_search_data(parsed_query=parsed1, bypass_cache=True)

print(f"\nRetrieved: {result1.row_count} rows")
if result1.data:
    total1 = sum(float(row.get('amount', 0) or 0) for row in result1.data)
    print(f"Total Amount: ${total1:,.2f}")
    
    # Show account number distribution
    account_prefixes = {}
    for row in result1.data:
        acct = str(row.get('number', '') or row.get('account_number', ''))
        if acct:
            prefix = acct[:2] if len(acct) >= 2 else acct[:1]
            account_prefixes[prefix] = account_prefixes.get(prefix, 0) + 1
    
    print(f"\nAccount Prefix Distribution:")
    for prefix, count in sorted(account_prefixes.items()):
        print(f"  {prefix}xxx: {count} rows")

# Test 2: S&M expenses only (with account prefix filter)
print("\n" + "=" * 80)
print("TEST 2: S&M EXPENSES ONLY (ACCOUNT PREFIX 53)")
print("=" * 80)

query2 = "what is the total S&M expense for the SDR department for the current fiscal year?"
parsed2 = parser.parse(query2)

print(f"\nParsed Filters:")
print(f"  Account Type Filter: {parsed2.account_type_filter}")
print(f"  Account Name Filter: {parsed2.account_name_filter}")
print(f"  Departments: {parsed2.departments}")
print(f"  Time Period: {parsed2.time_period.period_name if parsed2.time_period else None}")

# Show RESTlet filters
builder = get_filter_builder()
filter_params2 = builder.build_from_parsed_query(parsed2)
print(f"\nRESTlet Filters:")
print(f"  Account Prefixes: {filter_params2.account_prefixes}")
print(f"  Account Name: {filter_params2.account_name}")
print(f"  Departments: {filter_params2.departments}")
print(f"  Period Names: {filter_params2.period_names[:3]}... ({len(filter_params2.period_names)} total)")

result2 = retriever.get_saved_search_data(parsed_query=parsed2, bypass_cache=True)

print(f"\nRetrieved: {result2.row_count} rows")
if result2.data:
    total2 = sum(float(row.get('amount', 0) or 0) for row in result2.data)
    print(f"Total Amount: ${total2:,.2f}")
    
    # Show account number distribution
    account_prefixes2 = {}
    for row in result2.data:
        acct = str(row.get('number', '') or row.get('account_number', ''))
        if acct:
            prefix = acct[:2] if len(acct) >= 2 else acct[:1]
            account_prefixes2[prefix] = account_prefixes2.get(prefix, 0) + 1
    
    print(f"\nAccount Prefix Distribution:")
    for prefix, count in sorted(account_prefixes2.items()):
        print(f"  {prefix}xxx: {count} rows")
    
    # Show sample account names
    print(f"\nSample Account Names (first 10):")
    for i, row in enumerate(result2.data[:10]):
        acct_name = row.get('name') or row.get('account_name', 'N/A')
        acct_num = row.get('number') or row.get('account_number', 'N/A')
        amount = row.get('amount', 0)
        print(f"  {i+1}. {acct_num} - {acct_name}: ${float(amount or 0):,.2f}")

# Comparison
print("\n" + "=" * 80)
print("COMPARISON")
print("=" * 80)
if result1.data and result2.data:
    print(f"All Expenses (prefix 5): ${total1:,.2f} ({result1.row_count} rows)")
    print(f"S&M Expenses (prefix 53): ${total2:,.2f} ({result2.row_count} rows)")
    print(f"Difference: ${total1 - total2:,.2f} ({result1.row_count - result2.row_count} rows)")
    print(f"\nExpected S&M Total: ~$3,800,000")
    print(f"Actual S&M Total: ${total2:,.2f}")
    print(f"Gap: ${3800000 - total2:,.2f}")
    print(f"\nPercentage of Expected: {(total2 / 3800000 * 100):.1f}%")

