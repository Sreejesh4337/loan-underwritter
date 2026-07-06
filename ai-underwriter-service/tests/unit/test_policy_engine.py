"""Unit tests for the deterministic policy rule engine, covering every rule
tier from LENDING_POLICY.pdf plus the high-income override and its edge case.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.policy_engine.engine import evaluate
from src.schemas.underwriting import Decision, FinancialMetrics


def make_metrics(**overrides) -> FinancialMetrics:
    base = dict(
        net_monthly_income=100000.0,
        net_monthly_income_source="income_sheet",
        existing_emis=5000.0,
        proposed_emi=15000.0,
        foir_pct=20.0,
        avg_bank_balance=30000.0,  # >= 1x proposed_emi (15000)
        payment_returns_count=0,
        salary_credit_months_count=6,
        vintage_months=24,
        unexplained_cash_deposit_flag=False,
    )
    base.update(overrides)
    return FinancialMetrics(**base)


class TestCleanCases:
    def test_clean_approve(self):
        result = evaluate(make_metrics(), credit_score=750)
        assert result.decision == Decision.APPROVE
        assert not any(r.fired for r in result.fired_rules)


class TestDeclineRules:
    def test_d1_low_credit_score(self):
        result = evaluate(make_metrics(), credit_score=600)
        assert result.decision == Decision.DECLINE
        assert any(r.rule_id == "D1_CREDIT_SCORE" for r in result.fired_rules)

    def test_d2_high_foir(self):
        result = evaluate(make_metrics(foir_pct=60.0), credit_score=750)
        assert result.decision == Decision.DECLINE
        assert any(r.rule_id == "D2_FOIR" for r in result.fired_rules)

    def test_d3_three_or_more_returns(self):
        result = evaluate(make_metrics(payment_returns_count=3), credit_score=750)
        assert result.decision == Decision.DECLINE
        assert any(r.rule_id == "D3_PAYMENT_RETURNS" for r in result.fired_rules)

    def test_d4_insufficient_salary_credits(self):
        result = evaluate(make_metrics(salary_credit_months_count=2), credit_score=750)
        assert result.decision == Decision.DECLINE
        assert any(r.rule_id == "D4_SALARY_CREDITS" for r in result.fired_rules)

    def test_self_employed_skips_salary_rule(self):
        # salary_credit_months_count=None means self-employed; D4 must not fire.
        result = evaluate(make_metrics(salary_credit_months_count=None), credit_score=750)
        assert result.decision == Decision.APPROVE

    def test_decline_takes_precedence_over_high_income_override(self):
        result = evaluate(
            make_metrics(net_monthly_income=300000, foir_pct=20.0, payment_returns_count=0),
            credit_score=600,  # below the hard decline floor
        )
        assert result.decision == Decision.DECLINE


class TestReferRules:
    def test_r1_credit_score_band(self):
        result = evaluate(make_metrics(), credit_score=670)
        assert result.decision == Decision.REFER
        assert any(r.rule_id == "R1_CREDIT_SCORE" and r.fired for r in result.fired_rules)

    def test_r2_foir_band(self):
        result = evaluate(make_metrics(foir_pct=52.0), credit_score=750)
        assert result.decision == Decision.REFER
        assert any(r.rule_id == "R2_FOIR" for r in result.fired_rules)

    def test_r3_exactly_two_returns(self):
        result = evaluate(make_metrics(payment_returns_count=2), credit_score=750)
        assert result.decision == Decision.REFER
        assert any(r.rule_id == "R3_PAYMENT_RETURNS" for r in result.fired_rules)

    def test_r4_short_vintage(self):
        result = evaluate(make_metrics(vintage_months=3), credit_score=750)
        assert result.decision == Decision.REFER
        assert any(r.rule_id == "R4_VINTAGE" for r in result.fired_rules)

    def test_r5_balance_below_one_emi(self):
        result = evaluate(make_metrics(avg_bank_balance=1000.0), credit_score=750)
        assert result.decision == Decision.REFER
        assert any(r.rule_id == "R5_BANK_BALANCE" for r in result.fired_rules)

    def test_r6_unexplained_deposit(self):
        result = evaluate(make_metrics(unexplained_cash_deposit_flag=True), credit_score=750)
        assert result.decision == Decision.REFER
        assert any(r.rule_id == "R6_UNEXPLAINED_DEPOSIT" for r in result.fired_rules)


class TestHighIncomeOverride:
    def test_override_neutralizes_score_band_refer(self):
        result = evaluate(
            make_metrics(net_monthly_income=250000, foir_pct=30.0, payment_returns_count=0),
            credit_score=685,  # squarely in the 650-699 refer band
        )
        assert result.decision == Decision.APPROVE
        assert result.override_applied is True
        r1 = next(r for r in result.fired_rules if r.rule_id == "R1_CREDIT_SCORE")
        assert r1.fired is False

    def test_override_does_not_suppress_other_refer_rules(self):
        # Same override-eligible profile, but vintage < 6 months must still refer.
        result = evaluate(
            make_metrics(net_monthly_income=250000, foir_pct=30.0, payment_returns_count=0, vintage_months=3),
            credit_score=685,
        )
        assert result.decision == Decision.REFER
        assert result.override_applied is True
        assert any(r.rule_id == "R4_VINTAGE" and r.fired for r in result.fired_rules)

    def test_override_requires_zero_returns(self):
        result = evaluate(
            make_metrics(net_monthly_income=250000, foir_pct=30.0, payment_returns_count=1),
            credit_score=685,
        )
        assert result.decision == Decision.REFER
        assert result.override_applied is False

    def test_override_requires_foir_at_or_below_35(self):
        result = evaluate(
            make_metrics(net_monthly_income=250000, foir_pct=36.0, payment_returns_count=0),
            credit_score=685,
        )
        assert result.decision == Decision.REFER
        assert result.override_applied is False

    def test_override_requires_income_at_or_above_200000(self):
        result = evaluate(
            make_metrics(net_monthly_income=199999, foir_pct=30.0, payment_returns_count=0),
            credit_score=685,
        )
        assert result.decision == Decision.REFER
        assert result.override_applied is False

    def test_override_not_needed_above_700_credit_score(self):
        # Score >= 700 never hits the R1 band in the first place — override is irrelevant.
        result = evaluate(
            make_metrics(net_monthly_income=250000, foir_pct=30.0, payment_returns_count=0),
            credit_score=750,
        )
        assert result.decision == Decision.APPROVE
        assert result.override_applied is False
