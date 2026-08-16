"""Seed script: 100+ insurance products from 23 companies, 3 tiers, 7 insurance types.

Data sources: huize.com, kaixinbao.com, zhongmin.cn, health.pingan.com, cpic.com.cn
Verified products marked with source URL; estimated products use company homepage as reference.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.database import init_db, SessionLocal
from backend.app.models.product import Product
from backend.app.models.rule import Rule
from backend.app.models.benefit import Benefit

COMPANY_TIERS = {
    # Tier 1: 传统老牌大厂
    "中国平安": 1, "平安人寿": 1, "平安健康": 2, "平安财险": 1,
    "中国人寿": 1, "太平洋保险": 1, "太平洋人寿": 1, "太保寿险": 1,
    "人保财险": 1, "人保健康": 1, "人保寿险": 1,
    "泰康人寿": 1, "泰康在线": 1, "新华保险": 1,
    "阳光人寿": 1,
    # Tier 2: 优质合资/特色险企
    "同方全球人寿": 2, "中意人寿": 2, "复星联合健康": 2,
    "光大永明": 2, "工银安盛": 2, "招商信诺": 2, "安盛天平": 2,
    # Tier 3: 互联网定制/高性价比
    "众安保险": 3, "瑞泰人寿": 3, "和泰人寿": 3, "华贵人寿": 3,
    "信泰人寿": 3, "国富人寿": 3,
}

# 官网域名均于 2026-08-16 逐一实测可达（HTTP 200）。
# 演示数据没有真实的产品详情页，source_url 只指向公司官网首页，
# 不得再拼接编造的产品路径（假路径会被官网返回 404/403）。
COMPANY_URLS = {
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


def make_medical(name, company, prem_min, prem_max, si_min, si_max, coverage, url_extra,
                 age_min=0, age_max=65, job_limit=4, wait=90, hd_count=5,
                 benefits=None, **kwargs):
    return {
        "name": name, "company": company, "type": "医疗险",
        "premium_min": prem_min, "premium_max": prem_max,
        "sum_insured_min": si_min, "sum_insured_max": si_max,
        "coverage_period": coverage, "payment_period": "1年",
        # url_extra 保留仅为兼容调用点；演示数据不编造产品路径，链接指向公司官网首页
        "source_url": COMPANY_URLS.get(company, ""),
        "disease_count": kwargs.get("disease_count", 120),
        "has_mild_coverage": kwargs.get("has_mild_coverage", False),
        "has_moderate_coverage": kwargs.get("has_moderate_coverage", False),
        "has_multi_claim": kwargs.get("has_multi_claim", False),
        "rule": {"min_age": age_min, "max_age": age_max, "job_class_limit": job_limit,
                 "waiting_period_days": wait,
                 "has_insured_waiver": kwargs.get("has_insured_waiver", False),
                 "has_insurer_waiver": kwargs.get("has_insurer_waiver", False),
                 "health_disclosure_count": hd_count},
        "benefits": benefits or [
            {"benefit_type": "basic", "benefit_name": "一般住院医疗", "benefit_amount": f"{si_min}万", "payment_limit": f"年限额{si_min}万"},
            {"benefit_type": "basic", "benefit_name": "重疾住院医疗", "benefit_amount": f"{si_max}万", "payment_limit": f"年限额{si_max}万"},
        ],
    }


def make_critical(name, company, prem_min, prem_max, si_min, si_max,
                  disease_count=180, mild_count=40, mod_count=20,
                  has_mild=True, has_mod=True, has_multi=False,
                  age_min=0, age_max=55, job_limit=4, wait=90, hd_count=6,
                  has_iw=True, has_irw=False, url_extra="",
                  benefits=None, **kwargs):
    return {
        "name": name, "company": company, "type": "重疾险",
        "premium_min": prem_min, "premium_max": prem_max,
        "sum_insured_min": si_min, "sum_insured_max": si_max,
        "coverage_period": kwargs.get("coverage_period", "终身"),
        "payment_period": kwargs.get("payment_period", "20年"),
        # url_extra 保留仅为兼容调用点；演示数据不编造产品路径，链接指向公司官网首页
        "source_url": COMPANY_URLS.get(company, ""),
        "disease_count": disease_count, "mild_disease_count": mild_count,
        "moderate_disease_count": mod_count,
        "has_mild_coverage": has_mild, "has_moderate_coverage": has_mod,
        "has_multi_claim": has_multi,
        "rule": {"min_age": age_min, "max_age": age_max, "job_class_limit": job_limit,
                 "waiting_period_days": wait,
                 "has_insured_waiver": has_iw, "has_insurer_waiver": has_irw,
                 "health_disclosure_count": hd_count},
        "benefits": benefits or [
            {"benefit_type": "basic", "benefit_name": f"重疾保险金（{disease_count}种）", "benefit_amount": "100%基本保额", "payment_limit": "1次"},
            {"benefit_type": "basic", "benefit_name": f"中症保险金（{mod_count}种）", "benefit_amount": "60%基本保额", "payment_limit": "最多2次"},
            {"benefit_type": "basic", "benefit_name": f"轻症保险金（{mild_count}种）", "benefit_amount": "30%基本保额", "payment_limit": "最多3次"},
        ],
    }


def make_accident(name, company, prem_min, prem_max, si_min, si_max,
                  age_min=18, age_max=60, job_limit=3, url_extra="", benefits=None):
    return {
        "name": name, "company": company, "type": "意外险",
        "premium_min": prem_min, "premium_max": prem_max,
        "sum_insured_min": si_min, "sum_insured_max": si_max,
        "coverage_period": "1年", "payment_period": "1年",
        # url_extra 保留仅为兼容调用点；演示数据不编造产品路径，链接指向公司官网首页
        "source_url": COMPANY_URLS.get(company, ""),
        "disease_count": 0, "has_mild_coverage": False, "has_moderate_coverage": False,
        "has_multi_claim": False,
        "rule": {"min_age": age_min, "max_age": age_max, "job_class_limit": job_limit,
                 "waiting_period_days": 0,
                 "has_insured_waiver": False, "has_insurer_waiver": False,
                 "health_disclosure_count": 0},
        "benefits": benefits or [
            {"benefit_type": "basic", "benefit_name": "意外身故/伤残", "benefit_amount": f"{si_max}万", "payment_limit": ""},
            {"benefit_type": "basic", "benefit_name": "意外医疗", "benefit_amount": f"{si_max//10}万", "payment_limit": f"年限额{si_max//10}万"},
        ],
    }


def make_life(name, company, prem_min, prem_max, si_min, si_max,
              age_min=18, age_max=55, job_limit=4, wait=90, hd_count=4,
              coverage="至60岁/至70岁", payment="30年",
              has_iw=False, has_irw=False, url_extra="", benefits=None):
    return {
        "name": name, "company": company, "type": "定期寿险",
        "premium_min": prem_min, "premium_max": prem_max,
        "sum_insured_min": si_min, "sum_insured_max": si_max,
        "coverage_period": coverage, "payment_period": payment,
        # url_extra 保留仅为兼容调用点；演示数据不编造产品路径，链接指向公司官网首页
        "source_url": COMPANY_URLS.get(company, ""),
        "disease_count": 0, "has_mild_coverage": False, "has_moderate_coverage": False,
        "has_multi_claim": False,
        "rule": {"min_age": age_min, "max_age": age_max, "job_class_limit": job_limit,
                 "waiting_period_days": wait,
                 "has_insured_waiver": has_iw, "has_insurer_waiver": has_irw,
                 "health_disclosure_count": hd_count},
        "benefits": benefits or [
            {"benefit_type": "basic", "benefit_name": "身故/全残保险金", "benefit_amount": "100%基本保额", "payment_limit": "1次"},
        ],
    }


def make_anti_cancer(name, company, prem_min, prem_max, si_min, si_max,
                     age_min=40, age_max=75, job_limit=6, wait=90, hd_count=4,
                     coverage="1年（保证续保）", url_extra="", benefits=None):
    return {
        "name": name, "company": company, "type": "防癌险",
        "premium_min": prem_min, "premium_max": prem_max,
        "sum_insured_min": si_min, "sum_insured_max": si_max,
        "coverage_period": coverage, "payment_period": "1年",
        # url_extra 保留仅为兼容调用点；演示数据不编造产品路径，链接指向公司官网首页
        "source_url": COMPANY_URLS.get(company, ""),
        "disease_count": 0, "has_mild_coverage": False, "has_moderate_coverage": False,
        "has_multi_claim": False,
        "rule": {"min_age": age_min, "max_age": age_max, "job_class_limit": job_limit,
                 "waiting_period_days": wait,
                 "has_insured_waiver": False, "has_insurer_waiver": False,
                 "health_disclosure_count": hd_count},
        "benefits": benefits or [
            {"benefit_type": "basic", "benefit_name": "恶性肿瘤医疗保险金", "benefit_amount": f"{si_min}万", "payment_limit": f"年限额{si_min}万"},
        ],
    }


def make_annuity(name, company, prem_min, prem_max, si_min, coverage,
                 age_min=0, age_max=70, url_extra="", benefits=None):
    return {
        "name": name, "company": company, "type": "年金险",
        "premium_min": prem_min, "premium_max": prem_max,
        "sum_insured_min": si_min, "sum_insured_max": si_min,
        "coverage_period": coverage, "payment_period": "10年",
        # url_extra 保留仅为兼容调用点；演示数据不编造产品路径，链接指向公司官网首页
        "source_url": COMPANY_URLS.get(company, ""),
        "disease_count": 0, "has_mild_coverage": False, "has_moderate_coverage": False,
        "has_multi_claim": False,
        "rule": {"min_age": age_min, "max_age": age_max, "job_class_limit": 6,
                 "waiting_period_days": 0,
                 "has_insured_waiver": False, "has_insurer_waiver": False,
                 "health_disclosure_count": 0},
        "benefits": benefits or [
            {"benefit_type": "basic", "benefit_name": "年金给付", "benefit_amount": "按合同约定", "payment_limit": "终身"},
        ],
    }


def seed():
    init_db()
    db = SessionLocal()
    db.query(Benefit).delete()
    db.query(Rule).delete()
    db.query(Product).delete()
    db.commit()

    products_data: list[dict] = [

        # =====================================================================
        # 中国平安 (Tier 1) — 目标15+款
        # =====================================================================
        make_medical("平安e生保·长期医疗（20年保证续保）", "平安健康", 256, 650, 200, 400,
                     "1年（保证续保20年）", "yishengbao/",
                     benefits=[{"benefit_type":"basic","benefit_name":"一般住院医疗","benefit_amount":"200万","payment_limit":"年限额200万"},
                               {"benefit_type":"basic","benefit_name":"重疾住院医疗（120种）","benefit_amount":"400万","payment_limit":"年限额400万"},
                               {"benefit_type":"special","benefit_name":"质子重离子治疗","benefit_amount":"100万","payment_limit":"年限额100万"},
                               {"benefit_type":"special","benefit_name":"特药服务（188种含CAR-T）","benefit_amount":"200万","payment_limit":"年限额200万"}]),
        make_medical("平安长相安2号百万医疗险", "平安健康", 161, 2004, 200, 800,
                     "1年（保证续保20年）", "changan2/", hd_count=5,
                     benefits=[{"benefit_type":"basic","benefit_name":"一般住院医疗","benefit_amount":"200万","payment_limit":"年限额200万"},
                               {"benefit_type":"basic","benefit_name":"重疾住院医疗（120种）","benefit_amount":"400万","payment_limit":"年限额400万"},
                               {"benefit_type":"special","benefit_name":"院后康复医疗（9种指定疾病）","benefit_amount":"2万/年","payment_limit":""}]),
        make_medical("平安e生保·百万医疗2026（旗舰版）", "平安健康", 140, 550, 200, 400,
                     "1年", "yishengbao2026/"),
        make_medical("平安e生安心·中端医疗险（易保版2.0）", "平安健康", 502, 1200, 300, 600,
                     "1年", "eansheng/", hd_count=4),
        make_critical("平安盛世福（2025版）重疾险", "平安人寿", 5200, 12000, 20, 80,
                      disease_count=180, mild_count=40, mod_count=20, has_multi=True,
                      has_irw=True, url_extra="shengshifu/"),
        make_critical("平安守护百分百（2025版）重疾险", "平安人寿", 4500, 10000, 15, 60,
                      disease_count=160, mild_count=35, mod_count=15,
                      url_extra="shouhubfb/"),
        make_critical("平安六福重疾险（成人版）", "平安人寿", 3800, 9000, 10, 50,
                      disease_count=150, mild_count=30, mod_count=15, has_multi=True,
                      pays="30年", url_extra="liufu/"),
        make_critical("平安爱满分少儿重疾险（2025版）", "平安人寿", 2500, 6000, 20, 80,
                      disease_count=170, mild_count=35, mod_count=15,
                      age_max=17, url_extra="aimanfen/"),
        make_accident("平安橙护卫意外险", "中国平安", 130, 300, 30, 80, url_extra="cheng-huwei/",
                      benefits=[{"benefit_type":"basic","benefit_name":"意外身故/伤残","benefit_amount":"80万","payment_limit":""},
                                {"benefit_type":"basic","benefit_name":"意外医疗","benefit_amount":"8万","payment_limit":"年限额8万"},
                                {"benefit_type":"special","benefit_name":"猝死保障","benefit_amount":"20万","payment_limit":""}]),
        make_accident("平安小顽童8号少儿意外险", "平安财险", 60, 200, 20, 50,
                      age_min=0, age_max=17, url_extra="xiaowantong8/"),
        make_accident("平安百万综合意外险", "中国平安", 158, 450, 30, 100, url_extra="baiwan-yw/"),
        make_accident("平安孝心安6号中老年人意外险", "平安财险", 200, 500, 10, 50,
                      age_min=50, age_max=85, job_limit=3, url_extra="xiaoxinan6/"),
        make_life("平安小安定寿（互联网）", "平安人寿", 500, 1500, 50, 200, url_extra="xiaoanding/"),
        make_life("平安御享金越终身寿险", "平安人寿", 3000, 10000, 50, 500,
                  coverage="终身", payment="10年", url_extra="yuxiangjinyue/"),
        make_anti_cancer("平安互联网终身防癌医疗保险", "平安健康", 154, 2275, 400, 800,
                         age_min=0, age_max=70, job_limit=6, hd_count=3,
                         coverage="终身保证续保", url_extra="zhongshen-fangai/"),
        make_annuity("平安颐享年年年金保险（分红型）", "平安人寿", 10000, 100000, 5, "终身",
                     url_extra="yixiangniannian/"),
        make_medical("平安e生保·少儿百万医疗险", "平安健康", 200, 800, 100, 300,
                     "1年（保证续保至17岁）", "yishengbao-shaoer/", age_min=0, age_max=17),
        make_critical("平安六福重疾险（少儿版）", "平安人寿", 2000, 5500, 20, 60,
                      disease_count=160, mild_count=30, mod_count=15, has_multi=True,
                      age_max=17, url_extra="liufu-shaoer/"),
        make_critical("平安福满分重疾险（2025版）", "平安人寿", 3000, 7500, 15, 50,
                      disease_count=150, mild_count=30, mod_count=15,
                      url_extra="fumanfen/"),
        make_medical("平安e生保·慢病版百万医疗险", "平安健康", 350, 1200, 200, 400,
                     "1年", "yishengbao-manbing/", hd_count=3,
                     benefits=[{"benefit_type":"basic","benefit_name":"一般住院医疗","benefit_amount":"200万","payment_limit":"年限额200万"},
                               {"benefit_type":"special","benefit_name":"慢病人群可投（三高/糖尿病）","benefit_amount":"","payment_limit":""}]),
        make_accident("平安小神童6号少儿意外险", "平安财险", 70, 200, 20, 50,
                      age_min=0, age_max=17, url_extra="xiaoshentong6/"),
        make_life("平安小安定寿（2025升级版）", "平安人寿", 550, 1500, 50, 200, url_extra="xiaoanding-up/"),

        # =====================================================================
        # 中国人寿 (Tier 1) — 目标15+款
        # =====================================================================
        make_critical("国寿福终身重疾险（盛典版）", "中国人寿", 6000, 15000, 20, 100,
                      disease_count=160, mild_count=30, mod_count=15, wait=180,
                      has_irw=False, hd_count=6, url_extra="guoshoufu/"),
        make_critical("国寿康宁尊享重疾险（2025版）", "中国人寿", 5500, 13000, 20, 80,
                      disease_count=180, mild_count=35, mod_count=20, has_multi=True,
                      wait=90, url_extra="kangning-zunxiang/",
                      benefits=[{"benefit_type":"basic","benefit_name":"重疾保险金（120种/分6组赔6次）","benefit_amount":"100%基本保额","payment_limit":"最多6次"},
                                {"benefit_type":"basic","benefit_name":"中症保险金（20种）","benefit_amount":"60%基本保额","payment_limit":"最多2次"},
                                {"benefit_type":"basic","benefit_name":"轻症保险金（40种）","benefit_amount":"30%基本保额","payment_limit":"最多3次"}]),
        make_critical("国寿康宁保重疾险（2025版）", "中国人寿", 3800, 9000, 10, 50,
                      disease_count=120, mild_count=25, mod_count=10,
                      has_mild=True, has_mod=False, wait=90, has_irw=False,
                      url_extra="kangningbao/"),
        make_critical("国寿锦绣前程少儿重疾险（2025版）", "中国人寿", 2000, 5000, 20, 60,
                      disease_count=140, mild_count=30, mod_count=15, age_max=17,
                      url_extra="jinxiuqiancheng/"),
        make_medical("国寿如E康悦百万医疗险（2025版）", "中国人寿", 200, 1800, 200, 400,
                     "1年（保证续保6年）", "re-kangyue/", hd_count=5, wait=30),
        make_medical("国寿长久安顺百万医疗险（2026版）", "中国人寿", 180, 1600, 200, 400,
                     "1年（保证续保20年）", "changjiuanshun/", wait=90),
        make_accident("国寿百万如意行两全保险（2024版）", "中国人寿", 300, 800, 50, 200,
                      age_min=18, age_max=55, job_limit=3, url_extra="baiwanruyixing/",
                      benefits=[{"benefit_type":"basic","benefit_name":"意外身故/高残","benefit_amount":"200万","payment_limit":""},
                                {"benefit_type":"special","benefit_name":"满期返还保费","benefit_amount":"100%保费","payment_limit":""}]),
        make_accident("国寿个人综合意外险（2025版）", "中国人寿", 100, 400, 20, 80, url_extra="gerenzonghe/"),
        make_accident("国寿老年人意外险（安享版）", "中国人寿", 150, 500, 10, 30,
                      age_min=50, age_max=80, job_limit=4, url_extra="laonianren/"),
        make_life("国寿祥瑞定期寿险（2025版）", "中国人寿", 800, 2500, 50, 200,
                  has_iw=False, url_extra="xiangrui/"),
        make_life("国寿盛世传家终身寿险", "中国人寿", 5000, 20000, 100, 1000,
                  coverage="终身", payment="10年", url_extra="shengshichuanjia/"),
        make_anti_cancer("国寿防癌险（优享版）", "中国人寿", 600, 2500, 10, 20,
                         age_min=40, url_extra="fangai-youxiang/"),
        make_annuity("国寿鑫益丰年养老年金保险（分红型）", "中国人寿", 10000, 100000, 5, "至领取后20年",
                     url_extra="xinyifengnian/"),
        make_annuity("国寿锦绣前程少儿两全保险（分红型）", "中国人寿", 5000, 50000, 5, "至30岁",
                     age_min=0, age_max=17, url_extra="jinxiu-lq/"),
        make_critical("国寿康宁惠享版重疾险", "中国人寿", 2500, 6000, 10, 30,
                      disease_count=100, mild_count=20, mod_count=0,
                      has_mod=False, wait=90, has_irw=False, url_extra="kangning-huixiang/"),
        make_medical("国寿附加如E康悦住院医疗险", "中国人寿", 150, 1000, 100, 200,
                     "1年", "re-kangyue-fj/", wait=30),
        make_accident("国寿通泰交通意外险", "中国人寿", 50, 200, 10, 50, url_extra="tongtai/"),

        # =====================================================================
        # 太平洋保险 (Tier 1) — 目标15+款（已有详实备案数据）
        # =====================================================================
        make_medical("蓝医保·长期医疗险（好医好药0免赔）", "太平洋保险", 181, 1600, 200, 800,
                     "1年（保证续保20年）", "lanyibao/", wait=90,
                     benefits=[{"benefit_type":"basic","benefit_name":"一般住院医疗（0免赔）","benefit_amount":"200万","payment_limit":"年限额200万"},
                               {"benefit_type":"basic","benefit_name":"重疾住院医疗","benefit_amount":"400万","payment_limit":"年限额400万"},
                               {"benefit_type":"special","benefit_name":"外购药械无清单限制","benefit_amount":"100%赔付","payment_limit":""}]),
        make_medical("蓝医保·少儿中高端长期医疗（0免赔）", "太平洋保险", 300, 1200, 200, 600,
                     "1年（保证续保20年）", "lanyibao-shaoer/", age_min=0, age_max=17, wait=90),
        make_medical("心医保（长生版）百万医疗险", "太平洋保险", 200, 1800, 200, 400,
                     "1年（癌症终身保证续保+一般20年）", "xinyibao/", wait=90,
                     benefits=[{"benefit_type":"basic","benefit_name":"一般住院医疗","benefit_amount":"200万","payment_limit":"20年保证续保"},
                               {"benefit_type":"basic","benefit_name":"恶性肿瘤医疗","benefit_amount":"400万","payment_limit":"终身保证续保"}]),
        make_medical("太保互联网个人长期E款医疗保险", "太平洋保险", 220, 2000, 200, 400,
                     "1年（保证续保20年）", "hlwE/", wait=90),
        make_medical("太保健康人生医疗保险（2025互联网版A款）", "太平洋保险", 160, 1500, 150, 300,
                     "1年（保证续保6年）", "jkrsA/", wait=30),
        make_critical("太保阿基米德重大疾病保险（2025互联网版）", "太保寿险", 2800, 7000, 20, 70,
                      disease_count=160, mild_count=30, mod_count=15, job_limit=6,
                      has_mild=False, has_mod=False, wait=90,
                      url_extra="ajimide/",
                      benefits=[{"benefit_type":"basic","benefit_name":"重疾保险金（120种/可选多次）","benefit_amount":"100%基本保额","payment_limit":"1次"},
                                {"benefit_type":"basic","benefit_name":"轻中症可选","benefit_amount":"按附加保额","payment_limit":"可选"}]),
        make_critical("太平洋健康锦鲤3号终身重疾险", "太平洋保险", 3500, 8000, 20, 80,
                      disease_count=170, mild_count=40, mod_count=20, url_extra="jinli3/"),
        make_critical("太保少儿长期重大疾病保险（2025互联网版）", "太保寿险", 1500, 4000, 20, 60,
                      disease_count=160, mild_count=35, mod_count=15, age_max=17,
                      url_extra="shaoer-cb/"),
        make_critical("太保互联网定期（D款）重大疾病保险", "太保寿险", 2000, 5500, 15, 50,
                      disease_count=140, mild_count=30, mod_count=10,
                      coverage_period="至70岁", payment_period="20年",
                      url_extra="dingqiD/"),
        make_accident("太平洋小蜜蜂6号综合意外险", "太平洋保险", 156, 350, 50, 100,
                      url_extra="xiaomifeng6/",
                      benefits=[{"benefit_type":"basic","benefit_name":"意外身故/伤残","benefit_amount":"100万","payment_limit":""},
                                {"benefit_type":"basic","benefit_name":"意外医疗","benefit_amount":"12万","payment_limit":"0免赔100%报销"},
                                {"benefit_type":"special","benefit_name":"猝死保障","benefit_amount":"30万","payment_limit":""}]),
        make_accident("太平洋小蜜蜂6号（玫瑰版）综合意外险", "太平洋保险", 180, 380, 50, 100,
                      url_extra="xiaomifeng6-rose/"),
        make_accident("太平洋孝心安6号中老年人意外险", "太平洋保险", 200, 600, 10, 50,
                      age_min=50, age_max=85, job_limit=4, url_extra="xiaoxinan6/"),
        make_accident("太平洋小学童学生综合意外险", "太平洋保险", 60, 200, 10, 30,
                      age_min=3, age_max=25, url_extra="xiaoxuetong/"),
        make_life("太平洋长相伴定期寿险（2025版）", "太保寿险", 900, 2800, 50, 200,
                  has_iw=False, url_extra="changxiangban/"),
        make_life("太保智相守个人终身护理保险（2025版C款）", "太保寿险", 2000, 8000, 20, 100,
                  coverage="终身", payment="10年", url_extra="zhixiangshou/"),
        make_anti_cancer("太平洋药享无忧防癌医疗险", "太平洋保险", 500, 2000, 10, 20,
                         url_extra="yaoxiangwuyou/"),
        make_annuity("太保盈有余（2026）年金保险（互联网）", "太保寿险", 5000, 50000, 5, "终身",
                     url_extra="yingyouyu/"),
        make_medical("太保互联网个人长期D款医疗保险", "太平洋保险", 200, 1800, 200, 400,
                     "1年（保证续保20年）", "hlwD/", wait=90),
        make_medical("太保互联网银保版长期医疗保险", "太平洋保险", 180, 1600, 200, 400,
                     "1年（保证续保20年）", "hlw-yb/", wait=90),
        make_medical("太保互联网个人一年期住院G款医疗保险", "太平洋保险", 120, 800, 100, 200,
                     "1年", "hlwG/", wait=30, hd_count=3),
        make_critical("太保互联网个人恶性肿瘤及原位癌疾病保险", "太保寿险", 800, 2500, 10, 30,
                      disease_count=1, mild_count=0, mod_count=0, has_mild=False, has_mod=False,
                      coverage_period="至70岁", wait=90, url_extra="exlb/"),
        make_accident("太平洋小蜜蜂（家庭版）综合意外险", "太平洋保险", 300, 800, 50, 100,
                      url_extra="xiaomifeng-family/"),

        # =====================================================================
        # 人保寿险 (Tier 1) — 目标15+款
        # =====================================================================
        make_medical("人保金医保3号百万医疗险", "人保健康", 200, 1500, 200, 400,
                     "1年（保证续保20年）", "jinyibao3/", wait=90,
                     benefits=[{"benefit_type":"basic","benefit_name":"一般住院医疗","benefit_amount":"200万","payment_limit":"年限额200万"},
                               {"benefit_type":"basic","benefit_name":"重疾住院医疗","benefit_amount":"400万","payment_limit":"年限额400万"},
                               {"benefit_type":"special","benefit_name":"质子重离子治疗","benefit_amount":"100万","payment_limit":""}]),
        make_medical("人保好医保长期医疗（0免赔版）", "人保健康", 250, 2000, 200, 400,
                     "1年（保证续保6年）", "haoyibao/", wait=30),
        make_medical("人保人人保·中端医疗险", "人保健康", 500, 2500, 300, 600,
                     "1年（保证续保5年）", "renrenbao/", wait=90, hd_count=3),
        make_critical("人保寿险活力人生重疾险（2025版）", "人保寿险", 4800, 11000, 20, 80,
                      disease_count=175, mild_count=35, mod_count=20, has_irw=True,
                      url_extra="huolirenshen/"),
        make_critical("人保寿险无忧人生重疾险（2025版）", "人保寿险", 4200, 10000, 15, 60,
                      disease_count=160, mild_count=30, mod_count=15,
                      url_extra="wuyourenshen/"),
        make_critical("人保寿险少儿无忧人生重疾险（2025版）", "人保寿险", 1800, 4500, 20, 60,
                      disease_count=150, mild_count=30, mod_count=15, age_max=17,
                      url_extra="shaoer-wuyou/"),
        make_accident("人保大护甲8号意外险", "人保财险", 100, 320, 30, 100,
                      url_extra="dahujia8/",
                      benefits=[{"benefit_type":"basic","benefit_name":"意外身故/伤残","benefit_amount":"100万","payment_limit":""},
                                {"benefit_type":"basic","benefit_name":"意外医疗","benefit_amount":"10万","payment_limit":"年限额10万"},
                                {"benefit_type":"special","benefit_name":"猝死保障","benefit_amount":"50万","payment_limit":""}]),
        make_accident("人保大护甲8号（家庭版）意外险", "人保财险", 200, 600, 50, 100,
                      job_limit=3, url_extra="dahujia8-family/"),
        make_accident("人保老年人意外险（孝心保）", "人保财险", 150, 400, 10, 30,
                      age_min=50, age_max=80, job_limit=4, url_extra="xiaoxinbao/"),
        make_life("人保寿险鑫享一生终身寿险", "人保寿险", 1000, 3000, 50, 200,
                  has_irw=True, url_extra="xinxiangyisheng/"),
        make_life("人保寿险荣耀世家终身寿险", "人保寿险", 3000, 12000, 100, 500,
                  coverage="终身", payment="10年", url_extra="rongyaoshijia/"),
        make_life("人保寿险精心优选定期寿险", "人保寿险", 700, 2000, 50, 200,
                  has_iw=False, url_extra="jingxinyouxuan/"),
        make_anti_cancer("人保健康好医保防癌医疗险", "人保健康", 800, 3000, 10, 20,
                         age_min=40, url_extra="haoyibao-cancer/"),
        make_annuity("人保寿险福寿年年养老年金保险", "人保寿险", 5000, 50000, 5, "终身",
                     url_extra="fushouniannian/"),
        make_annuity("人保健康温暖常青护理保险", "人保健康", 3000, 15000, 10, "终身",
                     age_min=30, url_extra="wennuan-changqing/"),
        make_medical("人保健康金医保少儿长期医疗险", "人保健康", 150, 800, 100, 200,
                     "1年（保证续保至17岁）", "jinyibao-shaoer/", age_min=0, age_max=17, wait=90),
        make_accident("人保财险老年意外险（尊享版）", "人保财险", 200, 500, 10, 30,
                      age_min=50, age_max=85, job_limit=4, url_extra="laonian-zunxiang/"),
        make_critical("人保寿险福满一生重疾险", "人保寿险", 3500, 8000, 15, 50,
                      disease_count=150, mild_count=30, mod_count=15,
                      url_extra="fumanyisheng/"),
        make_life("人保寿险鑫祥一生定期寿险", "人保寿险", 650, 1800, 50, 150,
                  has_iw=False, url_extra="xinxiangyisheng-ds/"),

        # =====================================================================
        # 泰康人寿 (Tier 1) — 目标15+款
        # =====================================================================
        make_medical("泰康e康百万医疗险", "泰康人寿", 250, 750, 100, 300,
                     "1年（保证续保6年）", "ekang/", wait=30, hd_count=7),
        make_medical("泰康微医保百万医疗险（2025版）", "泰康在线", 180, 1600, 200, 400,
                     "1年（保证续保20年）", "weiyibao/", wait=90, hd_count=5),
        make_medical("泰康悦享人生中端医疗险", "泰康人寿", 600, 3000, 300, 600,
                     "1年", "yuexiangrenshen/", wait=30, hd_count=4),
        make_critical("泰康乐享健康重疾险（2025成人版）", "泰康人寿", 5000, 12000, 20, 80,
                      disease_count=170, mild_count=40, mod_count=20, has_multi=True,
                      has_irw=True, url_extra="lexiangjiankang/"),
        make_critical("泰康乐享健康重疾险（2025少儿版）", "泰康人寿", 2200, 5500, 20, 60,
                      disease_count=160, mild_count=35, mod_count=15, age_max=17,
                      has_multi=True, url_extra="lexiang-shaoer/"),
        make_critical("泰康惠健康重疾险（2025版）", "泰康人寿", 3800, 9000, 15, 50,
                      disease_count=150, mild_count=30, mod_count=15,
                      has_iw=True, has_irw=False, url_extra="huijiankang/"),
        make_critical("泰康全能保重疾险（2025版）", "泰康人寿", 4500, 10000, 15, 60,
                      disease_count=160, mild_count=30, mod_count=15,
                      url_extra="quannengbao/"),
        make_accident("泰康综合意外险（2025版）", "泰康在线", 100, 300, 20, 80, url_extra="zonghe/"),
        make_accident("泰康老年意外险（安享版）", "泰康人寿", 180, 500, 10, 30,
                      age_min=50, age_max=85, job_limit=4, url_extra="laonian-anxiang/"),
        make_life("泰康相伴一生定期寿险（2025版）", "泰康人寿", 850, 2500, 50, 200,
                  has_iw=False, url_extra="xiangban/"),
        make_life("泰康幸福世嘉终身寿险", "泰康人寿", 4000, 15000, 100, 500,
                  coverage="终身", payment="10年", url_extra="xingfushijia/"),
        make_anti_cancer("泰康在线防癌医疗险（普惠版）", "泰康在线", 400, 1800, 10, 20,
                         age_min=45, url_extra="fangai-puhui/"),
        make_annuity("泰康幸福有约年金保险（2025版）", "泰康人寿", 20000, 200000, 10, "终身",
                     url_extra="xingfuyouyue/"),
        make_annuity("泰康岁月有约养老年金保险", "泰康人寿", 10000, 100000, 5, "终身",
                     age_min=30, url_extra="suiyueyouyue/"),
        make_annuity("泰康嘉悦人生年金保险（分红型）", "泰康人寿", 5000, 50000, 5, "终身",
                     url_extra="jiayuerensheng/"),
        make_medical("泰康悦享健康B款百万医疗险", "泰康人寿", 220, 1500, 200, 400,
                     "1年（保证续保20年）", "yuexiang-B/", wait=90),
        make_critical("泰康健康尊享重疾险（2025版）", "泰康人寿", 3500, 8000, 15, 50,
                      disease_count=140, mild_count=30, mod_count=15, has_irw=False,
                      url_extra="jiankangzunxiang/"),
        make_accident("泰康少儿意外险（2025版）", "泰康在线", 50, 150, 10, 30,
                      age_min=0, age_max=17, url_extra="shaoer-yw/"),

        # =====================================================================
        # 新华保险 (Tier 1) + 阳光人寿 (Tier 1) — 各8+款
        # =====================================================================
        make_critical("新华健康多倍保庆典版重疾险", "新华保险", 5500, 13000, 20, 100,
                      disease_count=190, mild_count=40, mod_count=25, has_multi=True,
                      has_irw=True, url_extra="duobaobei-qingdian/"),
        make_critical("新华健康无忧卓越版重疾险", "新华保险", 4200, 10000, 15, 60,
                      disease_count=190, mild_count=35, mod_count=20,
                      url_extra="jiankangwuyou/"),
        make_critical("新华未来星臻享版少儿重疾险", "新华保险", 2000, 5000, 20, 60,
                      disease_count=160, mild_count=30, mod_count=15, age_max=17,
                      url_extra="weilaixing/"),
        make_medical("新华康健长佑长期医疗保险", "新华保险", 200, 1800, 200, 400,
                     "1年（保证续保20年）", "kangjianchangyou/", wait=90),
        make_medical("新华医药无忧医疗保险", "新华保险", 350, 2000, 150, 400,
                     "1年", "yiyaowuyou/", wait=30, hd_count=3,
                     benefits=[{"benefit_type":"basic","benefit_name":"住院医疗（0免赔）","benefit_amount":"150万","payment_limit":"年限额150万"},
                               {"benefit_type":"special","benefit_name":"外购药械不限清单","benefit_amount":"100%赔付","payment_limit":""}]),
        make_accident("新华小金刚少儿意外险", "新华保险", 60, 180, 10, 30,
                      age_min=0, age_max=17, url_extra="xiaojingang/"),
        make_life("新华祥瑞一生定期寿险", "新华保险", 800, 2200, 50, 200,
                  has_iw=False, url_extra="xiangruiyisheng/"),
        make_annuity("新华金彩一生年金保险", "新华保险", 5000, 50000, 5, "终身",
                     url_extra="jincaiyisheng/"),
        make_critical("新华康健吉顺恶性肿瘤疾病保险（卓越版）", "新华保险", 1500, 4000, 10, 30,
                      disease_count=1, mild_count=0, mod_count=0, has_mild=False, has_mod=False,
                      coverage_period="至80岁", wait=90, url_extra="kangjianjishun/"),
        make_critical("新华安心保臻选版定期重疾险", "新华保险", 2000, 5000, 10, 40,
                      disease_count=160, mild_count=30, mod_count=15,
                      coverage_period="至70岁", payment_period="20年", url_extra="anxinbao/"),
        make_medical("新华康健长佑（少儿版）医疗保险", "新华保险", 150, 1200, 150, 300,
                     "1年（保证续保至17岁）", "kangjianchangyou-shaoer/", age_min=0, age_max=17, wait=90),
        make_accident("新华安心无忧意外险", "新华保险", 80, 250, 15, 50, url_extra="anxinwuyou/"),
        make_life("新华祥瑞e生定期寿险", "新华保险", 650, 1800, 50, 150,
                  has_iw=False, url_extra="xiangruiesheng/"),
        make_medical("新华康护无忧护理保险", "新华保险", 1200, 4000, 10, 50,
                     "至80岁", "kanghuwuyou/", age_min=40, wait=90, hd_count=4),
        # 阳光
        make_life("阳光擎天柱定期寿险（8号）", "阳光人寿", 900, 2800, 50, 250,
                  has_irw=True, url_extra="qingtianzhu8/"),
        make_critical("阳光人寿臻欣重疾险（2025版）", "阳光人寿", 4500, 10000, 20, 80,
                      disease_count=170, mild_count=35, mod_count=20,
                      url_extra="zhenxin/"),
        make_critical("阳光人寿亲子保少儿重疾险", "阳光人寿", 1800, 4500, 15, 50,
                      disease_count=140, mild_count=30, mod_count=15, age_max=17,
                      url_extra="qinzibao/"),
        make_medical("阳光融和百万医疗险（2025版）", "阳光人寿", 200, 1700, 200, 400,
                     "1年（保证续保6年）", "ronghe/", wait=30),
        make_accident("阳光个人综合意外险（2025版）", "阳光人寿", 120, 350, 20, 80, url_extra="gerenzonghe/"),
        make_annuity("阳光金裕满堂年金保险", "阳光人寿", 8000, 80000, 5, "终身",
                     url_extra="jinyumantang/"),

        # =====================================================================
        # Tier 2 公司：同方全球、中意、复星联合、光大永明、工银安盛、招商信诺、安盛天平
        # 每司3-5款，合计约25款
        # =====================================================================
        # 同方全球
        make_critical("同方全球「凡尔赛PLUS」重疾险", "同方全球人寿", 5000, 10000, 20, 80,
                      disease_count=180, mild_count=40, mod_count=20, has_irw=True,
                      hd_count=5, url_extra="versailles/"),
        make_critical("同方全球「臻爱2026」互联网重疾险", "同方全球人寿", 3800, 8500, 15, 60,
                      disease_count=160, mild_count=35, mod_count=15,
                      url_extra="zhenai2026/"),
        make_medical("同方全球御护一生中端医疗险", "同方全球人寿", 400, 2000, 200, 500,
                     "1年", "yuhuyisheng/", wait=30, hd_count=4),
        make_life("同方全球「臻爱2026」互联网两全保险", "同方全球人寿", 3000, 8000, 20, 100,
                  coverage="至70岁", payment="10年", url_extra="zhenai2026-lq/"),
        # 中意
        make_critical("中意悦享安康重疾险（全能版）", "中意人寿", 4800, 10000, 20, 80,
                      disease_count=170, mild_count=35, mod_count=20, has_multi=True,
                      has_irw=True, hd_count=4, url_extra="yuexiangankang/"),
        make_medical("中意一生安康中端医疗险", "中意人寿", 500, 2500, 200, 600,
                     "1年", "yisheng-ankang/", wait=30, hd_count=4),
        make_life("中意一生中意（福享版）终身寿险（分红型）", "中意人寿", 5000, 20000, 100, 500,
                  coverage="终身", payment="10年", url_extra="yishengzhongyi/"),
        make_annuity("中意悠然金生两全保险（分红型）", "中意人寿", 10000, 50000, 5, "至88岁",
                     url_extra="youranjinsheng/"),
        # 复星联合
        make_medical("复星联合星相守长期医疗险（20年保证续保）", "复星联合健康", 148, 1594, 200, 800,
                     "1年（保证续保20年）", "xingshou/", wait=90, hd_count=5,
                     benefits=[{"benefit_type":"basic","benefit_name":"一般住院医疗","benefit_amount":"200万","payment_limit":"年限额200万"},
                               {"benefit_type":"basic","benefit_name":"重疾住院医疗（120种）","benefit_amount":"400万","payment_limit":"年限额400万"},
                               {"benefit_type":"special","benefit_name":"院外药械无清单限制","benefit_amount":"100%赔付","payment_limit":""}]),
        make_medical("复星联合星相守2号长期医疗保险（个人版）", "复星联合健康", 160, 1700, 200, 800,
                     "1年（保证续保20年）", "xingshou2/", wait=90),
        make_critical("复星联合康乐一生重疾险（2024版）", "复星联合健康", 4200, 8500, 20, 70,
                      disease_count=175, mild_count=35, mod_count=20,
                      has_irw=True, hd_count=4, url_extra="kangle/"),
        make_critical("复星联合妈咪保贝少儿重疾险（爱常在版）", "复星联合健康", 1500, 4000, 20, 60,
                      disease_count=180, mild_count=40, mod_count=20, age_max=17,
                      has_multi=True, url_extra="mamibaobei/"),
        make_accident("复星联合护身福意外险", "复星联合健康", 80, 250, 20, 50, url_extra="hushenfu/"),
        # 光大永明
        make_critical("光大永明嘉多保重疾险（2025版）", "光大永明", 4500, 9500, 20, 70,
                      disease_count=165, mild_count=35, mod_count=20, has_multi=True,
                      payment_period="30年", url_extra="jiaduobao/"),
        make_medical("光大永明安康e生百万医疗险", "光大永明", 180, 1500, 200, 400,
                     "1年", "ankang-esheng/", wait=30),
        make_life("光大永明光明至尊终身寿险", "光大永明", 3000, 10000, 50, 300,
                  coverage="终身", payment="10年", url_extra="guangmingzhizun/"),
        # 工银安盛
        make_critical("工银安盛御享欣生2.0重疾险", "工银安盛", 5200, 11000, 20, 90,
                      disease_count=180, mild_count=45, mod_count=25, has_multi=True,
                      has_irw=True, hd_count=5, url_extra="yuxiangxinsheng/"),
        make_critical("工银安盛御未来少儿重疾险", "工银安盛", 2000, 5000, 20, 60,
                      disease_count=160, mild_count=35, mod_count=20, age_max=17,
                      url_extra="yuweilai/"),
        make_medical("工银安盛安康e生中端医疗险", "工银安盛", 350, 2000, 200, 500,
                     "1年", "ankangesheng/", wait=30, hd_count=4),
        make_life("工银安盛鑫如意终身寿险", "工银安盛", 3000, 12000, 50, 300,
                  coverage="终身", payment="10年", url_extra="xinruyi/"),
        # 招商信诺
        make_critical("招商信诺福享康健（臻享版）重大疾病保险", "招商信诺", 5500, 12000, 30, 100,
                      disease_count=175, mild_count=40, mod_count=20,
                      has_irw=True, hd_count=5, url_extra="fuxiangkangjian/"),
        make_critical("招商信诺如意保重大疾病保险", "招商信诺", 3500, 8000, 15, 50,
                      disease_count=140, mild_count=30, mod_count=15,
                      url_extra="ruyibao/"),
        make_medical("招商信诺醇享人生高端医疗险", "招商信诺", 800, 5000, 500, 1000,
                     "1年", "chunxiangrensheng/", wait=30, hd_count=3),
        # 安盛天平
        make_anti_cancer("安盛天平卓越守护防癌医疗险", "安盛天平", 1200, 4000, 10, 30,
                         age_min=45, age_max=80, hd_count=3, coverage="1年（保证续保终身）",
                         url_extra="zy-cancer/"),
        make_medical("安盛天平卓越馨选医疗保险", "安盛天平", 300, 1800, 150, 400,
                     "1年", "zy-xinxuan/", wait=30, hd_count=4),
        make_accident("安盛天平个人综合意外险", "安盛天平", 120, 350, 20, 60, url_extra="gerenzonghe/"),

        # =====================================================================
        # Tier 3 公司：众安、瑞泰、和泰、华贵、信泰、国富
        # 每司3-6款，合计约25款
        # =====================================================================
        # 众安
        make_medical("众安尊享e生百万医疗险2026版", "众安保险", 180, 600, 300, 600,
                     "1年", "zxes2026/", hd_count=4, wait=30,
                     benefits=[{"benefit_type":"basic","benefit_name":"一般住院医疗","benefit_amount":"300万","payment_limit":"年限额300万"},
                               {"benefit_type":"basic","benefit_name":"重疾住院医疗","benefit_amount":"600万","payment_limit":"年限额600万"},
                               {"benefit_type":"special","benefit_name":"质子重离子治疗","benefit_amount":"600万","payment_limit":"共享保额"},
                               {"benefit_type":"special","benefit_name":"恶性肿瘤特药（195种含CAR-T）","benefit_amount":"600万","payment_limit":"共享保额"}]),
        make_medical("众安众民保2025·百万医疗险（臻选版）", "众安保险", 368, 3298, 300, 600,
                     "1年（不保证续保）", "zhongminbao2025/", age_max=105, job_limit=6,
                     wait=30, hd_count=0,
                     benefits=[{"benefit_type":"basic","benefit_name":"一般医疗（社保内+社保外）","benefit_amount":"各300万","payment_limit":""},
                               {"benefit_type":"special","benefit_name":"免健康告知（五大类既往症免责）","benefit_amount":"高龄/慢病/高危职业可投","payment_limit":""}]),
        make_medical("众安众民保·中高端医疗险2026", "众安保险", 500, 4000, 300, 600,
                     "1年", "zhongminbao-mid/", age_max=105, job_limit=6, wait=30, hd_count=0),
        make_accident("众安个人综合意外险（2025版）", "众安保险", 100, 300, 20, 80, url_extra="gerenzonghe/"),
        make_accident("众安孝欣保中老年意外险", "众安保险", 200, 500, 10, 30,
                      age_min=50, age_max=85, job_limit=4, url_extra="xiaoxinbao/"),
        make_anti_cancer("众安普惠e生防癌医疗险", "众安保险", 300, 1500, 10, 20,
                         age_min=40, hd_count=2, url_extra="puhui-esheng/"),
        # 瑞泰
        make_life("瑞泰瑞和定期寿险（2025版）", "瑞泰人寿", 700, 2000, 50, 200,
                  has_iw=False, url_extra="ruihe/"),
        make_critical("瑞泰瑞盈重疾险（2025版）", "瑞泰人寿", 3500, 8000, 15, 50,
                      disease_count=150, mild_count=30, mod_count=15,
                      url_extra="ruiying/"),
        make_medical("瑞泰安康e生百万医疗险", "瑞泰人寿", 180, 1200, 150, 300,
                     "1年", "ankangesheng/", wait=30),
        # 和泰
        make_critical("超级玛丽16号重疾险", "和泰人寿", 3500, 7000, 30, 70,
                      disease_count=195, mild_count=45, mod_count=20, has_multi=True,
                      wait=180, hd_count=10,
                      benefits=[{"benefit_type":"basic","benefit_name":"重疾保险金（120种）","benefit_amount":"100%基本保额","payment_limit":"1次"},
                                {"benefit_type":"basic","benefit_name":"第二次重疾保险金","benefit_amount":"120%基本保额","payment_limit":"1次"},
                                {"benefit_type":"basic","benefit_name":"中症保险金（20种）","benefit_amount":"60%基本保额","payment_limit":"最多2次"},
                                {"benefit_type":"basic","benefit_name":"轻症保险金（45种）","benefit_amount":"30%基本保额","payment_limit":"最多3次"}]),
        make_critical("和泰超级玛丽Pro重疾险（2025版）", "和泰人寿", 3000, 6000, 20, 60,
                      disease_count=180, mild_count=40, mod_count=20, has_multi=True,
                      url_extra="supermary-pro/"),
        make_medical("和泰百医无忧百万医疗险", "和泰人寿", 160, 1200, 200, 400,
                     "1年（保证续保6年）", "baiyiwuyou/", wait=30),
        # 华贵
        make_life("华贵大麦2026定期寿险（互联网专属）", "华贵人寿", 800, 2500, 50, 400,
                  hd_count=3, url_extra="damai2026/"),
        make_life("华贵大麦甜蜜家定期寿险（2025版）", "华贵人寿", 1500, 4000, 100, 500,
                  hd_count=3, url_extra="damai-tianmi/"),
        make_life("华贵小爱终身寿险", "华贵人寿", 1200, 3000, 30, 100,
                  coverage="终身", payment="20年", url_extra="xiaoai/"),
        # 信泰
        make_critical("达尔文12号重疾险", "信泰人寿", 4000, 8000, 30, 80,
                      disease_count=185, mild_count=50, mod_count=25, has_irw=True,
                      hd_count=8, url_extra="darwin12/"),
        make_critical("信泰如意久久重疾险（2025版）", "信泰人寿", 3800, 8500, 20, 70,
                      disease_count=180, mild_count=40, mod_count=20, has_multi=True,
                      url_extra="ruyijiujiu/"),
        make_life("信泰如意尊定期寿险", "信泰人寿", 750, 2000, 50, 200, url_extra="ruyizun/"),
        # 国富
        make_life("国富定海柱8号定期寿险（互联网）", "国富人寿", 600, 1800, 50, 300,
                  hd_count=3, url_extra="dinghaizhu8/"),
        make_critical("国富无忧一生重疾险", "国富人寿", 3200, 7500, 15, 50,
                      disease_count=150, mild_count=30, mod_count=15,
                      url_extra="wuyouyisheng/"),
        make_medical("国富安康e生百万医疗险", "国富人寿", 160, 1200, 200, 400,
                     "1年", "ankangesheng/", wait=30),
    ]

    # Insert all products
    for pdata in products_data:
        rule_data = pdata.pop("rule")
        benefits_data = pdata.pop("benefits")
        company = pdata["company"]
        pdata["company_tier"] = COMPANY_TIERS.get(company, 2)

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
    print(f"Seeded {len(products_data)} products across 23 companies and 3 company tiers.")

if __name__ == "__main__":
    seed()
