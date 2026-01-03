# NetSuite Financial Analyst Agent - Architecture Overview

## Executive Summary

The NetSuite Financial Analyst Agent is an **Accuracy-First Agentic AI System** that transforms natural language queries into structured financial analysis. It follows a phased pipeline architecture where each stage adds value and validation before proceeding to the next.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER INTERFACE LAYER                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Slack Bot  │  │  CLI (main)  │  │ Interactive  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  FINANCIAL ANALYST AGENT                         │
│                    (Orchestration Layer)                          │
│                                                                   │
│  Phase 0: Query Parsing → Phase 1: Data Retrieval →            │
│  Phase 2: Calculations → Phase 3: Charts → Phase 4: Analysis →  │
│  Phase 5: Evaluation                                             │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   CORE       │    │    TOOLS     │    │    DATA      │
│  (Logic)     │    │ (Execution)  │    │ (Storage)    │
└──────────────┘    └──────────────┘    └──────────────┘
```

---

## Folder Structure & Component Breakdown

### 📁 **Root Directory**

**Key Files:**
- `main.py` - Entry point with CLI commands (slack, analyze, interactive, setup)
- `README.md` - Project documentation
- `requirements.txt` - Python dependencies
- `.env` - Environment configuration (not in repo)

**Validation Scripts:**
- `validation_*.py` - Test scripts comparing agent results with ground truth Excel exports

---

### 📁 **`config/` - Configuration Layer**

**Purpose:** Centralized configuration management, model-agnostic settings

**Files:**
- `settings.py` - Model registry, NetSuite config, fiscal calendar settings
- `data_dictionary.yaml` - Field mappings, parsing rules, department hierarchy
- `analysis_context.md` - Context templates for LLM prompts

**Key Features:**
- **Model-Agnostic Design**: Single `ACTIVE_MODEL` env var routes to Gemini/Claude/GPT
- **Fiscal Calendar Config**: `FISCAL_YEAR_START_MONTH` (default: 2 = February)
- **Data Dictionary**: Declarative field mappings (no code changes needed)

**How It Works:**
- `get_config()` returns a singleton `Config` object
- Model selection via `ACTIVE_MODEL` env var
- All LLM calls route through `ModelRouter` which uses config

---

### 📁 **`src/core/` - Core Logic Layer**

**Purpose:** Business logic, query understanding, routing decisions

#### **`query_parser.py`** - Query Understanding Engine
- **Purpose:** Converts natural language to structured `ParsedQuery`
- **Key Features:**
  - Hybrid parsing: keyword extraction + LLM fallback
  - Extracts: intent, time periods, departments, accounts, subsidiaries
  - Integrates with `financial_semantics.py` for term resolution
  - Handles disambiguation (e.g., "sales" = revenue or department?)
- **Output:** `ParsedQuery` dataclass with all extracted filters

#### **`financial_semantics.py`** - Financial Term Dictionary
- **Purpose:** Maps natural language terms to technical filters
- **Key Features:**
  - 200+ semantic term mappings
  - Categories: ACCOUNT, DEPARTMENT, TRANSACTION_TYPE, SUBSIDIARY, AMBIGUOUS
  - **NEW:** `COMPOUND_ACCOUNT` for filters requiring both account number AND name
  - Disambiguation support for ambiguous terms
- **Example:** "sales and marketing cost" → account prefix "5" + name contains "Sales & Marketing"

#### **`fiscal_calendar.py`** - Fiscal Period Management
- **Purpose:** Handles custom fiscal year calculations
- **Key Features:**
  - Fiscal year naming (FY2026 = Feb 1, 2025 - Jan 31, 2026)
  - YTD, QTD, MTD calculations based on fiscal periods
  - Trailing period support (TTM, trailing N months)
  - Quarter/month range calculations
- **Output:** `FiscalPeriod` objects with start/end dates

#### **`data_router.py`** - Smart Data Source Routing
- **Purpose:** Routes queries to optimal data source
- **Decision Logic:**
  1. **Pre-aggregated cache** (if query matches cached pattern)
  2. **RESTlet full fetch** (for all queries requiring accurate financial data)
- **Note:** SuiteQL optimization has been removed due to accuracy issues
  (SuiteQL uses transaction date instead of posting period for financial reporting)

#### **`query_cost_estimator.py`** - Query Performance Prediction
- **Purpose:** Warns users about expensive queries
- **Estimates:** Row count, execution time, complexity
- **Output:** `QueryCostEstimate` with warnings if query is expensive

#### **`query_decomposer.py`** - Complex Query Breakdown
- **Purpose:** Breaks complex queries into sub-queries
- **Example:** "Compare revenue and expenses" → 2 separate queries
- **Status:** Implemented but not heavily used yet

#### **`model_router.py`** - LLM Abstraction Layer
- **Purpose:** Model-agnostic LLM interface
- **Supports:** Gemini, Claude, GPT-4
- **Key Features:**
  - Single API for all providers
  - Provider-specific prompt optimization
  - Automatic retry logic
  - Token counting

#### **`memory.py`** - Conversational Memory
- **Purpose:** Maintains conversation context across queries
- **Features:**
  - Session management
  - Turn history
  - Context accumulation
- **Used By:** Interactive mode, Slack bot

#### **`data_context.py`** - Data Field Mapping
- **Purpose:** Maps NetSuite field names to standardized names
- **Uses:** `data_dictionary.yaml` for configuration
- **Features:**
  - Account classification (revenue, expense, asset, etc.)
  - Department hierarchy parsing
  - Field alias resolution

---

### 📁 **`src/agents/` - Agent Orchestration**

#### **`financial_analyst.py`** - Main Agent
- **Purpose:** Orchestrates the entire analysis pipeline
- **Pipeline Phases:**

  **Phase 0: Query Parsing**
  - Uses `QueryParser` to extract structured query
  - Checks for disambiguation needs
  - Returns clarification request if ambiguous

  **Phase 1: Data Retrieval**
  - Uses `DataRouter` to select optimal source
  - Fetches data via `NetSuiteDataRetriever` (always uses RESTlet)
  - All filters applied in Python (post-retrieval)

  **Phase 1.5: Data Filtering**
  - Applies remaining filters in Python:
    - Time period (YTD, Q1, etc.)
    - Account type (prefix "4", "5", etc.)
    - Account name (contains "Sales & Marketing")
    - Department (contains "SDR", "Marketing")
    - Transaction type (Journal, VendBill, etc.)
  - Excludes "Total" accounts

  **Phase 2: Deterministic Calculations**
  - Uses `FinancialCalculator` for all math
  - Calculates: totals, ratios, trends, variances
  - **Key Principle:** LLM never calculates, only interprets

  **Phase 3: Chart Generation**
  - Uses `ChartGenerator` to create visualizations
  - Generates: line charts, bar charts, pie charts
  - Saves as PNG files for Slack upload

  **Phase 4: Analysis Generation + Reflection**
  - LLM generates narrative analysis
  - Uses reflection pattern (self-critique)
  - Iterative refinement (up to `max_iterations`)

  **Phase 5: Evaluation**
  - Uses `EvaluationHarness` to assess quality
  - Cross-model evaluation (generate with one, judge with another)
  - Returns accuracy scores and suggestions

- **Key Classes:**
  - `FinancialAnalystAgent` - Main orchestrator
  - `AnalysisContext` - Data passed through pipeline
  - `AgentResponse` - Final output with analysis, calculations, charts, evaluation

---

### 📁 **`src/tools/` - Execution Tools**

#### **`netsuite_client.py`** - NetSuite Data Retrieval
- **Purpose:** Fetches data from NetSuite
- **Method:** RESTlet (`get_saved_search_data()`)
  - Fetches full saved search results
  - Parallel pagination (async, 1000 rows/page)
  - Returns all ~391,000 rows
  - Filters applied in Python after retrieval
  - Uses posting period dates (`formuladate`) for accurate financial reporting

- **Key Features:**
  - Query-aware caching (hashed query parameters)
  - Automatic retry logic
  - Error handling with fallback
  - `execute_suiteql()` method retained for non-transaction data (budgets, accounts)

- **Note:** SuiteQL optimization for transaction data has been removed due to accuracy issues
  (SuiteQL uses transaction date instead of posting period)

#### **`data_processor.py`** - Data Transformation
- **Purpose:** Filters and transforms financial data
- **Key Methods:**
  - `filter_by_account_type()` - Account number prefix filtering
  - `filter_by_account_name()` - Account name contains filtering (NEW)
  - `filter_by_department()` - Department name filtering
  - `filter_by_date_range()` - Date range filtering
  - `filter_by_transaction_type()` - Transaction type filtering
  - `aggregate_by()` - Multi-dimensional aggregation
- **Features:**
  - Automatic field detection (handles various field name formats)
  - "Total" account exclusion
  - Date parsing (handles M/D/YYYY format)

#### **`calculator.py`** - Financial Calculations
- **Purpose:** Deterministic financial calculations
- **Key Metrics:**
  - Totals, averages, growth rates
  - Profitability ratios (gross margin, net margin)
  - Efficiency ratios (ROA, ROE)
  - Trend analysis (slope, direction)
- **Principle:** All math done here, LLM only interprets results

#### **`charts.py`** - Visualization Generation
- **Purpose:** Creates charts for Slack
- **Features:**
  - Line charts (trends over time)
  - Bar charts (comparisons)
  - Pie charts (breakdowns)
  - Saves as PNG files

---

### 📁 **`src/data/` - Data Storage & Aggregation**

#### **`aggregation_cache.py`** - Pre-Aggregated Data Cache
- **Purpose:** Caches common aggregations for fast responses
- **Features:**
  - TTL-based expiration
  - Pattern matching (YTD by department, etc.)
  - Automatic refresh
- **Status:** Implemented but not heavily used yet

#### **`budget_retriever.py`** - Budget Data Access
- **Purpose:** Retrieves budget data for variance analysis
- **Features:**
  - Budget vs. Actual comparisons
  - Favorable/unfavorable classification
  - Period matching
- **Status:** Implemented for Phase 4.2

#### **`account_hierarchy.py`** - Account Rollup Support
- **Purpose:** Handles parent-child account relationships
- **Features:**
  - Hierarchy building from flat data
  - Rollup aggregations
  - Parent account reporting
- **Status:** Implemented for Phase 4.4

---

### 📁 **`src/evaluation/` - Quality Assurance**

#### **`evaluator.py`** - Evaluation Harness
- **Purpose:** Assesses analysis quality
- **Two Evaluators:**
  1. **Objective Evaluator**
     - Checks: data grounding, calculation accuracy, completeness
     - Returns: pass/fail, accuracy score
  
  2. **Qualitative Evaluator**
     - LLM-as-a-judge evaluation
     - Dimensions: clarity, insightfulness, actionability, professionalism
     - Returns: scores (1-10) per dimension, average, suggestions

- **Key Feature:** Cross-model evaluation (generate with Gemini, judge with Claude)

---

### 📁 **`src/integrations/` - External Integrations**

#### **`slack_bot.py`** - Slack Integration
- **Purpose:** Slack bot interface
- **Features:**
  - Socket Mode (no public URL needed)
  - `/analyze` slash command
  - @mentions support
  - Chart uploads
  - Thread replies

---

### 📁 **`src/models/`** - Data Models
- **Purpose:** Shared data structures (currently minimal)
- **Status:** Mostly uses dataclasses in respective modules

---

### 📁 **`tests/`** - Test Suite
- **Purpose:** Unit tests
- **Files:**
  - `test_financial_semantics.py` - Semantic term resolution tests

---

## Data Flow: How It All Works Together

### Example Query: "What is the total sales and marketing cost YTD for the SDR department?"

```
1. USER INPUT
   └─> Slack Bot or CLI receives: "What is the total sales and marketing cost YTD for the SDR department?"

