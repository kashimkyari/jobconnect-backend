from fastapi import Request, HTTPException, status
import time
from collections import defaultdict
from ..config import settings

class RateLimiter:
    def __init__(self, times: int, seconds: int):
        self.times = times
        self.seconds = seconds
        self.requests = defaultdict(list)

    async def __call__(self, request: Request):
        if not settings.RATE_LIMITING_ENABLED:
            return

        # Handle None client (can happen with certain proxy setups)
        if request.client:
            client_id = request.client.host
        else:
            # Fallback to X-Forwarded-For header or a default
            client_id = request.headers.get("x-forwarded-for", "unknown").split(",")[0].strip()
        
        now = time.time()
        
        # Clean up old requests
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id]
            if now - req_time < self.seconds
        ]
        
        # Check rate limit
        if len(self.requests[client_id]) >= self.times:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {self.seconds} seconds."
            )
        
        # Add current request
        self.requests[client_id].append(now)

# Example: 3 requests per 60 seconds
otp_rate_limiter = RateLimiter(times=3, seconds=60)
