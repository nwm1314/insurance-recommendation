"""Official company homepages, used to classify a product's source.

Why this lives in the application layer: `api.recommend` needs it to decide
whether a product's `source_url` points at the insurer's own site (official) or
at an aggregator page. It used to be imported from `backend/scripts/seed.py`,
which made the API depend on a CLI script — the layering inversion recorded as
REC-005. Moving the constant here removes that dependency; `scripts/seed.py`
re-exports it so existing scripts keep working.

All entries were verified reachable (HTTP 200) on 2026-08-16. They are
homepages only: demo data has no real product detail pages, so `source_url`
must never be assembled by appending a guessed path — a fabricated path is a
404 or 403 on the insurer's site.
"""

COMPANY_URLS: dict[str, str] = {
    "中国平安": "https://www.pingan.com/", "平安人寿": "https://life.pingan.com/",
    "平安健康": "https://health.pingan.com/", "平安财险": "https://property.pingan.com/",
    "中国人寿": "https://www.e-chinalife.com/", "太平洋保险": "https://www.cpic.com.cn/",
    "太平洋人寿": "https://www.cpic.com.cn/", "太保寿险": "https://www.cpic.com.cn/",
    "人保财险": "https://www.picc.com/", "人保健康": "https://www.picchealth.com/",
    "人保寿险": "https://www.picclife.com/", "泰康人寿": "https://www.taikang.com/",
    "泰康在线": "https://www.tk.cn/", "新华保险": "https://www.newchinalife.com/",
    "阳光人寿": "https://life.sinosig.com/",
    "同方全球人寿": "https://www.aegonthtf.com/",
    "中意人寿": "https://www.generalichina.com/",
    "复星联合健康": "https://www.fosun-uhi.com/",
    "光大永明": "https://www.sunlife-everbright.com/",
    "工银安盛": "https://www.icbc-axa.com/",
    "招商信诺": "https://www.cignacmb.com/",
    "安盛天平": "https://www.axa.cn/",
    "众安保险": "https://www.zhongan.com/",
    "瑞泰人寿": "https://www.oldmutual-chnenergy.com/",
    "和泰人寿": "https://www.htlife.com/",
    "华贵人寿": "https://www.huaguilife.cn/",
    "信泰人寿": "https://www.xintai.com/",
    "国富人寿": "https://www.e-guofu.com/",
}
