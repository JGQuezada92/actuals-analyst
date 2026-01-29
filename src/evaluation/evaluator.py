"""
Evaluation System

Implements the Accuracy-First Framework's evaluation-centric design:
1. Objective Metrics: Deterministic comparison against expected values
2. Qualitative Metrics: LLM-as-a-Judge assessment
3. Cross-Model Evaluation: Judge with different model than generator

CRITICAL: Use a DIFFERENT model for judging than for generation.
This prevents self-bias and provides independent quality assessment.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from enum import Enum

from src.core.model_router import get_router, get_judge_router, Message, LLMResponse
from src.core.prompt_manager import get_prompt_manager
from src.tools.calculator import CalculationResult
from config.settings import get_config, EvaluationConfig

logger = logging.getLogger(__name__)

class EvaluationDimension(Enum):
    """Qualitative evaluation dimensions."""
    NUMERICAL_ACCURACY = "numerical_accuracy"
    CLAIM_SUBSTANTIATION = "claim_substantiation"
    COMPLETENESS = "completeness"
    INSIGHT_QUALITY = "insight_quality"
    ACTIONABILITY = "actionability"
    CLARITY = "clarity"

@dataclass
class ObjectiveScore:
    """Score from objective (deterministic) evaluation."""
    metric_name: str
    expected_value: float
    actual_value: float
    is_correct: bool
    tolerance: float
    deviation: float  # Percentage deviation from expected
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
            "is_correct": self.is_correct,
            "tolerance": self.tolerance,
            "deviation": self.deviation,
        }

@dataclass
class QualitativeScore:
    """Score from LLM-as-a-Judge evaluation."""
    dimension: EvaluationDimension
    score: float  # 0-10
    rationale: str
    suggestions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "score": self.score,
            "rationale": self.rationale,
            "suggestions": self.suggestions,
        }

@dataclass
class EvaluationResult:
    """Complete evaluation result combining objective and qualitative scores."""
    # Objective metrics
    objective_scores: List[ObjectiveScore]
    objective_accuracy: float  # Percentage of correct calculations
    
    # Qualitative metrics
    qualitative_scores: List[QualitativeScore]
    average_qualitative_score: float
    
    # Overall
    passes_threshold: bool
    evaluation_model: str
    evaluated_at: datetime
    
    # Recommendations
    improvement_suggestions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective_scores": [s.to_dict() for s in self.objective_scores],
            "objective_accuracy": self.objective_accuracy,
            "qualitative_scores": [s.to_dict() for s in self.qualitative_scores],
            "average_qualitative_score": self.average_qualitative_score,
            "passes_threshold": self.passes_threshold,
            "evaluation_model": self.evaluation_model,
            "evaluated_at": self.evaluated_at.isoformat(),
            "improvement_suggestions": self.improvement_suggestions,
        }


@dataclass
class QualityGateConfig:
    """Configuration for quality gates."""
    min_qualitative_score: float = 6.0
    min_numerical_accuracy: float = 0.90
    allow_degraded_response: bool = True
    include_quality_warning: bool = True


class QualityGate:
    """
    Enforces quality standards before responses are delivered.
    
    Works with existing EvaluationResult from EvaluationHarness.
    """
    
    def __init__(self, config: Optional[QualityGateConfig] = None):
        self.config = config or QualityGateConfig()
    
    def check(self, evaluation: EvaluationResult) -> Tuple[bool, Optional[str]]:
        """
        Check if evaluation passes quality gate.
        
        Args:
            evaluation: Result from EvaluationHarness.evaluate_analysis()
            
        Returns:
            Tuple of (passes, warning_message_or_none)
        """
        issues = []
        
        # Check qualitative score
        qual_score = evaluation.average_qualitative_score
        if qual_score < self.config.min_qualitative_score:
            issues.append(f"quality score ({qual_score:.1f}/10)")
        
        # Check numerical accuracy
        if evaluation.objective_accuracy < self.config.min_numerical_accuracy:
            issues.append(f"numerical accuracy ({evaluation.objective_accuracy:.0%})")
        
        if not issues:
            return True, None
        
        if self.config.allow_degraded_response:
            warning = (
                f"**Quality Notice**: This analysis has potential issues with "
                f"{', '.join(issues)}. Please verify important figures."
            )
            return True, warning
        else:
            return False, f"Unable to provide analysis due to quality issues: {', '.join(issues)}"


def get_quality_gate(config: Optional[QualityGateConfig] = None) -> QualityGate:
    """Get a quality gate instance."""
    return QualityGate(config)


class ObjectiveEvaluator:
    """
    Deterministic evaluation of numerical accuracy.
    
    Compares calculated values against expected values
    within a configured tolerance.
    """
    
    def __init__(self, config: Optional[EvaluationConfig] = None):
        self.config = config or get_config().evaluation
    
    def evaluate(
        self,
        calculations: List[CalculationResult],
        expected_values: Dict[str, float],
    ) -> Tuple[List[ObjectiveScore], float]:
        """
        Evaluate calculations against expected values.
        
        Args:
            calculations: List of calculation results to evaluate
            expected_values: Dict mapping metric names to expected values
        
        Returns:
            Tuple of (list of scores, overall accuracy percentage)
        """
        scores = []
        correct_count = 0
        
        for calc in calculations:
            if calc.metric_name not in expected_values:
                continue
            
            expected = expected_values[calc.metric_name]
            actual = calc.value
            
            # Calculate deviation
            if expected != 0:
                deviation = abs((actual - expected) / expected)
            else:
                deviation = abs(actual) if actual != 0 else 0
            
            is_correct = deviation <= self.config.numerical_tolerance
            
            if is_correct:
                correct_count += 1
            
            scores.append(ObjectiveScore(
                metric_name=calc.metric_name,
                expected_value=expected,
                actual_value=actual,
                is_correct=is_correct,
                tolerance=self.config.numerical_tolerance,
                deviation=deviation,
            ))
        
        accuracy = correct_count / len(scores) if scores else 0
        return scores, accuracy

class QualitativeEvaluator:
    """
    LLM-as-a-Judge evaluation for analysis quality.
    
    Uses a DIFFERENT model from the generation model
    to prevent self-bias in evaluation.
    """
    
    EVALUATION_PROMPT = """You are an expert financial analyst evaluating the quality of an AI-generated financial analysis. 
