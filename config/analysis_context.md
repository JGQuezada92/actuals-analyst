# NetSuite Data Interpretation Guide

This document provides context for understanding and analyzing the NetSuite financial data.
The AI agent includes this context when generating analysis.

---

## Date Fields

**Always use "Month-End Date" for date-based queries.**

- The `Month-End Date` field (formuladate) represents the accounting period end date
- This should be used for all date filtering, YTD calculations, and period comparisons
- The `Transaction Date` (trandate) shows when the transaction occurred but may differ from the posting period
- Accounting periods are named like "Jan 2024", "Feb 2024", etc.

---

## Department Names

**Format: "Cost Category (Parent) : Department Name"**

Department names contain two pieces of information separated by " : ":

1. **Cost Category** (left side): The cost center classification
   - G&A = General & Administrative (overhead costs)
   - Cost of Sales = Direct costs of delivering products/services
   - R&D = Research & Development (product/engineering costs)
   - Sales & Marketing = Revenue generation costs

2. **Department Name** (right side): The actual department

### Examples:
| Raw Value | Cost Category | Department |
|-----------|---------------|------------|
| G&A (Parent) : Finance | G&A | Finance |
| G&A (Parent) : IT | G&A | IT |
| Cost of Sales (Parent) : GCC - Customer Centric Engineering | Cost of Sales | GCC - Customer Centric Engineering |
| R&D (Parent) : Engineering (Parent) | R&D | Engineering |

When a user asks about "G&A spend", include ALL departments under G&A (Finance, IT, HR, Legal, etc.).
When a user asks about "IT department", filter to just IT.

---

## Account Classification

**Account numbers indicate which financial statement the account appears on.**

### Income Statement Accounts (P&L)
Accounts starting with: **4, 5, 6, 7, 8**

| Prefix | Category | Description |
|--------|----------|-------------|
| 4 | Revenue | Income from sales and services |
| 5 | Operating Expenses | Operating expense accounts (parent category) |
| 51 | Cost of Goods Sold | Cost of Goods Sold/Cost of Sales |
| 52 | R&D | R&D/Product Development |
| 53 | Sales & Marketing | Sales & Marketing/S&M |
| 59 | General & Administrative | General & Administrative/G&A |
| 598 | Depreciation & Amortization | Depreciation & Amortization (within G&A) |
| 6 | Interest | Interest related accounts (expense or income) |
| 7 | Income Tax & Other | Income Tax, Other Expense and Other Income |
| 8 | Income Tax & Other | Income Tax, Other Expense and Other Income |

### Balance Sheet Accounts
Accounts starting with: **1, 2, 3**

| Prefix | Category | Description |
|--------|----------|-------------|
| 1 | Assets | What the company owns |
| 2 | Liabilities | What the company owes |
| 3 | Equity | Owner's stake in the company |

---

## Account Names

**The first segment of an account name (before the first ":") indicates its cost category.**

### Examples:
| Account Name | Cost Category | Interpretation |
|--------------|---------------|----------------|
| Sales & Marketing : Employee Costs : Payroll Taxes | Sales & Marketing | Payroll tax expense for S&M |
| G&A : Professional Services : Legal Fees | G&A | Legal fees as overhead |
| Accounts Payable : Accounts Payable A/P | Accounts Payable | Balance sheet liability |
| Purchase Tax Payables : Sales Tax Payable | Purchase Tax Payables | Sales tax liability |

---

## Amount Sign Convention

- **Expenses**: Positive amounts = expense increases (costs)
- **Revenue**: Amounts may appear as negative (credits) in the data
- **Debit Amount**: Increases assets/expenses
- **Credit Amount**: Increases liabilities/revenue/equity

When calculating "total spend" or "total expenses", sum the `amount` field for expense accounts.

---

## Subsidiaries

The `Entity` field (subsidiarynohierarchy) shows which legal entity the transaction belongs to:
- Phenom People Inc (US)
- Phenom People Private Limited (India)
- Phenom People Netherlands BV
- Phenom People Germany_Tandemploy
- And others...

When analyzing by subsidiary, group transactions by this field.

---

## Fiscal Calendar

**Fiscal year starts in February.**

- FY2024 = February 1, 2024 through January 31, 2025
- FY2025 = February 1, 2025 through January 31, 2026

When calculating YTD (Year-to-Date):
- Use the fiscal year start (February 1st), not January 1st
- "Current YTD" means from Feb 1 of current fiscal year to today

---

## Common Analysis Patterns

### YTD Spend by Department
1. Filter to Month-End Date >= Feb 1 of fiscal year
2. Filter to Income Statement accounts (prefixes 4-8)
3. Group by Department Name
4. Sum the Amount field

### Month-over-Month Variance
1. Filter current month by Month-End Date
2. Filter prior month by Month-End Date
3. Group by desired dimension (department, account, etc.)
4. Calculate: Current - Prior = Variance

### Cost Category Analysis
1. Parse department names to extract cost category
2. Group all departments by their cost category (G&A, Cost of Sales, R&D, S&M)
3. Sum amounts within each category

