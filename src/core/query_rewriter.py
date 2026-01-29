"""
Query Rewriter Module

Provides LLM-based query rewriting for conversational follow-ups.
This module enables the agent to understand messages like "filter by department instead"
or "same thing for G&A" by rewriting them into complete, standalone queries.

The rewriter:
1. Detects if a message is likely a conversational follow-up (fast heuristics)
2. If yes, uses an LLM to generate a complete query from context
3. Returns either the rewritten query or the original

This is ADDITIVE to existing disambiguation handling - it adds conversational
understanding while preserving guardrails like explicit disambiguation questions.
"""

import logging
import re
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.memory import Session

from src.core.model_router import ModelRouter, get_router
from src.core.prompt_manager import get_prompt_manager

logger = logging.getLogger(__name__)


class QueryRewriter:
    """
    Rewrites conversational follow-ups into complete, standalone queries.
    
    Uses fast heuristics to detect follow-ups, then LLM to rewrite if needed.
    """
    
    # Patterns that suggest a follow-up rather than a new query
    FOLLOWUP_PATTERNS = [
        # Modification requests
        r"\b(instead|but|also|same|again|try|change|switch|filter)\b",
        # Pronouns referencing previous context
        r"\b(it|that|this|those|them)\b",
        # Comparison to previous
        r"\b(previous|last|before|earlier)\b",
        # Drill-down requests
        r"\b(break.*down|drill|detail|expand|more)\b",
        # Exclusion/inclusion modifications
        r"\b(exclude|include|without|except|add|remove)\b",
        # Entity substitution (same X for Y)
        r"\bsame\s+(thing|query|analysis|data)\b",
        # Time period changes
        r"\b(what about|how about|and for|now for)\b",
    ]
    
    # Patterns that suggest a complete, standalone query
    COMPLETE_QUERY_PATTERNS = [
        # Has explicit time period
        r"\b(ytd|year.to.date|q[1-4]|fy\d{2,4}|january|february|march|april|may|june|july|august|september|october|november|december|\d{4})\b",
        # Has question structure
        r"^(what|how|show|give|get|list|compare|calculate)\b",
        # Has explicit totals/analysis types
        r"\b(total|sum|breakdown|comparison|trend|variance)\b.*\b(for|of|by)\b",
    ]
    
    # Minimum word count to consider a query "complete" by default
    MIN_COMPLETE_QUERY_WORDS = 5
    
    def __init__(
        self,
        llm_router: Optional[ModelRouter] = None,
    ):
        """
        Initialize the query rewriter.
        
        Args:
            llm_router: Model router for LLM calls. If None, will create one.
        """
        self.llm_router = llm_router
        self.prompt_manager = get_prompt_manager()
        self._prompt_loaded = False
        self._prompt = None
    
    def _ensure_prompt_loaded(self):
        """Lazy-load the prompt template."""
        if not self._prompt_loaded:
            try:
                self._prompt = self.prompt_manager.get_prompt("query_rewriting")
                self._prompt_loaded = True
            except FileNotFoundError:
                logger.warning("Query rewriting prompt not found - rewriting disabled")
                self._prompt = None
                self._prompt_loaded = True
    
    def _ensure_router(self):
        """Lazy-initialize the LLM router."""
        if self.llm_router is None:
            self.llm_router = get_router()
    
    def is_likely_followup(self, message: str, session: "Session") -> bool:
        """
        Fast heuristic check to determine if a message is likely a follow-up.
        
        This avoids unnecessary LLM calls for obviously complete queries.
        
        Args:
            message: The user's message
            session: The conversation session (for context)
        
        Returns:
            True if the message appears to be a follow-up that needs rewriting
        """
        if not session or not session.turns:
            # No conversation history - can't be a follow-up
            return False
        
        message_lower = message.lower().strip()
        word_count = len(message_lower.split())
        
        # Very short messages are likely follow-ups if there's context
        if word_count <= 3 and len(session.turns) > 0:
            return True
        
        # Check for follow-up patterns
        has_followup_pattern = any(
            re.search(pattern, message_lower, re.IGNORECASE)
            for pattern in self.FOLLOWUP_PATTERNS
        )
        
        # Check for complete query patterns
        has_complete_pattern = any(
            re.search(pattern, message_lower, re.IGNORECASE)
            for pattern in self.COMPLETE_QUERY_PATTERNS
        )
        
        # If it has follow-up patterns and no complete patterns, it's likely a follow-up
        if has_followup_pattern and not has_complete_pattern:
            return True
        
        # Short messages without complete query structure are likely follow-ups
        if word_count < self.MIN_COMPLETE_QUERY_WORDS and not has_complete_pattern:
            return True
        
        # Messages that are questions but very short
        if message_lower.startswith(("what about", "how about", "and ", "but ", "also ")):
            return True
        
        return False
    
    def _build_context_prompt(self, session: "Session") -> Dict[str, str]:
        """
        Build the context dictionary for the LLM prompt.
        
        Args:
            session: The conversation session
        
        Returns:
            Dictionary with prompt variables
        """
        # Get conversation history as formatted text
        history_parts = []
        for turn in list(session.turns)[-5:]:  # Last 5 turns
            role = turn.role.upper()
            content = turn.content[:500]  # Truncate long messages
            history_parts.append(f"{role}: {content}")
        
        conversation_history = "\n".join(history_parts) if history_parts else "No previous conversation"
        
        # Get context from session
        context = session.context
        
        # Format departments
        departments = ", ".join(context.departments) if context.departments else "None specified"
        
        # Format accounts
        accounts = ", ".join(context.accounts) if context.accounts else "None specified"
        
        # Format time periods
        time_periods = ", ".join(context.time_periods) if context.time_periods else "None specified"
        
        # Format last filters
        if context.last_data_filters:
            filter_parts = []
            for key, value in context.last_data_filters.items():
                filter_parts.append(f"{key}: {value}")
            last_filters = "; ".join(filter_parts)
        else:
            last_filters = "None applied"
        
        # Get last query from the most recent user turn
        last_query = ""
        for turn in reversed(list(session.turns)):
            if turn.role == "user":
                last_query = turn.content
                break
        
        # Format resolved disambiguations for LLM context
        resolved_disambiguations = self._format_disambiguation_context(session)
        
        return {
            "conversation_history": conversation_history,
            "last_query": last_query or "None",
            "departments": departments,
            "accounts": accounts,
            "time_periods": time_periods,
            "last_filters": last_filters,
            "analysis_type": context.last_analysis_type or "Unknown",
            "resolved_disambiguations": resolved_disambiguations,
        }
    
    def _format_disambiguation_context(self, session: "Session") -> str:
        """
        Format resolved disambiguation records for the LLM prompt.
        
        This provides the LLM with context about what disambiguation choices
        were made and for which topics, so it can decide whether to apply them.
        
        Args:
            session: The conversation session
        
        Returns:
            Formatted string describing disambiguation choices
        """
        if not hasattr(session, 'resolved_disambiguations') or not session.resolved_disambiguations:
            return "None - no previous disambiguation choices made"
        
        records = []
        for d in session.resolved_disambiguations:
            # Format each disambiguation record clearly
            record_str = (
                f"- Term '{d.term}' was clarified as {d.chosen_dimension.upper()} "
                f"(topic: '{d.topic_summary}', turn #{d.turn_index})"
            )
            
            # Add specific filter value if available
            if d.chosen_value:
                if 'prefix' in d.chosen_value:
                    record_str += f" [filter: account prefix '{d.chosen_value['prefix']}']"
                elif 'name' in d.chosen_value:
                    record_str += f" [filter: name '{d.chosen_value['name']}']"
            
            records.append(record_str)
        
        return "\n".join(records)
    
    def rewrite_if_needed(
        self,
        message: str,
        session: "Session",
    ) -> str:
        """
        Rewrite a message if it's a conversational follow-up.
        
        Args:
            message: The user's message
            session: The conversation session for context
        
        Returns:
            The rewritten query (or original if no rewriting needed)
        """
        # Fast path: no session or no history
        if not session or not session.turns:
            logger.debug("No session history - skipping rewrite check")
            return message
        
        # Fast heuristic check
        if not self.is_likely_followup(message, session):
            logger.debug(f"Message doesn't appear to be a follow-up: '{message[:50]}...'")
            return message
        
        # Ensure we have the prompt and router
        self._ensure_prompt_loaded()
        self._ensure_router()
        
        if not self._prompt or not self.llm_router:
            logger.warning("Query rewriting not available - returning original message")
            return message
        
        try:
            # Build context for prompt
            context = self._build_context_prompt(session)
            context["current_message"] = message
            
            # Format the user prompt
            user_prompt = self._prompt.format(**context)
            
            # Call LLM
            logger.info(f"Rewriting potential follow-up: '{message[:50]}...'")
            response = self.llm_router.generate_with_system(
                system_prompt=self._prompt.system_prompt,
                user_message=user_prompt,
                temperature=0.1,  # Low temperature for consistent rewrites
                max_tokens=500,   # Queries shouldn't be very long
            )
            
            rewritten = response.content.strip()
            
            # Clean up any markdown or extra formatting
            rewritten = self._clean_response(rewritten)
            
            # Validate the rewrite
            if not rewritten or len(rewritten) < 3:
                logger.warning("LLM returned empty/invalid rewrite - using original")
                return message
            
            # Log if we actually changed something
            if rewritten.lower() != message.lower():
                logger.info(f"Rewrote query: '{message}' -> '{rewritten}'")
            else:
                logger.debug("LLM returned query unchanged")
            
            return rewritten
            
        except Exception as e:
            logger.error(f"Query rewriting failed: {e}")
            # Fallback to original message
            return message
    
    def _clean_response(self, response: str) -> str:
        """
        Clean up the LLM response to extract just the query text.
        
        Handles cases where the LLM might add markdown or explanations.
        """
        # Remove markdown code blocks if present
        if response.startswith("```"):
            lines = response.split("\n")
            # Find content between ``` markers
            in_block = False
            content_lines = []
            for line in lines:
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                if in_block or not lines[0].startswith("```"):
                    content_lines.append(line)
            response = "\n".join(content_lines)
        
        # Remove leading/trailing quotes if the whole thing is quoted
        response = response.strip()
        if (response.startswith('"') and response.endswith('"')) or \
           (response.startswith("'") and response.endswith("'")):
            response = response[1:-1]
        
        # Remove any "Rewritten query:" or similar prefixes
        prefixes_to_remove = [
            "rewritten query:",
            "rewritten:",
            "query:",
            "answer:",
            "response:",
        ]
        response_lower = response.lower()
        for prefix in prefixes_to_remove:
            if response_lower.startswith(prefix):
                response = response[len(prefix):].strip()
                break
        
        return response.strip()


# Singleton instance
_query_rewriter: Optional[QueryRewriter] = None


def get_query_rewriter(llm_router: Optional[ModelRouter] = None) -> QueryRewriter:
    """
    Get the configured query rewriter instance.
    
    Args:
        llm_router: Optional LLM router to use. If None, will create one.
    
    Returns:
        QueryRewriter instance
    """
    global _query_rewriter
    if _query_rewriter is None:
        _query_rewriter = QueryRewriter(llm_router=llm_router)
    return _query_rewriter
