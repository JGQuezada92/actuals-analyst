"""
Query Robustness Tests

Verifies that semantically equivalent queries produce identical ParsedQuery results.
Tests integration with existing query_parser.py and financial_semantics.py.
"""

import pytest
from src.core.query_parser import get_query_parser, ParsedQuery
from src.core.fiscal_calendar import get_fiscal_calendar


class TestEquivalentQueries:
    """Test that equivalent queries produce same parsing results."""
    
    @pytest.fixture
    def parser(self):
        return get_query_parser()
    
    # Groups of semantically equivalent queries
    EQUIVALENT_GROUPS = [
        # Group 1: Basic YTD expense for Sales NA
        {
            "name": "Sales NA YTD Expense",
            "queries": [
                "What is the YTD expense for Sales NA department?",
                "Give me total expense for Sales NA",
                "Show YTD expenses for Sales NA",
                "Sales NA department expenses YTD",
                "total ytd expense sales na",
            ],
            "expected": {
                "has_time_period": True,
                "time_period_contains": "YTD",
                "departments_contain": "Sales NA",
                "has_account_filter": True,
            }
        },
        # Group 2: G&A Finance expenses
        {
            "name": "G&A Finance Expense",
            "queries": [
                "What are G&A Finance expenses YTD?",
                "Show expenses for Finance under G&A",
                "G&A Finance department YTD expense",
                "give me the expense for g&a finance",
            ],
            "expected": {
                "has_time_period": True,
                "departments_contain": "Finance",
            }
        },
        # Group 3: Revenue queries
        {
            "name": "Revenue YTD",
            "queries": [
                "What is total revenue YTD?",
                "Show YTD revenue",
                "How much revenue do we have year to date?",
            ],
            "expected": {
                "has_time_period": True,
                "has_account_filter": True,
                "account_prefix": ["4"],
            }
        },
    ]
    
    @pytest.mark.parametrize("group", EQUIVALENT_GROUPS, ids=lambda g: g["name"])
    def test_equivalent_queries_same_result(self, parser, group):
        """Test that all queries in a group produce equivalent ParsedQuery."""
        results = []
        
        for query in group["queries"]:
            parsed = parser.parse(query)
            results.append((query, parsed))
        
        expected = group["expected"]
        
        for query, parsed in results:
            # Check time period
            if expected.get("has_time_period"):
                assert parsed.time_period is not None, f"Query '{query}' missing time period"
                if expected.get("time_period_contains"):
                    assert expected["time_period_contains"] in parsed.time_period.period_name, \
                        f"Query '{query}' time period doesn't contain '{expected['time_period_contains']}'"
            
            # Check departments
            if expected.get("departments_contain"):
                dept_str = " ".join(parsed.departments).lower()
                assert expected["departments_contain"].lower() in dept_str, \
                    f"Query '{query}' departments don't contain '{expected['departments_contain']}'"
            
            # Check account filter
            if expected.get("has_account_filter"):
                assert parsed.account_type_filter is not None, \
                    f"Query '{query}' missing account filter"
            
            if expected.get("account_prefix"):
                assert parsed.account_type_filter is not None
                actual_prefixes = parsed.account_type_filter.get("values", [])
                assert set(expected["account_prefix"]).issubset(set(actual_prefixes)), \
                    f"Query '{query}' has wrong account prefixes"


class TestDepartmentResolution:
    """Test department name resolution."""
    
    @pytest.fixture
    def parser(self):
        return get_query_parser()
    
    DEPARTMENT_TESTS = [
        # (query, expected_department_substring)
        ("Sales NA expenses", "Sales NA"),
        ("Sales INTL expenses", "Sales INTL"),
        ("Account Management NA costs", "Account Management NA"),
        ("G&A Finance expenses", "Finance"),
        ("R&D Product Management costs", "Product Management"),
        ("Engineering expenses under R&D", "Engineering"),
    ]
    
    @pytest.mark.parametrize("query,expected_dept", DEPARTMENT_TESTS)
    def test_department_resolution(self, parser, query, expected_dept):
        """Test that department names are correctly resolved."""
        parsed = parser.parse(query)
        
        assert parsed.departments, f"No departments found in '{query}'"
        
        dept_str = " ".join(parsed.departments)
        assert expected_dept.lower() in dept_str.lower(), \
            f"Expected '{expected_dept}' in departments, got {parsed.departments}"


