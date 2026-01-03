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
        
        return search.createFilter({
            name: fieldId,
            operator: search.Operator.WITHIN,
            values: [start, end]
        });
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
        // DATE RANGE FILTER
        // =====================================================================
        // Uses trandate (Accounting Posting Date) for date filtering
        // Note: formuladate is a formula field and cannot be filtered directly
        if (params.startDate && params.endDate) {
            log.debug('Adding date filter', { 
                start: params.startDate, 
                end: params.endDate,
                field: params.dateField || 'trandate'
            });
            
            // Use configurable date field, default to trandate (Accounting Posting Date)
            var dateField = params.dateField || 'trandate';
            
            try {
                filters.push(buildDateFilter(dateField, params.startDate, params.endDate));
            } catch (e) {
                log.error('Date filter error', e);
                // Try alternative date field as fallback
                try {
                    filters.push(buildDateFilter('formuladate', params.startDate, params.endDate));
                    log.debug('Fell back to formuladate filter');
                } catch (e2) {
                    log.error('Fallback date filter also failed', e2);
                }
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
     * @param {string} [requestParams.startDate] - Start date for date range filter (MM/DD/YYYY or YYYY-MM-DD)
     * @param {string} [requestParams.endDate] - End date for date range filter
     * @param {string} [requestParams.dateField] - Date field to filter on (default: trandate - Accounting Posting Date)
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
                hasDateFilter: !!(requestParams.startDate && requestParams.endDate),
                hasDepartmentFilter: !!requestParams.department,
                hasAccountFilter: !!requestParams.accountPrefix,
                hasAccountNameFilter: !!requestParams.accountName,
                hasTypeFilter: !!requestParams.transactionType,
                hasSubsidiaryFilter: !!requestParams.subsidiary
            });

            // Load the saved search
            var savedSearch = search.load({ id: searchId });
            
            // Get original filter count for logging
            var originalFilterCount = savedSearch.filters ? savedSearch.filters.length : 0;
            
            // Parse and add filters from request parameters
            var additionalFilters = parseFilters(requestParams, savedSearch);
            
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
                filtersApplied: additionalFilters.length,
                // Include filter info for debugging
                filterInfo: {
                    dateRange: (requestParams.startDate && requestParams.endDate) ? 
                        { start: requestParams.startDate, end: requestParams.endDate } : null,
                    department: requestParams.department || null,
                    accountPrefix: requestParams.accountPrefix || null,
                    accountName: requestParams.accountName || null,
                    transactionType: requestParams.transactionType || null,
                    subsidiary: requestParams.subsidiary || null
                }
            };

        } catch (e) {
            log.error('Error executing saved search', {
                message: e.message,
                name: e.name,
                stack: e.stack
            });
            
            return {
                success: false,
                error: e.message,
                errorType: e.name,
                errorDetails: e.stack
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