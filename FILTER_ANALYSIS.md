# Filter Analysis: S&M Expense Query

## Query
**"what is the total S&M expense for the SDR department for the current fiscal year?"**

## Filters Applied

### Server-Side Filters (Sent to RESTlet)
1. **Period Names**: `Feb 2025,Mar 2025,Apr 2025,May 2025,Jun 2025,Jul 2025,Aug 2025,Sep 2025,Oct 2025,Nov 2025,Dec 2025,Jan 2026`
   - Converted to internal NetSuite period IDs by RESTlet v2.2
   - Applied as: `postingperiod ANYOF [internal_ids]`

2. **Date Range** (Fallback if period filter fails):
   - Start Date: `02/01/2025`
   - End Date: `01/31/2026`
   - Field: `formuladate` (month-end date)

3. **Department**: `SDR`
   - Applied as: `department.name CONTAINS 'SDR'`

4. **Account Prefix**: `53`
   - Applied as: `account.number STARTSWITH '53'`
   - This filters for accounts starting with "53" (Sales & Marketing)

5. **Exclude Totals**: `true`
   - Excludes accounts with "Total" in the name

### Client-Side Filters (Applied After Retrieval)
- Period filter: 133 → 133 rows (no change - already filtered)
- Account type filter: 133 → 133 rows (no change - already filtered)
- Department filter: 133 → 133 rows (no change - already filtered)

## Data Retrieved

### Results
- **Total Rows**: 133 rows
- **Total Pages**: 1 page
- **Server-Side Filters Applied**: 4 filters
- **RESTlet Version**: 2.2

### Calculation
- **Total Amount**: $320,842.89
- **Calculation Method**: Sum of `amount` field across all 133 rows
- **Formula**: `sum(float(row.get('amount', 0) or 0) for row in data)`

## Comparison

### All Expenses (prefix 5) vs S&M Expenses (prefix 53)
| Query | Account Prefix | Rows Retrieved | Total Amount |
|-------|---------------|----------------|--------------|
| "total expense" | 5 | 144 rows | $348,103.99 |
| "total S&M expense" | 53 | 133 rows | $320,842.89 |
| **Difference** | - | **11 rows** | **$27,261.10** |

## Expected vs Actual

- **Expected Total**: ~$3,800,000
- **Actual Total**: $320,842.89
- **Gap**: $3,479,157.11 (91.5% missing)

## Analysis

### Possible Issues

1. **RESTlet Filter Too Restrictive**
   - The account prefix filter `account.number STARTSWITH '53'` might be excluding valid accounts
   - Some S&M accounts might not start with "53" (e.g., could be "5300", "5310", etc.)
   - The filter should match "53", "530", "5300", etc., which STARTSWITH should handle correctly

2. **Saved Search Has Built-In Filters**
   - The NetSuite saved search might have filters that conflict with our RESTlet filters
   - These would limit the total rows returned

3. **Period Filter Issue**
   - If period lookup failed, it falls back to date range filtering
   - Date range might not match all transactions in the fiscal year

4. **Data Not in NetSuite**
   - The data might simply not exist in NetSuite for this period/department/account combination
   - However, the user expects ~$3.8M, suggesting the data should exist

### RESTlet Account Prefix Filter Implementation

From `actuals_analyst_saved_search_restlet_v2.2_fixed.js`:
```javascript
if (params.accountPrefix) {
    var prefixes = params.accountPrefix.split(',');
    if (prefixes.length === 1) {
        // Single prefix - use STARTSWITH
        filters.push(buildStartsWithFilter('number', prefixes[0].trim(), 'account'));
    }
}
```

This creates: `account.number STARTSWITH '53'`

This should match:
- 53
- 530
- 5300
- 5310
- etc.

## Recommendations

1. **Check NetSuite Saved Search Filters**
   - Review the saved search definition in NetSuite
   - Ensure no conflicting filters are applied

2. **Query Without Account Prefix Filter**
   - Test querying all expenses (prefix 5) and filter client-side
   - Compare totals to see if RESTlet filter is the issue

3. **Verify Account Numbers**
   - Check what account numbers actually exist in NetSuite for S&M expenses
   - Ensure they all start with "53"

4. **Check Period Coverage**
   - Verify all 12 periods (Feb 2025 - Jan 2026) exist in NetSuite
   - Check if period lookup is finding all periods correctly

5. **Review RESTlet Logs**
   - Check NetSuite script execution logs for filter warnings
   - Look for `filterWarnings` in the RESTlet response

