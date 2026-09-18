"""DEV-001 / DEV-002 回归：测试进程必须与真实 Redis 完全隔离。

背景：修复前，`RateLimiterMiddleware`、`recommend._get_redis`、`auth._get_redis_client`
三处入口都会连到 `settings.redis_url` 指向的**真实** Redis，导致：

* 限流计数跨用例累积，跑到第 N 条时所有同身份用例集体 429
  （实测 `rate_limit:user:day:1` 累积到 211/300，全量结果为 38 failed）；
* `ai_cache:*` 跨 pytest 进程存活，使"LLM 不可用应降级"的用例读到旧缓存
  （`engine_mode` 恒为 `ai`，实测 1 failed）。

本文件把"三个入口都已被替换为进程内假客户端"这一前提固化为回归用例——若将来有人
新增 Redis 入口或回退了 conftest 的安装逻辑，这里会直接失败。

注意：这里通过 `isolate_redis` / `fake_redis` 夹具取得假客户端实例，**不要**
`import backend.tests.conftest` —— 那会以另一个模块身份重新执行 conftest，产生
第二个互不相干的 FakeRedis 实例，从而误判。
"""

import pytest


def test_rate_limiter_uses_fake_redis(fake_redis):
    """限流中间件的 redis 必须是进程内假客户端，而非真实连接。"""
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
    import redis as redis_lib

    from backend.app.config import settings

    probe_key = "dev001_isolation_probe"
    fake_redis.incr(probe_key)
    assert fake_redis.get(probe_key) == "1", "假客户端应记录该键"

    # 注意：settings.redis_url 的 from_url 已被 conftest 全局替换，这里用未被
    # 替换的原始客户端类去连真实服务端。
    from backend.tests.conftest import REAL_REDIS_CLIENT_CLASS

    try:
        real = REAL_REDIS_CLIENT_CLASS.from_url(settings.redis_url, decode_responses=True)
        real.ping()
    except Exception:
        pytest.skip("本机无真实 Redis，跳过误写检查")

    try:
        assert real.get(probe_key) is None, "假客户端的写入不得出现在真实 Redis 上"
    finally:
        real.close()


def test_rate_limit_keys_are_empty_at_test_start(fake_redis):
    """限流键必须在每个用例开始时清零（消除顺序依赖）。

    若上一个用例的计数残留，本断言会失败。
    """
    assert fake_redis.keys("rate_limit:*") == [], "用例起始状态不应残留限流键"
    fake_redis.incr("rate_limit:ip:probe")
    assert fake_redis.keys("rate_limit:*") == ["rate_limit:ip:probe"]


def test_rate_limit_keys_do_not_leak_into_next_test(fake_redis):
    """与上一个用例配对：确认前一个用例写入的键没有泄漏到这里。"""
    assert fake_redis.keys("rate_limit:*") == [], "上个用例的限流键泄漏到了本用例"
