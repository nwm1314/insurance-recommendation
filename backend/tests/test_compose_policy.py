from pathlib import Path


COMPOSE_FILE = Path(__file__).resolve().parents[2] / "docker-compose.yml"


def test_frontend_publish_is_loopback_provable_to_application_agent():
    body = COMPOSE_FILE.read_text(encoding="utf-8")

    assert '"127.0.0.1:${FRONTEND_PORT:-18080}:80"' in body
    assert '"${FRONTEND_BIND:-127.0.0.1}:${FRONTEND_PORT:-18080}:80"' not in body


DOCKERFILE = COMPOSE_FILE.parent / "backend" / "Dockerfile"
ENTRYPOINT = COMPOSE_FILE.parent / "backend" / "entrypoint.sh"
ENV_EXAMPLE_FILE = COMPOSE_FILE.parent / ".env.example"
DEPLOYMENT_DOC = COMPOSE_FILE.parent / "docs" / "docker-deployment.md"


SECURITY_ENV_KEYS = (
    "APP_ENV: ${APP_ENV:-development}",
    "COOKIE_SECURE: ${COOKIE_SECURE:-false}",
    "COOKIE_SAMESITE: ${COOKIE_SAMESITE:-lax}",
    "TRUST_PROXY_HEADERS: ${TRUST_PROXY_HEADERS:-false}",
    "TRUSTED_PROXIES: ${TRUSTED_PROXIES:-}",
    "SECURITY_HEADERS: ${SECURITY_HEADERS:-true}",
    "HSTS_ENABLED: ${HSTS_ENABLED:-false}",
)


def test_backend_forwards_cookie_proxy_and_security_header_vars():
    body = COMPOSE_FILE.read_text(encoding="utf-8")
    backend_env = body.split("backend:", 1)[1].split("frontend:", 1)[0]
    for key in SECURITY_ENV_KEYS:
        assert key in backend_env


def test_backend_forwards_record_encryption_key():
    """OPEN-002（方案 3）：推荐记录加密密钥必须真的进入容器，且在两份部署清单里是硬性卡点。

    Compose 只把 environment: 段显式列出的变量注入容器——密钥只写在 .env、段里缺失，
    进程就读不到，含健康描述的推荐记录仍会明文落库（本轮核查发现的真实缺口）。
    文档清单同理：只在「推荐记录加密」章节提示、操作步骤里不出现，等于没有门禁。
    """
    body = COMPOSE_FILE.read_text(encoding="utf-8")
    backend_env = body.split("backend:", 1)[1].split("frontend:", 1)[0]
    assert "RECORD_ENCRYPTION_KEY: ${RECORD_ENCRYPTION_KEY:-}" in backend_env

    # .env.example 必须用大写变量名：小写名只被应用自身读取，compose 插值读不到。
    assert "RECORD_ENCRYPTION_KEY=" in ENV_EXAMPLE_FILE.read_text(encoding="utf-8")

    doc = DEPLOYMENT_DOC.read_text(encoding="utf-8")
    staging = doc.split("## 首次部署测试环境", 1)[1].split("## 更新测试环境", 1)[0]
    production = doc.split("## 生产部署", 1)[1].split("## 宿主机 Nginx 反代", 1)[0]
    for name, section in (("内测", staging), ("生产", production)):
        assert "RECORD_ENCRYPTION_KEY=" in section, f"{name}清单的 .env 段缺该密钥"
        assert "硬性卡点" in section, f"{name}清单缺启动后的明文落库检查步骤"
        assert "exit 1" in section, f"{name}清单的检查必须能让部署脚本失败，不能只是提示"


def test_backend_runs_migrations_before_starting_server():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT.read_text(encoding="utf-8")

    assert 'ENTRYPOINT ["sh", "/srv/backend/entrypoint.sh"]' in dockerfile
    assert "alembic upgrade head" in entrypoint
    assert "\ncd /srv\nexec \"$@\"" in entrypoint
    assert entrypoint.index("alembic upgrade head") < entrypoint.index("\ncd /srv\nexec \"$@\"")
    assert 'exec "$@"' in entrypoint