2. QUERY PARSING (Phase 0)
   └─> QueryParser.parse()
       ├─> financial_semantics.resolve_financial_terms()
       │   ├─> Finds "sales and marketing cost" → COMPOUND_ACCOUNT
       │   │   ├─> account_type_filter: prefix "5"
       │   │   └─> account_name_filter: contains "Sales & Marketing"
       │   ├─> Finds "SDR" → DEPARTMENT
       │   │   └─> departments: ["SDR"]
       │   └─> Finds "YTD" → TIME_PERIOD
       │       └─> time_period: FiscalPeriod(FY2026 YTD: Feb 1 - Nov 30)
       └─> Returns ParsedQuery with all filters

3. DISAMBIGUATION CHECK
   └─> If requires_disambiguation:
       └─> Return clarification request (e.g., "sales" = revenue or department?)
   └─> Else: Continue

4. DATA ROUTING (Phase 1)
   └─> DataRouter.route(parsed_query)
       ├─> Check cache → Miss
       └─> Returns: RoutingDecision(source=RESTLET_FULL)
           Reason: "All queries use RESTlet for accurate financial data"

5. DATA RETRIEVAL
   └─> NetSuiteDataRetriever.get_saved_search_data()
       ├─> Uses RESTlet (parallel pagination)
       ├─> Fetches all 390,000+ rows
       └─> Returns: SavedSearchResult(data=[...], row_count=390467)

