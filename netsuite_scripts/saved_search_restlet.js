/**
 * @NApiVersion 2.1
 * @NScriptType Restlet
 * @NModuleScope SameAccount
 * 
 * RESTlet to execute saved searches and return results as JSON.
 * 
 * DEPLOYMENT INSTRUCTIONS:
 * 1. Go to Customization > Scripting > Scripts > New
 * 2. Upload this file
 * 3. Create Script Record with Type: RESTlet
 * 4. Deploy the script and note the External URL
 * 5. Update your .env file with the RESTlet URL
 */

define(['N/search', 'N/log'], function(search, log) {

    /**
     * GET request handler - Execute a saved search
     * @param {Object} requestParams - Request parameters
     * @param {string} requestParams.searchId - The saved search ID (e.g., 'customsearch1463')
     * @param {number} [requestParams.pageSize] - Results per page (default: 1000, max: 1000)
     * @param {number} [requestParams.page] - Page number (default: 0)
     * @returns {Object} Search results with metadata
     */
    function get(requestParams) {
        try {
            var searchId = requestParams.searchId;
            var pageSize = parseInt(requestParams.pageSize) || 1000;
            var pageNum = parseInt(requestParams.page) || 0;

            if (!searchId) {
                return {
                    success: false,
                    error: 'Missing required parameter: searchId'
                };
            }

            log.debug('Executing saved search', { searchId: searchId, pageSize: pageSize, page: pageNum });

            // Load the saved search
            var savedSearch = search.load({ id: searchId });
            
            // Get search columns for metadata
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

            log.debug('Search complete', { 
                resultCount: results.length, 
                totalResults: totalResults,
                page: pageNum,
                totalPages: totalPages
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
                results: results
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

    /**
     * POST request handler - Execute a saved search with filters
     * @param {Object} requestBody - Request body
     * @returns {Object} Search results
     */
    function post(requestBody) {
        try {
            var searchId = requestBody.searchId;
            var filters = requestBody.filters || [];
            var pageSize = parseInt(requestBody.pageSize) || 1000;
            var pageNum = parseInt(requestBody.page) || 0;

            if (!searchId) {
                return {
                    success: false,
                    error: 'Missing required parameter: searchId'
                };
            }

            log.debug('Executing saved search with filters', { 
                searchId: searchId, 
                filterCount: filters.length 
            });

            // Load and modify the saved search
            var savedSearch = search.load({ id: searchId });
            
            // Add additional filters if provided
            if (filters.length > 0) {
                var existingFilters = savedSearch.filters || [];
                filters.forEach(function(f) {
                    existingFilters.push(search.createFilter({
                        name: f.name,
                        operator: f.operator,
                        values: f.values,
                        join: f.join || null
                    }));
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

            return {
                success: true,
                searchId: searchId,
                columns: columns,
                totalResults: totalResults,
                totalPages: totalPages,
                currentPage: pageNum,
                pageSize: pageSize,
                resultCount: results.length,
                results: results
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

