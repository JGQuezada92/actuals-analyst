"""Test script to see exact filters applied."""
from src.core.query_parser import get_query_parser
from src.core.netsuite_filter_builder import get_filter_builder

query = "what is the total S&M expense for the SDR department for the current fiscal year?"

# Parse query
parser = get_query_parser()
parsed = parser.parse(query)

print("=" * 80)
print("PARSED QUERY FILTERS")
print("=" * 80)
print(f"Account Type Filter: {parsed.account_type_filter}")
print(f"Account Name Filter: {parsed.account_name_filter}")
print(f"Departments: {parsed.departments}")
print(f"Time Period: {parsed.time_period.period_name if parsed.time_period else None}")
print(f"Time Period Range: {parsed.time_period.start_date} to {parsed.time_period.end_date if parsed.time_period else None}")

# Build RESTlet filters
builder = get_filter_builder()
filter_params = builder.build_from_parsed_query(parsed)

print("\n" + "=" * 80)
print("RESTLET FILTER PARAMETERS")
print("=" * 80)
print(f"Period Names: {filter_params.period_names}")
print(f"Start Date: {filter_params.start_date}")
print(f"End Date: {filter_params.end_date}")
print(f"Departments: {filter_params.departments}")
print(f"Account Prefixes: {filter_params.account_prefixes}")
print(f"Account Name: {filter_params.account_name}")
print(f"\nFilter Description: {filter_params.describe()}")

# Show query params
query_params = filter_params.to_query_params()
print("\n" + "=" * 80)
print("RESTLET QUERY PARAMETERS (URL)")
print("=" * 80)
for key, value in query_params.items():
    print(f"{key}: {value}")

