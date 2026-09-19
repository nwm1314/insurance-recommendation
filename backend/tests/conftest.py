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

# 在安装替换**之前**保存原始客户端类，供回归用例连真实 Redis 做"未误写"校验。
# 注意：三个调用点引用的都是同一个 `redis` 模块对象，故对该模块 `from_url` 的
# 替换是全局生效的；必须先把原始引用保存下来。
import redis as _redis_lib

REAL_REDIS_CLIENT_CLASS = _redis_lib.Redis


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
    """把 Redis 客户端工厂替换为进程内假客户端。

    **不导入任何 backend 模块**：conftest 在任何测试模块之前加载，若此时
    import `backend.app.*`，会连带 import `backend.app.database` 并把 DB engine
    绑定到 `settings.database_url` 的默认值（`sqlite:///data/insurance.db`，
    即开发库）——那时测试模块还没机会设 `DATABASE_URL`，于是全部测试都会写进
    开发库（实测会把 products 写进 data/insurance.db）。

    因此这里只改第三方 `redis` 模块上的 `from_url`：三个调用点
    （rate_limiter / recommend / auth）都是 `redis.from_url(...)` 或
    `redis_lib.from_url(...)`，指向同一个模块对象，运行期解析即得假客户端。
    """
    import redis as redis_lib

    redis_lib.from_url = lambda *a, **k: FAKE_REDIS


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
