import logging
import time
import redis
import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.app.config import settings
from backend.app.dependencies.auth import ACCESS_TOKEN_COOKIE, get_client_ip

logger = logging.getLogger(__name__)

# OPS-001：原子计数 Lua 脚本——INCR 与首次 EXPIRE 在一次 Redis 调用内完成，
# 消除 get→setex/incr 竞态（并发首击可能各自 setex 重置窗口）。
_ATOMIC_INCREMENT_LUA = """
local c = redis.call('INCR', KEYS[1])
if c == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return c
"""

# 运行期断路标记：Redis 异常时置位，放行请求且只刷一条 warning；
# 恢复成功后清除，避免每个请求都打日志。
_REDIS_ERROR_FLAG = {"down": False}


def _mark_redis_error(exc: Exception) -> None:
    if not _REDIS_ERROR_FLAG["down"]:
        _REDIS_ERROR_FLAG["down"] = True
        logger.warning("Redis unavailable, rate limiter fail-open: %s", exc)


def _mark_redis_recovered() -> None:
    _REDIS_ERROR_FLAG["down"] = False


def _get_client_ip(request: Request) -> str:
    """Real client IP, honoring X-Forwarded-For only via trusted proxies."""
    return get_client_ip(request) or "unknown"


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Redis 固定窗口限流（原子计数，故障 fail-open）。

    OPS-001：计数逻辑为原子 Lua（单次 INCR+EXPIRE）；启动时不再因 ping
    失败永久禁用——运行期 Redis 异常自动放行并打点，恢复后自动回归限流。
    """

    def __init__(self, app):
        super().__init__(app)
        self._script = None
        try:
            self.redis = redis.from_url(settings.redis_url, decode_responses=True)
            self.redis.ping()
            register = getattr(self.redis, "register_script", None)
            self._script = register(_ATOMIC_INCREMENT_LUA) if register else None
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

    def _atomic_increment(self, key: str, ttl_seconds: int) -> int | None:
        """原子 INCR+首次 EXPIRE。Redis 异常时 fail-open（返回 None 放行）。

        客户端不支持 register_script 时（如测试 stub）回退为 INCR 后按
        首次返回值补 EXPIRE 的近似原子实现。
        """
        try:
            if self._script is not None:
                result = self._script(keys=[key], args=[ttl_seconds])
            else:
                result = self.redis.incr(key)
                if int(result) == 1:
                    self.redis.setex(key, ttl_seconds, 1)
            _mark_redis_recovered()
            return int(result)
        except Exception as exc:
            # fail-open 边界：Redis 侧任何异常（RedisError/连接层错误/脚本
            # 加载失败）都不允许把请求打成 500，放行并打点
            _mark_redis_error(exc)
            return None

    def _check_ip_limit(self, ip: str) -> bool:
        if self.redis is None:
            return True  # Allow all when Redis unavailable
        key = f"rate_limit:ip:{ip}"
        count = self._atomic_increment(key, 60)
        if count is None:
            return True
        return count <= settings.rate_limit_ip_per_minute

    def _check_user_limit(self, user_id: str) -> bool:
        if self.redis is None:
            return True
        minute_key = f"rate_limit:user:minute:{user_id}"
        day_key = f"rate_limit:user:day:{user_id}"
        if not self._increment_with_limit(minute_key, settings.rate_limit_user_per_minute, 60):
            return False
        return self._increment_with_limit(day_key, settings.rate_limit_user_per_day, 86400)

    def _increment_with_limit(self, key: str, limit: int, ttl_seconds: int) -> bool:
        count = self._atomic_increment(key, ttl_seconds)
        if count is None:
            return True
        return count <= limit

    def _get_user_id(self, request: Request) -> str | None:
        authorization = request.headers.get("authorization")
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1]
        if not token:
            token = request.cookies.get(ACCESS_TOKEN_COOKIE)
        if not token:
            return None
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        except jwt.PyJWTError:
            return None
        if payload.get("type") != "access":
            return None
        return payload.get("sub")
