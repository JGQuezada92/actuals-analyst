"""
Mock NetSuite Data Generator

Generates fake financial data that mirrors the structure of real NetSuite saved search data.
This allows testing the codebase without exposing real financial data to LLM APIs.

Usage:
    Set USE_MOCK_DATA=true in .env to enable mock data mode.
"""
import random
import logging
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# Mock departments (mirroring real structure)
MOCK_DEPARTMENTS = [
    "G&A (Parent) : Finance",
    "G&A (Parent) : Human Resources",
    "G&A (Parent) : IT",
    "G&A (Parent) : Operations",
    "G&A (Parent) : Management",
    "Sales (Parent) : SDR",
    "Sales (Parent) : Account Management",
    "R&D (Parent) : Engineering",
    "R&D (Parent) : Product Management",
    "Marketing (Parent) : Marketing",
]

# Mock account prefixes and names
MOCK_ACCOUNTS = {
    "5": [  # Expense accounts
        ("531110", "Sales & Marketing : Employee Costs: Sales"),
        ("531130", "Sales & Marketing : Employee Costs: Sales"),
        ("531140", "Sales & Marketing : Employee Costs: Sales"),
        ("531160", "Sales & Marketing : Employee Costs: Sales"),
        ("531170", "Sales & Marketing : Employee Costs: Sales"),
        ("532020", "Sales & Marketing : Travel: Direct Sales"),
        ("532040", "Sales & Marketing : Travel: Direct Sales"),
        ("532050", "Sales & Marketing : Travel: Direct Sales"),
        ("532210", "Sales & Marketing : Professional Fees: Sales"),
        ("533060", "Sales & Marketing : Trade Shows, Events & Conferences"),
        ("533210", "Sales & Marketing : Travel: Marketing"),
        ("533240", "Sales & Marketing : Travel: Marketing"),
        ("533510", "Sales & Marketing : Trade Shows, Events & Conferences"),
        ("591110", "General & Administrative : Employee Cost"),
        ("591120", "General & Administrative : Employee Cost"),
        ("591130", "General & Administrative : Employee Cost"),
        ("591140", "General & Administrative : Employee Cost"),
        ("591320", "General & Administrative : Employee Cost"),
        ("591360", "General & Administrative : Employee Cost"),
        ("592010", "General & Administrative : Professional Fees"),
        ("592020", "General & Administrative : Professional Fees"),
        ("592030", "General & Administrative : Professional Fees"),
        ("593060", "General & Administrative : Facilities"),
        ("594020", "General & Administrative : Travel: G&A"),
        ("594030", "General & Administrative : Travel: G&A"),
        ("594040", "General & Administrative : Travel: G&A"),
        ("594060", "General & Administrative : Travel: G&A"),
        ("597010", "General & Administrative : Other Expense"),
        ("597060", "General & Administrative : Other Expense"),
        ("597070", "General & Administrative : Other Expense"),
        ("597140", "General & Administrative : Other Expense"),
    ],
    "53": [  # Sales & Marketing accounts (subset)
        ("531110", "Sales & Marketing : Employee Costs: Sales"),
        ("532020", "Sales & Marketing : Travel: Direct Sales"),
        ("532040", "Sales & Marketing : Travel: Direct Sales"),
        ("532210", "Sales & Marketing : Professional Fees: Sales"),
        ("533210", "Sales & Marketing : Travel: Marketing"),
        ("533240", "Sales & Marketing : Travel: Marketing"),
        ("533510", "Sales & Marketing : Trade Shows, Events & Conferences"),
    ],
}

# Mock transaction types
MOCK_TRANSACTION_TYPES = [
    "VendBill",
    "Journal",
    "VendorCredit",
    "ExpenseReport",
]

# Mock subsidiaries
MOCK_SUBSIDIARIES = [
    "Phenom People Inc",
    "Phenom Corp",
]

# FY2026 periods (Feb 2025 - Jan 2026)
FY2026_PERIODS = [
    "Feb 2025", "Mar 2025", "Apr 2025", "May 2025", "Jun 2025",
    "Jul 2025", "Aug 2025", "Sep 2025", "Oct 2025", "Nov 2025", "Dec 2025",
    "Jan 2026"
]

# Period to month-end date mapping
PERIOD_TO_DATE = {
    "Feb 2025": date(2025, 2, 1),
    "Mar 2025": date(2025, 3, 1),
    "Apr 2025": date(2025, 4, 1),
    "May 2025": date(2025, 5, 1),
    "Jun 2025": date(2025, 6, 1),
    "Jul 2025": date(2025, 7, 1),
    "Aug 2025": date(2025, 8, 1),
    "Sep 2025": date(2025, 9, 1),
    "Oct 2025": date(2025, 10, 1),
    "Nov 2025": date(2025, 11, 1),
    "Dec 2025": date(2025, 12, 1),
    "Jan 2026": date(2026, 1, 1),
}


