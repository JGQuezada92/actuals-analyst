"""
Conversation Memory System

In-memory session management for follow-up questions and contextual conversations.
Stores conversation history and accumulated context per session.

Supports file-based persistence for session continuity across process invocations.
"""
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)

# Default sessions directory (relative to project root)
DEFAULT_SESSIONS_DIR = Path(__file__).parent.parent.parent / "sessions"

@dataclass
class DisambiguationRecord:
    """
    Record of a user's disambiguation choice.
    
    Stores the term that was ambiguous, the dimension/entity the user chose,
    and contextual information to help determine when this choice applies.
    
    Supports two types of disambiguation:
    1. Dimension disambiguation: "Is R&D an account or department?"
       - disambiguation_type = "dimension"
       - chosen_dimension = "account" or "department"
       - chosen_value = {"prefix": "52"} or {"name": "R&D (Parent)"}
    
    2. Entity disambiguation: "Which R&D department?"
       - disambiguation_type = "entity"
       - chosen_dimension = "department" (always, since this is entity-level)
       - chosen_value = {
           "label": "All R&D departments (consolidated)",
           "departments": ["R&D (Parent)", "R&D (Parent) : Product Management", ...],
           "is_consolidated": True
         }
    """
    term: str                           # e.g., "R&D", "G&A"
    chosen_dimension: str               # "account" or "department"
    chosen_value: Dict[str, Any]        # The actual filter applied
    topic_summary: str                  # Brief description of the query topic
    turn_index: int                     # Which turn this was made in
    disambiguation_type: str = "dimension"  # "dimension" or "entity"
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "term": self.term,
            "chosen_dimension": self.chosen_dimension,
            "chosen_value": self.chosen_value,
            "topic_summary": self.topic_summary,
            "turn_index": self.turn_index,
            "disambiguation_type": self.disambiguation_type,
            "timestamp": self.timestamp.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DisambiguationRecord":
        """Create from a dictionary."""
        return cls(
            term=data["term"],
            chosen_dimension=data["chosen_dimension"],
            chosen_value=data.get("chosen_value", {}),
            topic_summary=data.get("topic_summary", ""),
            turn_index=data.get("turn_index", 0),
            disambiguation_type=data.get("disambiguation_type", "dimension"),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(),
        )


@dataclass
class ConversationTurn:
    """A single turn in a conversation."""
    role: str                          # "user" or "assistant"
    content: str                       # Message content
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Extracted context from this turn
    departments_mentioned: List[str] = field(default_factory=list)
    accounts_mentioned: List[str] = field(default_factory=list)
    time_periods_mentioned: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "departments": self.departments_mentioned,
            "accounts": self.accounts_mentioned,
            "periods": self.time_periods_mentioned,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationTurn":
        """Create a ConversationTurn from a dictionary."""
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
            departments_mentioned=data.get("departments", []),
            accounts_mentioned=data.get("accounts", []),
            time_periods_mentioned=data.get("periods", []),
        )
    
    def to_message_format(self) -> Dict[str, str]:
        """Convert to standard message format for LLM."""
        return {
            "role": self.role,
            "content": self.content,
        }

