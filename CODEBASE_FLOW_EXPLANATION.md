# How the Codebase Works: Query Flow Explanation

## Scenario: "what is the total YTD expense for the SDR department?"

### FIRST QUERY (Agent Startup)

#### Step 1: Query Parsing
```
Query: "what is the total YTD expense for the SDR department?"
  ↓
QueryParser.parse() creates ParsedQuery:
  - departments: ["SDR"]
  - time_period: YTD (Feb 2025 - Dec 2025)
  - account_type_filter: expense accounts (prefix "5")
  - intent: "total"
```

#### Step 2: Cache Key Generation
```python
# Location: NetSuiteDataRetriever._generate_cache_key()
cache_key = hash(
    search_id + 
    "tp:2025-02-01_2025-12-31" +  # time period
    "dept:SDR" +                    # department filter
    "acct:5"                        # account prefix
)
# Result: "customsearch1479_abc123def456"
```

#### Step 3: Cache Check
```python
# Location: NetSuiteDataRetriever.get_saved_search_data()
cached = self.cache.get(cache_key)
# Result: None (cache miss - first time)
```

#### Step 4: Registry Check & Fetch Decision
```python
# Location: NetSuiteRESTClient.execute_saved_search()
registry = get_dynamic_registry()

if registry.is_empty() or registry.needs_refresh():
    # Registry is empty → MUST do unfiltered fetch
    use_filtering = False
    logger.info("Registry needs refresh - using unfiltered fetch to rebuild")
else:
    # Registry populated → can use server-side filtering
    use_filtering = True
```

**First Query Result**: Registry is empty → `use_filtering = False`

#### Step 5: NetSuite API Call (UNFILTERED)
```python
# Fetches ALL data from NetSuite saved search
result = RESTlet.execute(search_id, filters=None)
# Returns: ~395,424 rows (ALL transactions)
```

#### Step 6: Cache Storage
```python
# Cache the result with the cache key
result.search_id = cache_key  # "customsearch1479_abc123def456"
self.cache.set(result)
# Stores: 395,424 rows with cache key that INCLUDES filter params
```

#### Step 7: Registry Population
```python
# Extract departments, accounts, subsidiaries from unfiltered data
registry.build_from_data(result.data)
# Registry now knows: 69 departments, 393 accounts, etc.
```

#### Step 8: Python-Side Filtering
```python
# Location: FinancialAnalystAgent._retrieve_data()
# Apply filters to the 395K rows
filtered = data_processor.apply_filters(
    data=395,424 rows,
    departments=["SDR"],
    period=YTD,
    account_type_filter={"prefix": "5"}
)
# Result: 2,218 rows
```

#### Step 9: Calculation
```python
# Calculate total expense
total = calculator.calculate_total(filtered_data)
# Result: $4,015,637.87
```

---

### SECOND QUERY (Same Exact Query)

#### Step 1: Query Parsing
```
Query: "what is the total YTD expense for the SDR department?"
  ↓
Same ParsedQuery as before:
  - departments: ["SDR"]
  - time_period: YTD
  - account_type_filter: expense accounts
```

#### Step 2: Cache Key Generation
```python
# SAME cache key (same query params)
cache_key = hash(
    search_id + 
    "tp:2025-02-01_2025-12-31" +
    "dept:SDR" +
    "acct:5"
)
# Result: "customsearch1479_abc123def456" (SAME KEY!)
```

#### Step 3: Cache Check
```python
cached = self.cache.get(cache_key)
# Result: Cache HIT! Returns cached SavedSearchResult
```

#### Step 4: Return Cached Data
```python
# Location: NetSuiteDataRetriever.get_saved_search_data()
if cached:
    logger.info(f"Cache hit for query {cache_key}")
    return cached  # Returns cached result immediately
    # NO NetSuite API call!
    # NO filtering needed!
```

**Wait... but the cached data has 395K rows, right?**

**NO!** Here's the key insight:

---

## THE CRITICAL DESIGN DECISION

### Cache Key Includes Filter Parameters

The cache key is generated **AFTER** parsing the query and includes the filter parameters:

```python
# Cache key includes:
- Time period (YTD dates)
- Departments (SDR)
- Account filters (prefix "5")
```

### What Gets Cached?

**Option A (Current Design):** Cache the **FILTERED** result
- Cache key includes filters → cached data is already filtered
- Second query gets cached filtered data (2,218 rows)
- Fast, but requires separate cache entry for each filter combination

**Option B (Database-like):** Cache the **UNFILTERED** result
- Single cache entry with all 395K rows
- Second query filters the cached data client-side
- Slower filtering, but one cache entry serves all queries

---

## WHY THE CURRENT DESIGN?

### Current Behavior (Cache Includes Filters)

