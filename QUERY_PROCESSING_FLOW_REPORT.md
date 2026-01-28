# Query Processing Flow: Phase-by-Phase Analysis

## Overview

This report explains how a user query flows through the NetSuite Analyst system, detailing where deterministic Python code handles processing and where LLM models are invoked for analysis generation.

**Example Query:** `"what are the total YTD expense for the product management department?"`

---

## Phase 0: Query Parsing (Deterministic)

### Python Code Location
- **File:** `src/core/query_parser.py`
- **Method:** `QueryParser.parse()`
- **Called from:** `FinancialAnalystAgent._parse_query()`

### What Happens (100% Deterministic)

1. **Intent Detection** (Regex-based)
   - Scans query for keywords matching `INTENT_PATTERNS`
   - Example: "total" → `QueryIntent.TOTAL`
   - Confidence score: 1.0 (exact match) or 0.7 (partial match)

2. **Time Period Extraction** (Regex + Fiscal Calendar)
   - Matches patterns like "YTD", "MTD", "this month", "FY2026"
   - Uses `FiscalCalendar` to resolve dates
   - Example: "YTD" → `FiscalPeriod(start_date="2025-02-01", end_date="2026-01-07")`

3. **Semantic Filter Extraction** (Financial Semantics Module)
   - Maps natural language to technical filters:
     - "expense" → Account prefix filter `["5"]` (expense accounts)
     - "revenue" → Account prefix filter `["4"]` (revenue accounts)
     - "sales" → Ambiguous (requires disambiguation)
   - Uses `financial_semantics.py` for term resolution

4. **Department Extraction** (Regex + Dynamic Registry)
   - Pattern matching: `r'\b([A-Z][A-Za-z0-9]{1,20})\s+(?:department|dept|expense)'`
   - Checks against `DynamicRegistry` for exact matches
   - Example: "product management department" → `["R&D (Parent) : Product Management"]`

5. **Disambiguation Detection**
   - If ambiguous terms found (e.g., "sales"), sets `requires_disambiguation=True`
   - Builds clarification message with options

### Output: `ParsedQuery` Object

```python
ParsedQuery(
    original_query="what are the total YTD expense for the product management department?",
    intent=QueryIntent.TOTAL,
    confidence=1.0,
    time_period=FiscalPeriod(period_name="FY2026 YTD", start_date="2025-02-01", end_date="2026-01-07"),
    departments=["R&D (Parent) : Product Management"],
    account_type_filter={"filter_type": "prefix", "values": ["5"]},
    requires_disambiguation=False
)
```

### LLM Usage: None

---

## Phase 1: Data Retrieval (Deterministic)

### Python Code Location
- **File:** `src/agents/financial_analyst.py`
- **Method:** `FinancialAnalystAgent._retrieve_data()`
- **Calls:** `NetSuiteDataRetriever.get_saved_search_data()`

### What Happens (100% Deterministic)

1. **Cache Check**
   - Generates cache key from `search_id` + filter hash
   - Checks disk cache for matching data
   - If cache hit: loads JSON file
   - If cache miss: proceeds to NetSuite API

2. **NetSuite RESTlet Call** (if cache miss)
   - Calls NetSuite RESTlet endpoint
   - RESTlet applies filters at database level (if supported)
   - Returns raw JSON data

3. **Data Summary Generation**
   - Counts rows, extracts column names
   - Creates `SavedSearchResult` object

### Output: `AnalysisContext` with `raw_data`

```python
AnalysisContext(
    query="what are the total YTD expense...",
    raw_data=SavedSearchResult(
        row_count=395611,
        column_names=['number', 'name', 'amount', 'trandate', 'periodname', 'formuladate', 'class', ...],
        data=[{...}, {...}, ...]  # List of 395,611 dictionaries
    ),
    data_summary={"row_count": 395611, "columns": [...]}
)
```

### LLM Usage: None

---

## Phase 1.5: Data Filtering (Deterministic)

### Python Code Location
- **File:** `src/agents/financial_analyst.py`
- **Method:** `FinancialAnalystAgent._filter_data()`
- **Calls:** `DataProcessor.filter_by_period()`, `DataProcessor.apply_filters()`

### What Happens (100% Deterministic)

Filters are applied sequentially in Python:

1. **Time Period Filter**
   - Filters by `periodname` field (e.g., "Feb 2025", "Mar 2025", ...)
   - Uses `FiscalPeriod` to determine which periods are in range
   - Result: `395611 → 184872 rows`

2. **Account Type Filter**
   - Filters by account prefix (e.g., accounts starting with "5" for expenses)
   - Excludes "Total" accounts
   - Result: `184872 → 63583 rows`

