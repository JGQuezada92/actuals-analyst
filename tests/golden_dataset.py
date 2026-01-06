"""
Golden Dataset Infrastructure for Regression Testing

Provides structured test cases with expected outcomes for validating
the financial analyst agent against known-good results.

Usage:
    from tests.golden_dataset import GoldenDataset, run_regression_suite
    
    dataset = GoldenDataset.load(Path("tests/golden_sets/v1.0.json"))
    results = run_regression_suite(agent, dataset)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class ExpectedCalculation:
    """Expected calculation result with tolerance."""
    metric_name: str
    expected_value: float
    tolerance_percent: float = 1.0  # Default 1% tolerance
    
    def matches(self, actual_value: float) -> bool:
        """Check if actual value is within tolerance."""
        if self.expected_value == 0:
            return abs(actual_value) < 0.01
        deviation = abs((actual_value - self.expected_value) / self.expected_value)
        return deviation <= (self.tolerance_percent / 100)


@dataclass
class GoldenTestCase:
    """
    A single test case with expected outcomes.
    
    Test cases should be created from actual production queries
    where the correct answer has been manually verified.
    """
    test_id: str
    name: str
    description: str
    query: str
    
    # Expected parsing results
    expected_intent: str
    expected_departments: List[str] = field(default_factory=list)
    expected_account_prefix: Optional[List[str]] = None
    expected_account_name_contains: Optional[List[str]] = None
    expected_time_period: Optional[str] = None
    
    # Expected calculation results (the ground truth)
    expected_calculations: List[ExpectedCalculation] = field(default_factory=list)
    
    # Content validation
    analysis_must_contain: List[str] = field(default_factory=list)
    analysis_must_not_contain: List[str] = field(default_factory=list)
    
    # Quality thresholds
    min_evaluation_score: float = 7.0
    min_confidence: float = 0.6
    
    # Metadata
    created_at: Optional[str] = None
    data_snapshot_date: Optional[str] = None
    notes: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoldenTestCase":
        """Create test case from dictionary."""
        expected_calcs = [
            ExpectedCalculation(**calc) if isinstance(calc, dict) else calc
            for calc in data.get("expected_calculations", [])
        ]
        return cls(
            test_id=data["test_id"],
            name=data["name"],
            description=data.get("description", ""),
            query=data["query"],
            expected_intent=data["expected_intent"],
            expected_departments=data.get("expected_departments", []),
            expected_account_prefix=data.get("expected_account_prefix"),
            expected_account_name_contains=data.get("expected_account_name_contains"),
            expected_time_period=data.get("expected_time_period"),
            expected_calculations=expected_calcs,
            analysis_must_contain=data.get("analysis_must_contain", []),
            analysis_must_not_contain=data.get("analysis_must_not_contain", []),
            min_evaluation_score=data.get("min_evaluation_score", 7.0),
            min_confidence=data.get("min_confidence", 0.6),
            created_at=data.get("created_at"),
            data_snapshot_date=data.get("data_snapshot_date"),
            notes=data.get("notes"),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize test case to dictionary."""
        return {
            "test_id": self.test_id,
            "name": self.name,
            "description": self.description,
            "query": self.query,
            "expected_intent": self.expected_intent,
            "expected_departments": self.expected_departments,
            "expected_account_prefix": self.expected_account_prefix,
            "expected_account_name_contains": self.expected_account_name_contains,
            "expected_time_period": self.expected_time_period,
            "expected_calculations": [
                {"metric_name": c.metric_name, "expected_value": c.expected_value, "tolerance_percent": c.tolerance_percent}
                for c in self.expected_calculations
            ],
            "analysis_must_contain": self.analysis_must_contain,
            "analysis_must_not_contain": self.analysis_must_not_contain,
            "min_evaluation_score": self.min_evaluation_score,
            "min_confidence": self.min_confidence,
            "created_at": self.created_at,
            "data_snapshot_date": self.data_snapshot_date,
            "notes": self.notes,
        }


