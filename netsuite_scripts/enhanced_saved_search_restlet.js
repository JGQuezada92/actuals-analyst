/**
 * @NApiVersion 2.1
 * @NScriptType Restlet
 * @NModuleScope SameAccount
 * 
 * Enhanced RESTlet to execute saved searches with server-side filtering.
 * 
 * FEATURES:
 * - Date range filtering (uses posting period date for accuracy)
 * - Department filtering
 * - Account type filtering (by prefix)
 * - Account name filtering (contains)
 * - Transaction type filtering
 * - Subsidiary filtering
 * 
 * DEPLOYMENT INSTRUCTIONS:
 * 1. Go to Customization > Scripting > Scripts > New
 * 2. Upload this file
 * 3. Create Script Record with Type: RESTlet
 * 4. Deploy the script and note the External URL
 * 5. Update your .env file with the RESTlet URL
 * 
 * VERSION: 2.0 - Added server-side filtering support
 */

define(['N/search', 'N/log', 'N/format'], function(search, log, format) {

    /**
     * Build a date filter for the search.
     * 
     * @param {string} fieldId - The field to filter on
     * @param {string} startDate - Start date (MM/DD/YYYY or YYYY-MM-DD)
     * @param {string} endDate - End date (MM/DD/YYYY or YYYY-MM-DD)
     * @returns {Object} Search filter object
     */
    function buildDateFilter(fieldId, startDate, endDate) {
        // Parse dates - handle multiple formats
        var start = startDate;
        var end = endDate;
        
        // Convert YYYY-MM-DD to MM/DD/YYYY if needed
        if (startDate && startDate.indexOf('-') === 4) {
            var parts = startDate.split('-');
            start = parts[1] + '/' + parts[2] + '/' + parts[0];
        }
        if (endDate && endDate.indexOf('-') === 4) {
            var parts = endDate.split('-');
            end = parts[1] + '/' + parts[2] + '/' + parts[0];
        }
        
        log.debug('Creating date filter', {
            field: fieldId,
            start: start,
            end: end,
            operator: 'WITHIN'
        });
        
        try {
            var filter = search.createFilter({
                name: fieldId,
                operator: search.Operator.WITHIN,
                values: [start, end]
            });
            log.debug('Date filter created successfully', { field: fieldId });
            return filter;
        } catch (e) {
            log.error('buildDateFilter failed', {
                field: fieldId,
                start: start,
                end: end,
                error: e.message,
                name: e.name,
                toString: e.toString()
            });
            throw e; // Re-throw to be caught by caller
        }
    }

    /**
     * Build a text contains filter.
     * 
     * @param {string} fieldId - The field to filter on
     * @param {string} value - Value to search for
     * @param {string} joinTable - Optional join table
     * @returns {Object} Search filter object
     */
    function buildContainsFilter(fieldId, value, joinTable) {
        var filterDef = {
            name: fieldId,
            operator: search.Operator.CONTAINS,
            values: [value]
        };
        
        if (joinTable) {
            filterDef.join = joinTable;
        }
        
        return search.createFilter(filterDef);
    }

    /**
     * Build a text "starts with" filter for account number prefixes.
     * 
     * @param {string} fieldId - The field to filter on
     * @param {string} prefix - Prefix to match
     * @param {string} joinTable - Optional join table
     * @returns {Object} Search filter object
     */
    function buildStartsWithFilter(fieldId, prefix, joinTable) {
        var filterDef = {
            name: fieldId,
            operator: search.Operator.STARTSWITH,
            values: [prefix]
        };
        
        if (joinTable) {
            filterDef.join = joinTable;
        }
        
        return search.createFilter(filterDef);
    }

    /**
     * Build an "any of" filter for multiple values.
     * 
     * @param {string} fieldId - The field to filter on
     * @param {Array} values - Array of values
     * @param {string} joinTable - Optional join table
     * @returns {Object} Search filter object
     */
    function buildAnyOfFilter(fieldId, values, joinTable) {
        var filterDef = {
            name: fieldId,
            operator: search.Operator.ANYOF,
            values: values
        };
        
        if (joinTable) {
            filterDef.join = joinTable;
        }
        
        return search.createFilter(filterDef);
    }

    /**
     * Parse filter parameters from request and build search filters.
     * 
     * @param {Object} params - Request parameters
     * @param {Object} savedSearch - The loaded saved search
     * @returns {Array} Array of additional filters to apply
     */
    function parseFilters(params, savedSearch) {
        var filters = [];
        
        // =====================================================================
        // ACCOUNTING PERIOD FILTER
        // =====================================================================
        // Uses accountingPeriod_periodname (Accounting Period: Name) for filtering
        // This matches the export file's "Month-End Date (Text Format)" filter
        // Period names are in format "Jan 2024", "Feb 2024", etc.
        if (params.periodNames) {
            log.debug('Adding accounting period filter', { 
                periodNames: params.periodNames
            });
            
            try {
                // Parse comma-separated period names
                var periodNamesArray = params.periodNames.split(',').map(function(p) {
                    return p.trim();
                }).filter(function(p) {
                    return p.length > 0;
                });
                
                if (periodNamesArray.length > 0) {
                    log.debug('Attempting to create accounting period filter', {
                        periods: periodNamesArray.length,
                        samplePeriods: periodNamesArray.slice(0, 3)
                    });
                    
                    // Try different approaches to create the filter
                    var periodFilter = null;
                    var filterCreated = false;
                    
                    // Approach 1: Try with 'accountingPeriod' join (most common)
                    try {
                        periodFilter = search.createFilter({
                            name: 'periodname',
                            join: 'accountingPeriod',
                            operator: search.Operator.ANYOF,
                            values: periodNamesArray
                        });
                        filterCreated = true;
                        log.debug('Accounting period filter created with accountingPeriod join');
                    } catch (e1) {
                        log.debug('Failed with accountingPeriod join, trying alternatives', {
                            error: e1.message
                        });
                        
                        // Approach 2: Try with 'accountingperiod' (lowercase)
                        try {
                            periodFilter = search.createFilter({
                                name: 'periodname',
                                join: 'accountingperiod',
                                operator: search.Operator.ANYOF,
                                values: periodNamesArray
                            });
                            filterCreated = true;
                            log.debug('Accounting period filter created with accountingperiod join');
                        } catch (e2) {
                            log.debug('Failed with accountingperiod join, trying without join', {
                                error: e2.message
                            });
                            
                            // Approach 3: Try without join (if field exists directly)
                            try {
                                periodFilter = search.createFilter({
                                    name: 'accountingPeriod_periodname',
                                    operator: search.Operator.ANYOF,
                                    values: periodNamesArray
                                });
                                filterCreated = true;
                                log.debug('Accounting period filter created without join');
                            } catch (e3) {
                                log.error('All accounting period filter approaches failed', {
                                    error1: e1.message,
                                    error2: e2.message,
                                    error3: e3.message
                                });
                                throw e1; // Throw original error
                            }
                        }
                    }
                    
                    if (filterCreated && periodFilter) {
                        filters.push(periodFilter);
                        log.debug('Accounting period filter added successfully', { 
                            periods: periodNamesArray.length 
                        });
                    }
                }
            } catch (e) {
                log.error('Accounting period filter error', {
                    message: e.message,
                    name: e.name,
                    toString: e.toString(),
                    periodNames: params.periodNames
                });
                // Store error info
                if (!params._dateFilterErrors) {
                    params._dateFilterErrors = [];
                }
                params._dateFilterErrors.push({
                    field: 'accountingPeriod_periodname',
                    error: e.message,
                    type: e.name
                });
                // Don't throw - continue without period filter
                log.warning('Continuing without accounting period filter due to error');
            }
        }
        
        // =====================================================================
        // DATE RANGE FILTER (FALLBACK - for backward compatibility)
        // =====================================================================
        // Only use if periodNames is not provided
        if (!params.periodNames && params.startDate && params.endDate) {
            log.debug('Adding date filter (fallback)', { 
                start: params.startDate, 
                end: params.endDate,
                field: params.dateField || 'trandate'
            });
            
            var dateField = params.dateField || 'trandate';
            
            try {
                var dateFilter = buildDateFilter(dateField, params.startDate, params.endDate);
                filters.push(dateFilter);
                log.debug('Date filter created successfully', { field: dateField });
            } catch (e) {
                log.error('Date filter error for ' + dateField, {
                    message: e.message,
                    name: e.name,
                    toString: e.toString(),
                    field: dateField,
                    startDate: params.startDate,
                    endDate: params.endDate
                });
                // Store error info
                if (!params._dateFilterErrors) {
                    params._dateFilterErrors = [];
                }
                params._dateFilterErrors.push({
                    field: dateField,
                    error: e.message,
                    type: e.name
                });
            }
        }
        
        // =====================================================================
        // DEPARTMENT FILTER
        // =====================================================================
        // Supports multiple departments (comma-separated)
        // Uses CONTAINS operator for partial matching (e.g., "Marketing" matches "S&M : Marketing")
        // Based on saved search column structure: 'name' field with 'department' join
        if (params.department) {
            var departments = params.department.split(',');
            log.debug('Adding department filter', { departments: departments });
            
            if (departments.length === 1) {
                // Single department - use CONTAINS for flexibility
                // Use 'name' field with 'department' join (matches column structure)
                try {
                    filters.push(buildContainsFilter('name', departments[0].trim(), 'department'));
                } catch (e) {
                    log.error('Department filter error', e);
                    // Try alternative: department_name as direct field
                    try {
                        filters.push(buildContainsFilter('department_name', departments[0].trim()));
                    } catch (e2) {
                        log.error('Department filter fallback also failed', e2);
                    }
                }
            } else {
                // Multiple departments - create multiple filters (OR condition)
                departments.forEach(function(dept) {
                    try {
                        filters.push(buildContainsFilter('name', dept.trim(), 'department'));
                    } catch (e) {
                        log.error('Department filter error for ' + dept, e);
                    }
                });
            }
        }
        
        // =====================================================================
        // ACCOUNT TYPE FILTER (by prefix)
        // =====================================================================
        // Filters accounts by number prefix (e.g., "5" for expenses, "4" for revenue)
        // Supports multiple prefixes (comma-separated)
        if (params.accountPrefix) {
            var prefixes = params.accountPrefix.split(',');
            log.debug('Adding account prefix filter', { prefixes: prefixes });
            
            // For multiple prefixes, we need a formula filter
            // NetSuite's STARTSWITH only works with single values
            if (prefixes.length === 1) {
                try {
                    filters.push(buildStartsWithFilter('number', prefixes[0].trim(), 'account'));
                } catch (e) {
                    log.error('Account prefix filter error', e);
                }
            } else {
                // Multiple prefixes - create formula filter
                // Formula: CASE WHEN {account.number} LIKE '5%' OR {account.number} LIKE '6%' THEN 1 ELSE 0 END = 1
                var formulaParts = prefixes.map(function(p) {
                    return "{account.number} LIKE '" + p.trim() + "%'";
                });
                var formula = 'CASE WHEN ' + formulaParts.join(' OR ') + ' THEN 1 ELSE 0 END';
                
                try {
                    filters.push(search.createFilter({
                        name: 'formulanumeric',
                        operator: search.Operator.EQUALTO,
                        values: [1],
                        formula: formula
                    }));
                } catch (e) {
                    log.error('Account prefix formula filter error', e);
                    // Fall back to first prefix only
                    try {
                        filters.push(buildStartsWithFilter('number', prefixes[0].trim(), 'account'));
                    } catch (e2) {
                        log.error('Fallback account prefix filter also failed', e2);
                    }
                }
            }
        }
        
        // =====================================================================
        // ACCOUNT NAME FILTER
        // =====================================================================
        // Filters accounts by name containing specific text
        // Useful for compound filters like "Sales & Marketing" in account name
        if (params.accountName) {
            log.debug('Adding account name filter', { name: params.accountName });
            
            try {
                filters.push(buildContainsFilter('name', params.accountName, 'account'));
            } catch (e) {
                log.error('Account name filter error', e);
            }
        }
        
        // =====================================================================
        // TRANSACTION TYPE FILTER
        // =====================================================================
        // Filters by transaction type (e.g., "Journal", "VendBill")
        // Supports multiple types (comma-separated)
        if (params.transactionType) {
            var types = params.transactionType.split(',');
            log.debug('Adding transaction type filter', { types: types });
            
            try {
                if (types.length === 1) {
                    filters.push(search.createFilter({
                        name: 'type',
                        operator: search.Operator.IS,
                        values: [types[0].trim()]
                    }));
                } else {
                    filters.push(buildAnyOfFilter('type', types.map(function(t) { return t.trim(); })));
                }
            } catch (e) {
                log.error('Transaction type filter error', e);
            }
        }
        
        // =====================================================================
        // SUBSIDIARY FILTER
        // =====================================================================
        // Filters by subsidiary/entity
        if (params.subsidiary) {
            log.debug('Adding subsidiary filter', { subsidiary: params.subsidiary });
            
            try {
                filters.push(buildContainsFilter('subsidiary', params.subsidiary));
            } catch (e) {
                log.error('Subsidiary filter error', e);
            }
        }
        
        // =====================================================================
        // EXCLUDE TOTAL ACCOUNTS
        // =====================================================================
        // Excludes summary/total accounts to prevent double-counting
        if (params.excludeTotals === 'true' || params.excludeTotals === true) {
            log.debug('Adding exclude totals filter');
            
            try {
                // Exclude accounts with "Total" in the name
                filters.push(search.createFilter({
                    name: 'name',
                    join: 'account',
                    operator: search.Operator.DOESNOTCONTAIN,
                    values: ['Total']
                }));
            } catch (e) {
                log.error('Exclude totals filter error', e);
            }
        }
        
        return filters;
    }

    /**
     * GET request handler - Execute a saved search with optional filters
     * 
     * @param {Object} requestParams - Request parameters
     * @param {string} requestParams.searchId - The saved search ID (required)
     * @param {number} [requestParams.pageSize] - Results per page (default: 1000, max: 1000)
     * @param {number} [requestParams.page] - Page number (default: 0)
     * @param {string} [requestParams.periodNames] - Accounting period names to filter (comma-separated, e.g., "Jan 2024,Feb 2024,Mar 2024")
     *                                                 Uses accountingPeriod_periodname field. This is the PRIMARY method for date filtering.
     * @param {string} [requestParams.startDate] - Start date for date range filter (MM/DD/YYYY or YYYY-MM-DD) - fallback if periodNames not provided
     * @param {string} [requestParams.endDate] - End date for date range filter
     * @param {string} [requestParams.dateField] - Date field to filter on (default: trandate) - only used if periodNames not provided
     * @param {string} [requestParams.department] - Department name(s) to filter (comma-separated)
     * @param {string} [requestParams.accountPrefix] - Account number prefix(es) to filter (comma-separated)
     * @param {string} [requestParams.accountName] - Account name to filter (contains)
     * @param {string} [requestParams.transactionType] - Transaction type(s) to filter (comma-separated)
     * @param {string} [requestParams.subsidiary] - Subsidiary to filter
     * @param {string} [requestParams.excludeTotals] - If 'true', exclude Total accounts
     * @returns {Object} Search results with metadata
     */
    function get(requestParams) {
        var startTime = new Date().getTime();
        
        try {
            var searchId = requestParams.searchId;
            var pageSize = Math.min(parseInt(requestParams.pageSize) || 1000, 1000);
            var pageNum = parseInt(requestParams.page) || 0;

            if (!searchId) {
                return {
                    success: false,
                    error: 'Missing required parameter: searchId'
                };
            }

            log.audit('Executing filtered saved search', { 
                searchId: searchId, 
                pageSize: pageSize, 
                page: pageNum,
                hasPeriodFilter: !!requestParams.periodNames,
                hasDateFilter: !!(requestParams.startDate && requestParams.endDate),
                hasDepartmentFilter: !!requestParams.department,
                hasAccountFilter: !!requestParams.accountPrefix,
                hasAccountNameFilter: !!requestParams.accountName,
                hasTypeFilter: !!requestParams.transactionType,
                hasSubsidiaryFilter: !!requestParams.subsidiary
            });

            // Load the saved search
            var savedSearch = search.load({ id: searchId });
            
            // Log available joins and columns for debugging
            var availableJoins = [];
            var periodColumns = [];
            if (savedSearch.columns) {
                savedSearch.columns.forEach(function(col) {
                    if (col.join && availableJoins.indexOf(col.join) === -1) {
                        availableJoins.push(col.join);
                    }
                    // Check for period-related columns
                    if (col.name && (col.name.toLowerCase().indexOf('period') !== -1 || 
                        col.name.toLowerCase().indexOf('accounting') !== -1)) {
                        periodColumns.push({
                            name: col.name,
                            join: col.join || null,
                            label: col.label || col.name
                        });
                    }
                });
            }
            log.audit('Saved search structure', { 
                joins: availableJoins,
                periodColumns: periodColumns,
                totalColumns: savedSearch.columns ? savedSearch.columns.length : 0
            });
            
            // Get original filter count for logging
            var originalFilterCount = savedSearch.filters ? savedSearch.filters.length : 0;
            
            // Parse and add filters from request parameters
            // Store any filter errors for return in response
            var filterErrors = [];
            var additionalFilters = parseFilters(requestParams, savedSearch);
            
            // Collect any filter errors that occurred during parsing
            var filterErrors = [];
            if (requestParams._dateFilterErrors && requestParams._dateFilterErrors.length > 0) {
                filterErrors = requestParams._dateFilterErrors;
            }
            
            if (additionalFilters.length > 0) {
                // Combine existing filters with new filters
                var existingFilters = savedSearch.filters ? savedSearch.filters.slice() : [];
                additionalFilters.forEach(function(filter) {
                    existingFilters.push(filter);
                });
                savedSearch.filters = existingFilters;
                
                log.debug('Filters applied', { 
                    original: originalFilterCount, 
                    added: additionalFilters.length,
                    total: existingFilters.length
                });
            }
            
            // Get columns metadata
            var columns = savedSearch.columns.map(function(col) {
                return {
                    name: col.name,
                    label: col.label || col.name,
                    join: col.join || null,
                    summary: col.summary || null
                };
            });

            // Run the search with pagination
            var pagedData = savedSearch.runPaged({ pageSize: pageSize });
            var totalResults = pagedData.count;
            var totalPages = Math.ceil(totalResults / pageSize);

            // Get the requested page
            var results = [];
            if (pageNum < totalPages) {
                var page = pagedData.fetch({ index: pageNum });
                
                page.data.forEach(function(result) {
                    var row = { _id: result.id, _recordType: result.recordType };
                    
                    savedSearch.columns.forEach(function(col) {
                        var colKey = col.join ? col.join + '_' + col.name : col.name;
                        row[colKey] = result.getValue(col);
                        
                        // Also get text value for lookups
                        var textVal = result.getText(col);
                        if (textVal && textVal !== row[colKey]) {
                            row[colKey + '_text'] = textVal;
                        }
                    });
                    
                    results.push(row);
                });
            }

            var executionTime = new Date().getTime() - startTime;

            log.audit('Search complete', { 
                resultCount: results.length, 
                totalResults: totalResults,
                page: pageNum,
                totalPages: totalPages,
                executionTimeMs: executionTime,
                filtersApplied: additionalFilters.length
            });

            var response = {
                success: true,
                searchId: searchId,
                columns: columns,
                totalResults: totalResults,
                totalPages: totalPages,
                currentPage: pageNum,
                pageSize: pageSize,
                resultCount: results.length,
                results: results,
                executionTimeMs: executionTime,
                filtersApplied: additionalFilters.length,
                // Include filter info for debugging
                filterInfo: {
                    dateRange: (requestParams.startDate && requestParams.endDate) ? 
                        { 
                            start: requestParams.startDate, 
                            end: requestParams.endDate,
                            field: requestParams.dateField || 'formuladate'
                        } : null,
                    department: requestParams.department || null,
                    accountPrefix: requestParams.accountPrefix || null,
                    accountName: requestParams.accountName || null,
                    transactionType: requestParams.transactionType || null,
                    subsidiary: requestParams.subsidiary || null
                }
            };
            
            // Add filter errors if any occurred
            if (filterErrors && filterErrors.length > 0) {
                response.filterErrors = filterErrors;
                response.warning = 'Some filters could not be applied. Check filterErrors for details.';
            }
            
            return response;

        } catch (e) {
            var errorDetails = {
                message: e.message,
                name: e.name,
                stack: e.stack,
                toString: e.toString(),
                timestamp: new Date().toISOString()
            };
            
            // Try to get more error details if available
            if (e.toString) {
                errorDetails.fullError = e.toString();
            }
            
            log.error('Error executing saved search', errorDetails);
            
            return {
                success: false,
                error: e.message,
                errorType: e.name,
                errorDetails: e.stack,
                timestamp: new Date().toISOString()
            };
        }
    }

    /**
     * POST request handler - Execute a saved search with complex filters
     * 
     * Use POST when you need to send complex filter configurations that
     * don't fit well in URL parameters.
     * 
     * @param {Object} requestBody - Request body
     * @param {string} requestBody.searchId - The saved search ID (required)
     * @param {number} [requestBody.pageSize] - Results per page (default: 1000)
     * @param {number} [requestBody.page] - Page number (default: 0)
     * @param {Array} [requestBody.filters] - Array of filter objects
     * @returns {Object} Search results
     */
    function post(requestBody) {
        var startTime = new Date().getTime();
        
        try {
            var searchId = requestBody.searchId;
            var filters = requestBody.filters || [];
            var pageSize = Math.min(parseInt(requestBody.pageSize) || 1000, 1000);
            var pageNum = parseInt(requestBody.page) || 0;

            if (!searchId) {
                return {
                    success: false,
                    error: 'Missing required parameter: searchId'
                };
            }

            log.audit('Executing saved search via POST', { 
                searchId: searchId, 
                filterCount: filters.length,
                pageSize: pageSize,
                page: pageNum
            });

            // Load and modify the saved search
            var savedSearch = search.load({ id: searchId });
            
            // Add additional filters if provided
            if (filters.length > 0) {
                var existingFilters = savedSearch.filters ? savedSearch.filters.slice() : [];
                
                filters.forEach(function(f) {
                    try {
                        existingFilters.push(search.createFilter({
                            name: f.name,
                            operator: f.operator,
                            values: f.values,
                            join: f.join || null,
                            formula: f.formula || null
                        }));
                    } catch (e) {
                        log.error('Error adding filter', { filter: f, error: e.message });
                    }
                });
                
                savedSearch.filters = existingFilters;
            }

            // Get columns metadata
            var columns = savedSearch.columns.map(function(col) {
                return {
                    name: col.name,
                    label: col.label || col.name,
                    join: col.join || null
                };
            });

            // Run with pagination
            var pagedData = savedSearch.runPaged({ pageSize: pageSize });
            var totalResults = pagedData.count;
            var totalPages = Math.ceil(totalResults / pageSize);

            var results = [];
            if (pageNum < totalPages) {
                var page = pagedData.fetch({ index: pageNum });
                
                page.data.forEach(function(result) {
                    var row = { _id: result.id, _recordType: result.recordType };
                    
                    savedSearch.columns.forEach(function(col) {
                        var colKey = col.join ? col.join + '_' + col.name : col.name;
                        row[colKey] = result.getValue(col);
                        var textVal = result.getText(col);
                        if (textVal && textVal !== row[colKey]) {
                            row[colKey + '_text'] = textVal;
                        }
                    });
                    
                    results.push(row);
                });
            }

            var executionTime = new Date().getTime() - startTime;

            return {
                success: true,
                searchId: searchId,
                columns: columns,
                totalResults: totalResults,
                totalPages: totalPages,
                currentPage: pageNum,
                pageSize: pageSize,
                resultCount: results.length,
                results: results,
                executionTimeMs: executionTime,
                filtersApplied: filters.length
            };

        } catch (e) {
            log.error('Error executing saved search', e);
            return {
                success: false,
                error: e.message,
                errorType: e.name
            };
        }
    }

    return {
        get: get,
        post: post
    };
});