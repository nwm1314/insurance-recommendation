import hashlib
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup


def fetch_page_text(url: str, timeout: int = 30000) -> tuple[str, str]:
    """Fetch page using Playwright and return plain text + raw HTML"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=timeout)
        page.wait_for_load_state("networkidle")
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        browser.close()
        return text, html


def compute_md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def detect_off_shelf(text: str) -> bool:
    """Detect if page contains off-shelf keywords"""
    keywords = ["已停售", "暂不可投保", "已下架", "停止销售", "不在售"]
    return any(kw in text for kw in keywords)
