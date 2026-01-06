"""Test script to see what semantic terms are matched."""
from src.core.financial_semantics import resolve_financial_terms_with_ranges

query = "what is the total S&M expense for the SDR department for the current fiscal year?"
terms, ranges = resolve_financial_terms_with_ranges(query)

print("=" * 80)
print("SEMANTIC TERMS MATCHED")
print("=" * 80)
for term in terms:
    print(f"\nTerm: '{term.term}'")
    print(f"  Category: {term.category.value}")
    print(f"  Filter Type: {term.filter_type.value}")
    print(f"  Filter Values (prefixes): {term.filter_values}")
    if hasattr(term, 'secondary_filter_values') and term.secondary_filter_values:
        print(f"  Secondary Filter (account name): {term.secondary_filter_values}")
    print(f"  Description: {term.description}")

print("\n" + "=" * 80)
print("MATCHED RANGES")
print("=" * 80)
for start, end in ranges:
    print(f"  Position {start}:{end} -> '{query[start:end]}'")

