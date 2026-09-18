"""后端测试共享夹具：Redis 隔离。

背景（DEV-001 / DEV-002）：
`RateLimiterMiddleware`、`recommend._get_redis`、`auth._get_redis_client` 三处都会
直接对 `settings.redis_url`（默认指向本机 6379 的**真实** Redis）建立连接。测试
进程未替换这些客户端时，计数与缓存会写进开发库并**跨用例、跨运行累积**：

* `rate_limit:user:day:*` 累积到 `rate_limit_user_per_day`（默认 300）后，所有使用
  同一 admin 身份的用例集体 429；
* `ai_cache:*` 因 TTL 较长而跨 pytest 进程存活，使"LLM 不可用应降级"的用例读到
  上一次运行留下的缓存，`engine_mode` 恒为 `ai`。

实现要点（为什么必须在**模块导入时**安装且用会话级 fixture 兜底）：
`app.add_middleware(RateLimiterMiddleware)` 只登记类，中间件实例在首次请求（即
`TestClient.__enter__`）时才构建。多个测试文件的 `client` fixture 是
`scope="session"`，其构建时机可能早于函数级 autouse fixture；若只在函数级替换
入口，第一份 TestClient 已抓取了真实 Redis 客户端，后续替换无济于事。

因此这里：
1. 在 **conftest 导入时**（早于任何被测模块导入）把假客户端安装到三个入口；
2. 再用会话级 autouse fixture 兜底重复安装；
3. 函数级 autouse fixture 保证每个用例前后清空键空间，消除顺序依赖。

本文件只改变"Redis 客户端从哪来"，不改变任何业务语义——限流阈值、配额、缓存
TTL 仍按 `settings` 原样生效，故各用例对限流 / 配额行为的断言强度不变。
"""

import fnmatch
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

# 在安装替换**之前**保存原始 from_url，供回归用例连真实 Redis 做"未误写"校验。
# 注意：`backend.app.middleware.rate_limiter` 里的 `redis` 就是同一个模块对象，
# 因此对 `rate_limiter_module.redis.from_url` 的替换会**全局**生效；必须在这里
# 先把原始函数引用保存下来。
import redis as _redis_lib

REAL_REDIS_CLIENT_CLASS = _redis_lib.Redis
REAL_FROM_URL = _redis_lib.from_url


class FakeRedis:
    """进程内最小 Redis 替身：覆盖本项目用到的 INCR / EXPIRE / GET / SETEX / 脚本。

    刻意不实现 TTL 过期——用例生命周期远短于任何真实 TTL，且"不自动过期"能让键
    累积在进程内可见，从而更严格地暴露隔离缺失问题。
    """

    def __init__(self):
        self.data: dict[str, str] = {}
        self.expires: dict[str, int] = {}

    # --- 连接语义 ---
    def ping(self):
        return True

    def register_script(self, lua):  # noqa: ARG002 - 与真实客户端签名保持一致
        def _run(keys, args):
            key = keys[0]
            ttl = int(args[0])
            value = self.incr(key)
            if value == 1:
                self.expire(key, ttl)
            return value

        return _run

    # --- 字符串操作 ---
    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, *args, **kwargs):  # noqa: ARG002
        self.data[key] = str(value)
        return True

    def setex(self, key, ttl, value):
        self.data[key] = str(value)
        self.expires[key] = int(ttl)
        return True

    def incr(self, key):
        current = int(self.data.get(key, "0"))
        self.data[key] = str(current + 1)
        return current + 1

    def expire(self, key, ttl):
        self.expires[key] = int(ttl)
        return True

    def delete(self, *keys):
        removed = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                removed += 1
            self.expires.pop(key, None)
        return removed

    def keys(self, pattern="*"):
        return [k for k in self.data if fnmatch.fnmatch(k, pattern)]

    def flushdb(self):
        self.data.clear()
        self.expires.clear()
        return True


# 会话级单例：同一测试会话内共享一个假 Redis（与线上共享实例的形态一致，但生命
# 周期限于本进程）。
FAKE_REDIS = FakeRedis()


def _install_fake_redis() -> None:
    """把三处 Redis 入口替换为进程内假客户端。

    在模块导入时调用一次（早于被测模块导入与 TestClient 构建），并在会话级
    fixture 中重复调用以兜底。
    """
    import backend.app.api.auth as auth_module
    import backend.app.api.recommend as recommend_module
    import backend.app.middleware.rate_limiter as rate_limiter_module

    # 1) 限流中间件：替换 from_url，并改写实例属性兜底（实例可能已构建）
    rate_limiter_module.redis.from_url = lambda *a, **k: FAKE_REDIS
    _original_init = rate_limiter_module.RateLimiterMiddleware.__init__

    if not getattr(_original_init, "_dsh_redis_patched", False):

        def __init__(self, app):
            _original_init(self, app)
            # 无视 from_url 的结果，强制指向假客户端
            self.redis = FAKE_REDIS
            self._script = FAKE_REDIS.register_script("")

        __init__._dsh_redis_patched = True
        rate_limiter_module.RateLimiterMiddleware.__init__ = __init__

    # 2) 推荐接口的 AI 缓存 / 每日配额
    recommend_module._get_redis = lambda: FAKE_REDIS

    # 3) 登录防爆破
    auth_module._get_redis_client = lambda: FAKE_REDIS


# 导入即安装：确保早于任何 client fixture 构建 TestClient。
_install_fake_redis()


@pytest.fixture(scope="session", autouse=True)
def isolate_redis_session():
    """会话级兜底安装：防止其它插件 / 模块在导入后回写真实入口。"""
    _install_fake_redis()
    yield FAKE_REDIS
    FAKE_REDIS.flushdb()


@pytest.fixture(autouse=True)
def isolate_redis():
    """每个用例从空键空间开始，消除"跑到第 N 条才击穿限流"的顺序依赖。"""
    FAKE_REDIS.flushdb()
    _install_fake_redis()
    yield FAKE_REDIS
    FAKE_REDIS.flushdb()


@pytest.fixture(scope="session")
def fake_redis():
    """供需要直接检查 / 预置键值的用例使用。"""
    return FAKE_REDIS
