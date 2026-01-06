"""
NetSuite Data Retrieval Tools

Deterministic data retrieval from NetSuite saved searches.
Following the framework principle: LLMs interpret, tools compute.

This module handles:
1. OneLogin SSO authentication flow
2. NetSuite REST API connection
3. Saved Search execution
4. Data validation and caching
5. SuiteQL optimization with pushed-down filters
6. Parallel pagination for faster data retrieval (Phase 2)

Enhanced with:
- SuiteQL query builder integration for optimized queries
- Smart routing between RESTlet (full search) and SuiteQL (filtered)
- Query-aware caching
- Parallel/concurrent pagination (reduces 28 min to ~3-4 min)
"""
import os
import json
import hashlib
import logging
import asyncio
import time
import random
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple, TYPE_CHECKING
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

logger = logging.getLogger(__name__)

# Try to import aiohttp for async HTTP
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logger.warning("aiohttp not installed - parallel pagination disabled. Install with: pip install aiohttp")

from config.settings import NetSuiteConfig, get_config

# Avoid circular imports
if TYPE_CHECKING:
    from src.core.query_parser import ParsedQuery

# Dynamic registry import (lazy to avoid circular dependency)
try:
    from src.core.dynamic_registry import get_dynamic_registry
    DYNAMIC_REGISTRY_AVAILABLE = True
except ImportError:
    DYNAMIC_REGISTRY_AVAILABLE = False
    logger.warning("Dynamic registry not available")

# Filter builder import
try:
    from src.core.netsuite_filter_builder import (
        NetSuiteFilterBuilder,
        NetSuiteFilterParams,
        get_filter_builder,
    )
    FILTER_BUILDER_AVAILABLE = True
except ImportError:
    FILTER_BUILDER_AVAILABLE = False
    logger.warning("Filter builder not available")

@dataclass
class SavedSearchResult:
    """Container for saved search results with metadata."""
    data: List[Dict[str, Any]]
    search_id: str
    retrieved_at: datetime
    row_count: int
    column_names: List[str]
    execution_time_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "data": self.data,
            "search_id": self.search_id,
            "retrieved_at": self.retrieved_at.isoformat(),
            "row_count": self.row_count,
            "column_names": self.column_names,
            "execution_time_ms": self.execution_time_ms,
        }

class OneLoginAuthenticator:
    """
    OneLogin SSO authentication handler.
    
    Implements OAuth 2.0 flow with OneLogin as IdP for NetSuite.
    """
    
    def __init__(self, config: NetSuiteConfig):
        self.config = config
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
    
    def get_access_token(self) -> str:
        """Get valid access token, refreshing if necessary."""
        if self._is_token_valid():
            return self._access_token
        
        return self._refresh_token()
    
    def _is_token_valid(self) -> bool:
        """Check if current token is still valid."""
        if not self._access_token or not self._token_expiry:
            return False
        # Add 5 minute buffer
        return datetime.utcnow() < (self._token_expiry - timedelta(minutes=5))
    
    def _refresh_token(self) -> str:
        """Obtain new access token from OneLogin."""
        token_url = f"https://{self.config.onelogin_subdomain}.onelogin.com/oidc/2/token"
        
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.config.onelogin_client_id,
            "client_secret": self.config.onelogin_client_secret,
            "scope": "openid profile",
        }
        
        try:
            response = requests.post(token_url, data=payload)
            response.raise_for_status()
            
            token_data = response.json()
            self._access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3600)
            self._token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
            
            logger.info("OneLogin access token refreshed successfully")
            return self._access_token
            
        except requests.RequestException as e:
            logger.error(f"OneLogin authentication failed: {e}")
            raise AuthenticationError(f"Failed to authenticate with OneLogin: {e}")