3. **Department Filter**
   - Exact match on department field
   - Example: `class == "R&D (Parent) : Product Management"`
   - Result: `63583 → 5143 rows`

4. **Transaction Type Filter** (if specified)
   - Filters by `type` field (e.g., "Journal", "VendBill")

### Output: Updated `AnalysisContext` with `filtered_data`

```python
context.filtered_data = [5143 filtered rows]
context.filter_summary = "Filtered 395611 -> 5143 rows (accountingPeriod_periodname in [...], account prefix in ['5'], department in ['R&D (Parent) : Product Management'])"
```

### LLM Usage: None

---

## Phase 2: Deterministic Calculations (100% Python)

### Python Code Location
- **File:** `src/agents/financial_analyst.py`
- **Method:** `FinancialAnalystAgent._perform_calculations()`
- **Calls:** `FinancialCalculator.ytd_total()`, `FinancialCalculator.sum_by_category()`

### What Happens (100% Deterministic)

1. **Total Amount Calculation**
   ```python
   total = sum(float(row.get("amount", 0) or 0) for row in data)
   # Result: 11363851.178
   ```

2. **Fiscal YTD Calculation**
   - Uses `formuladate` (month-end posting date)
   - Filters to fiscal year start date through current date
   - Sums amounts: `$11.36M`

3. **Category Breakdowns**
   - Groups by `type` field (Journal, VendBill, etc.)
   - Calculates subtotals and percentages
   - Example: Journal Total: $10.14M (89.21%)

4. **Trend Analysis** (if requested)
   - Linear regression on time series
   - Calculates slope, R², confidence intervals

5. **Variance Calculations** (if comparison requested)
   - Compares current period vs. prior period
   - Calculates absolute and percentage differences

### Output: `List[CalculationResult]`

```python
calculations = [
    CalculationResult(
        metric_name="Total Amount",
        value=11363851.178,
        formatted_value="$11,363,851.18",
        metric_type=MetricType.CASH_FLOW,
        formula="Sum of amount",
        interpretation_guide="The total across all 5143 records is $11,363,851.18."
    ),
    CalculationResult(
        metric_name="FY2026 YTD Total",
        value=11363851.178000005,
        formatted_value="$11.36M",
        formula="Sum of amount from 2025-02-01 to 2026-01-07",
        interpretation_guide="Year-to-date total for FY2026 is $11.36M..."
    ),
    # ... more calculations
]
```

### LLM Usage: None

---

## Phase 2.5: Statistical Analysis (Deterministic, Conditional)

### Python Code Location
- **File:** `src/agents/financial_analyst.py`
- **Method:** `FinancialAnalystAgent._run_statistical_analysis()`
- **Calls:** `StatisticalAnalyzer.full_revenue_correlation_analysis()`

### What Happens (100% Deterministic)

Only runs if `parsed_query.intent` is `CORRELATION`, `REGRESSION`, or `VOLATILITY`.

1. **Correlation Analysis**
   - Calculates Pearson correlations between revenue and expense categories
   - Identifies statistically significant relationships (p < 0.05)
   - Generates lagged correlation analysis

2. **Regression Analysis**
   - OLS regression with revenue as dependent variable
   - Calculates coefficients, R², p-values
   - Identifies explanatory variables

3. **ARCH/GARCH Volatility Analysis**
   - Models time-varying variance
   - Identifies volatility clustering

### Output: `Dict[str, Any]` with statistical results

```python
context.statistical_analysis = {
    "correlation_analysis": CorrelationAnalysis(...),
    "regression_result": RegressionResult(...),
    "llm_context": "Revenue shows strong positive correlation (r=0.85, p<0.01) with Marketing expenses..."
}
```

### LLM Usage: None (but generates text context for Phase 4)

---

## Phase 3: Chart Generation (Deterministic)

### Python Code Location
- **File:** `src/agents/financial_analyst.py`
- **Method:** `FinancialAnalystAgent._generate_charts()`
- **Calls:** `ChartGenerator.bar_chart()`, `ChartGenerator.line_chart()`

### What Happens (100% Deterministic)

1. **Chart Type Detection**
   - Determines chart type from query intent and data structure
   - Bar charts for category breakdowns
   - Line charts for time series

2. **Data Aggregation**
   - Groups data by category/date
   - Calculates sums for each group

3. **Matplotlib Rendering**
   - Uses professional financial styling (Arial Narrow, teal/navy/orange palette)
   - Generates PNG files
   - Saves to `.charts/` directory

### Output: `List[ChartOutput]`

