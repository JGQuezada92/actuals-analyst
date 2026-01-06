"""
Unit tests for NetSuite RESTlet v2.2+ compatibility.

Tests version checking, filterWarnings handling, and graceful degradation.
"""
import pytest
import json
from unittest.mock import Mock, patch
from src.tools.netsuite_client import NetSuiteRESTClient, DataRetrievalError
from src.core.netsuite_filter_builder import NetSuiteFilterParams
from config.settings import NetSuiteConfig


class TestRESTletV22Compatibility:
    """Tests for RESTlet v2.2+ features."""
    
    @pytest.fixture
    def mock_config(self):
        """Create a mock NetSuite config."""
        return NetSuiteConfig(
            account_id="test_account",
            consumer_key="test_key",
            consumer_secret="test_secret",
            token_id="test_token",
            token_secret="test_token_secret",
            restlet_url="https://test.netsuite.com/app/site/hosting/restlet.nl?script=123&deploy=1",
        )
    
    @pytest.fixture
    def client(self, mock_config):
        """Create a NetSuiteRESTClient instance."""
        return NetSuiteRESTClient(mock_config)
    
    def test_process_restlet_response_metadata_version_22(self, client):
        """Should log RESTlet v2.2+ version correctly."""
        result = {
            "success": True,
            "version": "2.2",
            "columns": [],
            "results": [],
            "totalPages": 1,
            "totalResults": 0,
        }
        
        # Should not raise any exceptions
        client._process_restlet_response_metadata(result, "test_search", page=0)
    
    def test_process_restlet_response_metadata_version_below_22(self, client, caplog):
        """Should warn if RESTlet version is below 2.2."""
        result = {
            "success": True,
            "version": "2.1",
            "columns": [],
            "results": [],
            "totalPages": 1,
            "totalResults": 0,
        }
        
        client._process_restlet_response_metadata(result, "test_search", page=0)
        
        # Check that warning was logged
        assert "below 2.2" in caplog.text.lower()
        assert "period ID conversion" in caplog.text.lower()
    
    def test_process_restlet_response_metadata_version_unknown(self, client):
        """Should handle missing version field gracefully."""
        result = {
            "success": True,
            "columns": [],
            "results": [],
            "totalPages": 1,
            "totalResults": 0,
        }
        
        # Should not raise any exceptions
        client._process_restlet_response_metadata(result, "test_search", page=0)
    
    def test_process_restlet_response_metadata_filter_warnings_periods(self, client, caplog):
        """Should log filterWarnings for missing periods."""
        result = {
            "success": True,
            "version": "2.2",
            "filterWarnings": [
                {
                    "type": "periodNames",
                    "notFound": ["Jan 2099", "Feb 2099", "Mar 2099"]
                }
            ],
            "columns": [],
            "results": [],
            "totalPages": 1,
            "totalResults": 0,
        }
        
        client._process_restlet_response_metadata(result, "test_search", page=0)
        
        # Check that warning was logged
        assert "period(s) not found" in caplog.text.lower()
        assert "Jan 2099" in caplog.text
        assert "fall back to date range" in caplog.text.lower()
    
    def test_process_restlet_response_metadata_filter_warnings_date_range(self, client, caplog):
        """Should log filterWarnings for date range issues."""
        result = {
            "success": True,
            "version": "2.2",
            "filterWarnings": [
                {
                    "type": "dateRange",
                    "message": "Date range filter could not be applied"
                }
            ],
            "columns": [],
            "results": [],
            "totalPages": 1,
            "totalResults": 0,
        }
        
        client._process_restlet_response_metadata(result, "test_search", page=0)
        
        # Check that warning was logged
        assert "date range filter warning" in caplog.text.lower()
    
    def test_process_restlet_response_metadata_filter_warnings_generic(self, client, caplog):
        """Should log generic filterWarnings."""
        result = {
            "success": True,
            "version": "2.2",
            "filterWarnings": [
                {
                    "type": "unknown",
                    "message": "Some filter issue occurred"
                }
            ],
            "columns": [],
            "results": [],
            "totalPages": 1,
            "totalResults": 0,
        }
        
        client._process_restlet_response_metadata(result, "test_search", page=0)
        
        # Check that warning was logged
        assert "filter warning" in caplog.text.lower()
        assert "Some filter issue occurred" in caplog.text
    
    def test_process_restlet_response_metadata_filter_errors(self, client, caplog):
        """Should log filterErrors (more severe than warnings)."""
        result = {
            "success": True,
            "version": "2.2",
            "filterErrors": [
                {
                    "type": "department",
                    "message": "Department filter failed"
                }
            ],
            "columns": [],
            "results": [],
            "totalPages": 1,
            "totalResults": 0,
        }
        
        client._process_restlet_response_metadata(result, "test_search", page=0)
        
        # Check that error was logged
        assert "filter error" in caplog.text.lower()
        assert "Department filter failed" in caplog.text
    
    def test_process_restlet_response_metadata_multiple_warnings(self, client, caplog):
        """Should handle multiple filterWarnings."""
        result = {
            "success": True,
            "version": "2.2",
            "filterWarnings": [
                {
                    "type": "periodNames",
                    "notFound": ["Jan 2099"]
                },
                {
                    "type": "dateRange",
                    "message": "Date range issue"
                }
            ],
            "columns": [],
            "results": [],
            "totalPages": 1,
            "totalResults": 0,
        }
        
        client._process_restlet_response_metadata(result, "test_search", page=0)
        
        # Check that both warnings were logged
        assert "period(s) not found" in caplog.text.lower()
        assert "date range filter warning" in caplog.text.lower()
    
    def test_process_restlet_response_metadata_version_only_on_first_page(self, client, caplog):
        """Should only log version on first page (page 0) to avoid spam."""
        result = {
            "success": True,
            "version": "2.2",
            "columns": [],
            "results": [],
            "totalPages": 1,
            "totalResults": 0,
        }
        
        # First page - should log version
        client._process_restlet_response_metadata(result, "test_search", page=0)
        assert "RESTlet version" in caplog.text
        
        # Clear log
        caplog.clear()
        
        # Second page - should NOT log version again
        client._process_restlet_response_metadata(result, "test_search", page=1)
        assert "RESTlet version" not in caplog.text
    
    def test_process_restlet_response_metadata_many_periods_not_found(self, client, caplog):
        """Should truncate long lists of missing periods."""
        result = {
            "success": True,
            "version": "2.2",
            "filterWarnings": [
                {
                    "type": "periodNames",
                    "notFound": [f"Jan {year}" for year in range(2099, 2110)]  # 11 periods
                }
            ],
            "columns": [],
            "results": [],
            "totalPages": 1,
            "totalResults": 0,
        }
        
        client._process_restlet_response_metadata(result, "test_search", page=0)
        
        # Should show first 5 and then "..."
        assert "Jan 2099" in caplog.text
        assert "Jan 2103" in caplog.text  # 5th period
        assert "..." in caplog.text  # Truncation indicator


