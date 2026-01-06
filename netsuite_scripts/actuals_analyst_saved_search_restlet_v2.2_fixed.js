/**
 * @NApiVersion 2.1
 * @NScriptType Restlet
 * @NModuleScope SameAccount
 * 
 * Enhanced RESTlet to execute saved searches with server-side filtering.
 * 
 * VERSION: 2.4 - Fixed department filter to use base fields instead of formula field
 * 
 * CRITICAL FIX (v2.4):
 * Department filter now uses base department fields (name+department join, direct department)
 * instead of 'formulatext' formula field. Formula fields cannot be filtered in NetSuite
 * saved searches, even though they appear in returned data.
 * 
 * Previous v2.3 attempted to use 'formulatext' field which resulted in 0 rows because
 * NetSuite doesn't allow filtering on formula/calculated fields in saved search filters.
 * 
 * STRATEGY (v2.4):
 * 1. PRIMARY: Use 'name' field with 'department' join (works for most departments)
 * 2. FALLBACK: Use direct 'department' field
 * 3. REMOVED: formulatext (formula fields can't be filtered)
 * 
 * Note: If base fields don't work for specific departments, those will be filtered
 * client-side in Python using formulatext from returned data.
 * 
 * PREVIOUS FIXES:
 * - v2.2: Fixed period filter to resolve period names to internal IDs
 * - v2.2: Replaced log.warning() with log.audit()
 * 
 * COMPATIBLE WITH: netsuite_filter_builder.py to_query_params()
 * 
 * PARAMETERS SUPPORTED:
 * - searchId (required): Saved search internal ID
 * - pageSize: Results per page (default: 1000, max: 1000)
 * - page: Page number (0-indexed, default: 0)
 * - periodNames: Accounting period names (comma-separated, e.g., "Jan 2025,Feb 2025")
 * - startDate: Start date (MM/DD/YYYY) - used if periodNames fails or not provided
 * - endDate: End date (MM/DD/YYYY)
 * - dateField: Date field for filtering (default: formuladate)
 * - department: Department name(s) (comma-separated, partial match)
 * - accountPrefix: Account number prefix(es) (comma-separated)
 * - accountName: Account name to filter (contains match)
 * - transactionType: Transaction type(s) (comma-separated)
 * - subsidiary: Subsidiary to filter (contains match)
 * - excludeTotals: If "true", exclude accounts with "Total" in name
 */

