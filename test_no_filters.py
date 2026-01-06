"""Test querying without account prefix filter to see total data."""
from src.core.query_parser import get_query_parser
from src.tools.netsuite_client import NetSuiteRESTClient
from config.settings import get_config

# Parse query
query = "what is the total S&M expense for the SDR department for the current fiscal year?"
parser = get_query_parser()
parsed = parser.parse(query)

# Remove account prefix filter
parsed.account_type_filter = None

print("=" * 80)
print("TESTING WITHOUT ACCOUNT PREFIX FILTER")
print("=" * 80)
print(f"Query: {query}")
print(f"Filters:")
print(f"  Departments: {parsed.departments}")
print(f"  Time Period: {parsed.time_period.period_name if parsed.time_period else None}")
print(f"  Account Prefix: {parsed.account_type_filter}")

# Get data
from src.tools.netsuite_client import NetSuiteDataRetriever
retriever = NetSuiteDataRetriever()
result = retriever.get_saved_search_data(parsed_query=parsed, bypass_cache=True)

print(f"\nRetrieved: {result.row_count} rows")
if result.data:
    # Sum amounts
    total = sum(float(row.get('amount', 0) or 0) for row in result.data)
    print(f"Total Amount: ${total:,.2f}")
    
    # Show sample account numbers
    account_numbers = set()
    for row in result.data[:20]:
        acct = row.get('number') or row.get('account_number')
        if acct:
            account_numbers.add(str(acct))
    print(f"\nSample Account Numbers (first 20 rows): {sorted(list(account_numbers))[:10]}")