@dataclass
class TestResult:
    """Result of running a single test case."""
    test_id: str
    test_name: str
    passed: bool
    
    # Detailed results
    intent_matched: bool = True
    departments_matched: bool = True
    calculations_matched: bool = True
    content_valid: bool = True
    evaluation_passed: bool = True
    
    # Actual values for debugging
    actual_intent: Optional[str] = None
    actual_departments: List[str] = field(default_factory=list)
    actual_calculations: Dict[str, float] = field(default_factory=dict)
    actual_evaluation_score: Optional[float] = None
    
    # Failure details
    failure_reasons: List[str] = field(default_factory=list)
    
    # Timing
    execution_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "passed": self.passed,
            "intent_matched": self.intent_matched,
            "departments_matched": self.departments_matched,
            "calculations_matched": self.calculations_matched,
            "content_valid": self.content_valid,
            "evaluation_passed": self.evaluation_passed,
            "actual_intent": self.actual_intent,
            "actual_departments": self.actual_departments,
            "actual_calculations": self.actual_calculations,
            "actual_evaluation_score": self.actual_evaluation_score,
            "failure_reasons": self.failure_reasons,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class RegressionReport:
    """Summary report of a regression test run."""
    dataset_version: str
    run_timestamp: str
    total_tests: int
    passed: int
    failed: int
    errors: int
    
    pass_rate: float = 0.0
    total_execution_time_ms: float = 0.0
    
    results: List[TestResult] = field(default_factory=list)
    
    def __post_init__(self):
        if self.total_tests > 0:
            self.pass_rate = self.passed / self.total_tests
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "run_timestamp": self.run_timestamp,
            "summary": {
                "total_tests": self.total_tests,
                "passed": self.passed,
                "failed": self.failed,
                "errors": self.errors,
                "pass_rate": f"{self.pass_rate:.1%}",
                "total_execution_time_ms": self.total_execution_time_ms,
            },
            "results": [r.to_dict() for r in self.results],
        }
    
    def print_summary(self):
        """Print human-readable summary."""
        print("\n" + "=" * 60)
        print("REGRESSION TEST RESULTS")
        print("=" * 60)
        print(f"Dataset Version: {self.dataset_version}")
        print(f"Run Time: {self.run_timestamp}")
        print(f"\nResults: {self.passed}/{self.total_tests} passed ({self.pass_rate:.1%})")
        print(f"  ✅ Passed: {self.passed}")
        print(f"  ❌ Failed: {self.failed}")
        print(f"  ⚠️  Errors: {self.errors}")
        print(f"\nTotal Execution Time: {self.total_execution_time_ms/1000:.1f}s")
        
        if self.failed > 0 or self.errors > 0:
            print("\n" + "-" * 60)
            print("FAILURES:")
            for result in self.results:
                if not result.passed:
                    print(f"\n  [{result.test_id}] {result.test_name}")
                    for reason in result.failure_reasons:
                        print(f"    - {reason}")
        print("=" * 60)


@dataclass
class GoldenDataset:
    """Collection of test cases for regression testing."""
    version: str
    name: str
    description: str
    created_at: str
    test_cases: List[GoldenTestCase]
    
    # Metadata
    data_source: Optional[str] = None
    fiscal_year: Optional[str] = None
    notes: Optional[str] = None
    
    @classmethod
    def load(cls, path: Path) -> "GoldenDataset":
        """Load dataset from JSON file."""
        with open(path) as f:
            data = json.load(f)
        
        test_cases = [GoldenTestCase.from_dict(tc) for tc in data.get("test_cases", [])]
        
        return cls(
            version=data["version"],
            name=data["name"],
            description=data.get("description", ""),
            created_at=data["created_at"],
            test_cases=test_cases,
            data_source=data.get("data_source"),
            fiscal_year=data.get("fiscal_year"),
            notes=data.get("notes"),
        )
    
    def save(self, path: Path):
        """Save dataset to JSON file."""
        data = {
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "data_source": self.data_source,
            "fiscal_year": self.fiscal_year,
            "notes": self.notes,
            "test_cases": [tc.to_dict() for tc in self.test_cases],
        }
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_test_case(self, test_case: GoldenTestCase):
        """Add a test case to the dataset."""
        self.test_cases.append(test_case)
    
    def get_test_case(self, test_id: str) -> Optional[GoldenTestCase]:
        """Get a test case by ID."""
        for tc in self.test_cases:
            if tc.test_id == test_id:
                return tc
        return None


