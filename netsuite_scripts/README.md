# NetSuite RESTlet Scripts

This directory contains the NetSuite SuiteScript RESTlet implementations used by the Python agent for data retrieval.

## RESTlet Versions

### RESTlet v2.2+ (Current)

**Key Features:**
- **Period ID Conversion**: Automatically converts period names (e.g., "Jan 2025") to internal NetSuite IDs
- **Graceful Degradation**: Falls back to date range filtering if period lookup fails
- **Enhanced Error Handling**: Returns `filterWarnings` for non-fatal filter issues
- **Version Field**: Response includes `version: "2.2"` for compatibility checking

**What Changed in v2.2:**
- Fixed critical bug where period names were passed directly to `postingperiod` ANYOF filter
- Added `lookupPeriodIds()` function that searches `accountingperiod` record type
- Period names are now converted to internal IDs before creating filters
- Returns `filterWarnings` array for periods not found (non-fatal)
- Falls back to date range filtering if all periods are missing

**Response Format:**
```json
{
  "success": true,
  "version": "2.2",
  "filterWarnings": [
    {
      "type": "periodNames",
      "notFound": ["Jan 2099", "Feb 2099"]
    }
  ],
  "columns": [...],
  "results": [...],
  "totalPages": 1,
  "totalResults": 0
}
```

### RESTlet v2.1 and Earlier

**Limitations:**
- Period names passed directly to filters (caused "UNEXPECTED_ERROR" at line 508)
- No version field in response
- No `filterWarnings` support
- Less graceful error handling

## Deployment

### Prerequisites
- NetSuite Administrator access
- SuiteScript 2.0 deployment permissions
- RESTlet script deployment access

### Deployment Steps

1. **Upload Script**
   - Navigate to Customization > Scripting > Scripts > New
   - Copy contents of `enhanced_saved_search_restlet.js` or `saved_search_restlet.js`
   - Set Script Type: RESTlet
   - Set Script ID: `customscript_actuals_analyst_saved_search_restlet` (or your preferred ID)

2. **Deploy Script**
   - Navigate to Customization > Scripting > Script Deployments > New
   - Select your RESTlet script
   - Set Deployment Status: Released
   - Set Log Level: Debug (for troubleshooting)
   - Set Available Without Login: No
   - Set Execute As: Administrator (or appropriate role)

3. **Get RESTlet URL**
   - Copy the External URL from the deployment
   - Format: `https://[account].app.netsuite.com/app/site/hosting/restlet.nl?script=[script_id]&deploy=[deployment_id]`
   - Add to Python `.env` file as `NETSUITE_RESTLET_URL`

4. **Set Up Authentication**
   - Create Token-Based Authentication (TBA) credentials
   - Role: Administrator (or role with saved search access)
   - Token Name: `netsuite-analyst-restlet`
   - Add credentials to Python `.env` file:
     ```
     NETSUITE_CONSUMER_KEY=...
     NETSUITE_CONSUMER_SECRET=...
     NETSUITE_TOKEN_ID=...
     NETSUITE_TOKEN_SECRET=...
     ```

## Period ID Conversion (v2.2+)

The RESTlet v2.2+ includes a `lookupPeriodIds()` function that:

1. **Takes period names** from Python (e.g., `["Jan 2025", "Feb 2025", "Mar 2025"]`)
2. **Searches NetSuite** `accountingperiod` record type for matching periods
3. **Extracts internal IDs** for each matching period
4. **Creates `postingperiod` ANYOF filter** with internal IDs (not text names)
5. **Falls back gracefully** to date range filtering if lookup fails

**Performance:**
- Period lookup adds ~100-200ms per request (one extra NetSuite search)
- Results are not cached (each request performs fresh lookup)
- If performance becomes an issue, consider caching period IDs in the RESTlet

**Error Handling:**
- If some periods are not found: Returns `filterWarnings` with `notFound` array, continues with found periods
- If all periods are not found: Falls back to date range filtering, returns warning
- If date range also fails: Falls back to `trandate` field, returns warning
- Python client-side filtering provides final safety net

## Filter Parameters

