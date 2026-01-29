"""
Dynamic Semantic Registry

Builds and maintains a runtime registry of departments, accounts, subsidiaries,
and other entities by extracting distinct values from actual NetSuite data.
This eliminates the need for hardcoded entity lists that become stale.

Architecture:
- Tier 1: Core financial semantics (static, in financial_semantics.py)
- Tier 2: Dynamic registry (this module, built from data)
- Tier 3: LLM fuzzy matching (fallback for unresolved terms)

Usage:
    from src.core.dynamic_registry import get_dynamic_registry
    
    registry = get_dynamic_registry()
    registry.build_from_data(netsuite_data)
    
    match = registry.lookup("GPS", EntityType.DEPARTMENT)
    if match.needs_clarification:
        print(match.clarification_options)
"""
import re
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)


class EntityType(Enum):
    """Types of entities tracked in the registry."""
    DEPARTMENT = "department"
    ACCOUNT = "account"
    ACCOUNT_NUMBER = "account_number"
    SUBSIDIARY = "subsidiary"
    VENDOR = "vendor"
    TRANSACTION_TYPE = "transaction_type"


@dataclass
class RegistryEntry:
    """
    A single entry in the dynamic registry.
    
    Represents a canonical entity (e.g., a department) with all its
    variations and metadata extracted from the data.
    """
    canonical_name: str           # The exact value from NetSuite
    entity_type: EntityType
    aliases: Set[str] = field(default_factory=set)  # Normalized variations for matching
    parent: Optional[str] = None  # For hierarchical entities (dept hierarchy)
    children: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)  # Extra info (account numbers, etc.)
    row_count: int = 0            # How many rows have this value (for ranking)
    last_seen: Optional[datetime] = None
    
    @staticmethod
    def _tokenize_words(text: str) -> set:
        """Tokenize text into words, stripping punctuation."""
        import re
        # Remove punctuation and split into words
        cleaned = re.sub(r'[,&()\-/]', ' ', text)
        return {w.strip() for w in cleaned.split() if w.strip()}
    
    def matches(self, query_term: str) -> Tuple[bool, float]:
        """
        Check if this entry matches a query term.
        
        Returns:
            Tuple of (is_match, confidence_score)
            - confidence 1.0 = exact match on canonical or child part
            - confidence 0.95 = exact match on an alias
            - confidence 0.85-0.94 = all query words match child part
            - confidence 0.5-0.84 = partial/contains match
            - confidence < 0.5 = weak match
        """
        query_lower = query_term.lower().strip()
        canonical_lower = self.canonical_name.lower()
        
        # Exact match on canonical name
        if query_lower == canonical_lower:
            return True, 1.0
        
        # Exact match on an alias
        if query_lower in self.aliases:
            return True, 0.95
        
        # For hierarchical names like "R&D (Parent) : Security, Privacy & Compliance",
        # check if query matches the CHILD part (highest priority for department queries)
        if ' : ' in canonical_lower:
            parts = canonical_lower.split(' : ')
            child_part = parts[-1].strip()  # Get the last part (most specific)
            
            # Exact match on child part -> very high confidence
            if query_lower == child_part:
                return True, 1.0
            
            # Tokenize words properly (strip punctuation)
            query_words = self._tokenize_words(query_lower)
            child_words = self._tokenize_words(child_part)
            
            # All query words are in child part -> high confidence
            if query_words and query_words.issubset(child_words):
                # Higher score if query covers most of child
                coverage = len(query_words) / len(child_words) if child_words else 0
                return True, max(0.85, min(0.94, 0.85 + coverage * 0.09))
            
            # Single-word query: check if it matches the FIRST word of child part
            # This handles "security" matching "Security, Privacy & Compliance"
            if len(query_words) == 1:
                query_word = list(query_words)[0]
                child_words_list = list(child_words)
                
                # Get the first meaningful word in child part
                if child_words_list:
                    first_child_word = child_words_list[0] if child_words_list else ""
                    
                    # Exact match on first word of child -> high confidence
                    if query_word == first_child_word:
                        return True, 0.90
                    
                    # Query word is in child words (not first) -> medium-high confidence
                    if query_word in child_words:
                        return True, 0.80
        
        # Multi-word query: require ALL words to be present (word-boundary matching)
        query_words = self._tokenize_words(query_lower)
        if len(query_words) > 1:
            canonical_words = self._tokenize_words(canonical_lower)
            
            # Check how many query words are in canonical
            matched_words = sum(1 for qw in query_words if qw in canonical_words)
            
            # All words must match for multi-word queries
            if matched_words == len(query_words):
                coverage = len(query_words) / len(canonical_words) if canonical_words else 0
                return True, max(0.6, min(0.84, 0.5 + coverage * 0.34))
            
            # Partial word match - very low confidence (likely wrong match)
            if matched_words > 0:
                return True, 0.3  # Low confidence - needs clarification
            
            return False, 0.0
        
        # Single-word query: use substring matching but with adjusted confidence
        # Query is contained in canonical name
        if query_lower in canonical_lower:
            # Score based on coverage ratio - boost for longer matches
            coverage = len(query_lower) / len(canonical_lower)
            # Boost confidence if query is a significant word (>= 5 chars)
            if len(query_lower) >= 5:
                return True, max(0.6, min(0.80, coverage + 0.35))
            return True, max(0.5, min(0.70, coverage + 0.2))
        
        # Canonical is contained in query (less confident)
        if canonical_lower in query_lower:
            return True, 0.35
        
        # Check aliases for partial matches (lower confidence)
        for alias in self.aliases:
            if query_lower == alias:
                return True, 0.9  # Exact alias match
            if query_lower in alias:
                coverage = len(query_lower) / len(alias)
                return True, max(0.35, min(0.6, coverage + 0.1))
            if alias in query_lower:
                return True, 0.3
        
        return False, 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for caching."""
        return {
            "canonical_name": self.canonical_name,
            "entity_type": self.entity_type.value,
            "aliases": list(self.aliases),
            "parent": self.parent,
            "children": self.children,
            "metadata": self.metadata,
            "row_count": self.row_count,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegistryEntry":
        """Deserialize from dictionary."""
        return cls(
            canonical_name=data["canonical_name"],
            entity_type=EntityType(data["entity_type"]),
            aliases=set(data.get("aliases", [])),
            parent=data.get("parent"),
            children=data.get("children", []),
            metadata=data.get("metadata", {}),
            row_count=data.get("row_count", 0),
            last_seen=datetime.fromisoformat(data["last_seen"]) if data.get("last_seen") else None,
        )


@dataclass
class RegistryMatch:
    """Result of a registry lookup."""
    term: str                              # Original search term
    entity_type: Optional[EntityType]      # Type searched (or None for all)
    matches: List[RegistryEntry]           # Matching entries, sorted by confidence
    confidence: float                      # Confidence of best match
    needs_clarification: bool              # True if user should choose
    clarification_options: List[str] = field(default_factory=list)
    
    @property
    def is_exact(self) -> bool:
        """True if single high-confidence match."""
        return len(self.matches) == 1 and self.confidence >= 0.85
    
    @property
    def best_match(self) -> Optional[RegistryEntry]:
        """Get the highest-confidence match."""
        return self.matches[0] if self.matches else None
    
    @property
    def is_empty(self) -> bool:
        """True if no matches found."""
        return len(self.matches) == 0
    
    def get_filter_values(self) -> List[str]:
        """Get canonical names for filtering."""
        return [m.canonical_name for m in self.matches]


class DynamicRegistry:
    """
    Runtime registry of entities extracted from NetSuite data.
    
    This registry is built by scanning actual data and extracting
    distinct values for departments, accounts, subsidiaries, etc.
    It provides fuzzy matching and disambiguation for user queries.
    
    Key Features:
    - Automatic discovery of all entities from transaction data
    - Intelligent alias generation for flexible matching
    - Confidence-scored matching with disambiguation
    - Disk caching with configurable TTL
    - Piggybacks on existing data retrieval (no extra API calls)
    """
    
    CACHE_FILE = "dynamic_registry.json"
    CACHE_TTL_HOURS = 24  # Rebuild registry after this many hours
    
    def __init__(self, cache_dir: Path = None):
        """
        Initialize the registry.
        
        Args:
            cache_dir: Directory for cache file. Defaults to .cache/
        """
        self.cache_dir = cache_dir or Path(".cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Registry storage: EntityType -> {canonical_name -> RegistryEntry}
        self._registry: Dict[EntityType, Dict[str, RegistryEntry]] = {
            et: {} for et in EntityType
        }
        
        # Inverted index for fast lookup: normalized_term -> [(EntityType, canonical_name), ...]
        self._index: Dict[str, List[Tuple[EntityType, str]]] = defaultdict(list)
        
        # Metadata
        self._built_at: Optional[datetime] = None
        self._source_row_count: int = 0
        self._field_mappings: Dict[str, str] = {}
        
        # Load from cache on initialization
        self._load_from_cache()
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    def needs_refresh(self) -> bool:
        """
        Check if registry needs to be refreshed.
        
        Returns True if:
        - No registry has been built yet
        - Cache is older than CACHE_TTL_HOURS
        """
        if not self._built_at:
            return True
        age = datetime.now() - self._built_at
        return age > timedelta(hours=self.CACHE_TTL_HOURS)
    
    def is_empty(self) -> bool:
        """Check if registry has any entries."""
        return all(len(entries) == 0 for entries in self._registry.values())
    
    def build_from_data(
        self,
        data: List[Dict[str, Any]],
        field_mappings: Dict[str, str] = None,
        force_rebuild: bool = False,
    ) -> "DynamicRegistry":
        """
        Build the registry by extracting distinct values from data.
        
        This is the primary method for populating the registry. It scans
        the provided data (typically from NetSuite saved search) and
        extracts all unique values for each entity type.
        
        Args:
            data: List of row dictionaries from NetSuite
            field_mappings: Map of entity type to field name in data
                           e.g., {"department": "department_name"}
                           If None, auto-detection is attempted.
            force_rebuild: If True, rebuild even if cache is valid
        
        Returns:
            Self for method chaining
        """
        # Check if we need to rebuild
        if not force_rebuild and not self.needs_refresh():
            logger.debug("Registry cache is valid, skipping rebuild")
            return self
        
        if not data:
            logger.warning("No data provided to build registry")
            return self
        
        logger.info(f"Building dynamic registry from {len(data):,} rows...")
        start_time = datetime.now()
        
        # Auto-detect field mappings if not provided
        self._field_mappings = field_mappings or self._auto_detect_fields(data)
        logger.debug(f"Field mappings: {self._field_mappings}")
        
        # Clear existing registry
        for et in EntityType:
            self._registry[et] = {}
        self._index.clear()
        
        # Extract each entity type
        self._extract_departments(data)
        self._extract_accounts(data)
        self._extract_account_numbers(data)
        self._extract_subsidiaries(data)
        self._extract_transaction_types(data)
        
        # Build inverted index for fast lookups
        self._build_index()
        
        # Update metadata
        self._built_at = datetime.now()
        self._source_row_count = len(data)
        
        # Persist to cache
        self._save_to_cache()
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"Registry built in {elapsed:.1f}s: "
            f"{len(self._registry[EntityType.DEPARTMENT])} departments, "
            f"{len(self._registry[EntityType.ACCOUNT])} accounts, "
            f"{len(self._registry[EntityType.ACCOUNT_NUMBER])} account numbers, "
            f"{len(self._registry[EntityType.SUBSIDIARY])} subsidiaries, "
            f"{len(self._registry[EntityType.TRANSACTION_TYPE])} transaction types"
        )
        
        return self
    
    def lookup(
        self,
        term: str,
        entity_type: EntityType = None,
        min_confidence: float = 0.5,
        max_results: int = 10,
        query_context: str = None,
    ) -> RegistryMatch:
        """
        Look up a term in the registry.
        
        Args:
            term: The search term (e.g., "GPS", "marketing", "53100")
            entity_type: Limit search to this entity type (optional)
            min_confidence: Minimum confidence score to include (0.0-1.0). Default 0.5 (raised from 0.3)
            max_results: Maximum number of matches to return
            query_context: Optional full query string for disambiguation context
        
        Returns:
            RegistryMatch with matches and clarification info
        """
        term_lower = term.lower().strip()
        exact_matches: List[Tuple[RegistryEntry, float]] = []
        partial_matches: List[Tuple[RegistryEntry, float]] = []
        
        # Step 1: Check inverted index for exact/alias matches FIRST (highest priority)
        if term_lower in self._index:
            for etype, canonical in self._index[term_lower]:
                if entity_type and etype != entity_type:
                    continue
                entry = self._registry[etype].get(canonical)
                if entry:
                    _, confidence = entry.matches(term_lower)
                    # Prioritize exact matches (confidence 1.0 or 0.95)
                    if confidence >= 0.95:
                        exact_matches.append((entry, confidence))
                    elif confidence >= min_confidence:
                        partial_matches.append((entry, confidence))
        
        # Step 2: If we have exact matches, return immediately (no need for fuzzy search)
        if exact_matches:
            # Sort exact matches by confidence, then row_count
            exact_matches.sort(key=lambda x: (x[1], x[0].row_count), reverse=True)
            matched_entries = [m[0] for m in exact_matches]
            best_confidence = exact_matches[0][1]
            
            # Single exact match -> no clarification needed
            if len(exact_matches) == 1:
                return RegistryMatch(
                    term=term,
                    entity_type=matched_entries[0].entity_type,
                    matches=matched_entries,
                    confidence=best_confidence,
                    needs_clarification=False,
                )
            
            # Multiple exact matches -> check if they're the same entity
            unique_canonicals = set(e.canonical_name for e in matched_entries)
            if len(unique_canonicals) == 1:
                return RegistryMatch(
                    term=term,
                    entity_type=matched_entries[0].entity_type,
                    matches=[matched_entries[0]],
                    confidence=best_confidence,
                    needs_clarification=False,
                )
            
            # Multiple distinct exact matches -> try contextual disambiguation first
            if query_context and entity_type == EntityType.DEPARTMENT:
                disambiguated = self._disambiguate_from_query_context(
                    term, matched_entries, query_context
                )
                if disambiguated:
                    # Return single match with high confidence
                    return RegistryMatch(
                        term=term,
                        entity_type=disambiguated.entity_type,
                        matches=[disambiguated],
                        confidence=0.95,
                        needs_clarification=False,
                    )
            
            # Still ambiguous -> needs clarification
            return RegistryMatch(
                term=term,
                entity_type=entity_type or matched_entries[0].entity_type,
                matches=matched_entries[:max_results],
                confidence=best_confidence,
                needs_clarification=True,
                clarification_options=[e.canonical_name for e in matched_entries[:max_results]],
            )
        
        # Step 3: If no exact matches, do fuzzy search across all entries
        if not partial_matches:
            types_to_search = [entity_type] if entity_type else list(EntityType)
            
            for etype in types_to_search:
                for entry in self._registry.get(etype, {}).values():
                    is_match, confidence = entry.matches(term_lower)
                    if is_match and confidence >= min_confidence:
                        partial_matches.append((entry, confidence))
        
        # Step 4: Sort by confidence (descending), then by row_count (descending)
        partial_matches.sort(key=lambda x: (x[1], x[0].row_count), reverse=True)
        
        # Step 5: Limit results
        partial_matches = partial_matches[:max_results]
        
        # Step 6: Determine if clarification is needed
        if not partial_matches:
            return RegistryMatch(
                term=term,
                entity_type=entity_type,
                matches=[],
                confidence=0.0,
                needs_clarification=False,
            )
        
        best_confidence = partial_matches[0][1]
        matched_entries = [m[0] for m in partial_matches]
        
        # NEW: Child-part priority matching for hierarchical departments
        # When searching for "Product Management", prefer "R&D (Parent) : Product Management"
        # over "Sales (Parent) : Sales NA : Enterprise Sales" (which might match on unrelated words)
        if len(partial_matches) > 1 and entity_type == EntityType.DEPARTMENT:
            child_exact_matches = []
            term_words = set(term_lower.split())
            
            for entry, confidence in partial_matches:
                canonical = entry.canonical_name.lower()
                if ' : ' in canonical:
                    # Get the child part (last segment after ":")
                    child_part = canonical.split(' : ')[-1].strip()
                    child_words = set(child_part.split())
                    
                    # Check if query exactly matches child part
                    if term_lower == child_part:
                        child_exact_matches.append((entry, 1.0))
                        logger.debug(f"Child-part exact match: '{term}' -> '{entry.canonical_name}'")
                    # Check if all query words are in child part (for multi-word queries)
                    elif term_words and term_words.issubset(child_words) and len(term_words) > 1:
                        # Calculate match quality based on word coverage
                        coverage = len(term_words) / len(child_words)
                        adjusted_confidence = max(confidence, 0.9 + coverage * 0.05)
                        child_exact_matches.append((entry, adjusted_confidence))
                        logger.debug(f"Child-part word match: '{term}' -> '{entry.canonical_name}' (conf={adjusted_confidence:.2f})")
            
            # If we found child-part matches, use those exclusively
            if child_exact_matches:
                child_exact_matches.sort(key=lambda x: (x[1], x[0].row_count), reverse=True)
                best_match = child_exact_matches[0]
                logger.info(f"Using child-part priority match: '{term}' -> '{best_match[0].canonical_name}'")
                
                return RegistryMatch(
                    term=term,
                    entity_type=best_match[0].entity_type,
                    matches=[best_match[0]],
                    confidence=best_match[1],
                    needs_clarification=False,
                )
        
        # Single high-confidence match -> no clarification needed
        if len(partial_matches) == 1 and best_confidence >= 0.85:
            return RegistryMatch(
                term=term,
                entity_type=matched_entries[0].entity_type,
                matches=matched_entries,
                confidence=best_confidence,
                needs_clarification=False,
            )
        
        # Multiple matches or lower confidence -> may need clarification
        # Check if all matches are essentially the same (e.g., aliases)
        unique_canonicals = set(e.canonical_name for e in matched_entries)
        
        if len(unique_canonicals) == 1 and best_confidence >= 0.7:
            # All matches point to same entity
            return RegistryMatch(
                term=term,
                entity_type=matched_entries[0].entity_type,
                matches=[matched_entries[0]],
                confidence=best_confidence,
                needs_clarification=False,
            )
        
        # Multiple distinct matches -> needs clarification
        return RegistryMatch(
            term=term,
            entity_type=entity_type or matched_entries[0].entity_type,
            matches=matched_entries,
            confidence=best_confidence,
            needs_clarification=True,
            clarification_options=[e.canonical_name for e in matched_entries],
        )
    
    def _disambiguate_from_query_context(
        self,
        term: str,
        matches: List[RegistryEntry],
        query: str,
    ) -> Optional[RegistryEntry]:
        """
        Try to disambiguate department from query context.
        
        Uses ONLY explicit geographic hints (NA, INTL, EMEA, APAC) to pick
        a specific match. Parent category terms (R&D, G&A, Sales, CoS) are
        NOT auto-disambiguated - these require user clarification since
        multiple sub-departments could be the intended target.
        
        Args:
            term: The original search term
            matches: List of matching RegistryEntry objects
            query: Full query string for context
            
        Returns:
            Single RegistryEntry if disambiguation successful, None otherwise
        """
        query_lower = query.lower()
        
        # Geographic disambiguation - these are specific enough to auto-select
        # Only apply if user explicitly mentions a region
        if re.search(r'\b(na|us|north\s*america|united\s*states|domestic)\b', query_lower):
            for m in matches:
                canonical_lower = m.canonical_name.lower()
                if ' na' in canonical_lower or 'na ' in canonical_lower or canonical_lower.endswith(' na'):
                    logger.info(f"Disambiguated '{term}' to '{m.canonical_name}' via NA context")
                    return m
        
        if re.search(r'\b(intl|international|global|emea|apac)\b', query_lower):
            for m in matches:
                canonical_lower = m.canonical_name.lower()
                if 'intl' in canonical_lower or 'international' in canonical_lower:
                    logger.info(f"Disambiguated '{term}' to '{m.canonical_name}' via INTL context")
                    return m
                if 'emea' in canonical_lower:
                    logger.info(f"Disambiguated '{term}' to '{m.canonical_name}' via EMEA context")
                    return m
                if 'apac' in canonical_lower:
                    logger.info(f"Disambiguated '{term}' to '{m.canonical_name}' via APAC context")
                    return m
        
        # NOTE: Parent category disambiguation (R&D, G&A, Sales, CoS, Marketing)
        # has been REMOVED. When a term matches multiple departments under a parent
        # hierarchy, we now require user clarification instead of auto-selecting.
        # This ensures users can choose:
        #   - All departments under the parent (consolidated)
        #   - Just the parent category
        #   - A specific sub-department
        #
        # See: build_entity_disambiguation_message() for clarification options
        
        logger.debug(f"No auto-disambiguation for '{term}' - requires user clarification ({len(matches)} matches)")
        return None
    
    def lookup_multiple(
        self,
        terms: List[str],
        entity_type: EntityType = None,
    ) -> Dict[str, RegistryMatch]:
        """
        Look up multiple terms at once.
        
        Args:
            terms: List of search terms
            entity_type: Limit search to this entity type
        
        Returns:
            Dict mapping each term to its RegistryMatch
        """
        return {term: self.lookup(term, entity_type) for term in terms}
    
    def get_all(self, entity_type: EntityType) -> List[RegistryEntry]:
        """Get all entries of a given type."""
        return list(self._registry.get(entity_type, {}).values())
    
    def get_all_canonical_names(self, entity_type: EntityType) -> List[str]:
        """Get all canonical names for an entity type."""
        return list(self._registry.get(entity_type, {}).keys())
    
    def get_hierarchy_members(
        self, 
        parent_prefix: str, 
        entity_type: EntityType = EntityType.DEPARTMENT
    ) -> List[str]:
        """
        Get all entities under a parent hierarchy.
        
        For example, get_hierarchy_members("R&D (Parent)") returns:
        - R&D (Parent)
        - R&D (Parent) : Product Management
        - R&D (Parent) : Engineering (Parent)
        - R&D (Parent) : Engineering (Parent) : Engineering 1 - Siva
        - ... all other R&D sub-departments
        
        Args:
            parent_prefix: The parent category prefix (e.g., "R&D (Parent)")
            entity_type: The entity type to search (default: DEPARTMENT)
            
        Returns:
            List of canonical names that start with the parent prefix
        """
        all_names = self.get_all_canonical_names(entity_type)
        # Include exact match and all children
        members = [
            name for name in all_names 
            if name == parent_prefix or name.startswith(parent_prefix + " :")
        ]
        return sorted(members)
    
    def find_parent_for_term(self, term: str) -> Optional[str]:
        """
        Find the parent category prefix for a search term.
        
        Maps common terms to their parent hierarchy:
        - "r&d", "research" -> "R&D (Parent)"
        - "g&a", "general admin" -> "G&A (Parent)"
        - "sales" -> "Sales (Parent)"
        - "cos", "cost of sales" -> "Cost of Sales (Parent)"
        - "marketing" -> "Marketing (Parent)"
        
        Args:
            term: The search term (e.g., "R&D", "Sales")
            
        Returns:
            Parent prefix if found, None otherwise
        """
        term_lower = term.lower().strip()
        
        parent_mappings = {
            "r&d": "R&D (Parent)",
            "rd": "R&D (Parent)",
            "research": "R&D (Parent)",
            "research and development": "R&D (Parent)",
            "g&a": "G&A (Parent)",
            "ga": "G&A (Parent)",
            "general admin": "G&A (Parent)",
            "general and admin": "G&A (Parent)",
            "general & admin": "G&A (Parent)",
            "general and administrative": "G&A (Parent)",
            "sales": "Sales (Parent)",
            "cos": "Cost of Sales (Parent)",
            "cost of sales": "Cost of Sales (Parent)",
            "cogs": "Cost of Sales (Parent)",
            "marketing": "Marketing (Parent)",
            "mktg": "Marketing (Parent)",
        }
        
        return parent_mappings.get(term_lower)
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            "departments": len(self._registry[EntityType.DEPARTMENT]),
            "accounts": len(self._registry[EntityType.ACCOUNT]),
            "account_numbers": len(self._registry[EntityType.ACCOUNT_NUMBER]),
            "subsidiaries": len(self._registry[EntityType.SUBSIDIARY]),
            "transaction_types": len(self._registry[EntityType.TRANSACTION_TYPE]),
            "index_terms": len(self._index),
            "source_rows": self._source_row_count,
            "built_at": self._built_at.isoformat() if self._built_at else None,
            "cache_valid": not self.needs_refresh(),
        }
    
    # =========================================================================
    # ENTITY EXTRACTION METHODS
    # =========================================================================
    
    def _extract_departments(self, data: List[Dict]):
        """Extract unique departments from data."""
        field_name = self._field_mappings.get("department")
        if not field_name:
            logger.warning("No department field mapped, skipping department extraction")
            return
        
        dept_info: Dict[str, Dict] = defaultdict(lambda: {
            "count": 0,
            "parent": None,
            "cost_category": None,
        })
        
        for row in data:
            raw_value = str(row.get(field_name, "") or "").strip()
            if not raw_value:
                continue
            
            dept_info[raw_value]["count"] += 1
            
            # Parse hierarchy: "G&A (Parent) : Finance" -> parent="G&A", dept="Finance"
            if " : " in raw_value:
                parts = raw_value.split(" : ")
                cost_category = parts[0].strip().replace("(Parent)", "").strip()
                dept_info[raw_value]["cost_category"] = cost_category
                dept_info[raw_value]["parent"] = cost_category
        
        # Create registry entries
        for raw_value, info in dept_info.items():
            aliases = self._generate_aliases(raw_value)
            
            # Add cost category as an alias if present
            if info["cost_category"]:
                aliases.add(info["cost_category"].lower())
            
            self._registry[EntityType.DEPARTMENT][raw_value] = RegistryEntry(
                canonical_name=raw_value,
                entity_type=EntityType.DEPARTMENT,
                aliases=aliases,
                parent=info["parent"],
                metadata={"cost_category": info["cost_category"]},
                row_count=info["count"],
                last_seen=datetime.now(),
            )
        
        logger.debug(f"Extracted {len(dept_info)} unique departments")
    
    def _extract_accounts(self, data: List[Dict]):
        """Extract unique account names from data."""
        field_name = self._field_mappings.get("account")
        number_field = self._field_mappings.get("account_number")
        
        if not field_name:
            logger.warning("No account name field mapped, skipping account extraction")
            return
        
        account_info: Dict[str, Dict] = defaultdict(lambda: {
            "count": 0,
            "numbers": set(),
            "cost_category": None,
        })
        
        for row in data:
            name = str(row.get(field_name, "") or "").strip()
            if not name:
                continue
            
            account_info[name]["count"] += 1
            
            # Capture associated account number
            if number_field:
                number = str(row.get(number_field, "") or "").strip()
                if number:
                    account_info[name]["numbers"].add(number)
            
            # Parse account hierarchy for cost category
            if " : " in name:
                parts = name.split(" : ")
                account_info[name]["cost_category"] = parts[0].strip()
        
        # Create registry entries
        for name, info in account_info.items():
            aliases = self._generate_aliases(name)
            
            # Add account numbers as aliases
            for num in info["numbers"]:
                aliases.add(num.lower())
                # Also add prefix variations (e.g., "531" for "531000")
                if len(num) >= 3:
                    aliases.add(num[:3])
                    aliases.add(num[:2])
            
            self._registry[EntityType.ACCOUNT][name] = RegistryEntry(
                canonical_name=name,
                entity_type=EntityType.ACCOUNT,
                aliases=aliases,
                metadata={
                    "numbers": list(info["numbers"]),
                    "cost_category": info["cost_category"],
                },
                row_count=info["count"],
                last_seen=datetime.now(),
            )
        
        logger.debug(f"Extracted {len(account_info)} unique accounts")
    
    def _extract_account_numbers(self, data: List[Dict]):
        """Extract unique account numbers from data."""
        field_name = self._field_mappings.get("account_number")
        name_field = self._field_mappings.get("account")
        
        if not field_name:
            logger.warning("No account number field mapped, skipping account number extraction")
            return
        
        number_info: Dict[str, Dict] = defaultdict(lambda: {
            "count": 0,
            "names": set(),
        })
        
        for row in data:
            number = str(row.get(field_name, "") or "").strip()
            if not number:
                continue
            
            number_info[number]["count"] += 1
            
            # Capture associated account name
            if name_field:
                name = str(row.get(name_field, "") or "").strip()
                if name:
                    number_info[number]["names"].add(name)
        
        # Create registry entries
        for number, info in number_info.items():
            aliases = self._generate_aliases(number)
            
            # Add prefix variations
            if len(number) >= 2:
                aliases.add(number[:2])
            if len(number) >= 3:
                aliases.add(number[:3])
            
            # Add associated names as aliases
            for name in info["names"]:
                # Add simplified name parts
                for part in name.split(" : "):
                    cleaned = part.strip().lower()
                    if cleaned and len(cleaned) > 2:
                        aliases.add(cleaned)
            
            self._registry[EntityType.ACCOUNT_NUMBER][number] = RegistryEntry(
                canonical_name=number,
                entity_type=EntityType.ACCOUNT_NUMBER,
                aliases=aliases,
                metadata={"names": list(info["names"])},
                row_count=info["count"],
                last_seen=datetime.now(),
            )
        
        logger.debug(f"Extracted {len(number_info)} unique account numbers")
    
    def _extract_subsidiaries(self, data: List[Dict]):
        """Extract unique subsidiaries from data."""
        field_name = self._field_mappings.get("subsidiary")
        
        if not field_name:
            logger.warning("No subsidiary field mapped, skipping subsidiary extraction")
            return
        
        sub_info: Dict[str, int] = defaultdict(int)
        
        for row in data:
            value = str(row.get(field_name, "") or "").strip()
            if value:
                sub_info[value] += 1
        
        # Create registry entries
        for value, count in sub_info.items():
            aliases = self._generate_aliases(value)
            
            # Add common abbreviations for regions
            value_lower = value.lower()
            if "north america" in value_lower or " na" in value_lower:
                aliases.update(["na", "north america", "us", "usa"])
            if "emea" in value_lower or "europe" in value_lower:
                aliases.update(["emea", "europe", "eu"])
            if "apac" in value_lower or "asia" in value_lower:
                aliases.update(["apac", "asia", "asia pacific"])
            if "india" in value_lower:
                aliases.add("india")
            if "germany" in value_lower:
                aliases.update(["germany", "de"])
            if "netherlands" in value_lower:
                aliases.update(["netherlands", "nl"])
            if "japan" in value_lower:
                aliases.update(["japan", "jp"])
            
            self._registry[EntityType.SUBSIDIARY][value] = RegistryEntry(
                canonical_name=value,
                entity_type=EntityType.SUBSIDIARY,
                aliases=aliases,
                row_count=count,
                last_seen=datetime.now(),
            )
        
        logger.debug(f"Extracted {len(sub_info)} unique subsidiaries")
    
    def _extract_transaction_types(self, data: List[Dict]):
        """Extract unique transaction types from data."""
        field_name = self._field_mappings.get("transaction_type")
        
        if not field_name:
            logger.warning("No transaction type field mapped, skipping extraction")
            return
        
        type_info: Dict[str, int] = defaultdict(int)
        
        for row in data:
            value = str(row.get(field_name, "") or "").strip()
            if value:
                type_info[value] += 1
        
        # Create registry entries with common aliases
        type_aliases = {
            "Journal": ["journal", "je", "journal entry", "manual entry"],
            "VendBill": ["vendbill", "vendor bill", "bill", "invoice", "ap"],
            "VendCred": ["vendcred", "vendor credit", "credit memo", "credit"],
            "ExpRept": ["exprept", "expense report", "expense", "er"],
            "Check": ["check", "cheque", "payment"],
            "Deposit": ["deposit", "bank deposit"],
        }
        
        for value, count in type_info.items():
            aliases = self._generate_aliases(value)
            
            # Add predefined aliases if available
            if value in type_aliases:
                aliases.update(type_aliases[value])
            
            self._registry[EntityType.TRANSACTION_TYPE][value] = RegistryEntry(
                canonical_name=value,
                entity_type=EntityType.TRANSACTION_TYPE,
                aliases=aliases,
                row_count=count,
                last_seen=datetime.now(),
            )
        
        logger.debug(f"Extracted {len(type_info)} unique transaction types")
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _auto_detect_fields(self, data: List[Dict]) -> Dict[str, str]:
        """
        Auto-detect field names from data sample.
        
        Returns mapping of entity type to actual field name in data.
        """
        if not data:
            return {}
        
        sample = data[0]
        keys_lower = {k.lower(): k for k in sample.keys()}
        
        mappings = {}
        
        # Department field detection
        dept_candidates = ["department_name", "department", "dept_name", "dept"]
        for candidate in dept_candidates:
            if candidate.lower() in keys_lower:
                mappings["department"] = keys_lower[candidate.lower()]
                break
        
        # Account name field detection
        account_candidates = ["account_name", "account", "acctname", "acct_name"]
        for candidate in account_candidates:
            if candidate.lower() in keys_lower:
                mappings["account"] = keys_lower[candidate.lower()]
                break
        
        # Account number field detection
        number_candidates = ["account_number", "acctnumber", "acct_number", "acctno"]
        for candidate in number_candidates:
            if candidate.lower() in keys_lower:
                mappings["account_number"] = keys_lower[candidate.lower()]
                break
        
        # Subsidiary field detection
        sub_candidates = ["subsidiarynohierarchy", "subsidiary", "subsidiary_name", "entity"]
        for candidate in sub_candidates:
            if candidate.lower() in keys_lower:
                mappings["subsidiary"] = keys_lower[candidate.lower()]
                break
        
        # Transaction type field detection
        type_candidates = ["type", "trantype", "transaction_type", "type_text"]
        for candidate in type_candidates:
            if candidate.lower() in keys_lower:
                mappings["transaction_type"] = keys_lower[candidate.lower()]
                break
        
        return mappings
    
    def _generate_aliases(self, value: str) -> Set[str]:
        """
        Generate normalized aliases for a value.
        
        Creates multiple variations for flexible matching:
        - Lowercase normalized
        - Without parenthetical suffixes
        - Split on common separators
        - Acronyms from multi-word values
        - Common abbreviation expansions
        
        Examples:
            "G&A (Parent) : Finance" -> {"g&a", "finance", "g&a finance", "ga", "general and administrative"}
            "GPS - North America" -> {"gps", "north america", "gps na", "gps - north america"}
        """
        aliases = set()
        value_lower = value.lower().strip()
        
        if not value_lower:
            return aliases
        
        # Full normalized value
        aliases.add(value_lower)
        
        # Remove common suffixes like "(Parent)"
        cleaned = re.sub(r'\s*\(parent\)\s*', ' ', value_lower, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if cleaned and cleaned != value_lower:
            aliases.add(cleaned)
        
        # Split on common separators and add parts
        separators = [" : ", " - ", " / ", ", ", " – "]
        for sep in separators:
            if sep in value_lower:
                parts = value_lower.split(sep)
                for part in parts:
                    part = part.strip()
                    if part and len(part) > 1:
                        aliases.add(part)
                        # Also clean parenthetical from parts
                        part_cleaned = re.sub(r'\s*\(parent\)\s*', '', part).strip()
                        if part_cleaned and part_cleaned != part:
                            aliases.add(part_cleaned)
                
                # Add combinations for two-part values
                if len(parts) == 2:
                    p1 = parts[0].strip().replace("(parent)", "").strip()
                    p2 = parts[1].strip().replace("(parent)", "").strip()
                    if p1 and p2:
                        aliases.add(f"{p1} {p2}")
        
        # Handle ampersand variations
        if "&" in value_lower:
            aliases.add(value_lower.replace("&", " and "))
            aliases.add(value_lower.replace("&", "").replace("  ", " "))
            aliases.add(value_lower.replace(" & ", ""))
        
        # Generate acronym from multi-word values
        words = re.findall(r'\b[a-z]+\b', cleaned if cleaned else value_lower)
        if len(words) >= 2:
            acronym = "".join(w[0] for w in words if len(w) > 0)
            if len(acronym) >= 2 and len(acronym) <= 6:
                aliases.add(acronym)
        
        # Common abbreviation mappings
        abbreviations = {
            "general and administrative": ["g&a", "ga", "admin"],
            "general & administrative": ["g&a", "ga", "admin"],
            "research and development": ["r&d", "rd", "research"],
            "research & development": ["r&d", "rd", "research"],
            "sales and marketing": ["s&m", "sm", "sales marketing"],
            "sales & marketing": ["s&m", "sm", "sales marketing"],
            "cost of goods sold": ["cogs", "cos"],
            "cost of sales": ["cos", "cogs"],
            "north america": ["na"],
            "information technology": ["it"],
            "human resources": ["hr"],
            "customer success": ["cs"],
            "sales development": ["sdr"],
            "product development": ["pd", "product dev"],
            "accounts payable": ["ap"],
            "accounts receivable": ["ar"],
        }
        
        for full_form, abbrevs in abbreviations.items():
            if full_form in value_lower:
                aliases.update(abbrevs)
        
        return aliases
    
    def _build_index(self):
        """
        Build inverted index for fast lookups.
        
        Maps each alias/term to the list of (EntityType, canonical_name) pairs
        that it could refer to.
        """
        self._index.clear()
        
        for entity_type, entries in self._registry.items():
            for canonical, entry in entries.items():
                # Index by canonical name
                canonical_lower = canonical.lower()
                self._index[canonical_lower].append((entity_type, canonical))
                
                # Index by each alias
                for alias in entry.aliases:
                    if alias != canonical_lower:
                        self._index[alias].append((entity_type, canonical))
        
        logger.debug(f"Built inverted index with {len(self._index)} terms")
    
    # =========================================================================
    # CACHE MANAGEMENT
    # =========================================================================
    
    def _save_to_cache(self):
        """Persist registry to disk cache."""
        cache_path = self.cache_dir / self.CACHE_FILE
        
        data = {
            "version": 2,  # Increment when format changes
            "built_at": self._built_at.isoformat() if self._built_at else None,
            "source_row_count": self._source_row_count,
            "field_mappings": self._field_mappings,
            "registry": {},
        }
        
        for entity_type, entries in self._registry.items():
            data["registry"][entity_type.value] = {
                canonical: entry.to_dict()
                for canonical, entry in entries.items()
            }
        
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Registry cache saved to {cache_path}")
        except Exception as e:
            logger.error(f"Failed to save registry cache: {e}")
    
    def _load_from_cache(self):
        """Load registry from disk cache."""
        cache_path = self.cache_dir / self.CACHE_FILE
        
        if not cache_path.exists():
            logger.info("No registry cache found, will build on first data fetch")
            return
        
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Check version compatibility
            if data.get("version", 0) < 2:
                logger.warning("Registry cache version outdated, will rebuild")
                return
            
            # Load metadata
            self._built_at = (
                datetime.fromisoformat(data["built_at"])
                if data.get("built_at") else None
            )
            self._source_row_count = data.get("source_row_count", 0)
            self._field_mappings = data.get("field_mappings", {})
            
            # Load registry entries
            for entity_type_str, entries in data.get("registry", {}).items():
                try:
                    entity_type = EntityType(entity_type_str)
                except ValueError:
                    continue
                
                for canonical, entry_data in entries.items():
                    self._registry[entity_type][canonical] = RegistryEntry.from_dict(entry_data)
            
            # Rebuild search index
            self._build_index()
            
            logger.info(
                f"Loaded registry cache: {self.stats['departments']} depts, "
                f"{self.stats['accounts']} accounts, "
                f"{self.stats['subsidiaries']} subsidiaries, "
                f"built {self._built_at}"
            )
            
        except Exception as e:
            logger.error(f"Failed to load registry cache: {e}")
            # Clear any partial state
            for et in EntityType:
                self._registry[et] = {}
            self._index.clear()


# =============================================================================
# SINGLETON MANAGEMENT
# =============================================================================

_dynamic_registry: Optional[DynamicRegistry] = None


def get_dynamic_registry() -> DynamicRegistry:
    """Get the dynamic registry singleton."""
    global _dynamic_registry
    if _dynamic_registry is None:
        _dynamic_registry = DynamicRegistry()
    return _dynamic_registry


def reset_dynamic_registry():
    """Reset the registry (useful for testing)."""
    global _dynamic_registry
    _dynamic_registry = None

