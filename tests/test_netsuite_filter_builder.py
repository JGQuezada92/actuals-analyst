"""
Unit tests for NetSuite Filter Builder.

Tests the conversion of ParsedQuery objects to NetSuite filter parameters.
"""
import pytest
from datetime import date
from src.core.netsuite_filter_builder import (
    NetSuiteFilterBuilder,
    NetSuiteFilterParams,
    get_filter_builder,
)
from src.core.fiscal_calendar import FiscalPeriod


class TestNetSuiteFilterParams:
    """Tests for NetSuiteFilterParams dataclass."""
    
    def test_to_query_params_empty(self):
        """Empty params should return excludeTotals only."""
        params = NetSuiteFilterParams()
        query_params = params.to_query_params()
        assert query_params == {"excludeTotals": "true"}
    
    def test_to_query_params_period_names(self):
        """Period names should be formatted correctly."""
        params = NetSuiteFilterParams(
            period_names=["Feb 2024", "Mar 2024", "Apr 2024"]
        )
        query_params = params.to_query_params()
        
        assert query_params["periodNames"] == "Feb 2024,Mar 2024,Apr 2024"
        assert "startDate" not in query_params
        assert "endDate" not in query_params
    
    def test_to_query_params_date_range_fallback(self):
        """Date range should be used as fallback if period names not provided."""
        params = NetSuiteFilterParams(
            start_date="02/01/2024",
            end_date="12/31/2024",
        )
        query_params = params.to_query_params()
        
        assert query_params["startDate"] == "02/01/2024"
        assert query_params["endDate"] == "12/31/2024"
        assert query_params["dateField"] == "trandate"
        assert "periodNames" not in query_params
    
    def test_to_query_params_departments(self):
        """Multiple departments should be comma-separated."""
        params = NetSuiteFilterParams(
            departments=["Marketing", "Sales"]
        )
        query_params = params.to_query_params()
        
        assert query_params["department"] == "Marketing,Sales"
    
    def test_to_query_params_account_prefixes(self):
        """Multiple prefixes should be comma-separated."""
        params = NetSuiteFilterParams(
            account_prefixes=["5", "6", "7"]
        )
        query_params = params.to_query_params()
        
        assert query_params["accountPrefix"] == "5,6,7"
    
    def test_has_filters_false(self):
        """Empty params should report no filters."""
        params = NetSuiteFilterParams()
        assert not params.has_filters()
    
    def test_has_filters_true(self):
        """Params with any filter should report has filters."""
        params = NetSuiteFilterParams(departments=["Marketing"])
        assert params.has_filters()
    
    def test_describe(self):
        """Describe should return readable string."""
        params = NetSuiteFilterParams(
            start_date="02/01/2024",
            end_date="12/31/2024",
            departments=["Marketing"],
            account_prefixes=["5"],
        )
        desc = params.describe()
        
        assert "02/01/2024" in desc
        assert "Marketing" in desc
        assert "5" in desc


class TestNetSuiteFilterBuilder:
    """Tests for NetSuiteFilterBuilder class."""
    
    @pytest.fixture
    def builder(self):
        return NetSuiteFilterBuilder()
    
    def test_build_from_components_date(self, builder):
        """Should build date filter from FiscalPeriod."""
        period = FiscalPeriod(
            start_date=date(2024, 2, 1),
            end_date=date(2024, 12, 31),
            period_name="FY2025 YTD",
            fiscal_year=2025,
        )
        
        params = builder.build_from_components(time_period=period)
        
        assert params.start_date == "02/01/2024"
        assert params.end_date == "12/31/2024"
    
    def test_build_from_components_departments(self, builder):
        """Should build department filter."""
        params = builder.build_from_components(
            departments=["Marketing", "Sales"]
        )
        
        assert params.departments == ["Marketing", "Sales"]
    
    def test_build_from_components_account_prefixes(self, builder):
        """Should build account prefix filter."""
        params = builder.build_from_components(
            account_prefixes=["5", "6"]
        )
        
        assert params.account_prefixes == ["5", "6"]
    
    def test_build_from_components_combined(self, builder):
        """Should build combined filters."""
        period = FiscalPeriod(
            start_date=date(2024, 2, 1),
            end_date=date(2024, 12, 31),
            period_name="FY2025 YTD",
            fiscal_year=2025,
        )
        
        params = builder.build_from_components(
            time_period=period,
            departments=["Marketing"],
            account_prefixes=["5", "6", "7", "8"],
            transaction_types=["Journal", "VendBill"],
        )
        
        assert params.start_date == "02/01/2024"
        assert params.departments == ["Marketing"]
        assert params.account_prefixes == ["5", "6", "7", "8"]
        assert params.transaction_types == ["Journal", "VendBill"]
        
        # Verify query params
        query_params = params.to_query_params()
        assert "startDate" in query_params
        assert "department" in query_params
        assert "accountPrefix" in query_params
        assert "transactionType" in query_params


class TestFilterBuilderIntegration:
    """Integration tests with ParsedQuery."""
    
    def test_build_from_parsed_query(self):
        """Should build filters from ParsedQuery."""
        # This test requires ParsedQuery to be importable
        # Skip if not available
        pytest.importorskip("src.core.query_parser")
        
        from src.core.query_parser import ParsedQuery, QueryIntent
        from src.core.fiscal_calendar import FiscalPeriod
        
        parsed = ParsedQuery(
            original_query="YTD expenses for Marketing",
            intent=QueryIntent.BREAKDOWN,
            time_period=FiscalPeriod(
                start_date=date(2024, 2, 1),
                end_date=date(2024, 11, 30),
                period_name="FY2025 YTD",
                fiscal_year=2025,
            ),
            departments=["Marketing"],
            account_type_filter={
                "filter_type": "prefix",
                "values": ["5", "6", "7", "8"],
            },
        )
        
        builder = NetSuiteFilterBuilder()
        params = builder.build_from_parsed_query(parsed)
        
        assert params.start_date == "02/01/2024"
        assert params.end_date == "11/30/2024"
        assert params.departments == ["Marketing"]
        assert params.account_prefixes == ["5", "6", "7", "8"]
        assert params.has_filters()