```python
charts = [
    ChartOutput(
        chart_type="bar",
        title="Expenses by Category",
        file_path=".charts/chart_12345.png",
        file_bytes=<PNG bytes>,
        alt_text="Bar chart showing Journal: $10.14M, VendBill: $1.23M"
    )
]
```

### LLM Usage: None

---

## Phase 4: Analysis Generation (LLM-Driven)

### Python Code Location
- **File:** `src/agents/financial_analyst.py`
- **Method:** `FinancialAnalystAgent._generate_analysis()`
- **LLM Router:** `ModelRouter.generate_with_system()`

### What Happens (Hybrid: Python Prepares, LLM Generates)

#### Step 1: Python Prepares Context (Deterministic)

1. **Calculation Summary**
   ```python
   calc_summary = "\n".join([
       f"- {c.metric_name}: {c.formatted_value} ({c.interpretation_guide})"
       for c in context.calculations[:20]
   ])
   ```
   Output:
   ```
   - Total Amount: $11,363,851.18 (The total across all 5143 records...)
   - FY2026 YTD Total: $11.36M (Year-to-date total for FY2026...)
   - Journal Total: $10.14M (Journal represents 89.21% of total...)
   ```

2. **Sample Data Extraction**
   - Takes first 10 rows from filtered data
   - Converts to JSON string

3. **Date Range Calculation**
   - Extracts min/max dates from data
   - Formats as "2025-02-01 to 2026-01-07"

4. **Conversation Context** (if session exists)
   - Retrieves previous conversation history
   - Formats as prompt context

5. **Parsed Query Info**
   - Formats intent, time period, departments, accounts
   - Adds to prompt context

6. **Statistical Context** (if available)
   - Adds statistical analysis results

#### Step 2: Prompt Construction (Deterministic)

**Prompt Manager** (`src/core/prompt_manager.py`):
- Loads versioned prompt from `config/prompts/financial_analysis/v1.0.yaml`
- Formats template with variables

**System Prompt** (from YAML):
```
You are a senior financial analyst with expertise in interpreting 
NetSuite financial data. You provide accurate, insightful analysis based strictly on 
the data provided.

## Core Principles
1. **Data-Grounded**: Every claim must reference specific data points
2. **Calculated Precision**: Use the provided calculation results - do not recalculate
3. **Actionable Insights**: Provide clear, specific recommendations
4. **Professional Tone**: Write for a CFO-level audience

## Analysis Structure
1. Executive Summary (2-3 sentences)
2. Key Findings (with specific numbers)
3. Trend Analysis (if applicable)
4. Recommendations (specific, actionable)
```

**User Prompt** (formatted):
```
Analyze the following financial data and provide a professional analysis.

## Query
what are the total YTD expense for the product management department?

(Data filtered: Filtered 395611 -> 5143 rows...)

## Time Context
2025-02-01 to 2026-01-07

## Data Summary
- Total rows: 5143
- Date range: 2025-02-01 to 2026-01-07
- Columns available: number, name, amount, trandate, periodname, formuladate, class, ...

## Pre-Calculated Metrics
IMPORTANT: Use these exact values - do not recalculate.
- Total Amount: $11,363,851.18 (The total across all 5143 records...)
- FY2026 YTD Total: $11.36M (Year-to-date total for FY2026...)
- Journal Total: $10.14M (Journal represents 89.21% of total...)
- VendBill Total: $1.23M (VendBill represents 10.79% of total...)
- Trend Analysis: Upward trend ($0.24/period) (Data shows a weak upward trend...)

## Sample Data (first 10 rows)
[
  {"number": "JE-12345", "amount": 50000, "type": "Journal", ...},
  ...
]

## Detected Analysis Parameters
- Intent: total
- Time Period: FY2026 YTD (2025-02-01 to 2026-01-07)
- Departments: R&D (Parent) : Product Management
```

#### Step 3: LLM Generation (LLM-Driven)

**Code Structure:**
```python
response = self.router.generate_with_system(
    system_prompt=system_prompt,
    user_message=user_prompt,
)
```

**What the LLM Does:**
1. Receives structured prompt with:
   - System instructions (role, principles, structure)
   - User query
   - Pre-calculated metrics (must use these, not recalculate)
   - Sample data
   - Filter summary
   - Statistical context (if available)

2. Generates analysis following structure:
   - Executive Summary
   - Key Findings (references specific calculations)
   - Trend Analysis
   - Recommendations

3. **Critical Constraint:** LLM must use provided calculations, not recalculate

#### Step 4: Reflection Loop (LLM-Driven, Optional)

**Code:** `Evaluator.reflect_and_improve()`

