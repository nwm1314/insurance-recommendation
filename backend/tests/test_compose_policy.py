from pathlib import Path


COMPOSE_FILE = Path(__file__).resolve().parents[2] / "docker-compose.yml"


def test_frontend_publish_is_loopback_provable_to_application_agent():
    body = COMPOSE_FILE.read_text(encoding="utf-8")

    assert '"127.0.0.1:${FRONTEND_PORT:-18080}:80"' in body
    assert '"${FRONTEND_BIND:-127.0.0.1}:${FRONTEND_PORT:-18080}:80"' not in body


DOCKERFILE = COMPOSE_FILE.parent / "backend" / "Dockerfile"
ENTRYPOINT = COMPOSE_FILE.parent / "backend" / "entrypoint.sh"


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


def test_backend_runs_migrations_before_starting_server():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    entrypoint = ENTRYPOINT.read_text(encoding="utf-8")

    assert 'ENTRYPOINT ["sh", "/srv/backend/entrypoint.sh"]' in dockerfile
    assert "alembic upgrade head" in entrypoint
    assert "\ncd /srv\nexec \"$@\"" in entrypoint
    assert entrypoint.index("alembic upgrade head") < entrypoint.index("\ncd /srv\nexec \"$@\"")
    assert 'exec "$@"' in entrypoint