You must be rigorous and objective in your assessment.

## Analysis to Evaluate
{analysis}

## Source Data Summary
{data_summary}

## Evaluation Criteria
Rate each dimension from 0-10 and provide specific rationale:

1. **Numerical Accuracy** (0-10): Are calculations correctly applied and consistent with source data?
2. **Claim Substantiation** (0-10): Is every claim backed by specific data points?
3. **Completeness** (0-10): Does the analysis address all relevant aspects?
4. **Insight Quality** (0-10): Are insights meaningful, non-obvious, and actionable?
5. **Actionability** (0-10): Does the analysis provide clear recommendations?
6. **Clarity** (0-10): Is the analysis well-organized and easy to understand?

## Response Format
Respond in JSON format exactly as follows:
{{
    "scores": {{
        "numerical_accuracy": {{"score": <0-10>, "rationale": "<specific reasoning>"}},
        "claim_substantiation": {{"score": <0-10>, "rationale": "<specific reasoning>"}},
        "completeness": {{"score": <0-10>, "rationale": "<specific reasoning>"}},
        "insight_quality": {{"score": <0-10>, "rationale": "<specific reasoning>"}},
        "actionability": {{"score": <0-10>, "rationale": "<specific reasoning>"}},
        "clarity": {{"score": <0-10>, "rationale": "<specific reasoning>"}}
    }},
    "overall_assessment": "<brief overall assessment>",
    "improvement_suggestions": ["<suggestion 1>", "<suggestion 2>", ...]
}}
"""
    
    def __init__(self):
        # Use judge router (different model from generator)
        self.router = get_judge_router()
        self.prompt_manager = get_prompt_manager()
    
    def evaluate(
        self,
        analysis: str,
        data_summary: str,
    ) -> Tuple[List[QualitativeScore], float, List[str]]:
        """
        Evaluate analysis quality using LLM-as-a-Judge.
        
        Args:
            analysis: The generated analysis text to evaluate
            data_summary: Summary of source data for context
        
        Returns:
            Tuple of (list of dimension scores, average score, improvement suggestions)
        """
        # Use prompt manager for versioned prompts
        try:
            eval_prompt = self.prompt_manager.get_prompt("evaluation")
            user_prompt = eval_prompt.format(
                analysis=analysis,
                data_summary=data_summary,
            )
            system_prompt = eval_prompt.system_prompt
        except FileNotFoundError as e:
            # Fallback to inline prompt
            logger.warning(f"Evaluation prompt not found: {e}. Using inline prompt.")
        except Exception as e:
            # Catch other errors (e.g., missing variables, YAML parsing errors)
            logger.warning(f"Evaluation prompt error: {e}. Using inline prompt.")
            user_prompt = self.EVALUATION_PROMPT.format(
            analysis=analysis,
            data_summary=data_summary,
        )
            system_prompt = "You are a rigorous financial analysis evaluator. Respond only in valid JSON."
        
        response = self.router.generate_with_system(
            system_prompt=system_prompt,
            user_message=user_prompt,
            temperature=0.1,  # Low temperature for consistent evaluation
        )
        
        # Parse response
        try:
            # Extract JSON from response
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            eval_data = json.loads(content.strip())
        except (json.JSONDecodeError, IndexError) as e:
            logger.error(f"Failed to parse evaluation response: {e}")
            # Return default low scores
            return self._default_scores(), 5.0, ["Evaluation parsing failed"]
        
        # Convert to QualitativeScore objects
        scores = []
        dimension_map = {
            "numerical_accuracy": EvaluationDimension.NUMERICAL_ACCURACY,
            "claim_substantiation": EvaluationDimension.CLAIM_SUBSTANTIATION,
            "completeness": EvaluationDimension.COMPLETENESS,
            "insight_quality": EvaluationDimension.INSIGHT_QUALITY,
            "actionability": EvaluationDimension.ACTIONABILITY,
            "clarity": EvaluationDimension.CLARITY,
        }
        
        for key, dimension in dimension_map.items():
            score_data = eval_data.get("scores", {}).get(key, {})
            scores.append(QualitativeScore(
                dimension=dimension,
                score=float(score_data.get("score", 5.0)),
                rationale=score_data.get("rationale", "No rationale provided"),
            ))
        
        average_score = sum(s.score for s in scores) / len(scores) if scores else 5.0
        suggestions = eval_data.get("improvement_suggestions", [])
        
        return scores, average_score, suggestions
    
    def _default_scores(self) -> List[QualitativeScore]:
        """Return default low scores for failed evaluation."""
        return [
            QualitativeScore(dimension=d, score=5.0, rationale="Evaluation failed")
            for d in EvaluationDimension
        ]

class ReflectionEvaluator:
    """
    Self-critique evaluation for the Reflection pattern.
    
    Used during agent's iterative refinement process.
    Uses the SAME model as generation for reflection.
    """
    
    REFLECTION_PROMPT = """Review your analysis and identify areas for improvement.