@dataclass
class ConversationContext:
    """Accumulated context from conversation history."""
    # Entities mentioned across the conversation
    departments: List[str] = field(default_factory=list)
    accounts: List[str] = field(default_factory=list)
    time_periods: List[str] = field(default_factory=list)
    
    # Last analysis results (for follow-up questions)
    last_data_filters: Dict[str, Any] = field(default_factory=dict)
    last_analysis_type: Optional[str] = None
    last_result_summary: Optional[str] = None
    
    # Working data storage (for follow-up queries)
    working_data: Optional[List[Dict[str, Any]]] = None
    working_data_row_count: int = 0
    working_data_columns: List[str] = field(default_factory=list)
    working_data_filter_signature: Optional[str] = None  # Hash of filters applied
    working_data_timestamp: Optional[datetime] = None
    
    def has_context(self) -> bool:
        """Check if there's any accumulated context."""
        return bool(
            self.departments or 
            self.accounts or 
            self.time_periods or 
            self.last_analysis_type
        )
    
    def has_working_data(self) -> bool:
        """Check if we have valid working data."""
        if self.working_data is None:
            return False
        # Expire after 30 minutes
        if self.working_data_timestamp:
            age = datetime.now() - self.working_data_timestamp
            if age.total_seconds() > 1800:  # 30 minutes
                return False
        return True
    
    def store_working_data(
        self,
        data: List[Dict[str, Any]],
        columns: List[str],
        filter_signature: str,
    ):
        """Store working data for follow-up queries."""
        self.working_data = data
        self.working_data_row_count = len(data)
        self.working_data_columns = columns
        self.working_data_filter_signature = filter_signature
        self.working_data_timestamp = datetime.now()
        logger.debug(f"Stored working data: {len(data)} rows, signature={filter_signature[:16]}...")
    
    def clear_working_data(self):
        """Clear working data (e.g., when filters change incompatibly)."""
        self.working_data = None
        self.working_data_row_count = 0
        self.working_data_columns = []
        self.working_data_filter_signature = None
        self.working_data_timestamp = None
    
    def get_filter_signature(self) -> str:
        """Generate signature from current filter state."""
        import hashlib
        import json
        sig_data = {
            "departments": sorted(self.departments),
            "accounts": sorted(self.accounts),
            "time_periods": sorted(self.time_periods),
            "last_data_filters": self.last_data_filters,
        }
        sig_str = json.dumps(sig_data, sort_keys=True)
        return hashlib.md5(sig_str.encode()).hexdigest()
    
    def to_prompt_context(self) -> str:
        """Convert context to text for LLM prompt."""
        parts = []
        
        if self.departments:
            parts.append(f"Previously discussed departments: {', '.join(self.departments)}")
        
        if self.accounts:
            parts.append(f"Previously discussed accounts: {', '.join(self.accounts)}")
        
        if self.time_periods:
            parts.append(f"Previously discussed time periods: {', '.join(self.time_periods)}")
        
        if self.last_analysis_type:
            parts.append(f"Last analysis type: {self.last_analysis_type}")
        
        if self.last_result_summary:
            parts.append(f"Last result: {self.last_result_summary}")
        
        if self.has_working_data():
            parts.append(f"Working data available: {self.working_data_row_count} rows")
        
        return "\n".join(parts) if parts else ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "departments": self.departments,
            "accounts": self.accounts,
            "time_periods": self.time_periods,
            "last_data_filters": self.last_data_filters,
            "last_analysis_type": self.last_analysis_type,
            "last_result_summary": self.last_result_summary,
            "has_working_data": self.has_working_data(),
            "working_data_row_count": self.working_data_row_count,
            # Note: working_data itself is NOT serialized (too large)
            "working_data_columns": self.working_data_columns,
            "working_data_filter_signature": self.working_data_filter_signature,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationContext":
        """Create a ConversationContext from a dictionary."""
        ctx = cls(
            departments=data.get("departments", []),
            accounts=data.get("accounts", []),
            time_periods=data.get("time_periods", []),
            last_data_filters=data.get("last_data_filters", {}),
            last_analysis_type=data.get("last_analysis_type"),
            last_result_summary=data.get("last_result_summary"),
        )
        # Restore working data metadata (but not the actual data)
        ctx.working_data_row_count = data.get("working_data_row_count", 0)
        ctx.working_data_columns = data.get("working_data_columns", [])
        ctx.working_data_filter_signature = data.get("working_data_filter_signature")
        return ctx


