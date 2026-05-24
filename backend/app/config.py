import os
import yaml
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_yaml(filename: str) -> dict:
    path = BASE_DIR / "config" / filename
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class Settings(BaseSettings):
    database_url: str = "sqlite:///data/insurance.db"
    redis_url: str = "redis://localhost:6379"

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_max_retries: int = 3
    llm_connect_timeout: float = 3.0
    llm_read_timeout: float = 30.0

    rate_limit_ip_per_minute: int = 10
    rate_limit_user_per_minute: int = 3
    rate_limit_user_per_day: int = 50

    class Config:
        env_file = ".env"


settings = Settings()

# Load adjustable params from YAML
SCORING_WEIGHTS = _load_yaml("scoring_weights.yaml")
BUDGET_RULES = _load_yaml("budget_rules.yaml")
