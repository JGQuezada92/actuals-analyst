"""Test query without server-side account prefix filter to compare totals."""
import asyncio
from src.agents.financial_analyst import get_financial_analyst
from src.core.query_parser import get_query_parser

async def test_unfiltered():
    query = "what is the total expense for the SDR department for the current fiscal year?"
    
    print("=" * 80)
    print("TEST 1: ALL EXPENSES (prefix 5) - NO ACCOUNT PREFIX FILTER")
    print("=" * 80)
    
    agent = get_financial_analyst()
    response = await agent.analyze(query, include_charts=False, max_iterations=1)
    
    print(f"\nQuery: {query}")
    print(f"Retrieved Rows: {response.metadata['data_rows']}")
    print(f"Filtered Rows: {response.metadata['filtered_rows']}")
    
    total_calc = next((c for c in response.calculations if c['metric_name'] == 'Total Amount'), None)
    if total_calc:
        print(f"Total Amount: {total_calc['formatted_value']}")
        print(f"Calculation Details: {total_calc.get('inputs', {})}")
    
    print("\n" + "=" * 80)
    print("TEST 2: S&M EXPENSES ONLY (prefix 53) - WITH ACCOUNT PREFIX FILTER")
    print("=" * 80)
    
    query2 = "what is the total S&M expense for the SDR department for the current fiscal year?"
    response2 = await agent.analyze(query2, include_charts=False, max_iterations=1)
    
    print(f"\nQuery: {query2}")
    print(f"Retrieved Rows: {response2.metadata['data_rows']}")
    print(f"Filtered Rows: {response2.metadata['filtered_rows']}")
    
    total_calc2 = next((c for c in response2.calculations if c['metric_name'] == 'Total Amount'), None)
    if total_calc2:
        print(f"Total Amount: {total_calc2['formatted_value']}")
        print(f"Calculation Details: {total_calc2.get('inputs', {})}")
    
    print("\n" + "=" * 80)
    print("COMPARISON")
    print("=" * 80)
    if total_calc and total_calc2:
        print(f"All Expenses (prefix 5): {total_calc['formatted_value']} ({response.metadata['data_rows']} rows)")
        print(f"S&M Expenses (prefix 53): {total_calc2['formatted_value']} ({response2.metadata['data_rows']} rows)")
        print(f"Difference: ${total_calc['value'] - total_calc2['value']:,.2f}")
        print(f"\nExpected: ~$3,800,000")
        print(f"Actual S&M: {total_calc2['formatted_value']}")
        print(f"Gap: ${3800000 - total_calc2['value']:,.2f}")

if __name__ == "__main__":
    asyncio.run(test_unfiltered())

