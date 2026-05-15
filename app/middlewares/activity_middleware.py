from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from jose import jwt
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.utils.logging import app_logger


class ActivityMiddleware(BaseHTTPMiddleware):
    """Simple middleware that updates `last_active_at` for authenticated users.

    It is intentionally lightweight: it reads the Authorization header, decodes
    the JWT to obtain `sub` (user id), and updates the corresponding user row
    using the DB session provided by DBSessionMiddleware (request.state.db).
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            auth: Optional[str] = request.headers.get("authorization")
            if auth and auth.lower().startswith("bearer ") and hasattr(request.state, "db"):
                token = auth.split(None, 1)[1]
                try:
                    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
                    user_id = payload.get("sub")
                    if user_id is not None:
                        # fetch and update last_active_at
                        try:
                            user = await request.state.db.get(request.state.db._model_registry.get('User'), int(user_id))
                        except Exception:
                            user = None
                        # Fallback: try the import to avoid depending on internal registry
                        if user is None:
                            from app.models.user import User
                            try:
                                user = await request.state.db.get(User, int(user_id))
                            except Exception:
                                user = None

                        if user is not None:
                            user.last_active_at = datetime.now(timezone.utc)
                            # Do not commit here — DBSessionMiddleware will commit at end of request.
                except Exception:
                    # Ignore token decode errors; user simply not authenticated for this request
                    pass
        except Exception:
            app_logger.exception("ActivityMiddleware error")

        response = await call_next(request)
        return response