async def run_single_test(
    agent,
    test_case: GoldenTestCase,
) -> TestResult:
    """Run a single test case and return results."""
    import time
    
    result = TestResult(
        test_id=test_case.test_id,
        test_name=test_case.name,
        passed=True,
    )
    
    start_time = time.time()
    
    try:
        # Run the analysis
        response = await agent.analyze(
            query=test_case.query,
            include_charts=False,  # Skip charts for speed
            max_iterations=2,  # Limit iterations for speed
        )
        
        result.execution_time_ms = (time.time() - start_time) * 1000
        
        # Check intent
        actual_intent = response.metadata.get("parsed_intent", "")
        result.actual_intent = actual_intent
        if actual_intent != test_case.expected_intent:
            result.intent_matched = False
            result.failure_reasons.append(
                f"Intent mismatch: expected '{test_case.expected_intent}', got '{actual_intent}'"
            )
        
        # Check calculations
        if test_case.expected_calculations:
            actual_calcs = {c["metric_name"]: c["value"] for c in response.calculations}
            result.actual_calculations = actual_calcs
            
            for expected in test_case.expected_calculations:
                if expected.metric_name not in actual_calcs:
                    result.calculations_matched = False
                    result.failure_reasons.append(
                        f"Missing calculation: {expected.metric_name}"
                    )
                elif not expected.matches(actual_calcs[expected.metric_name]):
                    result.calculations_matched = False
                    result.failure_reasons.append(
                        f"Calculation mismatch for {expected.metric_name}: "
                        f"expected {expected.expected_value}, got {actual_calcs[expected.metric_name]}"
                    )
        
        # Check content
        analysis_lower = response.analysis.lower()
        
        for must_contain in test_case.analysis_must_contain:
            if must_contain.lower() not in analysis_lower:
                result.content_valid = False
                result.failure_reasons.append(
                    f"Analysis missing required content: '{must_contain}'"
                )
        
        for must_not_contain in test_case.analysis_must_not_contain:
            if must_not_contain.lower() in analysis_lower:
                result.content_valid = False
                result.failure_reasons.append(
                    f"Analysis contains forbidden content: '{must_not_contain}'"
                )
        
        # Check evaluation score
        eval_score = response.evaluation_summary.get("qualitative_score")
        result.actual_evaluation_score = eval_score
        
        if eval_score is not None and eval_score < test_case.min_evaluation_score:
            result.evaluation_passed = False
            result.failure_reasons.append(
                f"Evaluation score {eval_score} below minimum {test_case.min_evaluation_score}"
            )
        
        # Determine overall pass/fail
        result.passed = (
            result.intent_matched and
            result.departments_matched and
            result.calculations_matched and
            result.content_valid and
            result.evaluation_passed
        )
        
    except Exception as e:
        result.execution_time_ms = (time.time() - start_time) * 1000
        result.passed = False
        result.failure_reasons.append(f"Exception: {type(e).__name__}: {str(e)}")
        logger.error(f"Test {test_case.test_id} failed with exception: {e}", exc_info=True)
    
    return result


async def run_regression_suite(
    agent,
    dataset: GoldenDataset,
    parallel: bool = False,
) -> RegressionReport:
    """
    Run all test cases in a dataset.
    
    Args:
        agent: The FinancialAnalystAgent instance
        dataset: The golden dataset to test against
        parallel: Whether to run tests in parallel (faster but uses more resources)
    
    Returns:
        RegressionReport with all results
    """
    import time
    
    start_time = time.time()
    results = []
    
    logger.info(f"Running regression suite: {dataset.name} v{dataset.version}")
    logger.info(f"Total test cases: {len(dataset.test_cases)}")
    
    if parallel:
        # Run tests in parallel
        tasks = [run_single_test(agent, tc) for tc in dataset.test_cases]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions that were returned
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                tc = dataset.test_cases[i]
                processed_results.append(TestResult(
                    test_id=tc.test_id,
                    test_name=tc.name,
                    passed=False,
                    failure_reasons=[f"Exception: {str(result)}"],
                ))
            else:
                processed_results.append(result)
        results = processed_results
    else:
        # Run tests sequentially
        for i, tc in enumerate(dataset.test_cases):
            logger.info(f"Running test {i+1}/{len(dataset.test_cases)}: {tc.test_id}")
            result = await run_single_test(agent, tc)
            results.append(result)
            
            status = "✅" if result.passed else "❌"
            logger.info(f"  {status} {tc.name}: {result.execution_time_ms:.0f}ms")
    
    total_time = (time.time() - start_time) * 1000
    
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed and r.failure_reasons and "Exception" not in str(r.failure_reasons))
    errors = sum(1 for r in results if not r.passed and r.failure_reasons and "Exception" in str(r.failure_reasons))
    
    report = RegressionReport(
        dataset_version=dataset.version,
        run_timestamp=datetime.utcnow().isoformat(),
        total_tests=len(results),
        passed=passed,
        failed=failed,
        errors=errors,
        total_execution_time_ms=total_time,
        results=results,
    )
    
    return report


def create_test_case_from_response(
    query: str,
    response,  # AgentResponse
    test_id: str,
    name: str,
    description: str = "",
) -> GoldenTestCase:
    """
    Helper to create a golden test case from an actual agent response.
    
    Use this when you have verified a response is correct and want to
    add it to the golden dataset.
    """
    expected_calcs = [
        ExpectedCalculation(
            metric_name=calc["metric_name"],
            expected_value=calc["value"],
            tolerance_percent=1.0,
        )
        for calc in response.calculations
        if calc.get("value") is not None
    ]
    
    return GoldenTestCase(
        test_id=test_id,
        name=name,
        description=description,
        query=query,
        expected_intent=response.metadata.get("parsed_intent", "summary"),
        expected_calculations=expected_calcs,
        min_evaluation_score=response.evaluation_summary.get("qualitative_score", 7.0) - 0.5,
        created_at=datetime.utcnow().isoformat(),
        data_snapshot_date=datetime.utcnow().strftime("%Y-%m-%d"),
    )

