import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(tempfile.gettempdir(), 'insurance_ssrf_pytest.db').replace(os.sep, '/')}",
)
os.environ.setdefault("DISABLE_SCHEDULER_IN_TESTS", "true")

try:
    os.remove(os.path.join(tempfile.gettempdir(), "insurance_ssrf_pytest.db"))
except OSError:
    pass

import pytest
from backend.app.crawler.scraper import validate_url_for_ssrf, SSRFError, open_url_checked, validate_redirect_chain


class TestSSRFLocalhost:
    def test_block_localhost(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://localhost/path")

    def test_block_localhost_https(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("https://localhost:8080/path")

    def test_block_localhost_with_port(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://localhost:3000/api/secret")


class TestSSRFIPAddressBlocks:
    def test_block_127_0_0_1(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://127.0.0.1/path")

    def test_block_127_1_1_1(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://127.1.1.1/")

    def test_block_10_private(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://10.0.0.1/internal")

    def test_block_172_16_private(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://172.16.0.1/admin")

    def test_block_192_168_private(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://192.168.1.1/router")

    def test_block_169_254_link_local(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://169.254.169.254/latest/meta-data")

    def test_block_0_0_0_0(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://0.0.0.0:8080/")


class TestSSRFCGNATAndReserved:
    def test_block_cgnat_100_64(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://100.64.0.1/internal")

    def test_block_cgnat_100_127(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://100.127.255.254/")

    def test_block_reserved_198_18(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://198.18.0.1/")

    def test_block_reserved_192_0_0(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://192.0.0.1/")

    def test_block_reserved_240_0(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://240.0.0.1/")

    def test_block_doc_test_networks(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://192.0.2.1/")
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://198.51.100.1/")
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://203.0.113.1/")


class TestSSRFIPv6:
    def test_block_ipv6_loopback(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://[::1]/")

    def test_block_ipv6_ula(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://[fc00::1]/")

    def test_block_ipv6_link_local(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://[fe80::1]/")

    def test_block_ipv4_mapped_ipv6_loopback(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://[::ffff:127.0.0.1]/")

    def test_block_ipv4_mapped_ipv6_private(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://[::ffff:10.0.0.1]/")

    def test_block_ipv4_compatible_ipv6_private(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://[::10.0.0.1]/")


class TestSSRFInvalidScheme:
    def test_block_ftp(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("ftp://example.com/file")

    def test_block_file_scheme(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("file:///etc/passwd")


class TestSSRFInvalidURL:
    def test_block_missing_hostname(self):
        with pytest.raises(SSRFError):
            validate_url_for_ssrf("http://")


class TestSSRFValidURLs:
    def test_allow_public_url(self):
        host = validate_url_for_ssrf("https://www.example.com/path/to/page")
        assert host == "www.example.com"

    def test_allow_public_url_with_port(self):
        host = validate_url_for_ssrf("https://www.example.com:8443/secure")
        assert host == "www.example.com"


class _RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/to-internal":
            self.send_response(302)
            self.send_header("Location", "http://10.0.0.1/secret")
            self.end_headers()
            return
        if self.path == "/chain":
            self.send_response(301)
            self.send_header("Location", "/final")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def local_server():
    server = HTTPServer(("127.0.0.1", 0), _RedirectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def allow_local_loopback(monkeypatch):
    monkeypatch.setenv("SSRF_ALLOWED_NETWORKS", "127.0.0.0/8")


class TestSSRFRedirects:
    def test_redirect_to_internal_blocked(self, local_server, allow_local_loopback):
        with pytest.raises(SSRFError):
            validate_redirect_chain(f"{local_server}/to-internal")

    def test_redirect_chain_ok(self, local_server, allow_local_loopback):
        final_url = validate_redirect_chain(f"{local_server}/chain")
        assert final_url.endswith("/final")

    def test_open_url_checked_follows_and_validates_each_hop(self, local_server, allow_local_loopback):
        final_url, response = open_url_checked(f"{local_server}/chain")
        with response:
            assert final_url.endswith("/final")
            assert response.status == 200

    def test_redirect_to_internal_blocked_via_open_url_checked(self, local_server, allow_local_loopback):
        with pytest.raises(SSRFError):
            open_url_checked(f"{local_server}/to-internal")

    def test_entry_url_still_blocked_without_allowlist(self, local_server):
        with pytest.raises(SSRFError):
            validate_redirect_chain(f"{local_server}/chain")


class TestSSRFRobots:
    def test_robots_url_goes_through_same_validation(self, local_server, allow_local_loopback):
        from backend.app.models.data_ingestion import SourcePage, SourcePlatform
        from backend.app.data_ingestion.fetchers.page_fetcher import assert_robots_allowed

        platform = SourcePlatform(name="local-test", platform_type="third_party", robots_url=f"{local_server}/robots.txt", rate_limit_seconds=0, is_active=True)
        page = SourcePage(platform_id=0, url="http://example.com/page", page_type="product", is_active=True)
        page.platform = platform
        try:
            assert_robots_allowed(page)
        except Exception:
            pytest.fail("robots fetch through local server should not raise SSRFError")

    def test_robots_url_blocked_when_robots_points_internal(self):
        from backend.app.data_ingestion.fetchers.page_fetcher import assert_robots_allowed
        from backend.app.models.data_ingestion import SourcePage, SourcePlatform

        platform = SourcePlatform(name="bad-robots", platform_type="third_party", robots_url="http://127.0.0.1/robots.txt", rate_limit_seconds=0, is_active=True)
        page = SourcePage(platform_id=0, url="http://example.com/page", page_type="product", is_active=True)
        page.platform = platform
        with pytest.raises(SSRFError):
            assert_robots_allowed(page)