class NetSuiteRESTClient:
    """
    NetSuite REST API client with Token-Based Authentication.
    
    Supports saved search execution via RESTlet, SuiteQL, and REST endpoints.
    """
    
    def __init__(self, config: NetSuiteConfig):
        self.config = config
        self.base_url = f"https://{config.account_id}.suitetalk.api.netsuite.com"
        self.restlet_url = config.restlet_url
        self.filter_builder = get_filter_builder() if FILTER_BUILDER_AVAILABLE else None
    
    def _get_auth_headers(self, method: str, url: str) -> Dict[str, str]:
        """Generate OAuth 1.0 headers for NetSuite TBA."""
        import time
        import hmac
        import base64
        import urllib.parse
        
        timestamp = str(int(time.time()))
        nonce = hashlib.sha256(f"{timestamp}{os.urandom(8).hex()}".encode()).hexdigest()[:32]
        
        # OAuth parameters (without realm - realm goes in header separately)
        oauth_params = {
            "oauth_consumer_key": self.config.consumer_key,
            "oauth_token": self.config.token_id,
            "oauth_signature_method": "HMAC-SHA256",
            "oauth_timestamp": timestamp,
            "oauth_nonce": nonce,
            "oauth_version": "1.0",
        }
        
        # Create signature base string
        base_string = self._create_signature_base_string(method, url, oauth_params)
        
        # Create signing key
        signing_key = f"{urllib.parse.quote(self.config.consumer_secret, safe='')}&{urllib.parse.quote(self.config.token_secret, safe='')}"
        
        # Create signature
        signature = base64.b64encode(
            hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha256).digest()
        ).decode()
        
        oauth_params["oauth_signature"] = signature
        
        # Build Authorization header with realm first
        realm = self.config.account_id.replace("_", "-")
        auth_parts = [f'realm="{realm}"']
        auth_parts.extend(
            f'{k}="{urllib.parse.quote(str(v), safe="")}"'
            for k, v in sorted(oauth_params.items())
        )
        auth_header = "OAuth " + ", ".join(auth_parts)
        
        return {
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "Prefer": "transient",
        }
    
    def _create_signature_base_string(self, method: str, url: str, oauth_params: Dict[str, str]) -> str:
        """Create OAuth signature base string."""
        import urllib.parse
        
        # Sort and encode parameters (excluding realm)
        sorted_params = sorted(oauth_params.items())
        param_string = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted_params
        )
        
        # Create base string with actual method and URL
        return f"{method}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(param_string, safe='')}"
    
    def execute_saved_search(
        self,
        search_id: Optional[str] = None,
        parsed_query: Optional['ParsedQuery'] = None,
        use_suiteql_optimization: bool = False,
    ) -> SavedSearchResult:
        """
        Execute a saved search via RESTlet with intelligent filtering.
        
        NOTE: Server-side filtering is currently DISABLED due to accuracy issues.
        All queries use unfiltered fetch + Python-side filtering for accuracy.
        
        Previous behavior (DISABLED):
        - Used server-side filtering when registry was valid
        - Caused 91.5% data loss (133 rows vs ~400K expected)
        
        Current behavior:
        - Always uses unfiltered fetch from RESTlet
        - Python-side filtering applied to full dataset
        - Registry updated from unfiltered data
        """
        search_id = search_id or self.config.saved_search_id
        start_time = datetime.utcnow()
        
        if not self.restlet_url:
            raise DataRetrievalError("RESTlet not configured")
        
        if not search_id:
            raise ValueError("No saved search ID provided")
        
        # DECISION: Should we use server-side filtering?
        # ENABLED: Server-side filtering now works correctly for all departments
        # - Fixed: RESTlet now uses 'formulatext' field instead of 'name' with 'department' join
        # - Verified: Works for both SDR and Product Management departments
        # - See COMPREHENSIVE_FILTER_COMPARISON.md for test results
        registry = get_dynamic_registry()
        use_filtering = False  # Will be set to True if conditions met
        filter_params = None
        
        if registry.needs_refresh() or registry.is_empty():
            # Registry needs data - do UNFILTERED fetch
            logger.info("Registry needs refresh - using unfiltered fetch to rebuild")
            use_filtering = False
        elif parsed_query and self.filter_builder:
            # Registry is valid - safe to use filtering
            filter_params = self.filter_builder.build_from_parsed_query(parsed_query)
            use_filtering = filter_params.has_filters()
            if use_filtering:
                logger.info(f"Using server-side filtering: {filter_params.describe()}")
            else:
                logger.info("No filterable criteria in query - using unfiltered fetch")
        else:
            logger.info("No parsed_query provided - using unfiltered fetch")
        
        # Execute fetch with or without filters
        # Note: ThreadPoolExecutor-based parallel fetching works without aiohttp
        # Only async/await-based fetching requires aiohttp
        use_parallel = os.getenv("NETSUITE_PARALLEL_FETCH", "true").lower() == "true"
        
        if use_parallel:
            # Use parallel filtered method (uses ThreadPoolExecutor, works without aiohttp)
            result = self._execute_via_restlet_parallel_filtered(
                search_id, start_time, filter_params if use_filtering else None
            )
        else:
            # Sequential fetching
            result = self._execute_via_restlet_filtered(
                search_id, start_time, filter_params if use_filtering else None
            )
        
        # Update registry from UNFILTERED fetches only
        if not use_filtering:
            self._update_registry_from_data(result.data)
        
        return result
    
    def _execute_via_restlet(self, search_id: str, start_time: datetime) -> SavedSearchResult:
        """
        Execute saved search via deployed RESTlet.
        """
        # Parse the RESTlet URL to get base URL for OAuth
        from urllib.parse import urlparse, parse_qs
        
        parsed = urlparse(self.restlet_url)
        base_restlet_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        existing_params = parse_qs(parsed.query)
        
        # Flatten existing params and add our params
        query_params = {k: v[0] if isinstance(v, list) else v for k, v in existing_params.items()}
        query_params["searchId"] = search_id
        # Use page size of 1000 (RESTlet max per page)
        query_params["pageSize"] = os.getenv("NETSUITE_PAGE_SIZE", "1000")
        
        # No limit on results - fetch all data from the saved search
        # The saved search should be configured to return only relevant data
        max_results = None  # Fetch all rows
        
        all_results = []
        current_page = 0
        total_pages = 1
        columns = []
        
        while current_page < total_pages:
            # Check if we've reached the max results limit (if set)
            if max_results is not None and len(all_results) >= max_results:
                logger.info(f"Reached max results limit ({max_results}), stopping pagination")
                break
                
            query_params["page"] = str(current_page)
            
            # Generate OAuth headers for RESTlet
            headers = self._get_auth_headers_for_restlet("GET", base_restlet_url, query_params)
            
            # Build full URL
            query_string = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in query_params.items())
            full_url = f"{base_restlet_url}?{query_string}"
            
            logger.info(f"Calling RESTlet page {current_page + 1}/{total_pages}...")
            
            response = requests.get(full_url, headers=headers, timeout=120)
            
            if response.status_code != 200:
                logger.error(f"RESTlet error: {response.status_code} - {response.text[:500]}")
                raise DataRetrievalError(f"RESTlet returned {response.status_code}: {response.text[:200]}")
            
            result = response.json()
            
            if not result.get("success"):
                error_msg = result.get("error", "Unknown error")
                raise DataRetrievalError(f"RESTlet error: {error_msg}")
            
            # Get metadata from first response
            if current_page == 0:
                columns = result.get("columns", [])
                total_pages = result.get("totalPages", 1)
                total_in_search = result.get('totalResults', 0)
                logger.info(f"Total in saved search: {total_in_search}, Pages: {total_pages}, Fetching up to {max_results}")
            
            # Collect results
            page_results = result.get("results", [])
            all_results.extend(page_results)
            logger.info(f"Retrieved {len(page_results)} results from page {current_page + 1} (total so far: {len(all_results)})")
            
            current_page += 1
        
        # Extract column names
        column_names = [col.get("name") or col.get("label") for col in columns]
        if all_results and not column_names:
            column_names = [k for k in all_results[0].keys() if not k.startswith("_")]
        
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        pages_per_second = total_pages / (execution_time / 1000) if execution_time > 0 else 0
        
        logger.info(
            f"Successfully retrieved {len(all_results)} total results via RESTlet "
            f"({pages_per_second:.2f} pages/sec)"
        )
        
        return SavedSearchResult(
            data=all_results,
            search_id=search_id,
            retrieved_at=datetime.utcnow(),
            row_count=len(all_results),
            column_names=column_names,
            execution_time_ms=execution_time,
        )
    
    def _execute_via_restlet_filtered(
        self,
        search_id: str,
        start_time: datetime,
        filter_params: Optional['NetSuiteFilterParams'] = None,
    ) -> SavedSearchResult:
        """Execute saved search with optional server-side filtering (sequential)."""
        from urllib.parse import urlparse, parse_qs
        
        parsed = urlparse(self.restlet_url)
        base_restlet_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        existing_params = parse_qs(parsed.query)
        
        query_params = {k: v[0] if isinstance(v, list) else v for k, v in existing_params.items()}
        query_params["searchId"] = search_id
        query_params["pageSize"] = os.getenv("NETSUITE_PAGE_SIZE", "1000")
        
        # Add filter parameters if provided
        if filter_params:
            query_params.update(filter_params.to_query_params())
            logger.debug(f"Filter params: {filter_params.to_query_params()}")
        
        all_results = []
        current_page = 0
        total_pages = 1
        columns = []
        
        while current_page < total_pages:
            query_params["page"] = str(current_page)
            
            headers = self._get_auth_headers_for_restlet("GET", base_restlet_url, query_params)
            query_string = "&".join(
                f"{k}={requests.utils.quote(str(v))}" 
                for k, v in query_params.items()
            )
            full_url = f"{base_restlet_url}?{query_string}"
            
            logger.info(f"Fetching page {current_page + 1}/{total_pages}...")
            response = requests.get(full_url, headers=headers, timeout=120)
            
            if response.status_code != 200:
                error_text = response.text[:1000] if response.text else "No response body"
                logger.error(
                    f"RESTlet HTTP error {response.status_code} for search {search_id} (page {current_page}):\n"
                    f"URL: {full_url[:200]}...\n"
                    f"Response: {error_text}"
                )
                raise DataRetrievalError(
                    f"RESTlet returned {response.status_code}: {error_text[:200]}"
                )
            
            try:
                result = response.json()
            except Exception as e:
                error_text = response.text[:1000] if response.text else "No response body"
                logger.error(
                    f"Failed to parse RESTlet JSON response for search {search_id} (page {current_page}):\n"
                    f"URL: {full_url[:200]}...\n"
                    f"Response text: {error_text}\n"
                    f"Parse error: {e}"
                )
                raise DataRetrievalError(
                    f"RESTlet returned invalid JSON: {error_text[:200]}"
                )
            
            if not result.get("success"):
                error_msg = result.get('error', 'Unknown error')
                error_details = result.get('errorDetails', {})
                error_stack = result.get('errorStack', '')
                
                # Log comprehensive error details
                logger.error(
                    f"RESTlet error for search {search_id} (page {current_page}):\n"
                    f"Error: {error_msg}\n"
                    f"Error Details: {error_details}\n"
                    f"Error Stack: {error_stack[:500] if error_stack else 'N/A'}\n"
                    f"Filters Applied: {filter_params}\n"
                    f"Full Response: {json.dumps(result, indent=2)[:1000]}"
                )
                
                # Build detailed error message
                detailed_error = f"RESTlet error: {error_msg}"
                if error_details:
                    detailed_error += f"\nDetails: {json.dumps(error_details)}"
                if error_stack:
                    detailed_error += f"\nStack trace: {error_stack[:500]}"
                
                raise DataRetrievalError(detailed_error)
            
            # Process RESTlet v2.2+ metadata (version, filterWarnings)
            if current_page == 0:
                self._process_restlet_response_metadata(result, search_id, current_page)
            
            if current_page == 0:
                columns = result.get("columns", [])
                total_pages = result.get("totalPages", 1)
                total_results = result.get("totalResults", 0)
                filters_applied = result.get("filtersApplied", 0)
                
                logger.info(
                    f"Query results: {total_results:,} rows, {total_pages} pages"
                    f"{f', {filters_applied} server-side filters applied' if filters_applied else ''}"
                )
            
            page_results = result.get("results", [])
            all_results.extend(page_results)
            current_page += 1
        
        column_names = [col.get("name") or col.get("label") for col in columns]
        if all_results and not column_names:
            column_names = [k for k in all_results[0].keys() if not k.startswith("_")]
        
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        logger.info(f"Retrieved {len(all_results):,} rows in {execution_time/1000:.1f}s")
        
        return SavedSearchResult(
            data=all_results,
            search_id=search_id,
            retrieved_at=datetime.utcnow(),
            row_count=len(all_results),
            column_names=column_names,
            execution_time_ms=execution_time,
        )
    
    def _execute_via_restlet_parallel_filtered(
        self,
        search_id: str,
        start_time: datetime,
        filter_params: Optional['NetSuiteFilterParams'] = None,
    ) -> SavedSearchResult:
        """Execute saved search with optional server-side filtering (parallel)."""
        from urllib.parse import urlparse, parse_qs
        
        parsed = urlparse(self.restlet_url)
        base_restlet_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        existing_params = parse_qs(parsed.query)
        
        page_size = os.getenv("NETSUITE_PAGE_SIZE", "1000")
        
        query_params = {k: v[0] if isinstance(v, list) else v for k, v in existing_params.items()}
        query_params["searchId"] = search_id
        query_params["pageSize"] = page_size
        
        # Add filter parameters if provided
        if filter_params:
            query_params.update(filter_params.to_query_params())
            logger.debug(f"Filter params: {filter_params.to_query_params()}")
        
        # Fetch first page for metadata
        query_params["page"] = "0"
        headers = self._get_auth_headers_for_restlet("GET", base_restlet_url, query_params)
        query_string = "&".join(
            f"{k}={requests.utils.quote(str(v))}" 
            for k, v in query_params.items()
        )
        full_url = f"{base_restlet_url}?{query_string}"
        
        logger.info("Fetching first page for metadata...")
        response = requests.get(full_url, headers=headers, timeout=120)
        
        if response.status_code != 200:
            error_text = response.text[:1000] if response.text else "No response body"
            logger.error(
                f"RESTlet HTTP error {response.status_code} for search {search_id}:\n"
                f"URL: {full_url[:200]}...\n"
                f"Response: {error_text}"
            )
            raise DataRetrievalError(
                f"RESTlet returned {response.status_code}: {error_text[:200]}"
            )
        
        try:
            first_result = response.json()
        except Exception as e:
            error_text = response.text[:1000] if response.text else "No response body"
            logger.error(
                f"Failed to parse RESTlet JSON response for search {search_id}:\n"
                f"URL: {full_url[:200]}...\n"
                f"Response text: {error_text}\n"
                f"Parse error: {e}"
            )
            raise DataRetrievalError(
                f"RESTlet returned invalid JSON: {error_text[:200]}"
            )
        
        if not first_result.get("success"):
            error_msg = first_result.get('error', 'Unknown error')
            error_details = first_result.get('errorDetails', {})
            error_stack = first_result.get('errorStack', '')
            
            # Log comprehensive error details
            logger.error(
                f"RESTlet error for search {search_id}:\n"
                f"Error: {error_msg}\n"
                f"Error Details: {error_details}\n"
                f"Error Stack: {error_stack[:500] if error_stack else 'N/A'}\n"
                f"Filters Applied: {filter_params}\n"
                f"Full Response: {json.dumps(first_result, indent=2)[:1000]}"
            )
            
            # Build detailed error message
            detailed_error = f"RESTlet error: {error_msg}"
            if error_details:
                detailed_error += f"\nDetails: {json.dumps(error_details)}"
            if error_stack:
                detailed_error += f"\nStack trace: {error_stack[:500]}"
            
            raise DataRetrievalError(detailed_error)
        
        # Process RESTlet v2.2+ metadata (version, filterWarnings)
        self._process_restlet_response_metadata(first_result, search_id, page=0)
        
        columns = first_result.get("columns", [])
        total_pages = first_result.get("totalPages", 1)
        total_results = first_result.get("totalResults", 0)
        first_page_results = first_result.get("results", [])
        filters_applied = first_result.get("filtersApplied", 0)
        
        logger.info(
            f"Query results: {total_results:,} rows, {total_pages} pages"
            f"{f', {filters_applied} server-side filters applied' if filters_applied else ''}"
        )
        
        # Remove page param for parallel fetch
        del query_params["page"]
        
        if total_pages <= 1:
            all_results = first_page_results
        elif self._should_use_parallel_fetch(total_pages):
            logger.info(f"Using parallel fetch for {total_pages} pages")
            
            # Use ThreadPoolExecutor - works regardless of event loop state
            try:
                all_results = self._fetch_all_pages_threaded(
                    base_restlet_url,
                    query_params,
                    total_pages,
                    first_page_results,
                )
            except Exception as e:
                logger.warning(f"Threaded parallel fetch failed, falling back to sequential: {e}")
                return self._execute_via_restlet_filtered(search_id, start_time, filter_params)
        else:
            logger.info(f"Using sequential fetch for {total_pages} pages (below parallel threshold)")
            return self._execute_via_restlet_filtered(search_id, start_time, filter_params)
        
        column_names = [col.get("name") or col.get("label") for col in columns]
        if all_results and not column_names:
            column_names = [k for k in all_results[0].keys() if not k.startswith("_")]
        
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        pages_per_second = total_pages / (execution_time / 1000) if execution_time > 0 else 0
        
        logger.info(
            f"Retrieved {len(all_results):,} rows in {execution_time/1000:.1f}s "
            f"({pages_per_second:.1f} pages/sec)"
        )
        
        return SavedSearchResult(
            data=all_results,
            search_id=search_id,
            retrieved_at=datetime.utcnow(),
            row_count=len(all_results),
            column_names=column_names,
            execution_time_ms=execution_time,
        )
    
    def _process_restlet_response_metadata(self, result: Dict[str, Any], search_id: str, page: int = 0):
        """
        Process RESTlet v2.2+ response metadata: version checking and filter warnings.
        
        This method handles:
        - RESTlet version logging (v2.2+ includes version field)
        - filterWarnings processing (new in v2.2 for periods not found, etc.)
        - filterErrors processing (existing error handling)
        
        Args:
            result: Parsed JSON response from RESTlet
            search_id: Search ID for logging context
            page: Page number (0 for first page, used in logging)
        """
        # Log RESTlet version (helps debugging and confirms v2.2+)
        restlet_version = result.get("version", "unknown")
        if restlet_version != "unknown":
            if page == 0:  # Only log version on first page to avoid spam
                logger.info(f"RESTlet version: {restlet_version}")
            
            # Warn if version is below 2.2 (period ID conversion may not work)
            try:
                version_parts = restlet_version.split(".")
                major = int(version_parts[0]) if len(version_parts) > 0 else 0
                minor = int(version_parts[1]) if len(version_parts) > 1 else 0
                
                if major < 2 or (major == 2 and minor < 2):
                    logger.warning(
                        f"RESTlet version {restlet_version} is below 2.2. "
                        f"Period ID conversion may not work correctly. "
                        f"Please update to RESTlet v2.2+ for proper period filtering."
                    )
            except (ValueError, IndexError):
                # Version string doesn't match expected format, log as debug
                logger.debug(f"RESTlet version format unexpected: {restlet_version}")
        
        # Handle filter warnings (new in v2.2)
        # These are non-fatal warnings about filter issues (e.g., periods not found)
        filter_warnings = result.get("filterWarnings", [])
        if filter_warnings:
            for warning in filter_warnings:
                warning_type = warning.get("type", "unknown")
                
                if warning_type == "periodNames":
                    # Period names that couldn't be found in NetSuite
                    not_found = warning.get("notFound", [])
                    if not_found:
                        logger.warning(
                            f"RESTlet: {len(not_found)} period(s) not found in NetSuite: "
                            f"{', '.join(not_found[:5])}"
                            f"{'...' if len(not_found) > 5 else ''}. "
                            f"RESTlet will fall back to date range filtering."
                        )
                elif warning_type == "dateRange":
                    # Date range filter issue
                    warning_msg = warning.get("message", "Date range filter warning")
                    logger.warning(f"RESTlet date range filter warning: {warning_msg}")
                else:
                    # Generic warning
                    warning_msg = warning.get("message", str(warning))
                    logger.warning(f"RESTlet filter warning ({warning_type}): {warning_msg}")
        
        # Handle filter errors (existing error handling - these are more severe)
        filter_errors = result.get("filterErrors", [])
        if filter_errors:
            for error in filter_errors:
                error_type = error.get("type", "unknown")
                error_msg = error.get("message", str(error))
                logger.error(f"RESTlet filter error ({error_type}): {error_msg}")
    
    def _update_registry_from_data(self, data: List[Dict]):
        """Update dynamic registry from fetched data."""
        try:
            registry = get_dynamic_registry()
            if registry.needs_refresh() and data:
                logger.info("Updating dynamic registry from fetched data...")
                registry.build_from_data(data, force_rebuild=False)
                logger.info(f"Registry updated: {registry.stats}")
        except Exception as e:
            logger.warning(f"Failed to update registry: {e}")
    
    def _fetch_page_sync(
        self,
        base_url: str,
        query_params: Dict[str, str],
        page: int,
        request_delay: float = 0.0,
        max_retries: int = 3,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Fetch a single page synchronously with retry logic.
        
        This is used by ThreadPoolExecutor for parallel fetching.
        Includes staggered delay to prevent OAuth signature collisions.
        
        Args:
            base_url: RESTlet base URL
            query_params: Query parameters (without page)
            page: Page number to fetch
            request_delay: Delay before making request (for staggering)
            max_retries: Maximum retry attempts
        
        Returns:
            Tuple of (page_number, results)
        """
        # Staggered delay BEFORE generating OAuth headers
        # This ensures unique timestamps across parallel requests
        if request_delay > 0:
            time.sleep(request_delay)
        
        # Build params with page number
        params = dict(query_params)
        params["page"] = str(page)
        
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                # Generate FRESH OAuth headers for each attempt
                # This must happen AFTER any delays to ensure valid timestamp
                headers = self._get_auth_headers_for_restlet("GET", base_url, params)
                
                # Build the full URL
                query_string = "&".join(
                    f"{k}={requests.utils.quote(str(v))}" 
                    for k, v in params.items()
                )
                full_url = f"{base_url}?{query_string}"
                
                # Make the request
                response = requests.get(full_url, headers=headers, timeout=120)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("success"):
                        return page, result.get("results", [])
                    else:
                        error_msg = result.get("error", "Unknown error")
                        
                        # Check for rate limit in response body
                        if "SSS_REQUEST_LIMIT_EXCEEDED" in str(error_msg):
                            if attempt < max_retries:
                                wait_time = (2 ** attempt) + random.uniform(0.5, 1.5)
                                logger.warning(
                                    f"Page {page} rate limited (attempt {attempt + 1}/{max_retries + 1}), "
                                    f"waiting {wait_time:.1f}s..."
                                )
                                time.sleep(wait_time)
                                continue
                        
                        last_error = f"RESTlet error: {error_msg}"
                
                elif response.status_code == 400:
                    # Bad request - likely OAuth signature issue or malformed request
                    text = response.text[:500]
                    logger.warning(f"Page {page} got 400 Bad Request: {text}")
                    
                    if attempt < max_retries:
                        wait_time = (2 ** attempt) + random.uniform(0.1, 0.5)
                        logger.warning(
                            f"Page {page} bad request (attempt {attempt + 1}/{max_retries + 1}), "
                            f"retrying in {wait_time:.1f}s..."
                        )
                        time.sleep(wait_time)
                        continue
                    
                    last_error = f"Bad request: {text}"
                
                elif response.status_code == 403:
                    # Auth failure
                    text = response.text[:200]
                    
                    if attempt < max_retries:
                        wait_time = (2 ** attempt) + random.uniform(0.5, 1.0)
                        logger.warning(
                            f"Page {page} auth failed (attempt {attempt + 1}/{max_retries + 1}), "
                            f"retrying in {wait_time:.1f}s..."
                        )
                        time.sleep(wait_time)
                        continue
                    
                    last_error = f"Auth failed (403): {text}"
                
                elif response.status_code == 429:
                    # Explicit rate limit
                    if attempt < max_retries:
                        wait_time = (2 ** attempt) + random.uniform(1.0, 2.0)
                        logger.warning(
                            f"Page {page} rate limited (attempt {attempt + 1}/{max_retries + 1}), "
                            f"waiting {wait_time:.1f}s..."
                        )
                        time.sleep(wait_time)
                        continue
                    
                    last_error = f"Rate limited (429) after {max_retries + 1} attempts"
                
                else:
                    text = response.text[:200]
                    last_error = f"HTTP {response.status_code}: {text}"
                    
                    if attempt < max_retries:
                        wait_time = 2 ** attempt
                        logger.warning(
                            f"Page {page} got {response.status_code}, "
                            f"retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                        continue
                        
            except requests.exceptions.Timeout:
                last_error = "Request timeout"
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(f"Page {page} timed out, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
            
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(f"Page {page} error: {e}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
            
            except Exception as e:
                last_error = f"Unexpected error: {e}"
                logger.error(f"Page {page} unexpected error: {e}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
        
        logger.error(f"Page {page} failed after {max_retries + 1} attempts: {last_error}")
        raise DataRetrievalError(f"Page {page} failed: {last_error}")

    def _fetch_all_pages_threaded(
        self,
        base_url: str,
        query_params: Dict[str, str],
        total_pages: int,
        first_page_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Fetch all pages using ThreadPoolExecutor with OAuth-safe staggering.
        
        This method uses staggered request submission to prevent OAuth
        signature collisions that cause INVALID_LOGIN_ATTEMPT errors.
        
        Args:
            base_url: RESTlet base URL
            query_params: Base query parameters (without page number)
            total_pages: Total number of pages to fetch
            first_page_results: Results from page 0 (already fetched)
        
        Returns:
            All results combined in page order
        """
        # CRITICAL: Keep max_workers LOW to prevent OAuth collisions
        # NetSuite's OAuth 1.0a doesn't handle many simultaneous auth attempts well
        max_workers = min(int(os.getenv("NETSUITE_MAX_CONCURRENT_PAGES", "5")), 6)
        
        # Delay between batches (seconds)
        batch_delay = float(os.getenv("NETSUITE_BATCH_DELAY_SECONDS", "2.0"))
        
        # Stagger delay between requests within a batch (seconds)
        # This ensures each request gets a unique OAuth timestamp/nonce
        intra_batch_delay = float(os.getenv("NETSUITE_INTRA_BATCH_DELAY", "0.3"))
        
        # Page 0 is already fetched
        pages_to_fetch = list(range(1, total_pages))
        
        if not pages_to_fetch:
            return first_page_results
        
        logger.info(
            f"Fetching {len(pages_to_fetch)} pages using ThreadPoolExecutor "
            f"(max workers: {max_workers}, stagger: {intra_batch_delay}s)"
        )
        
        results_by_page: Dict[int, List[Dict]] = {0: first_page_results}
        failed_pages: List[Tuple[int, str]] = []
        
        total_batches = (len(pages_to_fetch) + max_workers - 1) // max_workers
        
        for batch_idx, batch_start in enumerate(range(0, len(pages_to_fetch), max_workers)):
            batch_pages = pages_to_fetch[batch_start:batch_start + max_workers]
            batch_num = batch_idx + 1
            
            logger.info(
                f"Processing batch {batch_num}/{total_batches}: "
                f"pages {batch_pages[0]}-{batch_pages[-1]} ({len(batch_pages)} pages)"
            )
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit requests with staggered delays to prevent OAuth collisions
                future_to_page = {}
                for i, page in enumerate(batch_pages):
                    # Stagger each request within the batch
                    stagger_delay = i * intra_batch_delay
                    future = executor.submit(
                        self._fetch_page_sync,
                        base_url,
                        query_params,
                        page,
                        stagger_delay,  # Pass the stagger delay
                    )
                    future_to_page[future] = page
                
                # Collect results
                for future in as_completed(future_to_page):
                    page = future_to_page[future]
                    try:
                        page_num, page_data = future.result()
                        results_by_page[page_num] = page_data
                        logger.debug(f"Page {page_num}: {len(page_data)} rows")
                    except Exception as e:
                        error_msg = str(e)
                        logger.warning(f"Page {page} failed in batch: {error_msg}")
                        failed_pages.append((page, error_msg))
            
            # Delay between batches to let NetSuite's auth system recover
            if batch_start + max_workers < len(pages_to_fetch):
                logger.debug(f"Batch delay: {batch_delay}s")
                time.sleep(batch_delay)
        
        # Retry failed pages one at a time with longer delays
        if failed_pages:
            logger.info(f"Retrying {len(failed_pages)} failed pages sequentially...")
            
            for page, original_error in failed_pages:
                logger.info(f"Retrying page {page} (original error: {original_error[:50]}...)")
                
                # Longer delay before retry
                time.sleep(3.0)
                
                try:
                    page_num, page_data = self._fetch_page_sync(
                        base_url, query_params, page, 
                        request_delay=0,  # No additional delay needed
                        max_retries=5,    # More retries for failed pages
                    )
                    results_by_page[page_num] = page_data
                    logger.info(f"Page {page_num} succeeded on retry ({len(page_data)} rows)")
                except Exception as e:
                    logger.error(f"Page {page} failed permanently: {e}")
                    raise DataRetrievalError(
                        f"Failed to fetch page {page} after all retries. "
                        f"Try reducing NETSUITE_MAX_CONCURRENT_PAGES to 3-4."
                    )
        
        # Combine results in page order
        all_results = []
        for page in range(total_pages):
            page_results = results_by_page.get(page, [])
            all_results.extend(page_results)
        
        logger.info(
            f"Parallel fetch complete: {len(all_results):,} total rows "
            f"from {total_pages} pages"
        )
        
        return all_results

    def _get_auth_headers_for_restlet(self, method: str, url: str, query_params: dict = None) -> Dict[str, str]:
        """Generate OAuth 1.0 headers for RESTlet calls, including query params in signature."""
        import time
        import hmac
        import base64
        import urllib.parse
        
        timestamp = str(int(time.time()))
        nonce = hashlib.sha256(f"{timestamp}{os.urandom(8).hex()}".encode()).hexdigest()[:32]
        
        oauth_params = {
            "oauth_consumer_key": self.config.consumer_key,
            "oauth_token": self.config.token_id,
            "oauth_signature_method": "HMAC-SHA256",
            "oauth_timestamp": timestamp,
            "oauth_nonce": nonce,
            "oauth_version": "1.0",
        }
        
        # Combine OAuth params with query params for signature
        all_params = dict(oauth_params)
        if query_params:
            all_params.update(query_params)
        
        # Sort ALL parameters for signature base string
        sorted_params = sorted(all_params.items())
        param_string = "&".join(
            f"{urllib.parse.quote(str(k), safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted_params
        )
        
        # Base string uses URL without query string
        base_string = f"{method}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(param_string, safe='')}"
        
        signing_key = f"{urllib.parse.quote(self.config.consumer_secret, safe='')}&{urllib.parse.quote(self.config.token_secret, safe='')}"
        signature = base64.b64encode(
            hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha256).digest()
        ).decode()
        
        oauth_params["oauth_signature"] = signature
        realm = self.config.account_id.replace("_", "-")
        
        auth_parts = [f'realm="{realm}"']
        auth_parts.extend(
            f'{k}="{urllib.parse.quote(str(v), safe="")}"'
            for k, v in sorted(oauth_params.items())
        )
        auth_header = "OAuth " + ", ".join(auth_parts)
        
        return {
            "Authorization": auth_header,
            "Content-Type": "application/json",
        }
    
    # =========================================================================
    # PARALLEL PAGINATION (Phase 2.1)
    # =========================================================================
    
    def _should_use_parallel_fetch(self, total_pages: int) -> bool:
        """Determine if parallel fetching should be used.
        
        Note: ThreadPoolExecutor-based parallel fetching works without aiohttp.
        Only async/await-based fetching requires aiohttp.
        """
        # Check environment variable
        parallel_enabled = os.getenv("NETSUITE_PARALLEL_FETCH", "true").lower() == "true"
        if not parallel_enabled:
            return False
        
        # Only use parallel for multi-page fetches
        min_pages_for_parallel = int(os.getenv("NETSUITE_PARALLEL_MIN_PAGES", "3"))
        return total_pages >= min_pages_for_parallel
    
    async def _fetch_page_async(
        self,
        session: 'aiohttp.ClientSession',
        base_url: str,
        query_params: Dict[str, str],
        page: int,
        max_retries: int = 3,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Fetch a single page asynchronously with retry logic.
        
        Returns:
            Tuple of (page_number, results)
        """
        params = dict(query_params)
        params["page"] = str(page)
        
        headers = self._get_auth_headers_for_restlet("GET", base_url, params)
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        full_url = f"{base_url}?{query_string}"
        
        for attempt in range(max_retries + 1):
            try:
                async with session.get(full_url, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as response:
                    if response.status != 200:
                        text = await response.text()
                        
                        # Check if it's a rate limit error
                        is_rate_limit = (
                            response.status == 429 or 
                            "SSS_REQUEST_LIMIT_EXCEEDED" in text or
                            "REQUEST_LIMIT_EXCEEDED" in text
                        )
                        
                        if is_rate_limit and attempt < max_retries:
                            # Exponential backoff: 2^attempt seconds
                            wait_time = 2 ** attempt
                            logger.warning(f"Page {page} rate limited (attempt {attempt + 1}/{max_retries + 1}), waiting {wait_time}s...")
                            await asyncio.sleep(wait_time)
                            continue
                        
                        logger.error(f"Page {page} failed: {response.status} - {text[:200]}")
                        raise DataRetrievalError(f"Page {page} failed: {response.status}")
                    
                    result = await response.json()
                    
                    if not result.get("success"):
                        error_msg = result.get("error", "Unknown error")
                        
                        # Check if it's a rate limit error in the response body
                        is_rate_limit = (
                            "SSS_REQUEST_LIMIT_EXCEEDED" in str(error_msg) or
                            "REQUEST_LIMIT_EXCEEDED" in str(error_msg)
                        )
                        
                        if is_rate_limit and attempt < max_retries:
                            wait_time = 2 ** attempt
                            logger.warning(f"Page {page} rate limited (attempt {attempt + 1}/{max_retries + 1}), waiting {wait_time}s...")
                            await asyncio.sleep(wait_time)
                            continue
                        
                        raise DataRetrievalError(f"Page {page} error: {error_msg}")
                    
                    return page, result.get("results", [])
            except asyncio.TimeoutError:
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(f"Page {page} timed out (attempt {attempt + 1}/{max_retries + 1}), retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"Page {page} timed out after {max_retries + 1} attempts")
                raise DataRetrievalError(f"Page {page} timed out")
        
        # Should never reach here, but just in case
        raise DataRetrievalError(f"Page {page} failed after {max_retries + 1} attempts")
    
    async def _fetch_all_pages_parallel(
        self,
        base_url: str,
        query_params: Dict[str, str],
        total_pages: int,
        first_page_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Fetch all pages in parallel with concurrency limit.
        
        Args:
            base_url: RESTlet base URL
            query_params: Base query parameters
            total_pages: Total number of pages to fetch
            first_page_results: Results from page 0 (already fetched)
        
        Returns:
            All results combined in page order
        """
        max_concurrent = int(os.getenv("NETSUITE_MAX_CONCURRENT_PAGES", "10"))
        
        # Page 0 is already fetched, fetch pages 1 to total_pages-1
        pages_to_fetch = list(range(1, total_pages))
        
        if not pages_to_fetch:
            return first_page_results
        
        logger.info(f"Fetching {len(pages_to_fetch)} pages in parallel (max concurrent: {max_concurrent})")
        
        # Results dict to maintain order
        results_by_page: Dict[int, List[Dict]] = {0: first_page_results}
        
        connector = aiohttp.TCPConnector(limit=max_concurrent, limit_per_host=max_concurrent)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Process in batches to respect concurrency limit
            batch_delay = float(os.getenv("NETSUITE_BATCH_DELAY_SECONDS", "0.5"))  # Small delay between batches
            
            for batch_start in range(0, len(pages_to_fetch), max_concurrent):
                batch_pages = pages_to_fetch[batch_start:batch_start + max_concurrent]
                
                tasks = [
                    self._fetch_page_async(session, base_url, query_params, page)
                    for page in batch_pages
                ]
                
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results and handle retries for failed pages
                failed_pages = []
                for i, result in enumerate(batch_results):
                    if isinstance(result, Exception):
                        page_num = batch_pages[i]
                        logger.warning(f"Page {page_num} failed: {result}")
                        failed_pages.append((page_num, result))
                    else:
                        page_num, page_data = result
                        results_by_page[page_num] = page_data
                        logger.debug(f"Page {page_num}: {len(page_data)} rows")
                
                # Retry failed pages individually with backoff
                if failed_pages:
                    logger.info(f"Retrying {len(failed_pages)} failed pages from batch...")
                    for page_num, error in failed_pages:
                        try:
                            # Wait a bit before retrying to avoid rate limits
                            await asyncio.sleep(1)
                            page_num, page_data = await self._fetch_page_async(session, base_url, query_params, page_num)
                            results_by_page[page_num] = page_data
                            logger.info(f"Page {page_num} succeeded on retry")
                        except Exception as retry_error:
                            logger.error(f"Page {page_num} failed after retry: {retry_error}")
                            raise retry_error
                
                logger.info(f"Batch complete: pages {batch_pages[0]}-{batch_pages[-1]} ({len(batch_results)} pages)")
                
                # Small delay between batches to avoid rate limits
                if batch_start + max_concurrent < len(pages_to_fetch) and batch_delay > 0:
                    await asyncio.sleep(batch_delay)
        
        # Combine results in page order
        all_results = []
        for page in range(total_pages):
            all_results.extend(results_by_page.get(page, []))
        
        return all_results
    
    def _execute_via_restlet_parallel(self, search_id: str, start_time: datetime) -> SavedSearchResult:
        """
        Execute saved search via RESTlet with parallel pagination.
        
        This method first fetches page 0 to get metadata, then fetches
        remaining pages in parallel for much faster total retrieval.
        """
        from urllib.parse import urlparse, parse_qs
        
        parsed = urlparse(self.restlet_url)
        base_restlet_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        existing_params = parse_qs(parsed.query)
        
        # Get page size from environment or use default
        # Note: RESTlet caps at 1000 rows per page regardless of requested size
        page_size = os.getenv("NETSUITE_PAGE_SIZE", "1000")
        
        query_params = {k: v[0] if isinstance(v, list) else v for k, v in existing_params.items()}
        query_params["searchId"] = search_id
        query_params["pageSize"] = page_size
        
        # Fetch first page to get metadata
        query_params["page"] = "0"
        headers = self._get_auth_headers_for_restlet("GET", base_restlet_url, query_params)
        query_string = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in query_params.items())
        full_url = f"{base_restlet_url}?{query_string}"
        
        logger.info("Fetching first page to get metadata...")
        response = requests.get(full_url, headers=headers, timeout=120)
        
        if response.status_code != 200:
            logger.error(f"RESTlet error: {response.status_code} - {response.text[:500]}")
            raise DataRetrievalError(f"RESTlet returned {response.status_code}: {response.text[:200]}")
        
        first_result = response.json()
        
        if not first_result.get("success"):
            error_msg = first_result.get("error", "Unknown error")
            raise DataRetrievalError(f"RESTlet error: {error_msg}")
        
        columns = first_result.get("columns", [])
        total_pages = first_result.get("totalPages", 1)
        total_results = first_result.get("totalResults", 0)
        first_page_results = first_result.get("results", [])
        
        logger.info(f"Total results: {total_results}, Pages: {total_pages}")
        
        # Remove page from params for async fetch (it will add its own)
        del query_params["page"]
        
        if total_pages <= 1:
            # Only one page, no need for parallel fetch
            all_results = first_page_results
        else:
            # Check if we should use parallel fetch
            if self._should_use_parallel_fetch(total_pages):
                logger.info(f"Using parallel pagination for {total_pages} pages")
                
                # Use ThreadPoolExecutor - works regardless of event loop state
                try:
                    all_results = self._fetch_all_pages_threaded(
                        base_restlet_url,
                        query_params,
                        total_pages,
                        first_page_results,
                    )
                except Exception as e:
                    logger.warning(f"Threaded parallel fetch failed, falling back to sequential: {e}")
                    # Fall back to sequential
                    return self._execute_via_restlet(search_id, start_time)
            else:
                # Sequential fetch for small page counts or when parallel is disabled
                logger.info(f"Using sequential pagination for {total_pages} pages")
                return self._execute_via_restlet(search_id, start_time)
        
        # Extract column names
        column_names = [col.get("name") or col.get("label") for col in columns]
        if all_results and not column_names:
            column_names = [k for k in all_results[0].keys() if not k.startswith("_")]
        
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        pages_per_second = total_pages / (execution_time / 1000) if execution_time > 0 else 0
        
        logger.info(
            f"PARALLEL: Retrieved {len(all_results)} results in {execution_time/1000:.1f}s "
            f"({pages_per_second:.2f} pages/sec) - {total_pages} pages"
        )
        
        return SavedSearchResult(
            data=all_results,
            search_id=search_id,
            retrieved_at=datetime.utcnow(),
            row_count=len(all_results),
            column_names=column_names,
            execution_time_ms=execution_time,
        )
    
    def _execute_search_via_restlet_simulation(self, search_id: str, start_time: datetime) -> SavedSearchResult:
        """
        Try to get saved search info and run equivalent SuiteQL.
        """
        # First, try to get the saved search definition
        url = f"{self.base_url}/services/rest/record/v1/savedsearch/{search_id}"
        
        try:
            headers = self._get_auth_headers("GET", url)
            response = requests.get(url, headers=headers, timeout=60)
            
            if response.status_code == 200:
                search_def = response.json()
                logger.info(f"Saved search definition: {search_def}")
                # Could parse and build equivalent SuiteQL here
        except Exception as e:
            logger.debug(f"Could not get saved search definition: {e}")
        
        # Fall back to generic query
        logger.warning(f"Could not execute saved search '{search_id}' - it may require a RESTlet")
        raise DataRetrievalError(
            f"Cannot execute saved search '{search_id}' via REST API. "
            f"Options: 1) Ensure the saved search record type is supported, "
            f"2) Create a RESTlet in NetSuite to execute this saved search, "
            f"3) Provide the equivalent SuiteQL query."
        )
    
    def _execute_search_via_suiteql(self, search_id: str, start_time: datetime) -> SavedSearchResult:
        """
        Alternative method: Execute a basic transaction query via SuiteQL.
        Used when saved search API is not available.
        """
        url = f"{self.base_url}/services/rest/query/v1/suiteql"
        
        # Query transaction lines for financial data
        # Using correct NetSuite SuiteQL field names
        query = """
            SELECT 
                tl.id,
                tl.transaction,
                t.tranid,
                t.trandate,
                t.type,
                t.status,
                tl.account,
                a.acctnumber,
                a.acctname,
                a.accttype,
                tl.amount AS lineamount,
                tl.netamount,
                tl.memo,
                tl.department,
                tl.class,
                tl.location
            FROM transactionline tl
            INNER JOIN transaction t ON tl.transaction = t.id
            LEFT JOIN account a ON tl.account = a.id
            WHERE t.trandate >= ADD_MONTHS(SYSDATE, -12)
            AND tl.mainline = 'F'
            ORDER BY t.trandate DESC
            FETCH FIRST 500 ROWS ONLY
        """
        
        headers = self._get_auth_headers("POST", url)
        
        try:
            response = requests.post(
                url,
                json={"q": query},
                headers=headers,
                timeout=60
            )
            response.raise_for_status()
        except requests.RequestException as e:
            # If transaction line query fails, try a simpler query
            logger.warning(f"Transaction line query failed, trying simpler query: {e}")
            return self._execute_simple_query(search_id, start_time)
        
        result_data = response.json()
        items = result_data.get("items", [])
        
        column_names = list(items[0].keys()) if items else []
        column_names = [c for c in column_names if c != 'links']
        
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return SavedSearchResult(
            data=items,
            search_id=search_id,
            retrieved_at=datetime.utcnow(),
            row_count=len(items),
            column_names=column_names,
            execution_time_ms=execution_time,
        )
    
    def _execute_simple_query(self, search_id: str, start_time: datetime) -> SavedSearchResult:
        """
        Simplest fallback: Query just accounts for testing.
        """
        url = f"{self.base_url}/services/rest/query/v1/suiteql"
        
        query = """
            SELECT 
                id,
                acctnumber,
                acctname,
                accttype,
                balance
            FROM account
            WHERE isinactive = 'F'
            ORDER BY acctnumber
            FETCH FIRST 100 ROWS ONLY
        """
        
        headers = self._get_auth_headers("POST", url)
        
        response = requests.post(
            url,
            json={"q": query},
            headers=headers,
            timeout=60
        )
        response.raise_for_status()
        
        result_data = response.json()
        items = result_data.get("items", [])
        
        column_names = list(items[0].keys()) if items else []
        column_names = [c for c in column_names if c != 'links']
        
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return SavedSearchResult(
            data=items,
            search_id=search_id,
            retrieved_at=datetime.utcnow(),
            row_count=len(items),
            column_names=column_names,
            execution_time_ms=execution_time,
        )
    
    def execute_suiteql(self, query: str) -> List[Dict[str, Any]]:
        """Execute raw SuiteQL query."""
        url = f"{self.base_url}/services/rest/query/v1/suiteql"
        
        try:
            headers = self._get_auth_headers("POST", url)
            response = requests.post(
                url, 
                json={"q": query},
                headers=headers,
                timeout=60
            )
            response.raise_for_status()
            return response.json().get("items", [])
        except requests.RequestException as e:
            logger.error(f"SuiteQL query failed: {e}")
            raise DataRetrievalError(f"SuiteQL query failed: {e}")

