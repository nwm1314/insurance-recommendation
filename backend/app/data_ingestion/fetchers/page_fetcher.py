import time
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from backend.app.crawler.scraper import SSRFError, fetch_page_text, open_url_checked
from backend.app.models.data_ingestion import SourcePage
from backend.app.time import utc_now


@dataclass
class FetchResult:
    text: str
    html: str | None
    http_status: int | None = None


class RobotsBlockedError(Exception):
    pass


def _robots_url_for(page: SourcePage) -> str:
    if page.platform and page.platform.robots_url:
        return page.platform.robots_url
    parsed = urlparse(page.url)
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def assert_robots_allowed(page: SourcePage, user_agent: str = "insurance-recommendation-bot") -> None:
    parser = RobotFileParser()
    robots_url = _robots_url_for(page)
    try:
        final_url, response = open_url_checked(robots_url, timeout=5)
        with response:
            lines = [line.decode("utf-8", errors="ignore") for line in response.readlines()]
    except SSRFError:
        raise
    except Exception:
        # robots.txt unreachable is treated as unknown, not as a hard block.
        return
    parser.set_url(final_url)
    parser.parse(lines)
    if not parser.can_fetch(user_agent, page.url):
        raise RobotsBlockedError(f"robots.txt disallows fetching {page.url}")


def fetch_source_page(page: SourcePage, retries: int = 2, timeout_ms: int = 20000) -> FetchResult:
    assert_robots_allowed(page)
    delay = max(page.platform.rate_limit_seconds if page.platform else 0, 0)
    if delay and page.last_crawled_at:
        elapsed = (utc_now() - page.last_crawled_at).total_seconds()
        if elapsed < delay:
            time.sleep(delay - elapsed)
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        if delay and attempt > 0:
            time.sleep(delay)
        try:
            text, html, http_status = fetch_page_text(page.url, timeout=timeout_ms)
            if not text and http_status not in (404, 410):
                raise ValueError("empty page text")
            return FetchResult(text=text[:12000], html=html, http_status=http_status)
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"fetch failed after {retries + 1} attempts: {last_error}")
