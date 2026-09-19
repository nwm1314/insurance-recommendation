import re
from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
GLOBAL_SETUP = FRONTEND / "tests" / "e2e" / "global-setup.ts"
PLAYWRIGHT_CONFIG = FRONTEND / "playwright.config.ts"
VITE_CONFIG = FRONTEND / "vite.config.ts"

# 形如 localhost:3000 / 127.0.0.1:8000 的字面量端口
HARDCODED_PORT_RE = re.compile(r"(localhost|127\.0\.0\.1):\d{2,5}")


def test_e2e_warmup_url_comes_from_resolved_config():
    """DEV-009：globalSetup 的预热地址必须来自已解析配置，不能写死端口。

    写死 localhost:3000 时，只要前端换了端口（E2E_FRONTEND_PORT），预热就打到该端口上
    恰好存在的另一个应用（实测：本机被另一个项目的 vite dev server 占用），本项目的
    首条用例于是与 dev-server 惰性编译竞争——正是 globalSetup 要消除的那类偶发失败。
    """
    body = GLOBAL_SETUP.read_text(encoding="utf-8")

    assert "config.projects[0].use.baseURL" in body, "预热地址应取自解析后的 use.baseURL"
    assert not HARDCODED_PORT_RE.search(body), "global-setup.ts 不应出现字面量 localhost:<port>"


def test_e2e_frontend_port_has_single_source():
    """playwright.config.ts 是前端端口的唯一来源，测试与预热共用 baseURL。"""
    body = PLAYWRIGHT_CONFIG.read_text(encoding="utf-8")

    assert "process.env.E2E_FRONTEND_PORT" in body, "前端端口应可被 E2E_FRONTEND_PORT 覆盖"
    assert "baseURL: `http://localhost:${PORT}`" in body, "baseURL 应由端口变量拼出"


def test_api_proxy_follows_e2e_backend_port():
    """DEV-009：/api 代理目标必须与 E2E 后端端口同源。

    代理写死 8000、而后端端口可由 E2E_BACKEND_PORT 覆盖时，偏移后端端口会让所有 /api
    请求打到空端口，整条 E2E 以与业务无关的原因失败（实测 9 条误报）。
    """
    body = VITE_CONFIG.read_text(encoding="utf-8")

    assert "process.env.E2E_BACKEND_PORT" in body, "代理目标应跟随 E2E_BACKEND_PORT"
    assert "target: `http://localhost:${BACKEND_PORT}`" in body, "代理目标应由端口变量拼出"
    assert "target: 'http://localhost:8000'" not in body, "代理目标不应保留写死的 8000"
