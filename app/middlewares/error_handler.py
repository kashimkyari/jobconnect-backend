from fastapi import Request, status, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from ..utils.logging import StructuredLogger

error_logger = StructuredLogger("error_handler")

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except HTTPException as e:
            # Let HTTPExceptions pass through with their original status codes
            # This preserves 429 (rate limit), 401 (unauthorized), 403 (forbidden), etc.
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "detail": e.detail,
                    "type": "http_exception",
                    "code": "HTTP_ERROR"
                }
            )
        except Exception as e:
            try:
                import sentry_sdk

                sentry_sdk.capture_exception(e)
            except Exception:
                pass

            # Log the error
            error_logger.error(
                "Unhandled exception",
                path=str(request.url.path),
                method=request.method,
                error=str(e),
                error_type=type(e).__name__
            )
            
            # Return structured error response
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": "An unexpected error occurred",
                    "type": "internal_server_error",
                    "code": "INTERNAL_ERROR"
                }
            )
