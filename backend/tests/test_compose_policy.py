from pathlib import Path


COMPOSE_FILE = Path(__file__).resolve().parents[2] / "docker-compose.yml"


def test_frontend_publish_is_loopback_provable_to_application_agent():
    body = COMPOSE_FILE.read_text(encoding="utf-8")

    assert '"127.0.0.1:${FRONTEND_PORT:-18080}:80"' in body
    assert '"${FRONTEND_BIND:-127.0.0.1}:${FRONTEND_PORT:-18080}:80"' not in body
