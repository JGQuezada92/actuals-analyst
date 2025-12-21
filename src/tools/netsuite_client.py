"""
NetSuite Data Retrieval Tools

Deterministic data retrieval from NetSuite saved searches.
Following the framework principle: LLMs interpret, tools compute.

This module handles:
1. OneLogin SSO authentication flow
2. NetSuite REST API connection
3. Saved Search execution
4. Data validation and caching
"""
import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import requests

from config.settings import NetSuiteConfig, get_config

logger = logging.getLogger(__name__)

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
    
    Supports saved search execution via SuiteQL and REST endpoints.
    """
    
    def __init__(self, config: NetSuiteConfig):
        self.config = config
        self.base_url = f"https://{config.account_id}.suitetalk.api.netsuite.com"
        self._session: Optional[requests.Session] = None
    
    def _get_session(self) -> requests.Session:
        """Get or create authenticated session."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(self._get_auth_headers())
        return self._session
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Generate OAuth 1.0 headers for NetSuite TBA."""
        import time
        import hmac
        import base64
        import urllib.parse
        
        timestamp = str(int(time.time()))
        nonce = hashlib.sha256(f"{timestamp}{os.urandom(8).hex()}".encode()).hexdigest()[:32]
        
        # OAuth parameters
        oauth_params = {
            "oauth_consumer_key": self.config.consumer_key,
            "oauth_token": self.config.token_id,
            "oauth_signature_method": "HMAC-SHA256",
            "oauth_timestamp": timestamp,
            "oauth_nonce": nonce,
            "oauth_version": "1.0",
            "realm": self.config.account_id,
        }
        
        # Create signature base string
        base_string = self._create_signature_base_string(oauth_params)
        
        # Create signature
        signing_key = f"{urllib.parse.quote(self.config.consumer_secret)}&{urllib.parse.quote(self.config.token_secret)}"
        signature = base64.b64encode(
            hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha256).digest()
        ).decode()
        
        oauth_params["oauth_signature"] = signature
        
        # Build Authorization header
        auth_header = "OAuth " + ", ".join(
            f'{k}="{urllib.parse.quote(str(v), safe="")}"' 
            for k, v in oauth_params.items()
        )
        
        return {
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "Prefer": "transient",
        }
    
    def _create_signature_base_string(self, oauth_params: Dict[str, str]) -> str:
        """Create OAuth signature base string."""
        import urllib.parse
        
        # Sort and encode parameters
        sorted_params = sorted(oauth_params.items())
        param_string = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted_params
        )
        
        # Create base string
        method = "GET"
        url = f"{self.base_url}/services/rest/record/v1"
        
        return f"{method}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(param_string, safe='')}"
    
    def execute_saved_search(self, search_id: Optional[str] = None) -> SavedSearchResult:
        """
        Execute a saved search and return results.
        
        Args:
            search_id: The internal ID of the saved search. 
                      If None, uses the configured default.
        
        Returns:
            SavedSearchResult with data and metadata.
        """
        search_id = search_id or self.config.saved_search_id
        if not search_id:
            raise ValueError("No saved search ID provided or configured")
        
        start_time = datetime.utcnow()
        
        # Use SuiteQL to execute saved search
        url = f"{self.base_url}/services/rest/query/v1/suiteql"
        
        # Query to get saved search results
        query = f"""
            SELECT * FROM (
                SELECT * FROM SAVEDEARCH({search_id})
            )
        """
        
        try:
            session = self._get_session()
            response = session.post(
                url,
                json={"q": query},
                headers={"Prefer": "transient"}
            )
            response.raise_for_status()
            
            result_data = response.json()
            items = result_data.get("items", [])
            
            # Extract column names from first row
            column_names = list(items[0].keys()) if items else []
            
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return SavedSearchResult(
                data=items,
                search_id=search_id,
                retrieved_at=datetime.utcnow(),
                row_count=len(items),
                column_names=column_names,
                execution_time_ms=execution_time,
            )
            
        except requests.RequestException as e:
            logger.error(f"Failed to execute saved search: {e}")
            raise DataRetrievalError(f"NetSuite saved search failed: {e}")
    
    def execute_suiteql(self, query: str) -> List[Dict[str, Any]]:
        """Execute raw SuiteQL query."""
        url = f"{self.base_url}/services/rest/query/v1/suiteql"
        
        try:
            session = self._get_session()
            response = session.post(url, json={"q": query})
            response.raise_for_status()
            return response.json().get("items", [])
        except requests.RequestException as e:
            logger.error(f"SuiteQL query failed: {e}")
            raise DataRetrievalError(f"SuiteQL query failed: {e}")

class DataCache:
    """
    Simple file-based cache for saved search results.
    
    Prevents excessive API calls during development and testing.
    """
    
    def __init__(self, cache_dir: str = ".cache/netsuite"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_minutes = 15  # Cache TTL
    
    def _get_cache_path(self, search_id: str) -> Path:
        """Get cache file path for a search ID."""
        safe_id = hashlib.sha256(search_id.encode()).hexdigest()[:16]
        return self.cache_dir / f"{safe_id}.json"
    
    def get(self, search_id: str) -> Optional[SavedSearchResult]:
        """Get cached result if valid."""
        cache_path = self._get_cache_path(search_id)
        
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, 'r') as f:
                cached = json.load(f)
            
            cached_time = datetime.fromisoformat(cached["retrieved_at"])
            if datetime.utcnow() - cached_time > timedelta(minutes=self.ttl_minutes):
                return None
            
            return SavedSearchResult(
                data=cached["data"],
                search_id=cached["search_id"],
                retrieved_at=cached_time,
                row_count=cached["row_count"],
                column_names=cached["column_names"],
                execution_time_ms=cached["execution_time_ms"],
            )
        except (json.JSONDecodeError, KeyError):
            return None
    
    def set(self, result: SavedSearchResult) -> None:
        """Cache a search result."""
        cache_path = self._get_cache_path(result.search_id)
        with open(cache_path, 'w') as f:
            json.dump(result.to_dict(), f)

class NetSuiteDataRetriever:
    """
    High-level interface for NetSuite data retrieval.
    
    This is the primary class agents should use for data access.
    Handles caching, validation, and error recovery.
    """
    
    def __init__(self, config: Optional[NetSuiteConfig] = None, use_cache: bool = True):
        self.config = config or get_config().netsuite
        self.client = NetSuiteRESTClient(self.config)
        self.cache = DataCache() if use_cache else None
    
    def get_saved_search_data(
        self, 
        search_id: Optional[str] = None,
        bypass_cache: bool = False
    ) -> SavedSearchResult:
        """
        Retrieve data from a NetSuite saved search.
        
        Args:
            search_id: Internal ID of the saved search. 
                      Uses configured default if None.
            bypass_cache: Force fresh data retrieval.
        
        Returns:
            SavedSearchResult with validated data.
        """
        search_id = search_id or self.config.saved_search_id
        
        # Check cache first
        if self.cache and not bypass_cache:
            cached = self.cache.get(search_id)
            if cached:
                logger.info(f"Cache hit for search {search_id}")
                return cached
        
        # Fetch fresh data
        result = self.client.execute_saved_search(search_id)
        
        # Validate result
        self._validate_result(result)
        
        # Cache result
        if self.cache:
            self.cache.set(result)
        
        return result
    
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

# Custom exceptions
class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass

class DataRetrievalError(Exception):
    """Raised when data retrieval fails."""
    pass

# Factory function
def get_data_retriever(use_cache: bool = True) -> NetSuiteDataRetriever:
    """Factory function to get a configured data retriever."""
    return NetSuiteDataRetriever(use_cache=use_cache)