If `max_iterations > 1`:
1. **First Iteration:** LLM generates initial analysis
2. **Reflection:** LLM evaluates its own work (0-10 score)
3. **Improvement:** If score < threshold, LLM revises analysis
4. **Repeat:** Up to `max_iterations` times

**Reflection Prompt Structure:**
```
Evaluate this financial analysis on:
- Numerical accuracy (uses provided calculations correctly)
- Claim substantiation (references specific data)
- Completeness (covers all key findings)
- Insight quality (provides meaningful insights)
- Actionability (recommendations are specific)
- Clarity (well-structured, easy to read)

Score each dimension 0-10 and provide rationale.
```

### Output: Analysis Text String

```python
context.analysis_text = """*Executive Summary:*
The Product Management department has incurred total expenses of $11.36M YTD in FY2026...

*Key Findings:*
*   The total YTD expense for the Product Management department is *$11.36M*...
*   *Journal entries* account for $10.14M (89.21%) of the total expenses...
...
"""
```

### LLM Usage: Yes
- **Model:** Configured via `ModelRouter` (e.g., `gemini-2.0-flash`)
- **Purpose:** Generate narrative analysis from structured data
- **Constraints:** Must use provided calculations, follow structure

---

## Phase 5: Evaluation (LLM-Driven)

### Python Code Location
- **File:** `src/evaluation/evaluator.py`
- **Method:** `EvaluationHarness.evaluate_analysis()`
- **LLM Router:** `get_judge_router()` (different model than generator)

### What Happens (Hybrid: Python Prepares, LLM Judges)

#### Step 1: Objective Evaluation (Deterministic)

**Code:** `ObjectiveEvaluator.evaluate()`

1. Compares calculations against expected values (from golden dataset)
2. Calculates deviation percentages
3. Determines if within tolerance

**Output:**
```python
objective_scores = [
    ObjectiveScore(
        metric_name="FY2026 YTD Total",
        expected_value=11363851.18,
        actual_value=11363851.178000005,
        is_correct=True,
        deviation=0.0001
    )
]
objective_accuracy = 1.0  # 100% correct
```

#### Step 2: Qualitative Evaluation (LLM-Driven)

**Code:** `QualitativeEvaluator.evaluate()`

**Prompt Structure:**
```
Evaluate this financial analysis on the following dimensions:

1. **Numerical Accuracy**: Does the analysis use the provided calculations correctly?
2. **Claim Substantiation**: Are claims backed by specific data points?
3. **Completeness**: Does it cover all key findings?
4. **Insight Quality**: Are insights meaningful and non-obvious?
5. **Actionability**: Are recommendations specific and actionable?
6. **Clarity**: Is it well-structured and easy to read?

Analysis to evaluate:
{analysis_text}

Pre-calculated metrics:
{calculations}

Score each dimension 0-10 and provide rationale.
```

**LLM Response:**
```json
{
  "dimensions": {
    "numerical_accuracy": {"score": 9, "rationale": "Correctly uses all provided calculations..."},
    "claim_substantiation": {"score": 8, "rationale": "References specific dollar amounts..."},
    ...
  },
  "suggestions": ["Consider adding more context about capitalized software costs..."]
}
```

#### Step 3: Aggregation (Deterministic)

**Code:** Combines objective and qualitative scores

```python
evaluation = EvaluationResult(
    objective_scores=objective_scores,
    objective_accuracy=1.0,
    qualitative_scores=qualitative_scores,
    average_qualitative_score=8.5,
    passes_threshold=True,  # If avg > 7.0
    improvement_suggestions=["Consider adding more context..."]
)
```

### Output: `EvaluationResult` Object

### LLM Usage: Yes
- **Model:** Different from generator (prevents self-bias)
- **Purpose:** Judge quality of generated analysis
- **Output:** Scores, rationale, improvement suggestions

---

## Final Response Assembly (Deterministic)

### Python Code Location
- **File:** `src/agents/financial_analyst.py`
- **Method:** `FinancialAnalystAgent._build_response()`

### What Happens (100% Deterministic)

Assembles all phase outputs into final response:

```python
return AgentResponse(
    analysis=context.analysis_text,  # From Phase 4
    calculations=[c.to_dict() for c in context.calculations],  # From Phase 2
    charts=context.charts,  # From Phase 3
    evaluation_summary={
        "passes_threshold": context.evaluation.passes_threshold,  # From Phase 5
        "objective_accuracy": context.evaluation.objective_accuracy,
        "qualitative_score": context.evaluation.average_qualitative_score,
        "suggestions": context.evaluation.improvement_suggestions
    },
    metadata={
        "query": context.query,
        "data_rows": context.raw_data.row_count,
        "filtered_rows": len(context.working_data),
        "iteration_count": context.iteration_count,
        "model_used": self.router.config.model_name,
        "filter_summary": context.filter_summary
    }
)
```

