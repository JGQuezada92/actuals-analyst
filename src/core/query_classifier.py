"""
Query Classifier

Classifies queries to route them to appropriate processing paths.
Works WITH existing ParsedQuery, not instead of it.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional, List, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from src.core.query_parser import ParsedQuery

logger = logging.getLogger(__name__)


class ProcessingPath(Enum):
    """Processing paths for different query types."""
    STANDARD = "standard"           # Full pipeline
    FOLLOW_UP = "follow_up"         # Use working data from previous query
    CLARIFICATION = "clarification" # Resolve disambiguation
    CACHED_AGGREGATION = "cached"   # Use pre-computed aggregation


@dataclass
class ClassificationResult:
    """Result of query classification."""
    processing_path: ProcessingPath
    can_use_working_data: bool
    filter_dimensions: List[str]
    is_follow_up: bool
    notes: List[str]


class QueryClassifier:
    """
    Classifies queries based on ParsedQuery and session context.
    
    This is a THIN layer that makes routing decisions based on
    already-parsed query information.
    """
    
    # Patterns that indicate a follow-up query
    FOLLOW_UP_PATTERNS = [
        r'\b(break that down|break it down|drill into|drill down)\b',
        r'\b(now show|now filter|now group)\b',
        r'\b(same (thing|query) (but|for|with))\b',
        r'\b(what about|how about)\b',
        r'\b(and also|also show)\b',
    ]
    
    def __init__(self, session_context: Optional[dict] = None):
        """
        Initialize classifier.
        
        Args:
            session_context: Dict with keys:
                - has_working_data: bool
                - previous_filters: dict
                - awaiting_clarification: bool
        """
        self.session_context = session_context or {}
    
    def classify(
        self,
        query: str,
        parsed_query: 'ParsedQuery',
    ) -> ClassificationResult:
        """
        Classify a query for routing.
        
        Args:
            query: Original query string
            parsed_query: Already-parsed query from QueryParser
            
        Returns:
            ClassificationResult with routing decision
        """
        notes = []
        filter_dimensions = []
        
        # Determine filter dimensions from parsed query
        if parsed_query.time_period:
            filter_dimensions.append("time")
        if parsed_query.departments:
            filter_dimensions.append("department")
        if parsed_query.account_type_filter:
            filter_dimensions.append("account_type")
        if parsed_query.subsidiaries:
            filter_dimensions.append("subsidiary")
        
        # Check for clarification response
        if self.session_context.get("awaiting_clarification"):
            # Short responses or numbers might be clarification answers
            if len(query.split()) <= 3 or re.match(r'^\d+$', query.strip()):
                return ClassificationResult(
                    processing_path=ProcessingPath.CLARIFICATION,
                    can_use_working_data=False,
                    filter_dimensions=filter_dimensions,
                    is_follow_up=False,
                    notes=["Detected clarification response"],
                )
        
        # Check for follow-up patterns
        is_follow_up = any(
            re.search(pattern, query, re.IGNORECASE)
            for pattern in self.FOLLOW_UP_PATTERNS
        )
        
        if is_follow_up and self.session_context.get("has_working_data"):
            return ClassificationResult(
                processing_path=ProcessingPath.FOLLOW_UP,
                can_use_working_data=True,
                filter_dimensions=filter_dimensions,
                is_follow_up=True,
                notes=["Detected follow-up query with available working data"],
            )
        
        # Check if current filters are subset of previous (can reuse working data)
        can_use_working_data = self._check_filter_compatibility(parsed_query)
        
        if can_use_working_data:
            notes.append("Filters compatible with working data")
        
        return ClassificationResult(
            processing_path=ProcessingPath.STANDARD,
            can_use_working_data=can_use_working_data,
            filter_dimensions=filter_dimensions,
            is_follow_up=is_follow_up,
            notes=notes,
        )
    
    def _check_filter_compatibility(self, parsed_query: 'ParsedQuery') -> bool:
        """Check if current query can use working data from previous query."""
        if not self.session_context.get("has_working_data"):
            return False
        
        previous_filters = self.session_context.get("previous_filters", {})
        if not previous_filters:
            return False
        
        # Current query must be same or narrower than previous
        # Time period must match
        if parsed_query.time_period:
            current_period = parsed_query.time_period.period_name
            previous_period = previous_filters.get("time_period")
            if previous_period and current_period != previous_period:
                return False
        
        # Departments must be subset
        if parsed_query.departments:
            previous_depts = set(previous_filters.get("departments", []))
            current_depts = set(parsed_query.departments)
            if previous_depts and not current_depts.issubset(previous_depts):
                return False
        
        return True


def get_query_classifier(session_context: Optional[dict] = None) -> QueryClassifier:
    """Get a query classifier instance."""
    return QueryClassifier(session_context)
