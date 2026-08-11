import hashlib
import ipaddress
import os
import socket
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

_USER_AGENT = "insurance-recommendation-bot"

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::/96"),
    ipaddress.ip_network("::ffff:0:0/96"),
    ipaddress.ip_network("100::/64"),
    ipaddress.ip_network("2001:db8::/32"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
]


def _allowed_networks() -> list[ipaddress._BaseNetwork]:
    raw = os.environ.get("SSRF_ALLOWED_NETWORKS", "").strip()
    networks = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            networks.append(ipaddress.ip_network(part))
        except ValueError:
            pass
    return networks


class SSRFError(ValueError):
    """Raised when a URL resolves to a blocked (private/internal) address."""
    pass


def _is_blocked(ip: ipaddress._BaseAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if any(ip in network for network in _allowed_networks()):
        return False
    return any(ip in network for network in _BLOCKED_NETWORKS)


def validate_url_for_ssrf(url: str) -> str:
    """Validate that a URL does not target private or internal network addresses.

    Returns the resolved hostname on success; raises SSRFError on violation.
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise SSRFError(f"Invalid URL format: {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise SSRFError(f"Unsupported URL scheme: {scheme!r}")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL missing hostname")

    hostname_lower = hostname.lower()
    if hostname_lower in ("localhost", "0.0.0.0", "[::1]", "[::]"):
        raise SSRFError("Access to localhost/loopback is blocked")

    try:
        literal_ip = ipaddress.ip_address(hostname_lower)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        if _is_blocked(literal_ip):
            raise SSRFError("Access to internal/private network addresses is blocked")
        return hostname

    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise SSRFError(f"Could not resolve hostname: {hostname}") from exc

    if not resolved:
        raise SSRFError(f"Could not resolve hostname: {hostname}")

    for _family, _type, _proto, _canonname, sockaddr in resolved:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if _is_blocked(ip):
            raise SSRFError("Access to internal/private network addresses is blocked")

    return hostname


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_url_checked(url: str, max_redirects: int = 5, timeout: float = 10.0) -> tuple[str, object]:
    """Follow redirects manually, validating every hop with validate_url_for_ssrf.

    Returns (final_url, response). The response body is never logged by callers.
    """
    current = url
    opener = build_opener(_NoRedirect)
    seen: set[str] = set()
    for _ in range(max_redirects + 1):
        validate_url_for_ssrf(current)
        seen.add(current)
        request = Request(current, headers={"User-Agent": _USER_AGENT})
        try:
            return current, opener.open(request, timeout=timeout)
        except HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                location = exc.headers.get("Location")
                exc.close()
                if not location:
                    raise SSRFError(f"Redirect from {current} missing Location header")
                current = urljoin(current, location)
                if current in seen:
                    raise SSRFError(f"Redirect loop detected at {current}")
                continue
            return current, exc
    raise SSRFError(f"Too many redirects (>{max_redirects}) resolving {url}")


def validate_redirect_chain(url: str, max_redirects: int = 5) -> str:
    """Resolve a redirect chain step by step; raise SSRFError on any unsafe hop.

    Returns the final URL after at most max_redirects hops.
    """
    final_url, response = open_url_checked(url, max_redirects=max_redirects)
    response.close()
    return final_url


def fetch_page_text(url: str, timeout: int = 30000) -> tuple[str, str, int | None]:
    """Fetch page using Playwright and return plain text, raw HTML and HTTP status.

    Validates the URL to prevent SSRF attacks before accessing it. The HTTP
    status is captured so that 404/410 responses can be classified as off-shelf
    instead of silently treated as successful 200s.
    """
    validate_url_for_ssrf(url)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        response = page.goto(url, timeout=timeout)
        if response is not None:
            request = response.request
            while request is not None:
                validate_url_for_ssrf(request.url)
                request = request.redirected_from
        page.wait_for_load_state("networkidle")
        if page.url != url:
            validate_url_for_ssrf(page.url)
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        browser.close()
        return text, html, response.status if response is not None else None


def compute_md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def detect_off_shelf(text: str) -> bool:
    """Detect if page contains off-shelf keywords"""
    keywords = ["已停售", "暂不可投保", "已下架", "停止销售", "不在售"]
    return any(kw in text for kw in keywords)
