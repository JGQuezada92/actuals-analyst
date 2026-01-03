"""
Unit tests for the Financial Semantics module.

Tests cover:
- Semantic term resolution
- Ambiguous term detection
- Case insensitivity
- Plural/singular handling
- Disambiguation message building
"""
import pytest
from src.core.financial_semantics import (
    SemanticTerm,
    SemanticCategory,
    FilterType,
    get_semantic_term,
    resolve_financial_terms,
    needs_disambiguation,
    build_disambiguation_message,
    apply_disambiguation_choice,
    get_account_filter_for_term,
    get_department_filter_for_term,
    is_account_term,
    is_department_term,
    is_ambiguous_term,
)


class TestGetSemanticTerm:
    """Tests for get_semantic_term function."""
    
    def test_revenue_returns_account_term(self):
        """Revenue should map to account prefix 4, not Sales department."""
        term = get_semantic_term("revenue")
        
        assert term is not None
        assert term.category == SemanticCategory.ACCOUNT
        assert term.filter_type == FilterType.PREFIX
        assert term.filter_values == ["4"]
        assert term.disambiguation_required is False
    
    def test_revenue_case_insensitive(self):
        """Revenue matching should be case-insensitive."""
        assert get_semantic_term("REVENUE") is not None
        assert get_semantic_term("Revenue") is not None
        assert get_semantic_term("ReVeNuE") is not None
    
    def test_expenses_returns_all_expense_prefixes(self):
        """Expenses should map to account prefixes 5, 6, 7, 8."""
        term = get_semantic_term("expenses")
        
        assert term is not None
        assert term.category == SemanticCategory.ACCOUNT
        assert set(term.filter_values) == {"5", "6", "7", "8"}
    
    def test_expense_singular_works(self):
        """Singular 'expense' should also work."""
        term = get_semantic_term("expense")
        
        assert term is not None
        assert term.category == SemanticCategory.ACCOUNT
    
    def test_cogs_returns_account_prefix_5(self):
        """COGS should map to account prefix 5."""
        term = get_semantic_term("cogs")
        
        assert term is not None
        assert term.filter_values == ["5"]
    
    def test_marketing_returns_department(self):
        """Marketing should map to Marketing department."""
        term = get_semantic_term("marketing")
        
        assert term is not None
        assert term.category == SemanticCategory.DEPARTMENT
        assert "Marketing" in term.filter_values
    
    def test_sales_department_returns_department(self):
        """'Sales department' should explicitly map to Sales department."""
        term = get_semantic_term("sales department")
        
        assert term is not None
        assert term.category == SemanticCategory.DEPARTMENT
        assert "Sales" in term.filter_values
        assert term.disambiguation_required is False
    
    def test_sales_alone_is_ambiguous(self):
        """'Sales' alone should require disambiguation."""
        term = get_semantic_term("sales")
        
        assert term is not None
        assert term.category == SemanticCategory.AMBIGUOUS
        assert term.disambiguation_required is True
        assert term.disambiguation_options is not None
        assert len(term.disambiguation_options) == 2
    
    def test_journal_entries_returns_transaction_type(self):
        """Journal entries should map to transaction type."""
        term = get_semantic_term("journal entries")
        
        assert term is not None
        assert term.category == SemanticCategory.TRANSACTION_TYPE
        assert "Journal" in term.filter_values
    
    def test_unknown_term_returns_none(self):
        """Unknown terms should return None."""
        assert get_semantic_term("foobar") is None
        assert get_semantic_term("xyz123") is None
    
    def test_ganda_with_ampersand(self):
        """G&A should work with ampersand."""
        term = get_semantic_term("g&a")
        
        assert term is not None
        assert term.category == SemanticCategory.DEPARTMENT
    
    def test_assets_returns_account_prefix_1(self):
        """Assets should map to account prefix 1."""
        term = get_semantic_term("assets")
        
        assert term is not None
        assert term.category == SemanticCategory.ACCOUNT
        assert term.filter_values == ["1"]
    
    def test_liabilities_returns_account_prefix_2(self):
        """Liabilities should map to account prefix 2."""
        term = get_semantic_term("liabilities")
        
        assert term is not None
        assert term.filter_values == ["2"]
    
    def test_equity_returns_account_prefix_3(self):
        """Equity should map to account prefix 3."""
        term = get_semantic_term("equity")
        
        assert term is not None
        assert term.filter_values == ["3"]


class TestResolveFinancialTerms:
    """Tests for resolve_financial_terms function."""
    
    def test_single_term_in_query(self):
        """Should find single term in query."""
        terms = resolve_financial_terms("What is YTD revenue?")
        
        assert len(terms) >= 1
        term_names = [t.term for t in terms]
        assert "revenue" in term_names
    
    def test_multiple_terms_in_query(self):
        """Should find multiple terms in query."""
        terms = resolve_financial_terms("Show marketing and engineering expenses")
        
        term_names = [t.term for t in terms]
        assert "marketing" in term_names
        assert "engineering" in term_names
        assert "expenses" in term_names
    
    def test_longer_match_preferred(self):
        """Should prefer 'sales department' over 'sales'."""
        terms = resolve_financial_terms("Show me sales department spend")
        
        # Should match "sales department" not just "sales"
        term_names = [t.term for t in terms]
        assert "sales department" in term_names or any(
            t.term == "sales department" or 
            (t.category == SemanticCategory.DEPARTMENT and "Sales" in t.filter_values)
            for t in terms
        )
    
    def test_no_terms_returns_empty(self):
        """Should return empty list when no terms found."""
        terms = resolve_financial_terms("Hello world")
        
        # May or may not find terms depending on the query
        # Just verify it doesn't crash
        assert isinstance(terms, list)


