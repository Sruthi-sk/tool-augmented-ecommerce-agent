"""Session state management. Single file owns all session logic."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from config import CONVERSATION_HISTORY_LIMIT


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class Session:
    session_id: str
    appliance_type: Optional[str] = None
    model_number: Optional[str] = None
    part_number: Optional[str] = None
    brand: Optional[str] = None
    symptom: Optional[str] = None
    last_tool_result: Optional[dict] = None
    last_source_url: Optional[str] = None
    conversation_history: list[Message] = field(default_factory=list)

    _SLOTS = {
        "appliance_type", "model_number", "part_number",
        "brand", "symptom", "last_tool_result", "last_source_url",
    }

    def update(self, **kwargs) -> None:
        """Set multiple fields at once. Ignores unknown fields."""
        for key, value in kwargs.items():
            if key in self._SLOTS:
                setattr(self, key, value)

    def clear_slot(self, slot: str) -> None:
        """Reset a specific field to None."""
        if slot in self._SLOTS:
            setattr(self, slot, None)

    def add_message(self, role: str, content: str) -> None:
        """Append a message, enforcing the history window."""
        self.conversation_history.append(Message(role=role, content=content))
        if len(self.conversation_history) > CONVERSATION_HISTORY_LIMIT:
            self.conversation_history = self.conversation_history[
                -CONVERSATION_HISTORY_LIMIT:
            ]

    def get_context_for_llm(self) -> dict:
        """Return current state as a dict for injection into the system prompt."""
        return {
            "session_id": self.session_id,
            "appliance_type": self.appliance_type,
            "model_number": self.model_number,
            "part_number": self.part_number,
            "brand": self.brand,
            "symptom": self.symptom,
            "last_source_url": self.last_source_url,
        }


class SessionStore(ABC):
    @abstractmethod
    async def get(self, session_id: str) -> Session: ...

    @abstractmethod
    async def save(self, session: Session) -> None: ...


class InMemorySessionStore(SessionStore):
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    async def get(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id=session_id)
        return self._sessions[session_id]

    async def save(self, session: Session) -> None:
        self._sessions[session.session_id] = session