### LLM Usage: None

---

## Summary: Deterministic vs. LLM Phases

| Phase | Component | Deterministic? | LLM Used? | Output Type |
|-------|-----------|----------------|-----------|-------------|
| 0 | Query Parsing | ✅ 100% | ❌ | `ParsedQuery` |
| 1 | Data Retrieval | ✅ 100% | ❌ | `SavedSearchResult` |
| 1.5 | Data Filtering | ✅ 100% | ❌ | Filtered data list |
| 2 | Calculations | ✅ 100% | ❌ | `List[CalculationResult]` |
| 2.5 | Statistical Analysis | ✅ 100% | ❌ | Statistical results dict |
| 3 | Chart Generation | ✅ 100% | ❌ | `List[ChartOutput]` |
| 4 | Analysis Generation | 🔄 Hybrid | ✅ | Analysis text string |
| 5 | Evaluation | 🔄 Hybrid | ✅ | `EvaluationResult` |

### Key Insights

1. **Deterministic Foundation:** Phases 0-3 are 100% deterministic Python code. They produce structured, verifiable outputs.

2. **LLM Augmentation:** Phases 4-5 use LLMs to:
   - Generate narrative analysis from structured data (Phase 4)
   - Evaluate quality and provide feedback (Phase 5)

3. **Separation of Concerns:**
   - **Python handles:** Data retrieval, filtering, calculations, chart generation
   - **LLM handles:** Natural language generation, qualitative assessment

4. **Error Resilience:** If LLM fails (quota exhausted, API error), system still returns:
   - All calculations (Phase 2)
   - Charts (Phase 3)
   - Placeholder analysis text
   - No evaluation (Phase 5 skipped)

5. **Prompt Engineering:**
   - System prompts define role and constraints
   - User prompts provide structured context
   - LLM is constrained to use provided calculations (not recalculate)

6. **Quality Control:**
   - Objective evaluation: Deterministic comparison against expected values
   - Qualitative evaluation: LLM-as-a-Judge with different model
   - Reflection loop: LLM self-critiques and improves

---

## Code Structure Guiding LLM Behavior

### 1. Prompt Templates (`config/prompts/financial_analysis/v1.0.yaml`)
- **System Prompt:** Defines role, principles, structure
- **User Prompt Template:** Structured format with variables
- **Versioning:** Allows prompt evolution without code changes

### 2. Prompt Manager (`src/core/prompt_manager.py`)
- Loads versioned prompts from YAML
- Formats templates with context variables
- Falls back to inline prompts if file not found

### 3. Model Router (`src/core/model_router.py`)
- Abstracts LLM provider differences
- Handles errors (quota exhausted, content blocked)
- Tracks usage and latency

### 4. Context Assembly (`FinancialAnalystAgent._generate_analysis()`)
- Prepares structured context from deterministic outputs
- Formats calculations, sample data, filters
- Adds conversation history and statistical context

### 5. Reflection System (`Evaluator.reflect_and_improve()`)
- Iterative improvement loop
- LLM evaluates its own work
- Stops when quality threshold met

---

## Example Flow Diagram

```
User Query
    ↓
[Phase 0] Query Parsing (Python) → ParsedQuery
    ↓
[Phase 1] Data Retrieval (Python) → Raw Data (395,611 rows)
    ↓
[Phase 1.5] Data Filtering (Python) → Filtered Data (5,143 rows)
    ↓
[Phase 2] Calculations (Python) → 5 CalculationResults
    ↓
[Phase 3] Chart Generation (Python) → 0 Charts (--no-charts flag)
    ↓
[Phase 4] Analysis Generation (LLM)
    ├─ Python: Prepares context, builds prompt
    ├─ LLM: Generates analysis text
    └─ Output: Analysis string
    ↓
[Phase 5] Evaluation (LLM)
    ├─ Python: Objective evaluation (deterministic)
    ├─ LLM: Qualitative evaluation
    └─ Output: EvaluationResult
    ↓
[Final] Response Assembly (Python) → AgentResponse
```

---

## Conclusion

The system uses a **hybrid architecture** where:
- **Deterministic Python code** handles all data processing, calculations, and filtering
- **LLM models** handle natural language generation and qualitative assessment
- **Clear separation** ensures calculations are always accurate (Python) while analysis is contextualized (LLM)
- **Error resilience** allows partial results even if LLM fails

This design ensures **accuracy-first** analysis: calculations are always deterministic, while LLM provides narrative context and insights.
