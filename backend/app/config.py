import yaml
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"


def safe_llm_base_url(value: str) -> str:
    """Return an operator-safe endpoint for logs (strip credentials/query)."""
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except (AttributeError, ValueError):
        return "<invalid>"
    if not parsed.scheme or not parsed.hostname:
        return "<invalid>"
    netloc = parsed.hostname
    if port:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))


def _load_yaml(filename: str) -> dict:
    path = BASE_DIR / "config" / filename
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class Settings(BaseSettings):
    # Resolve the repository .env independently of the process working
    # directory. The manual runbook starts Uvicorn from backend/, while Docker
    # injects the same values through Compose.
    model_config = SettingsConfigDict(env_file=ENV_FILE)

    database_url: str = "sqlite:///data/insurance.db"
    redis_url: str = "redis://localhost:6379"
    cors_allow_origins: str = "http://localhost,http://localhost:3000,http://127.0.0.1:3000"
    jwt_secret_key: str = "change_me_before_deploy"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    first_admin_email: str = "admin@example.com"
    first_admin_password: str = ""
    disable_scheduler_in_tests: bool = False
    scoring_weights_fail_fast: bool = False

    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-v4-flash"
    llm_max_retries: int = 3
    # Bound structured responses so DeepSeek V4 thinking cannot consume the
    # entire request budget before returning JSON content.
    llm_max_tokens: int = 2048
    llm_connect_timeout: float = 3.0
    llm_read_timeout: float = 90.0

    rate_limit_ip_per_minute: int = 120
    rate_limit_user_per_minute: int = 30
    rate_limit_user_per_day: int = 300

settings = Settings()

# Load adjustable params from YAML
SCORING_WEIGHTS = _load_yaml("scoring_weights.yaml")
BUDGET_RULES = _load_yaml("budget_rules.yaml")
