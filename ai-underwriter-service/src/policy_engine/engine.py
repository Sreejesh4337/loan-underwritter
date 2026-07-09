"""Deterministic policy rule engine — no LLM calls.

Applies the lending policy in the order specified by the policy document:
decline rules first, then refer rules (with the one high-income override),
then approve by default. Every threshold is read from the loaded YAML, never
hardcoded here — see policy/lending_policy.yaml.

Scoping decision (see project plan): the "strong model" decide step authors
the rationale narrative only; it has no authority to change the decision this
engine produces. This is what keeps decision_accuracy scoring against ground
truth reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.policy_engine.loader import DEFAULT_POLICY_PATH, load_policy
from src.schemas.underwriting import Decision, FiredRule, FinancialMetrics, RuleTier


@dataclass
class PolicyEvaluation:
    decision: Decision
    fired_rules: list[FiredRule] = field(default_factory=list)
    override_applied: bool = False


def _high_income_override_applies(
    metrics: FinancialMetrics, credit_score: int, policy: dict[str, Any]
) -> bool:
    override = policy["high_income_override"]
    return (
        metrics.net_monthly_income >= override["min_net_monthly_income"]
        and metrics.foir_pct <= override["max_foir"]
        and credit_score >= override["min_credit_score"]
        and metrics.payment_returns_count <= override["max_payment_returns"]
    )


def _decline_rules(metrics: FinancialMetrics, credit_score: int, policy: dict[str, Any]) -> list[FiredRule]:
    t = policy["thresholds"]
    fired = []

    if credit_score < t["credit_score"]["decline_below"]:
        fired.append(
            FiredRule(
                rule_id="D1_CREDIT_SCORE",
                tier=RuleTier.DECLINE,
                message=f"Credit score of {credit_score} is below the decline threshold of {t['credit_score']['decline_below']}.",
            )
        )
    if metrics.foir_pct > t["foir"]["decline_above"]:
        fired.append(
            FiredRule(
                rule_id="D2_FOIR",
                tier=RuleTier.DECLINE,
                message=f"FOIR of {metrics.foir_pct:.1f}% exceeds the decline threshold of {t['foir']['decline_above']}%.",
            )
        )
    if metrics.payment_returns_count >= t["payment_returns"]["decline_min"]:
        fired.append(
            FiredRule(
                rule_id="D3_PAYMENT_RETURNS",
                tier=RuleTier.DECLINE,
                message=(
                    f"{metrics.payment_returns_count} payment returns meet or exceed the "
                    f"decline threshold of {t['payment_returns']['decline_min']}."
                ),
            )
        )
    if (
        metrics.salary_credit_months_count is not None
        and metrics.salary_credit_months_count < t["salary_credit_months"]["decline_below"]
    ):
        fired.append(
            FiredRule(
                rule_id="D4_SALARY_CREDITS",
                tier=RuleTier.DECLINE,
                message=(
                    f"Salary was credited in only {metrics.salary_credit_months_count} of the last "
                    f"{t['salary_credit_months']['lookback_months']} months, below the "
                    f"decline threshold of {t['salary_credit_months']['decline_below']}."
                ),
            )
        )
    if metrics.name_mismatch_flag:
        fired.append(
            FiredRule(
                rule_id="D5_NAME_MISMATCH",
                tier=RuleTier.DECLINE,
                message="Applicant name does not match consistently across the KYC, income, and bank statement documents.",
            )
        )
    if metrics.income_mismatch_flag:
        fired.append(
            FiredRule(
                rule_id="D6_INCOME_MISMATCH",
                tier=RuleTier.DECLINE,
                message=(
                    "Declared income sheet salary does not match the bank statement's salary credits "
                    f"within {t['income_consistency']['tolerance_pct']:.0f}% tolerance."
                ),
            )
        )
    return fired


def _refer_rules(
    metrics: FinancialMetrics, credit_score: int, policy: dict[str, Any], override_applies: bool
) -> tuple[list[FiredRule], bool]:
    t = policy["thresholds"]
    fired: list[FiredRule] = []
    override_used = False

    score_in_refer_band = t["credit_score"]["refer_low"] <= credit_score <= t["credit_score"]["refer_high"]
    if score_in_refer_band:
        if override_applies:
            override_used = True
            fired.append(
                FiredRule(
                    rule_id="R1_CREDIT_SCORE",
                    tier=RuleTier.OVERRIDE,
                    fired=False,
                    message=(
                        f"Credit score of {credit_score} is in the refer band "
                        f"({t['credit_score']['refer_low']}-{t['credit_score']['refer_high']}), but the "
                        "high-income override applies (net monthly income, FOIR, score, and zero "
                        "payment returns all meet the override's own thresholds), so this rule does not fire."
                    ),
                )
            )
        else:
            fired.append(
                FiredRule(
                    rule_id="R1_CREDIT_SCORE",
                    tier=RuleTier.REFER,
                    message=(
                        f"Credit score of {credit_score} is in the refer band "
                        f"({t['credit_score']['refer_low']}-{t['credit_score']['refer_high']})."
                    ),
                )
            )

    if t["foir"]["refer_low"] <= metrics.foir_pct <= t["foir"]["refer_high"]:
        fired.append(
            FiredRule(
                rule_id="R2_FOIR",
                tier=RuleTier.REFER,
                message=(
                    f"FOIR of {metrics.foir_pct:.1f}% is in the refer band "
                    f"({t['foir']['refer_low']}-{t['foir']['refer_high']}%)."
                ),
            )
        )

    if metrics.payment_returns_count == t["payment_returns"]["refer_exact"]:
        fired.append(
            FiredRule(
                rule_id="R3_PAYMENT_RETURNS",
                tier=RuleTier.REFER,
                message=f"Exactly {t['payment_returns']['refer_exact']} payment returns were found.",
            )
        )

    if metrics.vintage_months < t["vintage_months"]["refer_below"]:
        fired.append(
            FiredRule(
                rule_id="R4_VINTAGE",
                tier=RuleTier.REFER,
                message=(
                    f"Vintage of {metrics.vintage_months} months is below the refer threshold of "
                    f"{t['vintage_months']['refer_below']} months."
                ),
            )
        )

    balance_floor = metrics.proposed_emi * t["bank_balance"]["refer_below_emi_multiple"]
    if metrics.avg_bank_balance < balance_floor:
        fired.append(
            FiredRule(
                rule_id="R5_BANK_BALANCE",
                tier=RuleTier.REFER,
                message=(
                    f"Average bank balance of {metrics.avg_bank_balance:,.0f} is below "
                    f"{t['bank_balance']['refer_below_emi_multiple']}x the proposed EMI of "
                    f"{metrics.proposed_emi:,.0f}."
                ),
            )
        )

    if metrics.unexplained_cash_deposit_flag:
        fired.append(
            FiredRule(
                rule_id="R6_UNEXPLAINED_DEPOSIT",
                tier=RuleTier.REFER,
                message=(
                    f"A large cash deposit exceeding {t['unexplained_deposit']['refer_above_income_fraction'] * 100:.0f}% "
                    "of monthly income was found without a clear explanation."
                ),
            )
        )

    return fired, override_used


def evaluate(
    metrics: FinancialMetrics, credit_score: int, policy_path: Path = DEFAULT_POLICY_PATH
) -> PolicyEvaluation:
    policy = load_policy(policy_path)

    decline_fired = _decline_rules(metrics, credit_score, policy)
    if decline_fired:
        return PolicyEvaluation(decision=Decision.DECLINE, fired_rules=decline_fired)

    override_applies = _high_income_override_applies(metrics, credit_score, policy)
    refer_fired, override_used = _refer_rules(metrics, credit_score, policy, override_applies)

    # A refer rule "fires" for decision purposes only if fired=True (the
    # neutralized R1-under-override entry is kept in the list for
    # transparency but must not itself trigger a refer decision).
    active_refers = [r for r in refer_fired if r.fired]
    if active_refers:
        return PolicyEvaluation(decision=Decision.REFER, fired_rules=refer_fired, override_applied=override_used)

    return PolicyEvaluation(
        decision=Decision.APPROVE,
        fired_rules=refer_fired,  # keep the neutralized-override entry, if any, for the memo's transparency
        override_applied=override_used,
    )
