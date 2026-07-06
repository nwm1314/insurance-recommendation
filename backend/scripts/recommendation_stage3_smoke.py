"""Smoke checks for stage-3 recommendation scoring invariants.

Run from backend directory:
  python scripts/recommendation_stage3_smoke.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.engine.models import BudgetAnalysis, UserProfile
from backend.app.engine.rule_engine import get_allowed_types
from backend.app.engine.combo_builder import build_combos
from backend.app.engine.scoring import DEFAULT_TYPE_WEIGHTS, validate_type_weights, _type_weights
from backend.app.engine.budget import calculate_budget
from backend.app.engine.ai_engine import render_ai_explanation, validate_ai_output


def main():
    assert _type_weights("医疗险")["coverage"] != _type_weights("定期寿险")["coverage"]
    assert abs(sum(DEFAULT_TYPE_WEIGHTS["医疗险"].values()) - 1.0) < 0.0001
    assert validate_type_weights() == []
    assert abs(sum(_type_weights("医疗险").values()) - 1.0) < 0.0001

    child = UserProfile(
        age=12,
        gender="male",
        annual_income=100000,
        job_class=1,
        life_stage="single",
        family_burden="none",
        health_status="standard",
    )
    assert "定期寿险" not in get_allowed_types(child)

    adult = UserProfile(
        age=32,
        gender="male",
        annual_income=200000,
        job_class=2,
        life_stage="married_with_kids",
        family_burden="dual",
        health_status="standard",
    )
    budget = BudgetAnalysis(annual_income=200000, total_budget=16000, allocation={})
    products = [
        {"product_id": 1, "name": "医疗A", "company": "A", "type": "医疗险", "premium": 800, "sum_insured": 300, "score": 80, "score_detail": {}, "risk_warnings": []},
        {"product_id": 2, "name": "意外A", "company": "A", "type": "意外险", "premium": 200, "sum_insured": 100, "score": 70, "score_detail": {}, "risk_warnings": []},
    ]
    combos = build_combos(products, adult, budget)
    assert combos
    assert combos[0].budget_utilization > 0
    assert combos[0].completeness_score < 1
    assert combos[0].coverage_gap_notes

    senior = UserProfile(
        age=60,
        gender="female",
        annual_income=100000,
        job_class=1,
        life_stage="retired",
        family_burden="none",
        health_status="standard",
    )
    senior_budget = calculate_budget(senior)
    assert "cancer" in senior_budget.allocation
    assert abs(sum(senior_budget.allocation.values()) - 1.0) < 0.001

    valid_ai = validate_ai_output(
        '{"selected_product_ids":[1],"summary":"方案摘要","reasoning":["保障完整"],"risk_notes":["以核保为准"],"comparison_notes":[]}',
        {1, 2},
    )
    assert valid_ai is not None
    assert "方案摘要" in render_ai_explanation(valid_ai)
    assert validate_ai_output('{"selected_product_ids":[999],"summary":"越权"}', {1, 2}) is None
    print("recommendation stage3 smoke ok")


if __name__ == "__main__":
    main()