6. DATA FILTERING (Phase 1.5)
   └─> DataProcessor applies filters:
       ├─> filter_by_period() → 390,467 → ~50,000 rows (Q1 period)
       ├─> filter_by_account_type(prefix "5") → ~20,000 rows
       ├─> filter_by_account_name(contains "Sales & Marketing") → ~5,000 rows
       ├─> filter_by_department(contains "SDR") → ~2,000 rows
       └─> Exclude "Total" accounts → 1,921 rows

7. CALCULATIONS (Phase 2)
   └─> FinancialCalculator.calculate()
       ├─> Sum all amounts → $3,536,137.27
       ├─> Group by account → 19 accounts
       ├─> Group by month → 10 months
       └─> Returns: [CalculationResult(...), ...]

8. CHART GENERATION (Phase 3)
   └─> ChartGenerator.generate()
       ├─> Monthly trend chart
       ├─> Account breakdown chart
       └─> Returns: [ChartOutput(...), ...]

9. ANALYSIS GENERATION (Phase 4)
   └─> LLM (via ModelRouter)
       ├─> Generate initial analysis
       ├─> Self-critique (reflection)
       ├─> Refine (up to max_iterations)
       └─> Returns: "Total SDR Sales & Marketing cost YTD is $3,536,137.27..."