The RESTlet accepts the following query parameters:

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `searchId` | string | Saved search internal ID | `customsearch1479` |
| `pageSize` | integer | Results per page | `1000` |
| `page` | integer | Page number (0-indexed) | `0` |
| `periodNames` | string | Comma-separated period names | `Jan 2025,Feb 2025,Mar 2025` |
| `startDate` | string | Start date (MM/DD/YYYY) | `02/01/2025` |
| `endDate` | string | End date (MM/DD/YYYY) | `01/31/2026` |
| `dateField` | string | Date field for filtering | `formuladate` or `trandate` |
| `department` | string | Comma-separated departments | `SDR,Marketing` |
|              |        | Uses 'formulatext' field for hierarchical name matching | |
| `accountPrefix` | string | Comma-separated account prefixes | `5,6` |
| `accountName` | string | Account name contains | `Sales & Marketing` |
| `transactionType` | string | Comma-separated transaction types | `Journal,VendBill` |
| `subsidiary` | string | Subsidiary name | `Main Subsidiary` |
| `excludeTotals` | string | Exclude total rows (`"true"` or `"false"`) | `true` |

## Response Format

### Success Response (v2.2+)
```json
{
  "success": true,
  "version": "2.2",
  "filterWarnings": [],
  "columns": [
    {"name": "formuladate", "label": "Month-End Date"},
    {"name": "amount", "label": "Amount"}
  ],
  "results": [
    {"formuladate": "2025-02-28", "amount": 1000.00},
    ...
  ],
  "totalPages": 1,
  "totalResults": 100,
  "filtersApplied": 3
}
```

### Warning Response (v2.2+)
```json
{
  "success": true,
  "version": "2.2",
  "filterWarnings": [
    {
      "type": "periodNames",
      "notFound": ["Jan 2099", "Feb 2099"]
    }
  ],
  "columns": [...],
  "results": [...],
  "totalPages": 1,
  "totalResults": 100
}
```

### Error Response
```json
{
  "success": false,
  "error": "An unexpected SuiteScript error has occurred",
  "errorType": "UNEXPECTED_ERROR",
  "errorStack": ["Error\n    at Object.get (...)"],
  "errorDetails": {},
  "timestamp": "2026-01-06T15:02:23.163Z"
}
```

## Troubleshooting

### "UNEXPECTED_ERROR" at line 508
- **Cause**: Using RESTlet v2.1 or earlier with period name filtering
- **Solution**: Upgrade to RESTlet v2.2+ which handles period ID conversion

### Periods Not Found Warnings
- **Cause**: Requesting periods that don't exist in NetSuite (e.g., future months)
- **Solution**: This is expected behavior - RESTlet falls back to date range filtering
- **Action**: No action needed - Python client-side filtering will catch any missed rows

### Version Field Missing
- **Cause**: Using RESTlet v2.1 or earlier
- **Solution**: Upgrade to RESTlet v2.2+ for version field support
- **Note**: Python code works with older versions but won't log version info

### Performance Issues
- **Cause**: Period lookup adds ~100-200ms per request
- **Solution**: 
  - Consider caching period IDs in RESTlet (future enhancement)
  - Reduce number of periods requested if possible
  - Use date range filtering instead if period names not critical

## Python Compatibility

The Python codebase is **backward compatible** with RESTlet v2.1 and earlier:
- Works without version field (just won't log version info)
- Works without `filterWarnings` (just won't log warnings)
- Falls back gracefully if period filtering fails

However, **RESTlet v2.2+ is recommended** for:
- Proper period filtering (no more "UNEXPECTED_ERROR")
- Better observability (version logging, filter warnings)
- Graceful degradation (automatic fallback to date range)

## Files

- `enhanced_saved_search_restlet.js` - Enhanced RESTlet with period ID conversion (v2.2+)
- `saved_search_restlet.js` - Original RESTlet (v2.1 or earlier)
- `README.md` - This file

## Support

For issues or questions:
1. Check Python logs for RESTlet version and filter warnings
2. Verify RESTlet deployment status in NetSuite
3. Check NetSuite script execution logs for detailed errors
4. Review Python code in `src/tools/netsuite_client.py` for response handling

