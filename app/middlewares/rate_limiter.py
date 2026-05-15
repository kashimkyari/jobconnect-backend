from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
import time
from collections import defaultdict
import asyncio
from ..config import settings

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.requests = defaultdict(list)
        self.lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMITING_ENABLED:
            return await call_next(request)

        # Get client IP (handle None client from certain proxy setups)
        if request.client:
            client_ip = request.client.host
        else:
            # Fallback to X-Forwarded-For header or a default
            client_ip = request.headers.get("x-forwarded-for", "unknown").split(",")[0].strip()
        
        # Clean up old requests
        now = time.time()
        async with self.lock:
            self.requests[client_ip] = [
                req_time for req_time in self.requests[client_ip]
                if now - req_time < 60  # Keep only requests from last minute
            ]
            
            # Check rate limit
            if len(self.requests[client_ip]) >= settings.RATE_LIMIT_PER_MINUTE:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later."
                )
            
            # Add current request
            self.requests[client_ip].append(now)
        
        response = await call_next(request)
        return response
