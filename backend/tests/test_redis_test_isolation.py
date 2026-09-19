"""DEV-001 / DEV-002 回归：测试进程必须与真实 Redis 完全隔离。

背景：修复前，`RateLimiterMiddleware`、`recommend._get_redis`、`auth._get_redis_client`
三处入口都会连到 `settings.redis_url` 指向的**真实** Redis，导致：

* 限流计数跨用例累积，跑到第 N 条时所有同身份用例集体 429
  （实测 `rate_limit:user:day:1` 累积到 211/300，全量结果为 38 failed）；
* `ai_cache:*` 跨 pytest 进程存活，使"LLM 不可用应降级"的用例读到旧缓存
  （`engine_mode` 恒为 `ai`，实测 1 failed）。

隔离手段：conftest 在导入期把 `redis.from_url` 替换为返回进程内 FakeRedis 的工厂。

注意：这里通过 `fake_redis` 夹具取得假客户端实例，**不要**
`import backend.tests.conftest` —— 那会以另一个模块身份重新执行 conftest，产生
第二个互不相干的 FakeRedis 实例，从而误判。
"""

import pytest


def test_redis_from_url_returns_fake_client(fake_redis):
    """`redis.from_url` 必须返回进程内假客户端（三处入口的共同依赖）。"""
    import redis as redis_lib

    client = redis_lib.from_url("redis://localhost:6379", decode_responses=True)
    assert client is fake_redis, "from_url 必须被替换为假客户端工厂"


def test_rate_limiter_endpoint_uses_fake_redis(fake_redis):
    """限流中间件通过 from_url 建连，因而必须拿到假客户端。"""
    from backend.app.middleware.rate_limiter import RateLimiterMiddleware

    class _App:
        pass

    middleware = RateLimiterMiddleware(_App())
    assert middleware.redis is fake_redis, "限流中间件必须指向假 Redis"


def test_recommend_redis_entry_is_fake(fake_redis):
    """推荐接口的 AI 缓存 / 配额入口必须返回假客户端。"""
    from backend.app.api import recommend

    assert recommend._get_redis() is fake_redis


def test_auth_redis_entry_is_fake(fake_redis):
    """登录防爆破入口必须返回假客户端。"""
    from backend.app.api import auth

    assert auth._get_redis_client() is fake_redis


def test_fake_redis_writes_do_not_reach_real_server(fake_redis):
    """向假客户端写入后，真实 Redis 不得出现对应键。"""
    from backend.app.config import settings
    from backend.tests.conftest import REAL_REDIS_CLIENT_CLASS

    probe_key = "dev001_isolation_probe"
    fake_redis.incr(probe_key)
    assert fake_redis.get(probe_key) == "1", "假客户端应记录该键"

    try:
        real = REAL_REDIS_CLIENT_CLASS.from_url(settings.redis_url, decode_responses=True)
        real.ping()
    except Exception:
        pytest.skip("本机无真实 Redis，跳过误写检查")

    try:
        assert real.get(probe_key) is None, "假客户端的写入不得出现在真实 Redis 上"
    finally:
        real.close()


def test_conftest_does_not_import_backend_at_load_time():
    """conftest 不得在导入期 import backend 模块。

    否则会连带 import `backend.app.database`，把 DB engine 绑定到默认的
    `sqlite:///data/insurance.db`（开发库）——此时测试模块还没机会设
    `DATABASE_URL`，导致所有测试写进开发库（实测会污染 data/insurance.db）。
    """
    import ast
    import io
    import os

    conftest_path = os.path.join(os.path.dirname(__file__), "conftest.py")
    source = io.open(conftest_path, encoding="utf-8").read()
    tree = ast.parse(source)

    # 收集模块级（顶层）的 import 语句；函数体内的延迟导入是允许的
    offenders = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("backend"):
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").startswith("backend"):
                offenders.append(node.module)

    assert offenders == [], (
        f"conftest.py 顶层不得 import backend 模块（会污染开发库）：{offenders}"
    )


def test_rate_limit_keys_are_empty_at_test_start(fake_redis):
    """限流键必须在每个用例开始时清零（消除顺序依赖）。"""
    assert fake_redis.keys("rate_limit:*") == [], "用例起始状态不应残留限流键"
    fake_redis.incr("rate_limit:ip:probe")
    assert fake_redis.keys("rate_limit:*") == ["rate_limit:ip:probe"]


def test_rate_limit_keys_do_not_leak_into_next_test(fake_redis):
    """与上一个用例配对：确认前一个用例写入的键没有泄漏到这里。"""
    assert fake_redis.keys("rate_limit:*") == [], "上个用例的限流键泄漏到了本用例"
