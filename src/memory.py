"""
Conversation memory: persistent chat history in PostgreSQL.
"""
from sqlalchemy.orm import Session

from database import transaction
from models import ChatMessage, Session as SessionModel
from state import ConversationMessage


class ChatMessageRepository:
    """Repository for ChatMessage (conversation memory)."""

    def __init__(self, session: Session):
        self.session = session

    def add(self, session_id: str, role: str, content: str) -> ChatMessage:
        chat_message = ChatMessage(session_id=session_id, role=role, content=content)
        self.session.add(chat_message)
        self.session.flush()
        return chat_message

    def latest(self, session_id: str, limit: int) -> list[ChatMessage]:
        """Most recent `limit` messages, returned in chronological order."""
        rows = (
            self.session.query(ChatMessage)
            .filter_by(session_id=session_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(rows))


class PersistentMemory:
    """Load -> invoke -> save manager backed by the chat_messages table."""

    def __init__(self, window: int = 10):
        self.window = window

    def ensure_session(self, session_id: str) -> None:
        """Insert the Session row if absent, so the FK on chat_messages holds."""
        with transaction() as session:
            if session.get(SessionModel, session_id) is None:
                session.add(SessionModel(id=session_id))

    def load_messages(self, session_id: str) -> list[ConversationMessage]:
        with transaction() as session:
            rows = ChatMessageRepository(session).latest(session_id, self.window)
            return [ConversationMessage(role=row.role, content=row.content) for row in rows]

    def save_message(self, session_id: str, role: str, content: str) -> None:
        self.ensure_session(session_id)
        with transaction() as session:
            ChatMessageRepository(session).add(session_id, role, content)