class TestRESTletV22Integration:
    """Integration tests for RESTlet v2.2+ behavior."""
    
    @pytest.fixture
    def mock_config(self):
        """Create a mock NetSuite config."""
        return NetSuiteConfig(
            account_id="test_account",
            consumer_key="test_key",
            consumer_secret="test_secret",
            token_id="test_token",
            token_secret="test_token_secret",
            restlet_url="https://test.netsuite.com/app/site/hosting/restlet.nl?script=123&deploy=1",
        )
    
    @pytest.mark.skip(reason="Requires actual RESTlet or extensive mocking")
    def test_restlet_handles_missing_periods_gracefully(self):
        """
        RESTlet v2.2 should gracefully handle periods that don't exist in NetSuite.
        
        Example: Requesting "Jan 2099" should:
        1. Return filterWarnings with the missing period
        2. Fall back to date range filtering
        3. NOT raise an error
        
        This test requires either:
        - A real RESTlet deployment (integration test)
        - Extensive mocking of the HTTP request/response cycle
        """
        # This would be an integration test that actually calls the RESTlet
        # with future periods that don't exist yet
        pass
    
    @pytest.mark.skip(reason="Requires actual RESTlet or extensive mocking")
    def test_restlet_version_field_present(self):
        """
        RESTlet v2.2+ should always include version field in response.
        
        This test verifies that the version field is present and >= 2.2
        """
        # This would be an integration test
        pass

