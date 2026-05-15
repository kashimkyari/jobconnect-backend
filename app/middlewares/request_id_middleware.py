"""
Request ID middleware for tracking and idempotency validation.

This middleware:
1. Extracts request IDs from headers (X-Request-ID, Idempotency-Key)
2. Generates one if missing
3. Adds it to request state for downstream use
4. Includes it in response headers for client confirmation
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import uuid
import logging

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that extracts or generates request IDs for idempotency tracking.
    
    Supports multiple header names:
    - X-Request-ID (standard)
    - Idempotency-Key (Stripe convention)
    - X-Idempotency-Key (alternative)
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next):
        # Extract request ID from headers (try multiple names)
        request_id = (
            request.headers.get('X-Request-ID') or
            request.headers.get('Idempotency-Key') or
            request.headers.get('X-Idempotency-Key')
        )
        
        # Generate one if not provided
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # Store in request state for downstream access
        request.state.request_id = request_id
        request.state.is_idempotency_key_provided = (
            'X-Request-ID' in request.headers or
            'Idempotency-Key' in request.headers or
            'X-Idempotency-Key' in request.headers
        )
        
        # Log request with ID
        path = request.url.path
        method = request.method
        logger.debug(
            f"Request {method} {path}",
            extra={
                'request_id': request_id,
                'has_idempotency_key': request.state.is_idempotency_key_provided
            }
        )
        
        # Process request
        response = await call_next(request)
        
        # Add request ID to response headers
        response.headers['X-Request-ID'] = request_id
        
        return response
