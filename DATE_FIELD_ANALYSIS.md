# Date Field Analysis - NetSuite Saved Search

## Summary

Investigation into available date fields in the NetSuite saved search and their filterability.

## Available Date Fields

### Fields Found in Saved Search Columns:

1. **`formuladate`** ✅ EXISTS
   - Column position: 8
   - Sample values: `1/1/2024`, `1/1/2024`, `1/1/2024` (all same value in sample)
   - Format: `M/D/YYYY` (no leading zeros)
   - **Status**: Present in saved search results

2. **`trandate`** ✅ EXISTS  
   - Column position: 18
   - Sample values: `1/1/2024`, `1/2/2024`, `1/3/2024`, `1/4/2024`, `1/5/2024`
   - Format: `M/D/YYYY` (no leading zeros)
   - **Status**: Present in saved search results

3. **`periodname`** ✅ EXISTS
   - Column position: 15
   - **Status**: Present (period name, not a date field)

4. **`formulatext`** ✅ EXISTS
   - Column position: 9
   - **Status**: Present (text representation, not filterable)

### All Columns (20 total):
1. amortemplate
2. amount
3. class
4. creditamount
5. debitamount
6. displayname
7. entityid
8. **formuladate** ← Date field
9. formulatext
10. memo
11. name
12. name (duplicate)
13. number
14. parent
15. periodname
16. schedulenumber
17. subsidiarynohierarchy
18. **trandate** ← Date field
19. tranid
20. type

## Filterability Test Results

### Test Configuration:
- Department: `G&A (Parent) : Finance`
- Account Prefix: `5`
- Date Range: `01/01/2024` to `01/31/2024`

### Results:

| Test | Date Field | Rows Returned | Status |
|------|------------|---------------|--------|
| Baseline | None | 3,373 | ✅ Working |
| Test 1 | `trandate` | 0 | ⚠️ Suspicious |
| Test 2 | `formuladate` | 0 | ⚠️ Suspicious |

## Key Findings

### ✅ Confirmed:
1. **Both `formuladate` and `trandate` exist** in the saved search columns
2. **Both fields contain date values** in the expected format
3. **Baseline query works** (3,373 rows without date filter)

### ⚠️ Issues:
1. **Both date filters return 0 rows** - This is suspicious because:
   - Baseline data shows dates like `1/1/2024`, `1/2/2024`, etc.
   - There should be data matching the date range `01/01/2024` to `01/31/2024`
   - Both `trandate` and `formuladate` filters fail identically

2. **Possible causes:**
   - Date format mismatch (we send `01/01/2024` but data has `1/1/2024`)
   - Filter logic error in RESTlet
   - Formula fields (`formuladate`) cannot be filtered directly in NetSuite
   - RESTlet error handling is swallowing errors

## NetSuite Formula Field Limitation

**Important**: In NetSuite, **formula fields cannot be used directly in search filters**. 

The `formuladate` field appears to be a formula/calculated field (based on the name "formula" + "date"). NetSuite's `search.createFilter()` API typically rejects formula fields because they are computed values, not stored database fields.

### Evidence:
- Field name contains "formula" → likely a calculated field
- Both filters return 0 rows identically → suggests both are failing
- RESTlet logs show "unexpected error occurred" → filter creation likely failing

## Recommendations

### Option 1: Use `trandate` (Accounting Posting Date)
- ✅ Known to be filterable (we tested this earlier successfully)
- ✅ Direct database field, not a formula
- ⚠️ May not match export file exactly (uses transaction date vs month-end date)

### Option 2: Filter on `accountingPeriod_periodname` ⭐ **RECOMMENDED**
- ✅ **FOUND**: `accountingPeriod_periodname` exists and has values
- Filter by accounting period name (e.g., "Jan 2024", "Feb 2024")
- This is a joined field, so it should be filterable
- Would match month-end date logic (each period represents a month-end)
- **NetSuite filter syntax**:
  ```javascript
  search.createFilter({
      name: 'periodname',
      join: 'accountingPeriod',
      operator: search.Operator.ANYOF,
      values: ['Jan 2024', 'Feb 2024', ...]
  })
  ```

### Option 3: Client-side filtering
- Fetch data without date filter
- Filter by `formuladate` in Python after retrieval
- Less efficient but would work

### Option 4: Check RESTlet error logs
- Deploy updated RESTlet with enhanced error logging
- Check NetSuite execution logs for exact error message
- Determine if `formuladate` filter is throwing an error

## Next Steps

1. ✅ **COMPLETED**: Verified `formuladate` exists in saved search
2. ✅ **COMPLETED**: Verified `trandate` exists in saved search  
3. ⏳ **PENDING**: Check RESTlet error logs for exact error message
4. ⏳ **PENDING**: Test if `postingperiod` field exists and is filterable
5. ⏳ **PENDING**: Verify date format handling (MM/DD/YYYY vs M/D/YYYY)

## Conclusion

**`formuladate` EXISTS in the saved search data**, but it may not be **filterable** in NetSuite search filters because it's likely a formula/calculated field. NetSuite typically does not allow filtering on formula fields directly.

The identical 0-row results for both `trandate` and `formuladate` filters suggest there may be a broader issue with date filtering (format, logic, or RESTlet error handling), but the most likely explanation is that `formuladate` cannot be filtered because it's a formula field.