def generate_mock_transaction(
    period: str,
    department: str,
    account_number: str,
    account_name: str,
    transaction_id: int,
) -> Dict[str, Any]:
    """
    Generate a single mock transaction row.
    
    Args:
        period: Period name (e.g., "Feb 2025")
        department: Department name
        account_number: Account number
        account_name: Account name
        transaction_id: Unique transaction ID
    
    Returns:
        Dict matching NetSuite saved search structure
    """
    # Generate realistic amount (expense accounts are typically positive)
    base_amount = random.uniform(10.0, 5000.0)
    # Occasionally add larger amounts
    if random.random() < 0.1:
        base_amount = random.uniform(5000.0, 50000.0)
    
    # Round to 2 decimals
    amount = round(base_amount, 2)
    
    # Determine if it's a debit or credit
    is_credit = random.random() < 0.3  # 30% chance of credit (negative)
    if is_credit:
        amount = -abs(amount)
    
    # Generate transaction date within the period
    period_date = PERIOD_TO_DATE.get(period, date(2025, 2, 1))
    # Random day within the month
    day = random.randint(1, 28)  # Use 28 to avoid month-end issues
    trandate = period_date.replace(day=day)
    
    # Format dates as strings (matching NetSuite format)
    trandate_str = f"{trandate.month}/{trandate.day}/{trandate.year}"
    formuladate_str = f"{period_date.month}/{period_date.day}/{period_date.year}"
    
    # Generate transaction type
    transaction_type = random.choice(MOCK_TRANSACTION_TYPES)
    
    # Generate memo
    memos = [
        "Monthly recurring expense",
        "Professional services",
        "Travel and entertainment",
        "Software subscription",
        "Office supplies",
        "Training and development",
        "Contractor payment",
        "Equipment purchase",
        "Marketing campaign",
        "Conference attendance",
    ]
    memo = random.choice(memos)
    
    # Generate vendor (sometimes)
    vendors = [
        "Vendor A",
        "Vendor B",
        "Vendor C",
        "Consultant XYZ",
        "Service Provider Inc",
        None,
    ]
    vendor = random.choice(vendors)
    
    # Build row matching NetSuite structure
    row = {
        "account_number": account_number,
        "account_name": account_name,
        "formulatext": str(random.randint(1, 100)),  # Department number
        "department_name": department,
        "amount": f"{amount:.2f}",
        "debitamount": f"{abs(amount):.2f}" if amount > 0 else "",
        "creditamount": f"{abs(amount):.2f}" if amount < 0 else "",
        "trandate": trandate_str,
        "accountingPeriod_periodname": period,
        "formuladate": formuladate_str,
        "subsidiarynohierarchy": random.choice(MOCK_SUBSIDIARIES),
        "type": transaction_type,
        "type_text": transaction_type.replace("VendBill", "Vendor Bill").replace("Vend", "Vendor ").replace("Credit", " Credit"),
        "memo": memo,
        "tranid": f"{transaction_id:03d}",
        "class": str(random.randint(100, 200)),
        "class_text": department,  # Class often matches department
    }
    
    # Add vendor if present
    if vendor:
        row["vendor_entityid"] = vendor
    
    # Add some optional fields that might be in real data
    if random.random() < 0.5:
        row["item_displayname"] = "- None -"
        row["item_parent"] = None
        row["item_parent_text"] = "- None -"
    
    if random.random() < 0.3:
        row["amortizationSchedule_amortemplate"] = "- None -"
        row["amortizationSchedule_schedulenumber"] = "- None -"
    
    return row


def generate_mock_netsuite_data(
    row_count: int = 1000,
    periods: Optional[List[str]] = None,
    departments: Optional[List[str]] = None,
    account_prefixes: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Generate mock NetSuite saved search data.
    
    Args:
        row_count: Number of rows to generate
        periods: Optional list of periods to include (defaults to FY2026)
        departments: Optional list of departments to include (defaults to all)
        account_prefixes: Optional list of account prefixes to include (defaults to ["5"])
    
    Returns:
        List of transaction rows matching NetSuite structure
    """
    if periods is None:
        periods = FY2026_PERIODS
    
    if departments is None:
        departments = MOCK_DEPARTMENTS
    
    if account_prefixes is None:
        account_prefixes = ["5"]
    
    # Collect all accounts matching the prefixes
    accounts_to_use = []
    for prefix in account_prefixes:
        if prefix in MOCK_ACCOUNTS:
            accounts_to_use.extend(MOCK_ACCOUNTS[prefix])
        else:
            # Generate some generic accounts for unknown prefixes
            for i in range(10):
                accounts_to_use.append(
                    (f"{prefix}{i:04d}", f"Account {prefix}{i:04d}")
                )
    
    if not accounts_to_use:
        # Fallback: use expense accounts
        accounts_to_use = MOCK_ACCOUNTS["5"][:10]
    
    data = []
    transaction_id = 1
    
    # Distribute rows across periods and departments
    rows_per_period = max(1, row_count // len(periods))
    rows_per_dept = max(1, rows_per_period // len(departments))
    
    for period in periods:
        for department in departments:
            # Generate rows for this period/department combination
            num_rows = random.randint(
                int(rows_per_dept * 0.5),
                int(rows_per_dept * 1.5)
            )
            
            for _ in range(num_rows):
                if len(data) >= row_count:
                    break
                
                account_number, account_name = random.choice(accounts_to_use)
                
                row = generate_mock_transaction(
                    period=period,
                    department=department,
                    account_number=account_number,
                    account_name=account_name,
                    transaction_id=transaction_id,
                )
                
                data.append(row)
                transaction_id += 1
            
            if len(data) >= row_count:
                break
        
        if len(data) >= row_count:
            break
    
    # Shuffle to make it more realistic
    random.shuffle(data)
    
    logger.info(f"Generated {len(data)} mock NetSuite transactions")
    return data


def get_mock_column_names() -> List[str]:
    """Get the column names that match real NetSuite saved search structure."""
    return [
        "account_number",
        "account_name",
        "formulatext",
        "department_name",
        "amount",
        "debitamount",
        "creditamount",
        "trandate",
        "accountingPeriod_periodname",
        "formuladate",
        "subsidiarynohierarchy",
        "type",
        "type_text",
        "memo",
        "tranid",
        "class",
        "class_text",
        "vendor_entityid",
        "item_displayname",
        "item_parent",
        "item_parent_text",
        "amortizationSchedule_amortemplate",
        "amortizationSchedule_schedulenumber",
    ]

