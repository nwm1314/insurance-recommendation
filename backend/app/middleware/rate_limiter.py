import time
import redis
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from backend.app.config import settings


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Redis token bucket rate limiter middleware"""

    def __init__(self, app):
        super().__init__(app)
        try:
            self.redis = redis.from_url(settings.redis_url, decode_responses=True)
            self.redis.ping()
        except Exception:
            self.redis = None

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/"):
            client_ip = request.client.host if request.client else "unknown"

            if not self._check_ip_limit(client_ip):
                raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

        response = await call_next(request)
        return response

    def _check_ip_limit(self, ip: str) -> bool:
        if self.redis is None:
            return True  # Allow all when Redis unavailable
        key = f"rate_limit:ip:{ip}"
        current = self.redis.get(key)
        limit = settings.rate_limit_ip_per_minute
        if current is None:
            self.redis.setex(key, 60, 1)
            return True
        if int(current) >= limit:
            return False
        self.redis.incr(key)
        return True