**First Query:**
1. Cache miss → Fetch unfiltered (395K rows)
2. Filter client-side → 2,218 rows
3. Cache the **FILTERED** result (2,218 rows) with key that includes filters

**Second Query:**
1. Cache hit → Return cached **FILTERED** result (2,218 rows)
2. No filtering needed → Already filtered!
3. Instant response

**Pros:**
- ✅ Second query is instant (no filtering needed)
- ✅ No redundant filtering work
- ✅ Cache key uniquely identifies query result

**Cons:**
- ❌ Different filter combinations = different cache entries
- ❌ Can't reuse unfiltered data for different queries
- ❌ More cache storage needed

### Alternative Design (Database-like)

**First Query:**
1. Cache miss → Fetch unfiltered (395K rows)
2. Cache the **UNFILTERED** result with simple key (just search_id)
3. Filter client-side → 2,218 rows

**Second Query:**
1. Cache hit → Get cached **UNFILTERED** result (395K rows)
2. Filter client-side again → 2,218 rows
3. Fast response (filtering is quick)

**Pros:**
- ✅ One cache entry serves all queries
- ✅ Database-like behavior
- ✅ Less cache storage

**Cons:**
- ❌ Must filter every time (even for same query)
- ❌ Filtering overhead on every query

---

## THE ACTUAL FLOW IN YOUR CODEBASE

Looking at the code, here's what **actually** happens:

### Cache Key Generation
```python
# Location: NetSuiteDataRetriever._generate_cache_key()
def _generate_cache_key(self, search_id, parsed_query):
    key_parts = [search_id]
    
    if parsed_query.time_period:
        key_parts.append(f"tp:{start_date}_{end_date}")
    
    if parsed_query.departments:
        key_parts.append(f"dept:{','.join(departments)}")
    
    if parsed_query.account_type_filter:
        key_parts.append(f"acct:{values}")
    
    return hash(key_parts)  # Includes ALL filter params!
```

### What Gets Cached?
```python
# Location: NetSuiteDataRetriever.get_saved_search_data()
result = self.client.execute_saved_search(
    search_id=search_id,
    parsed_query=parsed_query,  # Filters passed here
)

# Result contains:
# - If unfiltered fetch: 395K rows
# - If server-side filtered: ~144 rows (current issue)
# - Result is cached AS-IS

result.search_id = cache_key  # Cache key includes filters
self.cache.set(result)  # Cache whatever was returned
```

### The Problem

**Current behavior:**
- Cache key includes filters → Different queries = different cache keys
- Cached data is whatever NetSuite returned (filtered or unfiltered)
- Second identical query → Cache hit → Returns cached data

**What you're asking for:**
- Cache unfiltered data once (395K rows)
- All queries filter from the same cached dataset
- Like a database: one dataset, multiple queries

---

## SOLUTION: Change Cache Strategy

To make it work like a database:

### Option 1: Cache Unfiltered Data Separately
```python
# Cache unfiltered data with simple key
unfiltered_cache_key = search_id  # No filters
unfiltered_data = cache.get(unfiltered_cache_key)

if not unfiltered_data:
    # Fetch unfiltered
    unfiltered_data = fetch_from_netsuite(filters=None)
    cache.set(unfiltered_cache_key, unfiltered_data)

# Always filter from unfiltered data
filtered_data = apply_filters(unfiltered_data, parsed_query)
```

### Option 2: Two-Level Cache
```python
# Level 1: Unfiltered data (long TTL)
unfiltered_key = search_id
unfiltered_data = cache.get(unfiltered_key)

# Level 2: Filtered results (short TTL)
filtered_key = hash(search_id + filters)
filtered_data = cache.get(filtered_key)

if not filtered_data:
    if not unfiltered_data:
        unfiltered_data = fetch_from_netsuite()
        cache.set(unfiltered_key, unfiltered_data, ttl=24h)
    
    filtered_data = apply_filters(unfiltered_data, parsed_query)
    cache.set(filtered_key, filtered_data, ttl=15min)
```

---

## SUMMARY

**Current Design:**
- Cache key = search_id + filters
- Cached data = whatever NetSuite returned (filtered or unfiltered)
- Second identical query → Cache hit → Returns cached result
- Different queries → Different cache keys → Different cache entries

**Why Second Query Doesn't Use 395K Rows:**
- Cache key includes filters → Second query has SAME cache key
- Cache hit returns cached result (which might be filtered or unfiltered)
- If first query cached filtered result, second query gets filtered result
- If first query cached unfiltered result, second query gets unfiltered result

**To Make It Database-like:**
- Cache unfiltered data separately (simple key: just search_id)
- Always filter from cached unfiltered data
- One cache entry serves all queries

