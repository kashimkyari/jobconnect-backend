from fastapi import WebSocket
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id].add(websocket)
        logger.info(
            "WebSocket connected: user_id=%s total_user_connections=%s",
            user_id,
            len(self.active_connections[user_id]),
        )

    def disconnect(self, user_id: int, websocket: Optional[WebSocket] = None):
        if user_id not in self.active_connections:
            return
        if websocket is None:
            del self.active_connections[user_id]
            logger.info("WebSocket disconnected: user_id=%s all_connections_closed=true", user_id)
            return

        self.active_connections[user_id].discard(websocket)
        remaining = len(self.active_connections[user_id])
        if remaining == 0:
            del self.active_connections[user_id]
        logger.info(
            "WebSocket disconnected: user_id=%s remaining_user_connections=%s",
            user_id,
            remaining,
        )

    async def _send_text(self, user_id: int, websocket: WebSocket, message: str):
        try:
            await websocket.send_text(message)
        except Exception as exc:
            logger.warning("Failed to send text WebSocket message to user %s: %s", user_id, exc)
            self.disconnect(user_id, websocket)

    async def _send_json(self, user_id: int, websocket: WebSocket, data: dict):
        try:
            await websocket.send_json(data)
        except Exception as exc:
            logger.warning("Failed to send JSON WebSocket message to user %s: %s", user_id, exc)
            self.disconnect(user_id, websocket)

    async def send_personal_message(self, message: str, user_id: int):
        for connection in list(self.active_connections.get(user_id, [])):
            await self._send_text(user_id, connection, message)

    async def send_personal_json(self, data: dict, user_id: int):
        """Send JSON event to specific user."""
        for connection in list(self.active_connections.get(user_id, [])):
            await self._send_json(user_id, connection, data)

    async def broadcast(self, message: str):
        for user_id, connections in list(self.active_connections.items()):
            for connection in list(connections):
                await self._send_text(user_id, connection, message)

    async def broadcast_json(self, data: dict):
        """Broadcast JSON event to all connected users."""
        for user_id, connections in list(self.active_connections.items()):
            for connection in list(connections):
                await self._send_json(user_id, connection, data)

    async def broadcast_to_users(self, message: str, user_ids: List[int]):
        for user_id in user_ids:
            for connection in list(self.active_connections.get(user_id, [])):
                await self._send_text(user_id, connection, message)

    async def broadcast_json_to_users(self, data: dict, user_ids: List[int]):
        """Broadcast JSON event to specific users."""
        for user_id in user_ids:
            for connection in list(self.active_connections.get(user_id, [])):
                await self._send_json(user_id, connection, data)

    # Contract-specific broadcast methods
    async def broadcast_contract_activated(self, contract_id: int, job_id: int, worker_id: int, employer_id: int, job_title: str):
        """Notify both parties when contract is activated."""
        event = {
            "type": "contract.activated",
            "timestamp": datetime.utcnow().isoformat(),
            "payload": {
                "contract_id": contract_id,
                "job_id": job_id,
                "job_title": job_title,
                "message": f"Work has started on '{job_title}'"
            }
        }
        await self.broadcast_json_to_users(event, [worker_id, employer_id])

    async def broadcast_contract_marked_complete(self, contract_id: int, job_id: int, marked_by_user_id: int, 
                                                other_party_id: int, marked_by_role: str, job_title: str):
        """Notify other party when contract is marked complete."""
        event = {
            "type": "contract.marked_complete",
            "timestamp": datetime.utcnow().isoformat(),
            "payload": {
                "contract_id": contract_id,
                "job_id": job_id,
                "job_title": job_title,
                "marked_by_user_id": marked_by_user_id,
                "marked_by_role": marked_by_role,
                "message": f"The {marked_by_role.lower()} has marked '{job_title}' as complete"
            }
        }
        await self.broadcast_json_to_users(event, [other_party_id])

    async def broadcast_contract_completed(self, contract_id: int, job_id: int, worker_id: int, employer_id: int, job_title: str):
        """Notify both parties when contract is fully completed."""
        event = {
            "type": "contract.completed",
            "timestamp": datetime.utcnow().isoformat(),
            "payload": {
                "contract_id": contract_id,
                "job_id": job_id,
                "job_title": job_title,
                "message": f"'{job_title}' is now complete. You can leave a review.",
                "status": "completed"
            }
        }
        await self.broadcast_json_to_users(event, [worker_id, employer_id])

    async def broadcast_review_posted(self, contract_id: int, job_id: int, reviewer_id: int, target_user_id: int, 
                                     rating: int, reviewer_name: str, job_title: str):
        """Notify user when a review is posted."""
        event = {
            "type": "review.posted",
            "timestamp": datetime.utcnow().isoformat(),
            "payload": {
                "contract_id": contract_id,
                "job_id": job_id,
                "reviewer_id": reviewer_id,
                "reviewer_name": reviewer_name,
                "rating": rating,
                "job_title": job_title,
                "message": f"{reviewer_name} left a {rating}-star review on '{job_title}'"
            }
        }
        await self.broadcast_json_to_users(event, [target_user_id])

manager = ConnectionManager()
