"""产品来源链接策略回归（结果页产品链接 404/403 修复）。

历史缺陷：seed 用「公司域名 + 编造的产品路径」拼接 source_url，且 8 个公司
域名本身无法解析，导致结果页链接大面积 404/403。策略改为：演示目录的
source_url 只指向经过验证的公司官网首页，不编造深层路径。
"""
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.scripts.seed import COMPANY_TIERS, COMPANY_URLS, make_accident, make_annuity, make_anti_cancer, make_critical, make_life, make_medical


def test_all_company_urls_are_https_homepages():
    assert COMPANY_URLS, "COMPANY_URLS 不应为空"
    for company, url in COMPANY_URLS.items():
        parsed = urlparse(url)
        assert parsed.scheme == "https", f"{company} 官网必须 https: {url}"
        assert parsed.path in ("", "/"), f"{company} 官网 URL 只能是首页，不得带路径: {url}"
        assert not parsed.query and not parsed.fragment, f"{company} 官网 URL 不得带查询串/片段: {url}"


def test_every_seed_company_has_official_url():
    missing = set(COMPANY_TIERS) - set(COMPANY_URLS)
    assert not missing, f"seed 公司缺少官网映射: {missing}"


def test_make_helpers_never_fabricate_product_paths():
    makers = [
        (make_medical, ("1年", "fake-slug/")),
        (make_critical, ("fake-slug/",)),
        (make_accident, ("fake-slug/",)),
        (make_life, ("fake-slug/",)),
        (make_anti_cancer, ("fake-slug/",)),
        (make_annuity, ("fake-slug/",)),
    ]
    for maker, extra_args in makers:
        product = maker("测试产品", "中国平安", 100, 200, 10, 100, *extra_args)
        assert product["source_url"] == COMPANY_URLS["中国平安"], (
            f"{maker.__name__} 不得拼接编造的产品路径: {product['source_url']}"
        )
