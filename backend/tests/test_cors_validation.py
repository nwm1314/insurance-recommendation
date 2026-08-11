import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_cors_pytest.db').replace(os.sep, '/')}")
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_cors_pytest.db"))
except OSError:
    pass

import pytest
from pydantic import ValidationError
from backend.app.config import (
    Settings,
    ensure_no_wildcard_with_credentials,
    validate_origin_format,
)


class TestCORSValidOrigins:
    def test_valid_http_localhost(self):
        assert validate_origin_format("http://localhost") == "http://localhost"

    def test_valid_https_localhost_with_port(self):
        assert validate_origin_format("http://localhost:3000") == "http://localhost:3000"

    def test_valid_https_domain(self):
        assert validate_origin_format("https://example.com") == "https://example.com"

    def test_valid_https_domain_with_port(self):
        assert validate_origin_format("https://app.example.com:8443") == "https://app.example.com:8443"

    def test_valid_wildcard(self):
        assert validate_origin_format("*") == "*"


class TestCORSInvalidOrigins:
    def test_reject_ftp_scheme(self):
        with pytest.raises(ValueError, match="http/https"):
            validate_origin_format("ftp://example.com")

    def test_reject_no_scheme(self):
        with pytest.raises(ValueError, match="http/https"):
            validate_origin_format("example.com")

    def test_reject_invalid_scheme(self):
        with pytest.raises(ValueError, match="http/https"):
            validate_origin_format("javascript:alert(1)")

    def test_reject_with_path(self):
        with pytest.raises(ValueError, match="path"):
            validate_origin_format("http://localhost:3000/admin")

    def test_reject_with_query(self):
        with pytest.raises(ValueError, match="query"):
            validate_origin_format("http://localhost:3000?token=abc")

    def test_reject_with_fragment(self):
        with pytest.raises(ValueError, match="fragment"):
            validate_origin_format("http://localhost:3000#section")

    def test_reject_empty(self):
        with pytest.raises(ValueError, match="empty"):
            validate_origin_format("")


class TestCORSWildcardPolicy:
    def test_wildcard_format_validation_accepted(self):
        assert validate_origin_format("*") == "*"

    def test_development_allows_wildcard(self):
        assert Settings(app_env="development", cors_allow_origins="*").parsed_cors_origins == ["*"]

    def test_production_rejects_wildcard(self):
        with pytest.raises(ValidationError, match="Wildcard CORS origin"):
            Settings(app_env="production", cors_allow_origins="*")

    def test_production_accepts_explicit_origins(self):
        s = Settings(app_env="production", cors_allow_origins="https://example.com")
        assert s.parsed_cors_origins == ["https://example.com"]

    def test_production_rejects_wildcard_mixed_with_explicit(self):
        with pytest.raises(ValidationError, match="Wildcard CORS origin"):
            Settings(app_env="production", cors_allow_origins="https://example.com,*")


class TestCORSWildcardCredentialsConflict:
    def test_wildcard_with_credentials_rejected(self):
        with pytest.raises(ValueError, match="allow_credentials"):
            ensure_no_wildcard_with_credentials(["*"], allow_credentials=True)

    def test_wildcard_without_credentials_allowed(self):
        ensure_no_wildcard_with_credentials(["*"], allow_credentials=False)

    def test_explicit_origins_with_credentials_allowed(self):
        ensure_no_wildcard_with_credentials(
            ["http://localhost:3000", "https://example.com"], allow_credentials=True
        )

    def test_mixed_wildcard_with_credentials_rejected(self):
        with pytest.raises(ValueError, match="allow_credentials"):
            ensure_no_wildcard_with_credentials(
                ["http://localhost:3000", "*"], allow_credentials=True
            )

    def test_empty_origins_with_credentials_allowed(self):
        ensure_no_wildcard_with_credentials([], allow_credentials=True)


class TestSecurityConfig:
    def test_production_forces_secure_cookie(self):
        assert Settings(app_env="production").cookie_secure is True

    def test_production_rejects_explicit_insecure_cookie(self):
        with pytest.raises(ValidationError, match="cookie_secure"):
            Settings(app_env="production", cookie_secure=False)

    def test_development_cookie_inferred_insecure(self):
        assert Settings(app_env="development").cookie_secure is False

    def test_explicit_secure_cookie_kept_in_development(self):
        assert Settings(app_env="development", cookie_secure=True).cookie_secure is True

    def test_samesite_none_requires_secure(self):
        with pytest.raises(ValidationError, match="cookie_secure"):
            Settings(cookie_samesite="none")

    def test_samesite_strict_accepted(self):
        assert Settings(cookie_samesite="strict", cookie_secure=True).cookie_samesite == "strict"

    def test_invalid_samesite_rejected(self):
        with pytest.raises(ValidationError, match="cookie_samesite"):
            Settings(cookie_samesite="banana")

    def test_invalid_environment_rejected(self):
        with pytest.raises(ValidationError, match="app_env"):
            Settings(app_env="banana")

    def test_invalid_trusted_proxy_rejected(self):
        with pytest.raises(ValidationError, match="trusted proxy"):
            Settings(trusted_proxies="not-an-ip")

    def test_trusted_proxies_cidr_and_ip_accepted(self):
        s = Settings(trusted_proxies="127.0.0.1,10.0.0.0/8")
        assert len(s.parsed_trusted_proxies) == 2
