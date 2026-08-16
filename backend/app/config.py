import ipaddress
import yaml
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"
OPENAI_CHAT_COMPLETIONS_SUFFIX = "/chat/completions"


def normalize_llm_base_url(value: str) -> str:
    """Normalize a provider URL before handing it to the OpenAI SDK.

    OpenAI-compatible clients append ``/chat/completions`` themselves. Some
    deployment consoles incorrectly store the full operation URL, which would
    otherwise produce a doubled path and a provider 404 response.
    """
    raw = value.strip()
    try:
        parsed = urlsplit(raw)
        parsed.port
    except (AttributeError, ValueError):
        return raw
    if not parsed.scheme or not parsed.hostname:
        return raw
    path = parsed.path.rstrip("/")
    suffix = OPENAI_CHAT_COMPLETIONS_SUFFIX
    if path.lower().endswith(suffix):
        path = path[: -len(suffix)].rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def safe_llm_base_url(value: str) -> str:
    """Return an operator-safe endpoint for logs (strip credentials/query)."""
    try:
        parsed = urlsplit(normalize_llm_base_url(value))
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



def validate_origin_format(origin: str) -> str:
    origin = origin.strip()
    if not origin:
        raise ValueError("CORS origin cannot be empty")
    if origin == "*":
        return origin
    try:
        parsed = urlsplit(origin)
    except Exception as exc:
        raise ValueError(f"Invalid CORS origin format: {origin!r}") from exc
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"CORS origin must use http/https scheme: {origin!r}")
    if not parsed.hostname:
        raise ValueError(f"CORS origin missing hostname: {origin!r}")
    if parsed.path and parsed.path != "/":
        raise ValueError(f"CORS origin must not contain a path: {origin!r}")
    if parsed.query:
        raise ValueError(f"CORS origin must not contain a query string: {origin!r}")
    if parsed.fragment:
        raise ValueError(f"CORS origin must not contain a fragment: {origin!r}")
    return origin


def ensure_no_wildcard_with_credentials(origins, allow_credentials: bool) -> None:
    """Fail-closed guard: a wildcard origin can never be combined with credentials.

    Browsers reject `Access-Control-Allow-Origin: *` together with
    `Access-Control-Allow-Credentials: true`; Starlette would emit both,
    silently creating a credential-bearing open CORS policy. Every caller
    (e.g. the CORSMiddleware in main.py) must pass through this check.
    """
    if allow_credentials and "*" in [o.strip() for o in origins]:
        raise ValueError(
            "CORS wildcard '*' cannot be used with allow_credentials=True; "
            "configure explicit origins (CORS_ALLOW_ORIGINS)"
        )

ALLOWED_APP_ENVS = ("development", "test", "staging", "production")
ALLOWED_SAMESITE_VALUES = ("lax", "strict", "none")


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

    # Runtime environment. In "production" the auth cookies must be Secure
    # (fail-fast otherwise) and HSTS is the only place it is honored.
    app_env: str = "development"
    # Cookie settings for http-only token storage. cookie_secure defaults to
    # None so it can be inferred from app_env (production -> True); an explicit
    # False under APP_ENV=production is rejected at startup.
    cookie_secure: bool | None = None
    cookie_samesite: str = "lax"
    # Proxy trust boundary: X-Forwarded-For is parsed only when
    # trust_proxy_headers is on AND the direct peer is inside trusted_proxies.
    trust_proxy_headers: bool = False
    trusted_proxies: str = ""
    # Baseline security response headers; HSTS is only sent in production.
    security_headers: bool = True
    hsts_enabled: bool = False

    # ---- Product pool maintenance (aggregator-primary strategy) ----
    # Seed the 165-product demo catalog on an empty database. The production
    # product pool is built from crawled, reviewed aggregator data, so seeding
    # demo products defaults to off; E2E and local demos set it to true.
    seed_demo_products: bool = False
    # Auto-publish crawled drafts that clear the confidence and completeness
    # gate; anything else waits in the manual review queue.
    auto_publish_enabled: bool = True
    auto_publish_confidence: float = 0.8
    # Discover new product detail URLs from aggregator listing pages and
    # register crawl jobs for them.
    discovery_enabled: bool = True
    discovery_max_new_per_source: int = 20
    crawl_interval_minutes: int = 720
    # Official-site cross-verification (L2 existence check) and third-party
    # review matching run as part of pool maintenance; results are annotations
    # only and never gate availability.
    official_verification_enabled: bool = True

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, value: str) -> str:
        value = (value or "development").strip().lower()
        if value not in ALLOWED_APP_ENVS:
            raise ValueError(f"app_env must be one of {', '.join(ALLOWED_APP_ENVS)}")
        return value

    @field_validator("cookie_samesite")
    @classmethod
    def validate_cookie_samesite(cls, value: str) -> str:
        value = (value or "lax").strip().lower()
        if value not in ALLOWED_SAMESITE_VALUES:
            raise ValueError(f"cookie_samesite must be one of {', '.join(ALLOWED_SAMESITE_VALUES)}")
        return value

    @field_validator("trusted_proxies")
    @classmethod
    def validate_trusted_proxies(cls, value: str) -> str:
        value = (value or "").strip()
        for entry in (e.strip() for e in value.split(",") if e.strip()):
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError as exc:
                raise ValueError(f"Invalid trusted proxy entry {entry!r} (expected IP or CIDR)") from exc
        return value

    @model_validator(mode="after")
    def _resolve_cookie_secure(self):
        if self.cookie_secure is None:
            self.cookie_secure = self.app_env == "production"
        if self.app_env == "production" and not self.cookie_secure:
            raise ValueError("cookie_secure must be True when APP_ENV=production")
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("cookie_samesite='none' requires cookie_secure=True")
        return self

    @model_validator(mode="after")
    def _reject_wildcard_origin_in_production(self):
        if self.app_env == "production" and "*" in self.parsed_cors_origins:
            raise ValueError(
                "Wildcard CORS origin '*' is not allowed when APP_ENV=production; "
                "configure explicit origins (CORS_ALLOW_ORIGINS)"
            )
        return self


    @field_validator("cors_allow_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        origins = [o.strip() for o in value.split(",") if o.strip()]
        if not origins:
            raise ValueError("At least one CORS origin must be configured")
        for origin in origins:
            validate_origin_format(origin)
        return value

    @property
    def parsed_cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def parsed_trusted_proxies(self) -> list:
        networks = []
        for entry in (e.strip() for e in self.trusted_proxies.split(",") if e.strip()):
            try:
                networks.append(ipaddress.ip_network(entry, strict=False))
            except ValueError:
                continue
        return networks

settings = Settings()

# Load adjustable params from YAML
SCORING_WEIGHTS = _load_yaml("scoring_weights.yaml")
BUDGET_RULES = _load_yaml("budget_rules.yaml")
