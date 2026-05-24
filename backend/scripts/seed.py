"""Seed data script: insert sample insurance products for development/testing"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.database import init_db, SessionLocal
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.models.benefit import Benefit


def seed():
    init_db()
    db = SessionLocal()

    products_data = [
        {
            "name": "平安e生保长期医疗险", "company": "平安健康", "type": "医疗险",
            "premium_min": 300, "premium_max": 800, "sum_insured_min": 200, "sum_insured_max": 400,
            "coverage_period": "1年", "payment_period": "1年",
            "source_url": "https://health.pingan.com/yishengbao/index.shtml",
            "disease_count": 120, "has_mild_coverage": False, "has_moderate_coverage": False, "has_multi_claim": False,
            "rule": {"min_age": 0, "max_age": 65, "job_class_limit": 4, "waiting_period_days": 30,
                     "has_insured_waiver": False, "has_insurer_waiver": False, "health_disclosure_count": 5},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "一般住院医疗", "benefit_amount": "200万", "payment_limit": "年限额200万"},
                {"benefit_type": "basic", "benefit_name": "重疾住院医疗", "benefit_amount": "400万", "payment_limit": "年限额400万"},
                {"benefit_type": "special", "benefit_name": "质子重离子", "benefit_amount": "100万", "payment_limit": "年限额100万"},
            ],
        },
        {
            "name": "众安尊享e生百万医疗险", "company": "众安保险", "type": "医疗险",
            "premium_min": 200, "premium_max": 600, "sum_insured_min": 300, "sum_insured_max": 600,
            "coverage_period": "1年", "payment_period": "1年",
            "source_url": "https://www.zhongan.com/product/zxes/index.html",
            "disease_count": 100, "has_mild_coverage": False, "has_moderate_coverage": False, "has_multi_claim": False,
            "rule": {"min_age": 0, "max_age": 70, "job_class_limit": 4, "waiting_period_days": 30,
                     "has_insured_waiver": False, "has_insurer_waiver": False, "health_disclosure_count": 4},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "一般住院医疗", "benefit_amount": "300万", "payment_limit": "年限额300万"},
                {"benefit_type": "basic", "benefit_name": "重疾住院医疗", "benefit_amount": "600万", "payment_limit": "年限额600万"},
            ],
        },
        {
            "name": "人保大护甲意外险", "company": "人保财险", "type": "意外险",
            "premium_min": 100, "premium_max": 300, "sum_insured_min": 30, "sum_insured_max": 100,
            "coverage_period": "1年", "payment_period": "1年",
            "source_url": "https://www.picc.com/html/znhl/cpzs/dhj/index.shtml",
            "disease_count": 0, "has_mild_coverage": False, "has_moderate_coverage": False, "has_multi_claim": False,
            "rule": {"min_age": 18, "max_age": 60, "job_class_limit": 3, "waiting_period_days": 0,
                     "has_insured_waiver": False, "has_insurer_waiver": False, "health_disclosure_count": 0},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "意外身故/伤残", "benefit_amount": "50万", "payment_limit": "单次事故50万"},
                {"benefit_type": "basic", "benefit_name": "意外医疗", "benefit_amount": "5万", "payment_limit": "年限额5万"},
                {"benefit_type": "special", "benefit_name": "猝死保障", "benefit_amount": "20万", "payment_limit": ""},
            ],
        },
        {
            "name": "太平洋小蜜蜂意外险", "company": "太平洋保险", "type": "意外险",
            "premium_min": 150, "premium_max": 350, "sum_insured_min": 50, "sum_insured_max": 100,
            "coverage_period": "1年", "payment_period": "1年",
            "source_url": "https://www.cpic.com.cn/product/ywx/",
            "disease_count": 0, "has_mild_coverage": False, "has_moderate_coverage": False, "has_multi_claim": False,
            "rule": {"min_age": 18, "max_age": 65, "job_class_limit": 3, "waiting_period_days": 0,
                     "has_insured_waiver": False, "has_insurer_waiver": False, "health_disclosure_count": 0},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "意外身故/伤残", "benefit_amount": "100万", "payment_limit": ""},
                {"benefit_type": "basic", "benefit_name": "意外医疗", "benefit_amount": "10万", "payment_limit": "年限额10万"},
            ],
        },
        {
            "name": "达尔文10号重疾险", "company": "信泰人寿", "type": "重疾险",
            "premium_min": 4000, "premium_max": 8000, "sum_insured_min": 30, "sum_insured_max": 80,
            "coverage_period": "终身", "payment_period": "30年",
            "source_url": "https://www.xintai.com/product/darwin10/",
            "disease_count": 180, "mild_disease_count": 50, "moderate_disease_count": 25,
            "has_mild_coverage": True, "has_moderate_coverage": True, "has_multi_claim": False,
            "rule": {"min_age": 0, "max_age": 55, "job_class_limit": 4, "waiting_period_days": 90,
                     "has_insured_waiver": True, "has_insurer_waiver": True, "health_disclosure_count": 8},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "重疾保险金", "benefit_amount": "100%基本保额", "payment_limit": "1次"},
                {"benefit_type": "basic", "benefit_name": "中症保险金", "benefit_amount": "60%基本保额", "payment_limit": "最多2次"},
                {"benefit_type": "basic", "benefit_name": "轻症保险金", "benefit_amount": "30%基本保额", "payment_limit": "最多3次"},
                {"benefit_type": "waiver", "benefit_name": "被保人豁免", "benefit_amount": "豁免后续保费", "payment_limit": ""},
            ],
        },
        {
            "name": "超级玛丽12号重疾险", "company": "和泰人寿", "type": "重疾险",
            "premium_min": 3500, "premium_max": 7000, "sum_insured_min": 30, "sum_insured_max": 70,
            "coverage_period": "终身", "payment_period": "30年",
            "source_url": "https://www.htlife.com/product/supermary12/",
            "disease_count": 190, "mild_disease_count": 45, "moderate_disease_count": 20,
            "has_mild_coverage": True, "has_moderate_coverage": True, "has_multi_claim": True,
            "rule": {"min_age": 0, "max_age": 50, "job_class_limit": 4, "waiting_period_days": 180,
                     "has_insured_waiver": True, "has_insurer_waiver": False, "health_disclosure_count": 10},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "重疾保险金", "benefit_amount": "100%基本保额", "payment_limit": "1次"},
                {"benefit_type": "basic", "benefit_name": "第二次重疾保险金", "benefit_amount": "120%基本保额", "payment_limit": "1次"},
                {"benefit_type": "basic", "benefit_name": "中症保险金", "benefit_amount": "60%基本保额", "payment_limit": "最多2次"},
                {"benefit_type": "basic", "benefit_name": "轻症保险金", "benefit_amount": "30%基本保额", "payment_limit": "最多3次"},
            ],
        },
        {
            "name": "华贵大麦定寿", "company": "华贵人寿", "type": "定期寿险",
            "premium_min": 800, "premium_max": 2000, "sum_insured_min": 50, "sum_insured_max": 200,
            "coverage_period": "至60岁", "payment_period": "30年",
            "source_url": "https://www.huaguilife.com/product/damai/",
            "disease_count": 0, "has_mild_coverage": False, "has_moderate_coverage": False, "has_multi_claim": False,
            "rule": {"min_age": 18, "max_age": 55, "job_class_limit": 3, "waiting_period_days": 90,
                     "has_insured_waiver": False, "has_insurer_waiver": False, "health_disclosure_count": 4},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "身故/全残保险金", "benefit_amount": "100%基本保额", "payment_limit": "1次"},
            ],
        },
        {
            "name": "阳光人寿防癌险", "company": "阳光人寿", "type": "防癌险",
            "premium_min": 2000, "premium_max": 5000, "sum_insured_min": 10, "sum_insured_max": 20,
            "coverage_period": "终身", "payment_period": "20年",
            "source_url": "https://www.sunshine-life.com/product/fangaixian/",
            "disease_count": 0, "has_mild_coverage": False, "has_moderate_coverage": False, "has_multi_claim": False,
            "rule": {"min_age": 45, "max_age": 70, "job_class_limit": 6, "waiting_period_days": 180,
                     "has_insured_waiver": True, "has_insurer_waiver": False, "health_disclosure_count": 6},
            "benefits": [
                {"benefit_type": "basic", "benefit_name": "恶性肿瘤保险金", "benefit_amount": "100%基本保额", "payment_limit": "1次"},
                {"benefit_type": "basic", "benefit_name": "原位癌保险金", "benefit_amount": "20%基本保额", "payment_limit": "1次"},
            ],
        },
    ]

    for pdata in products_data:
        rule_data = pdata.pop("rule")
        benefits_data = pdata.pop("benefits")

        product = Product(**pdata)
        db.add(product)
        db.flush()

        rule = Rule(product_id=product.id, **rule_data)
        db.add(rule)

        for bdata in benefits_data:
            benefit = Benefit(product_id=product.id, **bdata)
            db.add(benefit)

        db.flush()

    db.commit()
    db.close()
    print(f"Seeded {len(products_data)} products successfully.")


if __name__ == "__main__":
    seed()
