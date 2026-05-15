from threading import Lock
from typing import Dict, Optional


class MessagePresence:
    """
    In-memory presence map for chat conversation focus.
    Tracks user_id -> active_conversation_user_id.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._active: Dict[int, int] = {}

    def set_active(self, user_id: int, other_user_id: int) -> None:
        if user_id is None or other_user_id is None:
            return
        with self._lock:
            self._active[int(user_id)] = int(other_user_id)

    def clear(self, user_id: int) -> None:
        if user_id is None:
            return
        with self._lock:
            self._active.pop(int(user_id), None)

    def is_active(self, user_id: int, other_user_id: int) -> bool:
        if user_id is None or other_user_id is None:
            return False
        with self._lock:
            return self._active.get(int(user_id)) == int(other_user_id)


message_presence = MessagePresence()