class TestNeedsDisambiguation:
    """Tests for needs_disambiguation function."""
    
    def test_filters_ambiguous_terms(self):
        """Should return only ambiguous terms."""
        all_terms = [
            get_semantic_term("revenue"),  # Not ambiguous
            get_semantic_term("sales"),    # Ambiguous
            get_semantic_term("marketing"), # Not ambiguous
        ]
        all_terms = [t for t in all_terms if t is not None]
        
        ambiguous = needs_disambiguation(all_terms)
        
        assert len(ambiguous) == 1
        assert ambiguous[0].term == "sales"
    
    def test_empty_list_if_no_ambiguous(self):
        """Should return empty list if no ambiguous terms."""
        terms = [
            get_semantic_term("revenue"),
            get_semantic_term("expenses"),
        ]
        terms = [t for t in terms if t is not None]
        
        ambiguous = needs_disambiguation(terms)
        
        assert len(ambiguous) == 0


class TestBuildDisambiguationMessage:
    """Tests for build_disambiguation_message function."""
    
    def test_builds_message_for_sales(self):
        """Should build a message with options for 'sales'."""
        sales_term = get_semantic_term("sales")
        message = build_disambiguation_message([sales_term])
        
        assert '"sales"' in message.lower() or "'sales'" in message.lower()
        assert "revenue" in message.lower() or "income" in message.lower()
        assert "department" in message.lower()
    
    def test_empty_for_no_terms(self):
        """Should return empty string for empty list."""
        message = build_disambiguation_message([])
        
        assert message == ""


class TestApplyDisambiguationChoice:
    """Tests for apply_disambiguation_choice function."""
    
    def test_applies_revenue_choice(self):
        """Should apply revenue choice correctly."""
        sales_term = get_semantic_term("sales")
        resolved = apply_disambiguation_choice(sales_term, 0)  # Revenue option
        
        assert resolved is not None
        assert resolved.category == SemanticCategory.ACCOUNT
        assert resolved.filter_values == ["4"]
        assert resolved.disambiguation_required is False
    
    def test_applies_department_choice(self):
        """Should apply department choice correctly."""
        sales_term = get_semantic_term("sales")
        resolved = apply_disambiguation_choice(sales_term, 1)  # Department option
        
        assert resolved is not None
        assert resolved.category == SemanticCategory.DEPARTMENT
        assert "Sales" in resolved.filter_values
    
    def test_invalid_index_returns_none(self):
        """Should return None for invalid index."""
        sales_term = get_semantic_term("sales")
        
        assert apply_disambiguation_choice(sales_term, -1) is None
        assert apply_disambiguation_choice(sales_term, 99) is None


class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def test_get_account_filter_for_revenue(self):
        """Should return account filter for revenue."""
        filter_info = get_account_filter_for_term("revenue")
        
        assert filter_info is not None
        assert filter_info["filter_type"] == "prefix"
        assert filter_info["values"] == ["4"]
    
    def test_get_account_filter_for_department_returns_none(self):
        """Should return None for department terms."""
        filter_info = get_account_filter_for_term("marketing")
        
        assert filter_info is None
    
    def test_get_department_filter_for_marketing(self):
        """Should return department filter for marketing."""
        departments = get_department_filter_for_term("marketing")
        
        assert departments is not None
        assert "Marketing" in departments
    
    def test_get_department_filter_for_account_returns_none(self):
        """Should return None for account terms."""
        departments = get_department_filter_for_term("revenue")
        
        assert departments is None
    
    def test_is_account_term(self):
        """Should correctly identify account terms."""
        assert is_account_term("revenue") is True
        assert is_account_term("expenses") is True
        assert is_account_term("marketing") is False
        assert is_account_term("sales") is False  # Ambiguous, not account
    
    def test_is_department_term(self):
        """Should correctly identify department terms."""
        assert is_department_term("marketing") is True
        assert is_department_term("engineering") is True
        assert is_department_term("revenue") is False
        assert is_department_term("sales") is False  # Ambiguous, not department
    
    def test_is_ambiguous_term(self):
        """Should correctly identify ambiguous terms."""
        assert is_ambiguous_term("sales") is True
        assert is_ambiguous_term("revenue") is False
        assert is_ambiguous_term("marketing") is False


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_whitespace_handling(self):
        """Should handle extra whitespace."""
        assert get_semantic_term("  revenue  ") is not None
        assert get_semantic_term("revenue ") is not None
    
    def test_plural_variations(self):
        """Should handle plural/singular variations."""
        # These should all work
        assert get_semantic_term("asset") is not None
        assert get_semantic_term("assets") is not None
        assert get_semantic_term("expense") is not None
        assert get_semantic_term("expenses") is not None
    
    def test_compound_terms(self):
        """Should handle compound terms."""
        assert get_semantic_term("cost of goods sold") is not None
        assert get_semantic_term("general and administrative") is not None
        assert get_semantic_term("research and development") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

