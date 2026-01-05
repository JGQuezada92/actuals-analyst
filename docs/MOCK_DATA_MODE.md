# Mock Data Mode

## Overview

Mock Data Mode allows you to test the codebase without exposing real NetSuite financial data to LLM APIs. This is especially useful when:

- Testing with non-enterprise LLM APIs (e.g., Claude personal account)
- Debugging query parsing and filtering logic
- Developing new features without accessing NetSuite
- Ensuring data privacy during development

## How It Works

When Mock Data Mode is enabled, the `NetSuiteDataRetriever` generates fake financial data that mirrors the exact structure of real NetSuite saved search data. The mock data:

- **Matches the structure**: Same column names, data types, and field formats
- **Respects filters**: Period, department, and account filters from `ParsedQuery` are applied
- **Maintains relationships**: Departments, accounts, and periods are consistent
- **Is realistic**: Amounts, dates, and transaction types follow realistic patterns

## Enabling Mock Data Mode

Add this to your `.env` file:

```bash
# Enable mock data mode (no real NetSuite data will be retrieved)
USE_MOCK_DATA=true
```

When enabled, all calls to `get_saved_search_data()` will return mock data instead of calling the NetSuite RESTlet.

## Mock Data Structure

The mock data generator creates transactions with the following fields (matching real NetSuite structure):

- `account_number`: Account number (e.g., "531110")
- `account_name`: Account name (e.g., "Sales & Marketing : Employee Costs: Sales")
- `department_name`: Department name (e.g., "G&A (Parent) : Finance")
- `amount`: Transaction amount (string, e.g., "3400.00")
- `debitamount`: Debit amount (string)
- `creditamount`: Credit amount (string)
- `trandate`: Transaction date (string, e.g., "3/22/2004")
- `accountingPeriod_periodname`: Period name (e.g., "Feb 2025")
- `formuladate`: Period end date (string, e.g., "2/1/2025")
- `type`: Transaction type (e.g., "VendBill")
- `type_text`: Transaction type text
- `memo`: Transaction memo
- `tranid`: Transaction ID
- `class`: Class code
- `class_text`: Class text
- `subsidiarynohierarchy`: Subsidiary name
- And other optional fields

## Mock Data Parameters

The mock data generator respects filters from `ParsedQuery`:

- **Periods**: If a time period is specified, only transactions for those periods are generated
- **Departments**: If departments are specified, only transactions for those departments are generated
- **Account Prefixes**: If account prefixes are specified (e.g., "5" for expenses), only matching accounts are used

## Example Usage

```python
from src.tools.netsuite_client import get_data_retriever
from src.core.query_parser import get_query_parser

# Enable mock data mode in .env: USE_MOCK_DATA=true

retriever = get_data_retriever()
parser = get_query_parser()

# Parse a query
parsed = parser.parse("what is the total expense for G&A Finance department for February through December 2025?")

# Get mock data (respects filters from parsed query)
result = retriever.get_saved_search_data(parsed_query=parsed)

print(f"Retrieved {result.row_count} mock transactions")
print(f"Columns: {result.column_names}")
print(f"Sample row: {result.data[0]}")
```

## Mock Data Defaults

When no filters are specified, the generator creates:

- **1000 transactions** (default)
- **All FY2026 periods** (Feb 2025 - Jan 2026)
- **All mock departments** (G&A, Sales, R&D, Marketing)
- **All expense accounts** (prefix "5")

When filters are applied, the row count adjusts accordingly:

- Specific period + department + account: ~500 rows
- Partial filters: ~750 rows
- No filters: 1000 rows

## Mock Departments

The generator includes these mock departments:

- G&A (Parent) : Finance
- G&A (Parent) : Human Resources
- G&A (Parent) : IT
- G&A (Parent) : Operations
- G&A (Parent) : Management
- Sales (Parent) : SDR
- Sales (Parent) : Account Management
- R&D (Parent) : Engineering
- R&D (Parent) : Product Management
- Marketing (Parent) : Marketing

## Mock Accounts

The generator includes realistic expense accounts:

- **5xx accounts**: General expense accounts
- **53x accounts**: Sales & Marketing accounts
- **59x accounts**: General & Administrative accounts

Account numbers and names follow NetSuite conventions.

## Testing with Mock Data

1. **Enable mock mode**: Set `USE_MOCK_DATA=true` in `.env`
2. **Run queries**: Use the agent normally - it will use mock data
3. **Verify behavior**: Check that filtering, calculations, and analysis work correctly
4. **Switch back**: Set `USE_MOCK_DATA=false` to use real NetSuite data

## Important Notes

- **No real data exposure**: When `USE_MOCK_DATA=true`, the NetSuite RESTlet is never called
- **Cache behavior**: Mock data is cached like real data (if caching is enabled)
- **Registry updates**: The dynamic registry can be updated from mock data (useful for testing)
- **LLM safety**: Only fake data is sent to LLM APIs when mock mode is enabled

## Troubleshooting

**Mock data not being used:**
- Check that `USE_MOCK_DATA=true` is set in `.env`
- Restart the application after changing `.env`
- Check logs for "Using MOCK DATA mode" message

**Mock data doesn't match expected structure:**
- Verify the mock data generator matches your NetSuite saved search columns
- Check `src/tools/mock_data_generator.py` for the column structure
- Update `get_mock_column_names()` if your structure differs

**Filters not working:**
- Ensure `ParsedQuery` is passed to `get_saved_search_data()`
- Check that query parser correctly extracts filters
- Verify mock data generator respects filters (check logs)


