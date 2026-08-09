import time
import redis
import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.app.config import settings


def _get_client_ip(request: Request) -> str:
    """Real client IP, respecting the reverse-proxy chain (X-Forwarded-For)."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or "unknown"
    return request.client.host if request.client else "unknown"


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
            client_ip = _get_client_ip(request)

            if not self._check_ip_limit(client_ip):
                return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"})

            user_id = self._get_user_id(request)
            if user_id and not self._check_user_limit(user_id):
                return JSONResponse(status_code=429, content={"detail": "用户请求过于频繁，请稍后再试"})

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

    def _check_user_limit(self, user_id: str) -> bool:
        if self.redis is None:
            return True
        minute_key = f"rate_limit:user:minute:{user_id}"
        day_key = f"rate_limit:user:day:{user_id}"
        if not self._increment_with_limit(minute_key, settings.rate_limit_user_per_minute, 60):
            return False
        return self._increment_with_limit(day_key, settings.rate_limit_user_per_day, 86400)

    def _increment_with_limit(self, key: str, limit: int, ttl_seconds: int) -> bool:
        current = self.redis.get(key)
        if current is None:
            self.redis.setex(key, ttl_seconds, 1)
            return True
        if int(current) >= limit:
            return False
        self.redis.incr(key)
        return True

    def _get_user_id(self, request: Request) -> str | None:
        authorization = request.headers.get("authorization")
        if not authorization or not authorization.lower().startswith("bearer "):
            return None
        token = authorization.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        except jwt.PyJWTError:
            return None
        if payload.get("type") != "access":
            return None
        return payload.get("sub")
