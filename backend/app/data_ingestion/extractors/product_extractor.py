from bs4 import BeautifulSoup

from backend.app.config import settings
from backend.app.crawler.llm_extractor import extract_product
from backend.app.data_ingestion.validators.product_schema import normalize_and_validate_product


def extract_product_data(text: str, html: str | None, url: str) -> tuple[dict, float, str]:
    if settings.llm_api_key:
        extracted = extract_product(text)
        if extracted:
            extracted["source_url"] = url
            normalized, confidence = normalize_and_validate_product(extracted)
            return normalized, confidence, "llm"

    fallback = _heuristic_extract(text, html, url)
    normalized, confidence = normalize_and_validate_product(fallback, base_confidence=0.35)
    return normalized, confidence, "heuristic"


def _heuristic_extract(text: str, html: str | None, url: str) -> dict:
    name = "待审核产品"
    if html:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("h1") or soup.find("title")
        if title and title.get_text(strip=True):
            name = title.get_text(strip=True)[:120]
    elif text:
        name = text.splitlines()[0][:120]

    return {
        "name": name,
        "company": "待审核",
        "type": "医疗险",
        "premium_min": 0,
        "premium_max": 0,
        "sum_insured_min": 0,
        "sum_insured_max": 0,
        "coverage_period": "待审核",
        "payment_period": "待审核",
        "source_url": url,
        "disease_count": 0,
        "mild_disease_count": 0,
        "moderate_disease_count": 0,
        "has_mild_coverage": False,
        "has_moderate_coverage": False,
        "has_multi_claim": False,
        "min_age": 0,
        "max_age": 100,
        "job_class_limit": 6,
        "waiting_period_days": 90,
        "has_insured_waiver": False,
        "has_insurer_waiver": False,
        "health_disclosure_count": 0,
        "health_requirements": [],
        "benefits": [],
    }