@dataclass
class Session:
    """A conversation session with history and context."""
    session_id: str
    created_at: datetime
    last_activity: datetime
    
    # Conversation history (limited to max_turns)
    turns: deque = field(default_factory=lambda: deque(maxlen=10))
    
    # Accumulated context
    context: ConversationContext = field(default_factory=ConversationContext)
    
    # Session metadata
    user_id: Optional[str] = None
    channel_id: Optional[str] = None  # For Slack
    
    # Pending disambiguation state (for follow-up responses)
    pending_query: Optional[str] = None  # Original query that triggered disambiguation
    pending_parsed_query: Optional[Dict[str, Any]] = None  # Serialized ParsedQuery
    pending_ambiguous_terms: Optional[List[str]] = None  # Terms needing clarification
    pending_disambiguation_options: Optional[Dict[str, List[Dict]]] = None  # Options per term
    
    # Resolved disambiguation choices (for topic-aware query rewriting)
    resolved_disambiguations: List[DisambiguationRecord] = field(default_factory=list)
    
    def add_turn(
        self,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None,
        departments: List[str] = None,
        accounts: List[str] = None,
        time_periods: List[str] = None
    ) -> ConversationTurn:
        """Add a new turn to the conversation."""
        turn = ConversationTurn(
            role=role,
            content=content,
            timestamp=datetime.now(),
            metadata=metadata or {},
            departments_mentioned=departments or [],
            accounts_mentioned=accounts or [],
            time_periods_mentioned=time_periods or [],
        )
        
        self.turns.append(turn)
        self.last_activity = datetime.now()
        
        # Update accumulated context
        if departments:
            for dept in departments:
                if dept not in self.context.departments:
                    self.context.departments.append(dept)
        
        if accounts:
            for acct in accounts:
                if acct not in self.context.accounts:
                    self.context.accounts.append(acct)
        
        if time_periods:
            for period in time_periods:
                if period not in self.context.time_periods:
                    self.context.time_periods.append(period)
        
        return turn
    
    def add_user_message(
        self, 
        content: str, 
        departments: List[str] = None,
        accounts: List[str] = None,
        time_periods: List[str] = None
    ) -> ConversationTurn:
        """Add a user message to the conversation."""
        return self.add_turn(
            role="user",
            content=content,
            departments=departments,
            accounts=accounts,
            time_periods=time_periods,
        )
    
    def add_assistant_message(
        self,
        content: str,
        analysis_type: str = None,
        result_summary: str = None,
        data_filters: Dict[str, Any] = None,
        working_data: List[Dict[str, Any]] = None,
        working_data_columns: List[str] = None,
    ) -> ConversationTurn:
        """Add an assistant message to the conversation."""
        if analysis_type:
            self.context.last_analysis_type = analysis_type
        if result_summary:
            self.context.last_result_summary = result_summary
        if data_filters:
            self.context.last_data_filters = data_filters
        
        # Store working data if provided
        if working_data is not None and working_data_columns:
            filter_sig = self.context.get_filter_signature()
            self.context.store_working_data(working_data, working_data_columns, filter_sig)
        
        return self.add_turn(
            role="assistant",
            content=content,
            metadata={
                "analysis_type": analysis_type,
                "result_summary": result_summary,
            }
        )
    
    def get_history_for_prompt(self, max_turns: int = 5) -> List[Dict[str, str]]:
        """Get conversation history formatted for LLM prompt."""
        recent_turns = list(self.turns)[-max_turns:]
        return [turn.to_message_format() for turn in recent_turns]
    
    def get_full_context_prompt(self) -> str:
        """Get full context as a prompt supplement."""
        parts = []
        
        context_text = self.context.to_prompt_context()
        if context_text:
            parts.append("=== Conversation Context ===")
            parts.append(context_text)
        
        if self.turns:
            parts.append("\n=== Recent Conversation ===")
            for turn in list(self.turns)[-5:]:
                parts.append(f"{turn.role.upper()}: {turn.content[:200]}...")
        
        return "\n".join(parts)
    
    def clear_context(self):
        """Clear accumulated context but keep history."""
        self.context = ConversationContext()
    
    def clear_pending_disambiguation(self):
        """Clear pending disambiguation state after it's been processed."""
        self.pending_query = None
        self.pending_parsed_query = None
        self.pending_ambiguous_terms = None
        self.pending_disambiguation_options = None
    
    def set_pending_disambiguation(
        self,
        query: str,
        parsed_query_dict: Dict[str, Any],
        ambiguous_terms: List[str],
        disambiguation_options: Dict[str, List[Dict]] = None,
    ):
        """Store pending disambiguation state for follow-up processing."""
        self.pending_query = query
        self.pending_parsed_query = parsed_query_dict
        self.pending_ambiguous_terms = ambiguous_terms
        self.pending_disambiguation_options = disambiguation_options or {}
        logger.debug(f"Set pending disambiguation for query: {query[:50]}...")
    
    def has_pending_disambiguation(self) -> bool:
        """Check if there's a pending disambiguation to process."""
        return self.pending_query is not None and self.pending_ambiguous_terms is not None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for display/logging."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "turn_count": len(self.turns),
            "context": self.context.to_dict(),
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            "has_pending_disambiguation": self.has_pending_disambiguation(),
            "resolved_disambiguation_count": len(self.resolved_disambiguations),
        }
    
    def to_serializable_dict(self) -> Dict[str, Any]:
        """Convert session to fully serializable dictionary for persistence."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            # Serialize turns
            "turns": [turn.to_dict() for turn in self.turns],
            # Serialize context
            "context": self.context.to_dict(),
            # Pending disambiguation state
            "pending_query": self.pending_query,
            "pending_parsed_query": self.pending_parsed_query,
            "pending_ambiguous_terms": self.pending_ambiguous_terms,
            "pending_disambiguation_options": self.pending_disambiguation_options,
            # Resolved disambiguation choices
            "resolved_disambiguations": [d.to_dict() for d in self.resolved_disambiguations],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], max_turns: int = 10) -> "Session":
        """Create a Session from a dictionary (for loading from persistence)."""
        # Deserialize resolved disambiguations
        resolved_disambiguations = []
        for d in data.get("resolved_disambiguations", []):
            resolved_disambiguations.append(DisambiguationRecord.from_dict(d))
        
        session = cls(
            session_id=data["session_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_activity=datetime.fromisoformat(data["last_activity"]),
            turns=deque(maxlen=max_turns),
            context=ConversationContext.from_dict(data.get("context", {})),
            user_id=data.get("user_id"),
            channel_id=data.get("channel_id"),
            pending_query=data.get("pending_query"),
            pending_parsed_query=data.get("pending_parsed_query"),
            pending_ambiguous_terms=data.get("pending_ambiguous_terms"),
            pending_disambiguation_options=data.get("pending_disambiguation_options"),
            resolved_disambiguations=resolved_disambiguations,
        )
        
        # Restore turns
        for turn_data in data.get("turns", []):
            turn = ConversationTurn.from_dict(turn_data)
            session.turns.append(turn)
        
        return session


class SessionManager:
    """
    Manages conversation sessions.
    
    Supports both in-memory and file-based persistence.
    File-based persistence enables session continuity across process invocations.
    """
    
    def __init__(
        self,
        session_timeout_minutes: int = 30,
        max_turns_per_session: int = 10,
        max_sessions: int = 1000,
        sessions_dir: Optional[Path] = None,
        persist_to_disk: bool = True,
    ):
        """
        Initialize the session manager.
        
        Args:
            session_timeout_minutes: Inactive sessions expire after this time
            max_turns_per_session: Maximum conversation turns to retain
            max_sessions: Maximum number of active sessions
            sessions_dir: Directory for session persistence (default: PROJECT_ROOT/sessions)
            persist_to_disk: Whether to persist sessions to disk
        """
        self.session_timeout_minutes = session_timeout_minutes
        self.max_turns_per_session = max_turns_per_session
        self.max_sessions = max_sessions
        self.persist_to_disk = persist_to_disk
        
        # Set up sessions directory
        self.sessions_dir = sessions_dir or DEFAULT_SESSIONS_DIR
        if self.persist_to_disk:
            self.sessions_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Sessions directory: {self.sessions_dir}")
        
        self._sessions: Dict[str, Session] = {}
        self._last_cleanup = time.time()
    
    def create_session(
        self,
        user_id: str = None,
        channel_id: str = None
    ) -> Session:
        """Create a new conversation session."""
        self._maybe_cleanup()
        
        session_id = str(uuid.uuid4())
        now = datetime.now()
        
        session = Session(
            session_id=session_id,
            created_at=now,
            last_activity=now,
            turns=deque(maxlen=self.max_turns_per_session),
            user_id=user_id,
            channel_id=channel_id,
        )
        
        self._sessions[session_id] = session
        logger.debug(f"Created session {session_id}")
        
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get an existing session by ID."""
        session = self._sessions.get(session_id)
        
        if session and self._is_expired(session):
            self.delete_session(session_id)
            return None
        
        return session
    
    def get_or_create_session(
        self,
        session_id: str = None,
        user_id: str = None,
        channel_id: str = None
    ) -> Session:
        """Get existing session or create a new one."""
        if session_id:
            session = self.get_session(session_id)
            if session:
                return session
        
        return self.create_session(user_id=user_id, channel_id=channel_id)
    
    def get_session_by_channel(self, channel_id: str, user_id: str = None) -> Optional[Session]:
        """Get a session by Slack channel (or create one)."""
        # Find existing session for this channel
        for session in self._sessions.values():
            if session.channel_id == channel_id:
                if not self._is_expired(session):
                    return session
        
        # Create new session for channel
        return self.create_session(user_id=user_id, channel_id=channel_id)
    
    def save_session(self, session_id: str) -> bool:
        """
        Persist a session to disk.
        
        Args:
            session_id: The session ID to save
            
        Returns:
            True if saved successfully, False otherwise
        """
        if not self.persist_to_disk:
            return False
        
        session = self._sessions.get(session_id)
        if not session:
            # Try to load from provided session_id if not in memory
            logger.warning(f"Session {session_id} not found in memory for saving")
            return False
        
        try:
            session_file = self.sessions_dir / f"{session_id}.json"
            session_data = session.to_serializable_dict()
            
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2, default=str)
            
            logger.debug(f"Saved session {session_id} to {session_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save session {session_id}: {e}")
            return False
    
    def load_session(self, session_id: str) -> Optional[Session]:
        """
        Load a session from disk.
        
        Args:
            session_id: The session ID to load
            
        Returns:
            The loaded Session, or None if not found or expired
        """
        # First check in-memory cache
        if session_id in self._sessions:
            session = self._sessions[session_id]
            if not self._is_expired(session):
                logger.debug(f"Session {session_id} found in memory")
                return session
            else:
                self.delete_session(session_id)
        
        if not self.persist_to_disk:
            return None
        
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            logger.debug(f"Session file not found: {session_file}")
            return None
        
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                session_data = json.load(f)
            
            session = Session.from_dict(session_data, max_turns=self.max_turns_per_session)
            
            # Check if expired
            if self._is_expired(session):
                logger.debug(f"Session {session_id} has expired, deleting")
                self._delete_session_file(session_id)
                return None
            
            # Add to in-memory cache
            self._sessions[session_id] = session
            logger.info(f"Loaded session {session_id} from disk (turns: {len(session.turns)}, pending: {session.has_pending_disambiguation()})")
            return session
            
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None
    
    def _delete_session_file(self, session_id: str):
        """Delete a session file from disk."""
        if not self.persist_to_disk:
            return
        
        session_file = self.sessions_dir / f"{session_id}.json"
        try:
            if session_file.exists():
                session_file.unlink()
                logger.debug(f"Deleted session file: {session_file}")
        except Exception as e:
            logger.error(f"Failed to delete session file {session_id}: {e}")
    
    def delete_session(self, session_id: str):
        """Delete a session from memory and disk."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.debug(f"Deleted session {session_id} from memory")
        
        # Also delete from disk
        self._delete_session_file(session_id)
    
    def _is_expired(self, session: Session) -> bool:
        """Check if a session has expired."""
        age = (datetime.now() - session.last_activity).total_seconds()
        return age > (self.session_timeout_minutes * 60)
    
    def _maybe_cleanup(self):
        """Periodically clean up expired sessions."""
        now = time.time()
        
        # Cleanup every 5 minutes
        if now - self._last_cleanup < 300:
            return
        
        self._last_cleanup = now
        
        expired = [
            sid for sid, session in self._sessions.items()
            if self._is_expired(session)
        ]
        
        for sid in expired:
            self.delete_session(sid)
        
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")
        
        # Enforce max sessions
        if len(self._sessions) > self.max_sessions:
            # Remove oldest sessions
            sorted_sessions = sorted(
                self._sessions.items(),
                key=lambda x: x[1].last_activity
            )
            
            to_remove = len(self._sessions) - self.max_sessions
            for sid, _ in sorted_sessions[:to_remove]:
                self.delete_session(sid)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get session manager statistics."""
        return {
            "active_sessions": len(self._sessions),
            "max_sessions": self.max_sessions,
            "timeout_minutes": self.session_timeout_minutes,
        }

# Singleton instance
_session_manager: Optional[SessionManager] = None

def get_session_manager() -> SessionManager:
    """Get the configured session manager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager

def reset_session_manager():
    """Reset the session manager (useful for testing)."""
    global _session_manager
    _session_manager = None

