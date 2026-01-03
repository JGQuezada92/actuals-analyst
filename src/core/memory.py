"""
Conversation Memory System

In-memory session management for follow-up questions and contextual conversations.
Stores conversation history and accumulated context per session.
"""
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)

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
    
    def has_context(self) -> bool:
        """Check if there's any accumulated context."""
        return bool(
            self.departments or 
            self.accounts or 
            self.time_periods or 
            self.last_analysis_type
        )
    
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
        
        return "\n".join(parts) if parts else ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "departments": self.departments,
            "accounts": self.accounts,
            "time_periods": self.time_periods,
            "last_data_filters": self.last_data_filters,
            "last_analysis_type": self.last_analysis_type,
            "last_result_summary": self.last_result_summary,
        }

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
        data_filters: Dict[str, Any] = None
    ) -> ConversationTurn:
        """Add an assistant message to the conversation."""
        if analysis_type:
            self.context.last_analysis_type = analysis_type
        if result_summary:
            self.context.last_result_summary = result_summary
        if data_filters:
            self.context.last_data_filters = data_filters
        
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
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "turn_count": len(self.turns),
            "context": self.context.to_dict(),
            "user_id": self.user_id,
            "channel_id": self.channel_id,
        }

class SessionManager:
    """
    Manages conversation sessions.
    
    In-memory storage - sessions are lost when the application restarts.
    For production, consider Redis or database persistence.
    """
    
    def __init__(
        self,
        session_timeout_minutes: int = 30,
        max_turns_per_session: int = 10,
        max_sessions: int = 1000
    ):
        """
        Initialize the session manager.
        
        Args:
            session_timeout_minutes: Inactive sessions expire after this time
            max_turns_per_session: Maximum conversation turns to retain
            max_sessions: Maximum number of active sessions
        """
        self.session_timeout_minutes = session_timeout_minutes
        self.max_turns_per_session = max_turns_per_session
        self.max_sessions = max_sessions
        
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
    
    def delete_session(self, session_id: str):
        """Delete a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.debug(f"Deleted session {session_id}")
    
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