10. EVALUATION (Phase 5)
    └─> EvaluationHarness.evaluate()
        ├─> Objective: Check data grounding, accuracy
        ├─> Qualitative: LLM-as-a-judge scores
        └─> Returns: EvaluationResult(passes_threshold=True, ...)

11. RESPONSE ASSEMBLY
    └─> Build AgentResponse:
        ├─> analysis: "Total SDR Sales & Marketing cost YTD is..."
        ├─> calculations: [{metric: "Total Cost", value: 3536137.27}, ...]
        ├─> charts: [ChartOutput(...), ...]
        └─> evaluation_summary: {passes_threshold: True, ...}

12. USER OUTPUT
    └─> Slack Bot uploads charts and sends analysis text
```

---

## Key Design Principles

### 1. **Accuracy-First Architecture**
- **Deterministic calculations** (code) + **Probabilistic interpretation** (LLM)
- LLM never calculates, only interprets pre-calculated results
- Cross-model evaluation for quality assurance

### 2. **Model-Agnostic Design**
- Single `ACTIVE_MODEL` env var controls all LLM routing
- `ModelRouter` abstracts provider differences
- Swap models without code changes

### 3. **Phased Quality Gates**
- Each phase validates before proceeding
- Disambiguation before data retrieval
- Evaluation after analysis generation

### 4. **Smart Data Routing**
- Cache → RESTlet priority
- All queries use RESTlet for accurate financial data (posting period dates)

### 5. **Semantic Understanding**
- Financial term dictionary (200+ terms)
- Handles ambiguity (asks for clarification)
- Compound filters (account number + name)

---

## Configuration Points

### Environment Variables (`.env`)
- `ACTIVE_MODEL` - LLM to use (gemini-2.0-flash, claude-sonnet-4, gpt-4o)
- `FISCAL_YEAR_START_MONTH` - Fiscal year start (default: 2 = February)
- `NETSUITE_*` - NetSuite authentication
- `SLACK_*` - Slack bot tokens
- `*_API_KEY` - LLM provider API keys

### Configuration Files
- `config/data_dictionary.yaml` - Field mappings, parsing rules
- `config/settings.py` - Model registry, default settings

---

## Extension Points

### Adding New Financial Terms
Edit `src/core/financial_semantics.py`:
```python
"new term": SemanticTerm(
    term="new term",
    category=SemanticCategory.ACCOUNT,
    filter_type=FilterType.PREFIX,
    filter_values=["5"],
    description="Description",
)
```

### Adding New Calculations
Edit `src/tools/calculator.py`:
```python
def my_new_metric(self, data: List[Dict]) -> CalculationResult:
    # Deterministic calculation
    value = ...
    return CalculationResult(...)
```

### Adding New Data Sources
Edit `src/core/data_router.py`:
- Add new `DataSource` enum value
- Update routing logic in `route()` method
- Implement retrieval in `SmartDataRetriever`

---

## Performance Characteristics

### Fast Queries (< 5 seconds)
- Cached aggregations
- RESTlet full fetch with Python filtering
- Simple calculations

### Medium Queries (5-30 seconds)
- RESTlet full fetch with Python filtering
- Account name filters (requires full data)
- Complex aggregations

### Slow Queries (30+ seconds)
- Large datasets (390,000+ rows)
- Multiple filters requiring full fetch
- Complex multi-dimensional aggregations

---

## Current Limitations & Future Enhancements

### Known Limitations
1. **All queries** require full data fetch via RESTlet for accuracy
2. **Large datasets** take ~10 minutes to fetch (~391,000 rows)
3. **Filters applied in Python** after data retrieval

### Future Enhancements
1. **Incremental caching**: Cache filtered subsets, not just full dataset
2. **Parallel processing**: Multi-threaded filtering for large datasets
3. **Smart caching**: Pre-filter common query patterns

---

## Summary

The NetSuite Financial Analyst Agent is a **sophisticated, accuracy-first system** that:

1. **Understands** natural language financial queries
2. **Routes** intelligently to optimal data sources
3. **Filters** precisely using semantic understanding
4. **Calculates** deterministically (no LLM math)
5. **Analyzes** with LLM interpretation
6. **Evaluates** quality before responding
7. **Delivers** professional financial insights

The architecture is **modular, extensible, and model-agnostic**, making it easy to add new features, swap LLM providers, or extend to new data sources.