class DataCache:
    """
    Intelligent file-based cache for saved search results.
    
    Enhanced with:
    - Query-aware caching based on parsed query parameters
    - Cache statistics (hit rate tracking)
    - Configurable TTL
    - Cache warming for common queries
    - Manual invalidation
    """
    
    def __init__(self, cache_dir: str = ".cache/netsuite"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Configurable TTL
        self.ttl_minutes = int(os.getenv("NETSUITE_CACHE_TTL_MINUTES", "15"))
        
        # Statistics
        self._hits = 0
        self._misses = 0
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """Get cache file path for a cache key."""
        safe_id = hashlib.sha256(cache_key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{safe_id}.json"
    
    @staticmethod
    def generate_query_hash(parsed_query: 'ParsedQuery') -> str:
        """
        Generate a deterministic hash for a parsed query.
        
        This ensures that identical query parameters produce the same cache key.
        """
        components = []
        
        # Time period
        if parsed_query.time_period:
            components.append(f"tp:{parsed_query.time_period.start_date}_{parsed_query.time_period.end_date}")
        
        # Departments (sorted for consistency)
        if parsed_query.departments:
            components.append(f"dept:{','.join(sorted(parsed_query.departments))}")
        
        # Account type filter
        if parsed_query.account_type_filter:
            values = parsed_query.account_type_filter.get("values", [])
            filter_type = parsed_query.account_type_filter.get("filter_type", "prefix")
            components.append(f"acct:{filter_type}:{','.join(sorted(values))}")
        
        # Transaction type filter
        if parsed_query.transaction_type_filter:
            components.append(f"txn:{','.join(sorted(parsed_query.transaction_type_filter))}")
        
        # Subsidiaries
        if parsed_query.subsidiaries:
            components.append(f"sub:{','.join(sorted(parsed_query.subsidiaries))}")
        
        hash_input = "|".join(components) if components else "no_filters"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    def get(self, cache_key: str) -> Optional[SavedSearchResult]:
        """Get cached result if valid."""
        cache_path = self._get_cache_path(cache_key)
        
        if not cache_path.exists():
            self._misses += 1
            return None
        
        try:
            with open(cache_path, 'r') as f:
                cached = json.load(f)
            
            cached_time = datetime.fromisoformat(cached["retrieved_at"])
            if datetime.utcnow() - cached_time > timedelta(minutes=self.ttl_minutes):
                self._misses += 1
                logger.debug(f"Cache expired for {cache_key}")
                return None
            
            self._hits += 1
            logger.debug(f"Cache hit for {cache_key}")
            
            return SavedSearchResult(
                data=cached["data"],
                search_id=cached["search_id"],
                retrieved_at=cached_time,
                row_count=cached["row_count"],
                column_names=cached["column_names"],
                execution_time_ms=cached["execution_time_ms"],
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Cache read error for {cache_key}: {e}")
            self._misses += 1
            return None
    
    def get_by_query(self, parsed_query: 'ParsedQuery', search_id: str = None) -> Optional[SavedSearchResult]:
        """
        Get cached result by parsed query parameters.
        
        Args:
            parsed_query: The parsed query to look up
            search_id: Optional search ID prefix
        """
        query_hash = self.generate_query_hash(parsed_query)
        cache_key = f"{search_id or 'query'}_{query_hash}"
        return self.get(cache_key)
    
    def set(self, result: SavedSearchResult) -> None:
        """Cache a search result using its search_id as key."""
        cache_path = self._get_cache_path(result.search_id)
        try:
            with open(cache_path, 'w') as f:
                json.dump(result.to_dict(), f)
            logger.debug(f"Cached result: {result.search_id} ({result.row_count} rows)")
        except IOError as e:
            logger.warning(f"Failed to write cache: {e}")
    
    def set_by_query(
        self,
        parsed_query: 'ParsedQuery',
        result: SavedSearchResult,
        search_id: str = None,
    ) -> None:
        """
        Cache a result keyed by parsed query parameters.
        
        Args:
            parsed_query: The parsed query to key by
            result: The result to cache
            search_id: Optional search ID prefix
        """
        query_hash = self.generate_query_hash(parsed_query)
        cache_key = f"{search_id or 'query'}_{query_hash}"
        
        # Update the result's search_id to match cache key
        result.search_id = cache_key
        self.set(result)
    
    def invalidate(self, cache_key: str) -> bool:
        """
        Invalidate a specific cache entry.
        
        Returns:
            True if entry was found and removed, False otherwise
        """
        cache_path = self._get_cache_path(cache_key)
        if cache_path.exists():
            cache_path.unlink()
            logger.info(f"Invalidated cache: {cache_key}")
            return True
        return False
    
    def invalidate_by_query(self, parsed_query: 'ParsedQuery', search_id: str = None) -> bool:
        """Invalidate cache entry for a specific parsed query."""
        query_hash = self.generate_query_hash(parsed_query)
        cache_key = f"{search_id or 'query'}_{query_hash}"
        return self.invalidate(cache_key)
    
    def clear_all(self) -> int:
        """
        Clear all cache entries.
        
        Returns:
            Number of entries cleared
        """
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
            count += 1
        
        self._hits = 0
        self._misses = 0
        logger.info(f"Cleared {count} cache entries")
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0
        
        # Count cache files and total size
        cache_files = list(self.cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in cache_files)
        
        return {
            "hits": self._hits,
            "misses": self._misses,
            "total_requests": total_requests,
            "hit_rate": hit_rate,
            "hit_rate_percent": f"{hit_rate * 100:.1f}%",
            "cache_entries": len(cache_files),
            "cache_size_bytes": total_size,
            "cache_size_mb": f"{total_size / (1024 * 1024):.2f} MB",
            "ttl_minutes": self.ttl_minutes,
        }
    
    def log_stats(self) -> None:
        """Log cache statistics."""
        stats = self.get_stats()
        logger.info(
            f"Cache stats: {stats['hits']} hits, {stats['misses']} misses, "
            f"{stats['hit_rate_percent']} hit rate, {stats['cache_entries']} entries "
            f"({stats['cache_size_mb']})"
        )

class NetSuiteDataRetriever:
    """
    High-level interface for NetSuite data retrieval.
    
    This is the primary class agents should use for data access.
    Handles caching, validation, and error recovery.
    
    Enhanced with:
    - ParsedQuery support for intelligent SuiteQL optimization
    - Query-aware caching based on filter parameters
    """
    
    def __init__(self, config: Optional[NetSuiteConfig] = None, use_cache: bool = True, update_registry: bool = True):
        self.config = config or get_config().netsuite
        self.client = NetSuiteRESTClient(self.config)
        self.cache = DataCache() if use_cache else None
        self._update_registry = update_registry  # Flag to control registry updates
    
    def get_saved_search_data(
        self, 
        search_id: Optional[str] = None,
        bypass_cache: bool = False,
        parsed_query: Optional['ParsedQuery'] = None,
        use_suiteql_optimization: bool = False,
    ) -> SavedSearchResult:
        """
        Retrieve data from a NetSuite saved search via RESTlet.
        
        Note: SuiteQL optimization has been removed. All queries use RESTlet
        for accurate financial reporting (posting period dates).
        
        Args:
            search_id: Internal ID of the saved search. 
                      Uses configured default if None.
            bypass_cache: Force fresh data retrieval.
            parsed_query: Optional ParsedQuery (used for caching, filters applied in Python).
            use_suiteql_optimization: Deprecated - ignored (always uses RESTlet).
        
        Returns:
            SavedSearchResult with validated data.
        """
        import os
        
        # Check if mock data mode is enabled
        use_mock_data = os.getenv("USE_MOCK_DATA", "false").lower() == "true"
        
        if use_mock_data:
            logger.info("Using MOCK DATA mode - generating fake NetSuite data")
            return self._get_mock_data(parsed_query=parsed_query)
        
        search_id = search_id or self.config.saved_search_id
        
        # Generate cache key based on query parameters
        cache_key = self._generate_cache_key(search_id, parsed_query)
        
        # Check cache first
        if self.cache and not bypass_cache:
            cached = self.cache.get(cache_key)
            if cached:
                logger.info(f"Cache hit for query {cache_key}")
                return cached
        
        # Always use RESTlet for accurate financial data
        result = self.client.execute_saved_search(
            search_id=search_id,
            parsed_query=parsed_query,
            use_suiteql_optimization=False,  # Always False - SuiteQL removed
        )
        
        # Update the search_id to match cache key
        result.search_id = cache_key
        
        # Validate result
        self._validate_result(result)
        
        # NEW: Update dynamic registry if enabled and we have data
        if self._update_registry and result.data:
            self._maybe_update_registry(result.data)
        
        # Cache result
        if self.cache:
            self.cache.set(result)
        
        return result
    
    def _get_mock_data(self, parsed_query: Optional['ParsedQuery'] = None) -> SavedSearchResult:
        """
        Generate mock NetSuite data for testing without exposing real financial data.
        
        Args:
            parsed_query: Optional ParsedQuery to apply filters to mock data generation
        
        Returns:
            SavedSearchResult with mock data
        """
        from src.tools.mock_data_generator import (
            generate_mock_netsuite_data,
            get_mock_column_names,
        )
        from src.core.netsuite_filter_builder import get_filter_builder
        
        # Determine parameters from parsed_query
        periods = None
        departments = None
        account_prefixes = None
        row_count = 1000  # Default row count
        
        if parsed_query:
            # Extract period names using filter builder's helper method
            if parsed_query.time_period:
                filter_builder = get_filter_builder()
                period_names = filter_builder._date_range_to_period_names(
                    parsed_query.time_period.start_date,
                    parsed_query.time_period.end_date
                )
                if period_names:
                    periods = period_names
            
            # Extract departments
            if parsed_query.departments:
                departments = parsed_query.departments
            
            # Extract account prefixes
            if parsed_query.account_type_filter:
                if parsed_query.account_type_filter.get("filter_type") == "prefix":
                    account_prefixes = parsed_query.account_type_filter.get("values", [])
            
            # Estimate row count based on filters (more specific = fewer rows)
            if periods and departments and account_prefixes:
                row_count = 500
            elif periods or departments or account_prefixes:
                row_count = 750
            else:
                row_count = 1000
        
        # Generate mock data
        mock_data = generate_mock_netsuite_data(
            row_count=row_count,
            periods=periods,
            departments=departments,
            account_prefixes=account_prefixes,
        )
        
        column_names = get_mock_column_names()
        
        logger.info(
            f"Generated {len(mock_data)} mock transactions "
            f"(periods: {periods or 'all'}, depts: {departments or 'all'}, "
            f"accounts: {account_prefixes or 'all'})"
        )
        
        return SavedSearchResult(
            data=mock_data,
            search_id="mock_search",
            retrieved_at=datetime.utcnow(),
            row_count=len(mock_data),
            column_names=column_names,
            execution_time_ms=10.0,  # Mock execution time
        )
    
    def _generate_cache_key(
        self,
        search_id: Optional[str],
        parsed_query: Optional['ParsedQuery'],
    ) -> str:
        """
        Generate a cache key based on the query parameters.
        
        This ensures that different filter combinations are cached separately.
        """
        if not parsed_query:
            return search_id or "default"
        
        # Create a hash of the relevant query parameters
        key_parts = [
            search_id or "default",
        ]
        
        if parsed_query.time_period:
            key_parts.append(f"tp:{parsed_query.time_period.start_date}_{parsed_query.time_period.end_date}")
        
        if parsed_query.account_type_filter:
            values = parsed_query.account_type_filter.get("values", [])
            key_parts.append(f"acct:{','.join(sorted(values))}")
        
        if parsed_query.departments:
            key_parts.append(f"dept:{','.join(sorted(parsed_query.departments))}")
        
        if parsed_query.transaction_type_filter:
            key_parts.append(f"txn:{','.join(sorted(parsed_query.transaction_type_filter))}")
        
        key_string = "|".join(key_parts)
        key_hash = hashlib.md5(key_string.encode()).hexdigest()[:12]
        
        return f"{search_id or 'suiteql'}_{key_hash}"
    
    def _validate_result(self, result: SavedSearchResult) -> None:
        """Validate search result data integrity."""
        if result.row_count == 0:
            logger.warning(f"Search {result.search_id} returned no data")
        
        # Check for required columns based on common financial data patterns
        expected_patterns = ["amount", "date", "account", "type"]
        found_patterns = []
        
        for col in result.column_names:
            col_lower = col.lower()
            for pattern in expected_patterns:
                if pattern in col_lower:
                    found_patterns.append(pattern)
        
        if len(found_patterns) < 2:
            logger.warning(
                f"Search may be missing expected financial columns. "
                f"Found: {result.column_names}"
            )
    
    def get_data_summary(self, result: SavedSearchResult) -> Dict[str, Any]:
        """Generate a summary of the data for agent context."""
        summary = {
            "search_id": result.search_id,
            "row_count": result.row_count,
            "columns": result.column_names,
            "retrieved_at": result.retrieved_at.isoformat(),
        }
        
        # Add basic statistics for numeric columns
        if result.data:
            numeric_stats = {}
            for col in result.column_names:
                values = []
                for row in result.data:
                    val = row.get(col)
                    if isinstance(val, (int, float)):
                        values.append(val)
                
                if values:
                    numeric_stats[col] = {
                        "min": min(values),
                        "max": max(values),
                        "sum": sum(values),
                        "count": len(values),
                        "avg": sum(values) / len(values),
                    }
            
            summary["numeric_stats"] = numeric_stats
        
        return summary
    
    def _maybe_update_registry(self, data: List[Dict]):
        """
        Update the dynamic registry from fetched data if needed.
        
        This piggybacks on existing data retrieval - no extra API calls.
        Registry is only rebuilt if cache is stale (default: 24 hours).
        
        Args:
            data: The data rows just fetched from NetSuite
        """
        if not DYNAMIC_REGISTRY_AVAILABLE:
            return
        
        try:
            registry = get_dynamic_registry()
            
            if registry.needs_refresh():
                logger.info("Dynamic registry needs refresh, updating from fetched data...")
                
                # Build field mappings using our field detection logic
                field_mappings = {
                    "department": self._find_field_name(data, "department"),
                    "account": self._find_field_name(data, "account"),
                    "account_number": self._find_field_name(data, "account_number"),
                    "subsidiary": self._find_field_name(data, "subsidiary"),
                    "transaction_type": self._find_field_name(data, "type"),
                }
                
                # Filter out None mappings
                field_mappings = {k: v for k, v in field_mappings.items() if v}
                
                registry.build_from_data(data, field_mappings)
                logger.info(f"Dynamic registry updated: {registry.stats}")
            else:
                logger.debug("Dynamic registry cache is valid, skipping update")
                
        except Exception as e:
            # Don't fail the data retrieval if registry update fails
            logger.warning(f"Failed to update dynamic registry: {e}")
    
    def _find_field_name(self, data: List[Dict], field_type: str) -> Optional[str]:
        """Find actual field name in data for a given field type."""
        if not data:
            return None
        
        sample = data[0]
        keys_lower = {k.lower(): k for k in sample.keys()}
        
        # Field type to candidate names mapping
        candidates = {
            "department": ["department_name", "department", "dept_name", "dept"],
            "account": ["account_name", "account", "acctname", "acct_name"],
            "account_number": ["account_number", "acctnumber", "acct_number", "acctno"],
            "subsidiary": ["subsidiarynohierarchy", "subsidiary", "subsidiary_name", "entity"],
            "type": ["type", "trantype", "transaction_type", "type_text"],
        }
        
        for candidate in candidates.get(field_type, [field_type]):
            if candidate.lower() in keys_lower:
                return keys_lower[candidate.lower()]
        
        return None

# Custom exceptions
class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass

class DataRetrievalError(Exception):
    """Raised when data retrieval fails."""
    pass

# Factory function
def get_data_retriever(use_cache: bool = True, update_registry: bool = True) -> NetSuiteDataRetriever:
    """Factory function to get a configured data retriever."""
    return NetSuiteDataRetriever(use_cache=use_cache, update_registry=update_registry)