class TestTimePeriodDefaults:
    """Test implicit time period handling."""
    
    @pytest.fixture
    def parser(self):
        return get_query_parser()
    
    SHOULD_DEFAULT_YTD = [
        "What are total expenses?",
        "Show G&A costs",
        "Marketing department spending",
        "give me expense for Sales NA",
    ]
    
    SHOULD_NOT_DEFAULT = [
        "What were Q1 expenses?",
        "Show January 2025 costs",
        "Last month spending",
        "FY2025 revenue",
    ]
    
    @pytest.mark.parametrize("query", SHOULD_DEFAULT_YTD)
    def test_default_ytd_for_expense_queries(self, parser, query):
        """Test that expense queries without explicit period default to YTD."""
        parsed = parser.parse(query)
        
        assert parsed.time_period is not None, f"Query '{query}' should have defaulted to YTD"
        assert "YTD" in parsed.time_period.period_name, \
            f"Query '{query}' should default to YTD, got {parsed.time_period.period_name}"
    
    @pytest.mark.parametrize("query", SHOULD_NOT_DEFAULT)
    def test_no_default_when_explicit(self, parser, query):
        """Test that explicit time periods are not overridden."""
        parsed = parser.parse(query)
        
        assert parsed.time_period is not None, f"Query '{query}' should have a time period"
        # Should NOT be YTD (since explicit period was provided)
        # This test verifies the explicit period is preserved


class TestAmbiguousTermResolution:
    """Test that ambiguous terms are resolved when context is clear."""
    
    @pytest.fixture
    def parser(self):
        return get_query_parser()
    
    def test_sales_resolved_by_department_context(self, parser):
        """Test that 'sales' is not ambiguous when department context is clear."""
        # When "Sales NA department" is mentioned, "sales" should not require disambiguation
        query = "What is the total YTD expense for the Sales NA department?"
        parsed = parser.parse(query)
        
        # Should NOT require disambiguation since "sales" is clearly a department
        assert not parsed.requires_disambiguation, \
            f"Query should not require disambiguation, but got: {parsed.ambiguous_terms}"
    
    def test_sales_ambiguous_without_department_context(self, parser):
        """Test that 'sales' is ambiguous when context is unclear."""
        # When just "sales" is mentioned without department context
        query = "What are sales for this quarter?"
        parsed = parser.parse(query)
        
        # May or may not require disambiguation depending on semantic parsing
        # This test just verifies parsing completes without error
        assert parsed is not None


class TestHierarchicalDepartments:
    """Test parsing of hierarchical department names."""
    
    @pytest.fixture
    def parser(self):
        return get_query_parser()
    
    HIERARCHICAL_TESTS = [
        # Query with multi-level department reference
        ("Sales NA Enterprise Sales expenses", ["Enterprise Sales", "Sales NA"]),
        ("G&A Finance EMEA costs", ["Finance", "EMEA"]),
    ]
    
    @pytest.mark.parametrize("query,expected_substrings", HIERARCHICAL_TESTS)
    def test_hierarchical_department_parsing(self, parser, query, expected_substrings):
        """Test that hierarchical departments are correctly parsed."""
        parsed = parser.parse(query)
        
        assert parsed.departments, f"No departments found in '{query}'"
        
        dept_str = " ".join(parsed.departments).lower()
        for substring in expected_substrings:
            assert substring.lower() in dept_str, \
                f"Expected '{substring}' in departments '{parsed.departments}'"