## Your Analysis
{analysis}

## Self-Critique Checklist
1. Are all numerical claims directly traceable to source data?
2. Have I made any unsupported generalizations?
3. Are there gaps in the analysis that should be addressed?
4. Could the recommendations be more specific or actionable?
5. Is the structure and flow logical and clear?

## Response Format
Respond in JSON:
{{
    "self_score": <0-10>,
    "weaknesses": ["<weakness 1>", "<weakness 2>", ...],
    "suggested_improvements": ["<improvement 1>", "<improvement 2>", ...],
    "should_revise": <true/false>,
    "revised_analysis": "<improved analysis if should_revise is true, otherwise null>"
}}
"""
    
    def __init__(self):
        # Use same model as generator for self-reflection
        self.router = get_router()
    
    def reflect(
        self,
        analysis: str,
        iteration: int = 1,
        max_iterations: int = 3,
    ) -> Tuple[str, float, bool]:
        """
        Perform self-reflection and optional revision.
        
        Args:
            analysis: Current analysis to reflect on
            iteration: Current iteration number
            max_iterations: Maximum allowed iterations
        
        Returns:
            Tuple of (possibly revised analysis, self-score, did_revise)
        """
        if iteration >= max_iterations:
            logger.info(f"Max reflection iterations ({max_iterations}) reached")
            return analysis, 7.0, False
        
        prompt = self.REFLECTION_PROMPT.format(analysis=analysis)
        
        response = self.router.generate_with_system(
            system_prompt="You are critically reviewing your own work. Be honest about weaknesses.",
            user_message=prompt,
            temperature=0.2,
        )
        
        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            reflection_data = json.loads(content.strip())
            
            self_score = float(reflection_data.get("self_score", 7.0))
            should_revise = reflection_data.get("should_revise", False)
            
            if should_revise and reflection_data.get("revised_analysis"):
                logger.info(f"Reflection iteration {iteration}: revising (score: {self_score})")
                return reflection_data["revised_analysis"], self_score, True
            
            return analysis, self_score, False
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Reflection parsing failed: {e}")
            return analysis, 7.0, False

class EvaluationHarness:
    """
    Complete evaluation harness combining all evaluation methods.
    
    This is the main interface for evaluation.
    """
    
    def __init__(self, config: Optional[EvaluationConfig] = None):
        self.config = config or get_config().evaluation
        self.objective_evaluator = ObjectiveEvaluator(self.config)
        self.qualitative_evaluator = QualitativeEvaluator()
        self.reflection_evaluator = ReflectionEvaluator()
    
    def evaluate_analysis(
        self,
        analysis: str,
        calculations: List[CalculationResult],
        expected_values: Dict[str, float],
        data_summary: str,
    ) -> EvaluationResult:
        """
        Perform complete evaluation of an analysis.
        
        Args:
            analysis: The generated analysis text
            calculations: List of calculation results
            expected_values: Dict of metric names to expected values
            data_summary: Summary of source data
        
        Returns:
            Complete EvaluationResult
        """
        # Objective evaluation
        objective_scores, objective_accuracy = self.objective_evaluator.evaluate(
            calculations, expected_values
        )
        
        # Qualitative evaluation
        qualitative_scores, avg_qualitative, suggestions = self.qualitative_evaluator.evaluate(
            analysis, data_summary
        )
        
        # Determine if passes thresholds
        passes = (
            objective_accuracy >= self.config.minimum_accuracy_score and
            avg_qualitative >= self.config.minimum_judge_score
        )
        
        return EvaluationResult(
            objective_scores=objective_scores,
            objective_accuracy=objective_accuracy,
            qualitative_scores=qualitative_scores,
            average_qualitative_score=avg_qualitative,
            passes_threshold=passes,
            evaluation_model=self.qualitative_evaluator.router.config.model_name,
            evaluated_at=datetime.utcnow(),
            improvement_suggestions=suggestions,
        )
    
    def reflect_and_improve(
        self,
        analysis: str,
        max_iterations: int = 3,
    ) -> Tuple[str, List[float]]:
        """
        Apply reflection pattern to improve analysis.
        
        Args:
            analysis: Initial analysis to improve
            max_iterations: Maximum reflection iterations
        
        Returns:
            Tuple of (final analysis, list of scores per iteration)
        """
        current_analysis = analysis
        scores = []
        
        for i in range(max_iterations):
            revised, score, did_revise = self.reflection_evaluator.reflect(
                current_analysis,
                iteration=i + 1,
                max_iterations=max_iterations,
            )
            scores.append(score)
            
            if not did_revise:
                logger.info(f"Reflection complete after {i + 1} iterations")
                break
            
            # Check if improvement is significant enough to continue
            if i > 0 and (score - scores[-2]) < self.config.reflection_improvement_threshold:
                logger.info("Improvement below threshold, stopping reflection")
                break
            
            current_analysis = revised
        
        return current_analysis, scores

# Factory functions
def get_evaluation_harness() -> EvaluationHarness:
    """Get the evaluation harness."""
    return EvaluationHarness()

def get_objective_evaluator() -> ObjectiveEvaluator:
    """Get objective evaluator only."""
    return ObjectiveEvaluator()

def get_qualitative_evaluator() -> QualitativeEvaluator:
    """Get qualitative evaluator only."""
    return QualitativeEvaluator()