define(['N/search', 'N/log'], function(search, log) {

    // =========================================================================
    // PERIOD ID LOOKUP CACHE
    // =========================================================================
    
    /**
     * Look up accounting period internal IDs from period names OR date range.
     * 
     * This is the critical fix - postingperiod ANYOF requires internal IDs,
     * not text names like "Jan 2025".
     * 
     * Uses date-based lookup as primary method (more reliable than name matching),
     * with name-based lookup as fallback.
     * 
     * @param {Array<string>} periodNames - Period names (e.g., ["Jan 2025", "Feb 2025"])
     * @param {string} startDate - Start date (MM/DD/YYYY) - optional, used for date-based lookup
     * @param {string} endDate - End date (MM/DD/YYYY) - optional, used for date-based lookup
     * @returns {Object} { ids: Array<string>, notFound: Array<string> }
     */
    function lookupPeriodIds(periodNames, startDate, endDate) {
        var periodIds = [];
        var notFoundPeriods = [];
        var foundPeriodMap = {};
        
        if ((!periodNames || periodNames.length === 0) && (!startDate || !endDate)) {
            return { ids: [], notFound: [] };
        }
        
        log.debug('Looking up period IDs', { 
            periodCount: periodNames ? periodNames.length : 0,
            periods: periodNames ? periodNames.slice(0, 5).join(', ') + (periodNames.length > 5 ? '...' : '') : 'none',
            dateRange: startDate && endDate ? startDate + ' to ' + endDate : 'none'
        });
        
        try {
            // METHOD 1: Try date-based lookup first (more reliable)
            // Find all periods that overlap with the date range
            if (startDate && endDate) {
                try {
                    // Convert MM/DD/YYYY to date objects for comparison
                    var startParts = startDate.split('/');
                    var endParts = endDate.split('/');
                    var startDateObj = new Date(parseInt(startParts[2]), parseInt(startParts[0]) - 1, parseInt(startParts[1]));
                    var endDateObj = new Date(parseInt(endParts[2]), parseInt(endParts[0]) - 1, parseInt(endParts[1]));
                    
                    // Search for periods that overlap with date range
                    // A period overlaps if: period.start <= endDate AND period.end >= startDate
                    var dateBasedSearch = search.create({
                        type: search.Type.ACCOUNTING_PERIOD,
                        filters: [
                            ['startdate', search.Operator.ONORBEFORE, endDate],
                            'AND',
                            ['enddate', search.Operator.ONORAFTER, startDate],
                            'AND',
                            ['isyear', search.Operator.IS, 'F'],
                            'AND',
                            ['isquarter', search.Operator.IS, 'F']
                        ],
                        columns: [
                            search.createColumn({ name: 'periodname' }),
                            search.createColumn({ name: 'internalid' }),
                            search.createColumn({ name: 'startdate' }),
                            search.createColumn({ name: 'enddate' })
                        ]
                    });
                    
                    dateBasedSearch.run().each(function(result) {
                        var periodName = result.getValue({ name: 'periodname' });
                        var periodId = result.id;
                        
                        if (periodIds.indexOf(periodId) === -1) {
                            periodIds.push(periodId);
                            foundPeriodMap[periodName] = periodId;
                            log.debug('Found period by date', { name: periodName, id: periodId });
                        }
                        return true; // Continue iteration
                    });
                    
                    log.debug('Date-based lookup found ' + periodIds.length + ' periods');
                } catch (dateError) {
                    log.debug('Date-based lookup failed, trying name-based', { error: dateError.message });
                }
            }
            
            // METHOD 2: Try name-based lookup (fallback or supplement)
            // Only if we have period names AND didn't find all periods via date lookup
            if (periodNames && periodNames.length > 0) {
                // If we already found periods via date lookup, only look for missing ones
                var namesToSearch = periodNames;
                if (periodIds.length > 0) {
                    // Filter out names we already found
                    namesToSearch = periodNames.filter(function(name) {
                        return !foundPeriodMap[name];
                    });
                }
                
                if (namesToSearch.length > 0) {
                    try {
                        // Try exact match first
                        var nameSearch = search.create({
                            type: search.Type.ACCOUNTING_PERIOD,
                            filters: [
                                ['periodname', search.Operator.ANYOF, namesToSearch],
                                'AND',
                                ['isyear', search.Operator.IS, 'F'],
                                'AND',
                                ['isquarter', search.Operator.IS, 'F']
                            ],
                            columns: [
                                search.createColumn({ name: 'periodname' }),
                                search.createColumn({ name: 'internalid' }),
                                search.createColumn({ name: 'startdate' }),
                                search.createColumn({ name: 'enddate' })
                            ]
                        });
                        
                        nameSearch.run().each(function(result) {
                            var periodName = result.getValue({ name: 'periodname' });
                            var periodId = result.id;
                            
                            if (periodIds.indexOf(periodId) === -1) {
                                periodIds.push(periodId);
                                foundPeriodMap[periodName] = periodId;
                                log.debug('Found period by name', { name: periodName, id: periodId });
                            }
                            return true; // Continue iteration
                        });
                    } catch (nameError) {
                        log.debug('Name-based lookup failed', { error: nameError.message });
                    }
                }
            }
            
            // Check which periods were not found (if we have period names)
            if (periodNames && periodNames.length > 0) {
                periodNames.forEach(function(name) {
                    if (!foundPeriodMap[name]) {
                        notFoundPeriods.push(name);
                    }
                });
            }
            
            if (notFoundPeriods.length > 0) {
                log.audit('Some periods not found by name', { 
                    notFound: notFoundPeriods,
                    foundCount: periodIds.length
                });
            }
            
            log.debug('Period ID lookup complete', { 
                requested: periodNames ? periodNames.length : 0,
                found: periodIds.length,
                notFound: notFoundPeriods.length,
                method: startDate && endDate ? 'date-based' : 'name-based'
            });
            
        } catch (e) {
            log.error('Period lookup failed', { 
                error: e.message, 
                stack: e.stack 
            });
            return { ids: [], notFound: periodNames || [], error: e.message };
        }
        
        return { 
            ids: periodIds, 
            notFound: notFoundPeriods,
            periodMap: foundPeriodMap
        };
    }

    // =========================================================================
    // FILTER BUILDER FUNCTIONS
    // =========================================================================

    /**
     * Build a date range filter (WITHIN operator).
     */
    function buildDateFilter(fieldId, startDate, endDate) {
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
     * Build a text CONTAINS filter.
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
     * Build a STARTSWITH filter.
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
     * Build an ANYOF filter for multiple values.
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
     * Build a DOESNOTCONTAIN filter.
     */
    function buildDoesNotContainFilter(fieldId, value, joinTable) {
        var filterDef = {
            name: fieldId,
            operator: search.Operator.DOESNOTCONTAIN,
            values: [value]
        };
        if (joinTable) {
            filterDef.join = joinTable;
        }
        return search.createFilter(filterDef);
    }

    // =========================================================================
    // MAIN FILTER PARSER
    // =========================================================================

    /**
     * Parse request parameters and build search filters.
     * 
     * CRITICAL: All filter creation is wrapped in try-catch.
     * If a filter fails, we log the error and continue without it.
     * Client-side filtering in Python will handle what server-side couldn't.
     * 
     * @param {Object} params - Request parameters
     * @returns {Object} { filters: Array, errors: Array, warnings: Array }
     */
    function parseFilters(params) {
        var filters = [];
        var errors = [];
        var warnings = [];

        // =====================================================================
        // PERIOD NAMES FILTER (PRIMARY DATE FILTER) - FIXED IN v2.2
        // =====================================================================
        // Now properly resolves period names to internal IDs before creating filter
        var periodFilterApplied = false;
        
        if (params.periodNames) {
            log.debug('Attempting period filter', { periodNames: params.periodNames });
            
            try {
                var periodNamesArray = params.periodNames.split(',')
                    .map(function(p) { return p.trim(); })
                    .filter(function(p) { return p.length > 0; });
                
                if (periodNamesArray.length > 0) {
                    // CRITICAL FIX: Look up internal IDs from period names
                    // Pass date range for more reliable date-based lookup
                    var periodLookup = lookupPeriodIds(
                        periodNamesArray,
                        params.startDate,
                        params.endDate
                    );
                    
                    if (periodLookup.ids && periodLookup.ids.length > 0) {
                        // Create filter with internal IDs (not text names!)
                        var periodFilter = search.createFilter({
                            name: 'postingperiod',
                            operator: search.Operator.ANYOF,
                            values: periodLookup.ids
                        });
                        filters.push(periodFilter);
                        periodFilterApplied = true;
                        
                        log.audit('Period filter applied successfully', {
                            requestedPeriods: periodNamesArray.length,
                            resolvedIds: periodLookup.ids.length,
                            notFound: periodLookup.notFound
                        });
                        
                        // Add warning if some periods weren't found
                        if (periodLookup.notFound && periodLookup.notFound.length > 0) {
                            warnings.push({
                                type: 'periodNames',
                                message: 'Some periods not found in NetSuite',
                                notFound: periodLookup.notFound
                            });
                        }
                    } else {
                        // No periods found - will fall back to date range
                        log.audit('No matching periods found, using date fallback', {
                            requestedPeriods: periodNamesArray,
                            lookupError: periodLookup.error
                        });
                        errors.push({
                            type: 'periodNames',
                            message: 'No matching accounting periods found: ' + periodNamesArray.join(', '),
                            details: periodLookup.error || 'Periods may not exist in NetSuite'
                        });
                    }
                }
            } catch (e) {
                log.error('Period filter error', { error: e.message, stack: e.stack });
                errors.push({
                    type: 'periodNames',
                    message: e.message
                });
            }
        }

        // =====================================================================
        // DATE RANGE FILTER (FALLBACK)
        // =====================================================================
        // Apply date filter if:
        // 1. periodNames was not provided, OR
        // 2. periodNames filter failed to apply
        if (params.startDate && params.endDate && !periodFilterApplied) {
            var dateField = params.dateField || 'formuladate';
            log.debug('Adding date filter (period filter not applied)', { 
                start: params.startDate, 
                end: params.endDate,
                field: dateField 
            });
            
            try {
                var dateFilter = buildDateFilter(dateField, params.startDate, params.endDate);
                filters.push(dateFilter);
                log.debug('Date filter created', { field: dateField });
            } catch (e) {
                log.error('Date filter error', { 
                    field: dateField,
                    error: e.message 
                });
                errors.push({
                    type: 'dateRange',
                    field: dateField,
                    message: e.message
                });
                
                // Try fallback to trandate if formuladate fails
                if (dateField !== 'trandate') {
                    try {
                        var fallbackFilter = buildDateFilter('trandate', params.startDate, params.endDate);
                        filters.push(fallbackFilter);
                        log.debug('Date filter fallback to trandate succeeded');
                    } catch (e2) {
                        log.error('Date filter fallback also failed', { error: e2.message });
                    }
                }
            }
        }

        // =====================================================================
        // DEPARTMENT FILTER - v2.4
        // =====================================================================
        // CRITICAL FIX: Use base department fields instead of formula field.
        // 
        // Issue with v2.3: 'formulatext' is a formula/calculated field which cannot
        // be filtered in NetSuite saved searches, even though it appears in returned data.
        // This caused 0 rows to be returned for all department queries.
        //
        // Solution (v2.4): Use base department fields that ARE filterable:
        // 1. PRIMARY: 'name' field with 'department' join (works for most departments)
        // 2. FALLBACK: Direct 'department' field
        //
        // Note: If base fields don't match all rows (e.g., short names like "SDR"),
        // Python-side filtering will handle the remainder using 'formulatext' from
        // returned data. This hybrid approach ensures accuracy.
        if (params.department) {
            var departments = params.department.split(',');
            log.debug('Adding department filter (v2.4 - using base fields)', { departments: departments });
            
            departments.forEach(function(dept) {
                var deptTrimmed = dept.trim();
                if (deptTrimmed) {
                    var filterCreated = false;
                    var filterStrategy = 'none';
                    
                    // STRATEGY 1 (PRIMARY): Use 'name' field with 'department' join
                    // This works for most departments including longer names like "Product Management"
                    // For short names like "SDR", this may not match all rows, but will match some
                    // Python-side filtering will catch the rest using formulatext
                    if (!filterCreated) {
                        try {
                            filters.push(buildContainsFilter('name', deptTrimmed, 'department'));
                            filterCreated = true;
                            filterStrategy = 'name+department';
                            log.debug('Department filter created', { 
                                dept: deptTrimmed, 
                                strategy: 'name with department join (PRIMARY)',
                                note: 'May not match all rows for short names - Python will handle remainder'
                            });
                        } catch (e) {
                            log.debug('name+department join filter failed, trying fallback', { 
                                dept: deptTrimmed, 
                                error: e.message 
                            });
                        }
                    }
                    
                    // STRATEGY 2 (FALLBACK): Direct 'department' field
                    // Use if join-based filter fails
                    if (!filterCreated) {
                        try {
                            filters.push(buildContainsFilter('department', deptTrimmed));
                            filterCreated = true;
                            filterStrategy = 'direct';
                            log.debug('Department filter created', { 
                                dept: deptTrimmed, 
                                strategy: 'direct department field (FALLBACK)'
                            });
                        } catch (e) {
                            log.error('All department filter strategies failed', { 
                                dept: deptTrimmed, 
                                errors: ['name+department failed', e.message]
                            });
                            errors.push({
                                type: 'department',
                                value: deptTrimmed,
                                message: 'All filter strategies failed: ' + e.message
                            });
                        }
                    }
                    
                    // Log the strategy used for debugging
                    if (filterCreated) {
                        log.audit('Department filter applied', {
                            department: deptTrimmed,
                            strategy: filterStrategy,
                            note: 'If results are incomplete, Python-side filtering will handle remainder'
                        });
                    }
                }
            });
        }

        // =====================================================================
        // ACCOUNT PREFIX FILTER
        // =====================================================================
        if (params.accountPrefix) {
            var prefixes = params.accountPrefix.split(',');
            log.debug('Adding account prefix filter', { prefixes: prefixes });
            
            if (prefixes.length === 1) {
                // Single prefix - use STARTSWITH
                try {
                    filters.push(buildStartsWithFilter('number', prefixes[0].trim(), 'account'));
                } catch (e) {
                    log.error('Account prefix filter error', { error: e.message });
                    errors.push({
                        type: 'accountPrefix',
                        value: prefixes[0],
                        message: e.message
                    });
                }
            } else {
                // Multiple prefixes - use formula filter
                try {
                    var formulaParts = prefixes.map(function(p) {
                        return "{account.number} LIKE '" + p.trim() + "%'";
                    });
                    var formula = 'CASE WHEN ' + formulaParts.join(' OR ') + ' THEN 1 ELSE 0 END';
                    
                    filters.push(search.createFilter({
                        name: 'formulanumeric',
                        formula: formula,
                        operator: search.Operator.EQUALTO,
                        values: [1]
                    }));
                    log.debug('Account prefix formula filter created');
                } catch (e) {
                    log.error('Account prefix formula filter error', { error: e.message });
                    // Fallback: add individual STARTSWITH filters
                    prefixes.forEach(function(p) {
                        try {
                            filters.push(buildStartsWithFilter('number', p.trim(), 'account'));
                        } catch (e2) {
                            log.error('Account prefix fallback error', { prefix: p, error: e2.message });
                        }
                    });
                    errors.push({
                        type: 'accountPrefix',
                        message: 'Formula filter failed, using individual filters'
                    });
                }
            }
        }

        // =====================================================================
        // ACCOUNT NAME FILTER
        // =====================================================================
        if (params.accountName) {
            log.debug('Adding account name filter', { name: params.accountName });
            
            try {
                filters.push(buildContainsFilter('name', params.accountName, 'account'));
            } catch (e) {
                log.error('Account name filter error', { error: e.message });
                errors.push({
                    type: 'accountName',
                    value: params.accountName,
                    message: e.message
                });
            }
        }

        // =====================================================================
        // TRANSACTION TYPE FILTER
        // =====================================================================
        if (params.transactionType) {
            var types = params.transactionType.split(',').map(function(t) { 
                return t.trim(); 
            }).filter(function(t) { 
                return t.length > 0; 
            });
            
            log.debug('Adding transaction type filter', { types: types });
            
            try {
                if (types.length === 1) {
                    filters.push(search.createFilter({
                        name: 'type',
                        operator: search.Operator.IS,
                        values: [types[0]]
                    }));
                } else {
                    filters.push(buildAnyOfFilter('type', types));
                }
            } catch (e) {
                log.error('Transaction type filter error', { error: e.message });
                errors.push({
                    type: 'transactionType',
                    values: types,
                    message: e.message
                });
            }
        }

        // =====================================================================
        // SUBSIDIARY FILTER
        // =====================================================================
        if (params.subsidiary) {
            log.debug('Adding subsidiary filter', { subsidiary: params.subsidiary });
            
            try {
                filters.push(buildContainsFilter('subsidiary', params.subsidiary));
            } catch (e) {
                log.error('Subsidiary filter error', { error: e.message });
                errors.push({
                    type: 'subsidiary',
                    value: params.subsidiary,
                    message: e.message
                });
            }
        }

        // =====================================================================
        // EXCLUDE TOTALS FILTER
        // =====================================================================
        if (params.excludeTotals === 'true' || params.excludeTotals === true) {
            log.debug('Adding exclude totals filter');
            
            try {
                filters.push(buildDoesNotContainFilter('name', 'Total', 'account'));
            } catch (e) {
                log.error('Exclude totals filter error', { error: e.message });
                errors.push({
                    type: 'excludeTotals',
                    message: e.message
                });
            }
        }

        return {
            filters: filters,
            errors: errors,
            warnings: warnings
        };
    }

    // =========================================================================
    // GET REQUEST HANDLER
    // =========================================================================

    function get(requestParams) {
        var startTime = new Date().getTime();
        
        try {
            var searchId = requestParams.searchId;
            var pageSize = Math.min(parseInt(requestParams.pageSize) || 1000, 1000);
            var pageNum = parseInt(requestParams.page) || 0;

            if (!searchId) {
                return {
                    success: false,
                    error: 'Missing required parameter: searchId',
                    version: '2.4'
                };
            }

            log.audit('Executing saved search', { 
                searchId: searchId, 
                pageSize: pageSize, 
                page: pageNum,
                version: '2.4',
                filters: {
                    periodNames: !!requestParams.periodNames,
                    dateRange: !!(requestParams.startDate && requestParams.endDate),
                    department: !!requestParams.department,
                    accountPrefix: !!requestParams.accountPrefix,
                    accountName: !!requestParams.accountName,
                    transactionType: !!requestParams.transactionType,
                    subsidiary: !!requestParams.subsidiary,
                    excludeTotals: requestParams.excludeTotals === 'true'
                }
            });

            // Load saved search
            var savedSearch = search.load({ id: searchId });
            
            // Parse and build filters
            var filterResult = parseFilters(requestParams);
            var additionalFilters = filterResult.filters;
            var filterErrors = filterResult.errors;
            var filterWarnings = filterResult.warnings || [];
            
            // Apply additional filters
            if (additionalFilters.length > 0) {
                var existingFilters = savedSearch.filters ? savedSearch.filters.slice() : [];
                additionalFilters.forEach(function(f) {
                    existingFilters.push(f);
                });
                savedSearch.filters = existingFilters;
                log.debug('Applied filters', { count: additionalFilters.length });
            }

            // Get column metadata
            var columns = savedSearch.columns.map(function(col) {
                return {
                    name: col.name,
                    label: col.label || col.name,
                    join: col.join || null
                };
            });

            // Execute with pagination
            var pagedData = savedSearch.runPaged({ pageSize: pageSize });
            var totalResults = pagedData.count;
            var totalPages = Math.ceil(totalResults / pageSize);

            // Fetch requested page
            var results = [];
            if (pageNum < totalPages && totalResults > 0) {
                var page = pagedData.fetch({ index: pageNum });
                
                page.data.forEach(function(result) {
                    var row = { 
                        _id: result.id, 
                        _recordType: result.recordType 
                    };
                    
                    savedSearch.columns.forEach(function(col) {
                        var colKey = col.join ? col.join + '_' + col.name : col.name;
                        row[colKey] = result.getValue(col);
                        
                        // Include text value for lookups
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
                filtersApplied: additionalFilters.length,
                filterErrors: filterErrors.length,
                filterWarnings: filterWarnings.length
            });

            // Build response
            var response = {
                success: true,
                version: '2.4',
                searchId: searchId,
                columns: columns,
                totalResults: totalResults,
                totalPages: totalPages,
                currentPage: pageNum,
                pageSize: pageSize,
                resultCount: results.length,
                results: results,
                executionTimeMs: executionTime,
                filtersApplied: additionalFilters.length
            };
            
            // Include filter errors if any
            if (filterErrors.length > 0) {
                response.filterErrors = filterErrors;
                response.warning = 'Some filters could not be applied server-side. Client-side filtering will handle them.';
            }
            
            // Include filter warnings if any
            if (filterWarnings.length > 0) {
                response.filterWarnings = filterWarnings;
            }
            
            return response;

        } catch (e) {
            log.error('Error executing saved search', {
                message: e.message,
                name: e.name,
                stack: e.stack
            });
            
            return {
                success: false,
                version: '2.4',
                error: e.message,
                errorType: e.name || 'UNEXPECTED_ERROR',
                errorStack: e.stack ? e.stack.split('\n') : [],
                timestamp: new Date().toISOString()
            };
        }
    }

    // =========================================================================
    // POST REQUEST HANDLER (for complex filter scenarios)
    // =========================================================================

    function post(requestBody) {
        // POST supports same parameters as GET, plus custom filter array
        var startTime = new Date().getTime();
        
        try {
            var searchId = requestBody.searchId;
            var pageSize = Math.min(parseInt(requestBody.pageSize) || 1000, 1000);
            var pageNum = parseInt(requestBody.page) || 0;
            var customFilters = requestBody.filters || [];

            if (!searchId) {
                return {
                    success: false,
                    error: 'Missing required parameter: searchId',
                    version: '2.4'
                };
            }

            log.audit('Executing saved search via POST', { 
                searchId: searchId,
                customFilterCount: customFilters.length,
                version: '2.4'
            });

            var savedSearch = search.load({ id: searchId });
            
            // Apply custom filters from POST body
            if (customFilters.length > 0) {
                var existingFilters = savedSearch.filters ? savedSearch.filters.slice() : [];
                
                customFilters.forEach(function(f) {
                    try {
                        existingFilters.push(search.createFilter({
                            name: f.name,
                            operator: f.operator,
                            values: f.values,
                            join: f.join || null,
                            formula: f.formula || null
                        }));
                    } catch (e) {
                        log.error('Error adding custom filter', { filter: f, error: e.message });
                    }
                });
                
                savedSearch.filters = existingFilters;
            }

            var columns = savedSearch.columns.map(function(col) {
                return {
                    name: col.name,
                    label: col.label || col.name,
                    join: col.join || null
                };
            });

            var pagedData = savedSearch.runPaged({ pageSize: pageSize });
            var totalResults = pagedData.count;
            var totalPages = Math.ceil(totalResults / pageSize);

            var results = [];
            if (pageNum < totalPages && totalResults > 0) {
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
                version: '2.4',
                searchId: searchId,
                columns: columns,
                totalResults: totalResults,
                totalPages: totalPages,
                currentPage: pageNum,
                pageSize: pageSize,
                resultCount: results.length,
                results: results,
                executionTimeMs: executionTime,
                filtersApplied: customFilters.length
            };

        } catch (e) {
            log.error('Error executing saved search via POST', {
                message: e.message,
                name: e.name,
                stack: e.stack
            });
            
            return {
                success: false,
                version: '2.4',
                error: e.message,
                errorType: e.name || 'UNEXPECTED_ERROR',
                errorStack: e.stack ? e.stack.split('\n') : [],
                timestamp: new Date().toISOString()
            };
        }
    }

    return {
        get: get,
        post: post
    };
});

