"""REC-005 回归：公司官网常量必须位于应用层。

历史问题：`api/recommend.py` 通过 `from backend.scripts.seed import COMPANY_URLS`
反向依赖 CLI 脚本，脚本层一改就可能打断 API。常量已上移到
`backend/app/catalog_sources.py`，seed.py 只做重新导出。

这两个用例把方向钉住：应用层不得再 import scripts；重新导出保持同一对象，
既有 `scripts/fix_product_source_urls.py` 无需改动。
"""

import inspect
import pathlib

from backend.app import catalog_sources
from backend.app.api import recommend as recommend_api
from backend.scripts import seed as seed_script


def test_recommend_api_does_not_import_scripts_layer():
    source = inspect.getsource(recommend_api)
    assert "backend.scripts" not in source, (
        "api layer must not import backend.scripts; keep shared constants in backend.app"
    )


def test_catalog_sources_module_does_not_import_api_or_scripts():
    path = pathlib.Path(catalog_sources.__file__)
    source = path.read_text(encoding="utf-8")
    assert "backend.app.api" not in source
    assert "backend.scripts" not in source


def test_seed_script_reexports_the_application_constant():
    assert seed_script.COMPANY_URLS is catalog_sources.COMPANY_URLS


def test_company_urls_are_https_homepages():
    assert catalog_sources.COMPANY_URLS, "company URL map must not be empty"
    for company, url in catalog_sources.COMPANY_URLS.items():
        assert company.strip() == company and company, f"company name not normalised: {company!r}"
        assert url.startswith("https://"), f"{company} must use https, got {url!r}"
        assert url.endswith("/"), f"{company} should point at a site root, got {url!r}"
