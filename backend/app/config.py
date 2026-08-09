import os
import yaml
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_yaml(filename: str) -> dict:
    path = BASE_DIR / "config" / filename
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

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
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_max_retries: int = 3
    llm_connect_timeout: float = 3.0
    llm_read_timeout: float = 30.0

    rate_limit_ip_per_minute: int = 120
    rate_limit_user_per_minute: int = 30
    rate_limit_user_per_day: int = 300

settings = Settings()

# Load adjustable params from YAML
SCORING_WEIGHTS = _load_yaml("scoring_weights.yaml")
BUDGET_RULES = _load_yaml("budget_rules.yaml")
