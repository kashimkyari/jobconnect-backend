from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session
from app.utils.logging import app_logger

class DBSessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        session: AsyncSession = async_session()
        request.state.db = session
        try:
            response = await call_next(request)
            await session.commit()
        except Exception as e:
            await session.rollback()
            app_logger.exception("An error occurred during a database transaction")
            raise e
        finally:
            await session.close()
        return response
