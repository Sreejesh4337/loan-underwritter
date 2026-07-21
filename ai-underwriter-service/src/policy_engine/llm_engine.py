"""LLM-based policy evaluation engine.

Instead of deterministic if/else logic, this module sends the full
lending_policy.yaml text and the applicant's computed financial metrics to a
strong LLM, which interprets the rules and produces the underwriting decision,
fired rules, rationale, and advisory notes in a single structured call.

The old deterministic engine (engine.py) is preserved and used as an automatic
fallback if the LLM call fails for any reason.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field as PydanticField

from src.policy_engine.loader import DEFAULT_POLICY_PATH, load_policy
from src.schemas.underwriting import Decision, FiredRule, FinancialMetrics, RuleTier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic response schema — used with OpenAI structured output
# ---------------------------------------------------------------------------


class FiredRuleResponse(BaseModel):
    """A single rule evaluation result from the LLM."""

    rule_id: str = PydanticField(
        description=(
            "A short identifier for the rule, e.g. D1_CREDIT_SCORE, R2_FOIR. "
            "Use D-prefix for decline rules, R-prefix for refer rules."
        )
    )
    tier: str = PydanticField(
        description="One of: 'decline', 'refer', 'approve', 'override'."
    )
    message: str = PydanticField(
        description="Human-readable explanation of why this rule fired or was neutralized."
    )
    fired: bool = PydanticField(
        default=True,
        description=(
            "True if the rule actually triggered (counts toward the decision). "
            "False if the rule was in-band but neutralized by an override."
        ),
    )


class LLMPolicyResponse(BaseModel):
    """Structured response expected from the LLM policy evaluation."""

    decision: str = PydanticField(
        description="The underwriting decision: 'approve', 'refer', or 'decline'."
    )
    fired_rules: list[FiredRuleResponse] = PydanticField(
        default_factory=list,
        description=(
            "List of all rules evaluated. Include every rule that was checked, "
            "marking fired=True for those that triggered and fired=False for "
            "those neutralized by overrides."
        ),
    )
    override_applied: bool = PydanticField(
        default=False,
        description="True if the high-income override was applied to neutralize a refer rule.",
    )
    rationale_text: str = PydanticField(
        description=(
            "2-4 sentence narrative explaining the decision in plain English, "
            "citing rule IDs and specific figures."
        )
    )
    advisory_notes: list[str] = PydanticField(
        default_factory=list,
        description="Up to 3 short qualitative observations (not new rules).",
    )


# ---------------------------------------------------------------------------
# Evaluation result (mirrors the shape of the old PolicyEvaluation + decide)
# ---------------------------------------------------------------------------


@dataclass
class LLMPolicyEvaluation:
    decision: Decision
    fired_rules: list[FiredRule] = field(default_factory=list)
    override_applied: bool = False
    rationale_text: str = ""
    advisory_notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core evaluation function
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a senior loan underwriter. You will receive a lending policy document \
(in YAML format) and the applicant's computed financial metrics. Your job is to:

1. Read EVERY rule defined in the lending policy — decline rules, refer rules, \
the high-income override, and the approve-by-default logic.
2. Evaluate EACH rule against the provided metrics and credit score.
3. Apply rules in the correct order: decline rules first, then refer rules \
(with the high-income override check), then approve by default if nothing fires.
4. For the high-income override: if ALL four override conditions are met AND \
the only refer-band trigger is R1_CREDIT_SCORE, then neutralize R1 \
(set fired=False, tier='override') and note the override was applied.
5. Produce the final decision (approve/refer/decline) based on which rules \
actually fired (fired=True).
6. Write a 2-4 sentence rationale and up to 3 advisory notes.

CRITICAL RULES:
- Format all currency values using 'INR' (e.g., INR 150,000). Never use $ or ₹.
- A DECLINE decision requires at least one decline-tier rule to fire.
- A REFER decision requires at least one refer-tier rule to fire (fired=True).
- If no decline or refer rules fire, the decision MUST be APPROVE.
- Be precise with threshold comparisons (< vs <=, > vs >=) as defined in the YAML.
- Include ALL rules you evaluated in fired_rules, even those that did not fire \
(mark them with fired=False if they were neutralized by override, or simply \
omit rules that didn't match at all).
"""


def _build_user_prompt(
    policy_yaml_text: str,
    metrics: FinancialMetrics,
    credit_score: int,
    cross_check: dict[str, Any] | None = None,
) -> str:
    """Build the user message with policy + metrics context."""
    metrics_dict = metrics.model_dump(mode="json")

    prompt = (
        "## LENDING POLICY (YAML)\n\n"
        f"```yaml\n{policy_yaml_text}\n```\n\n"
        "## APPLICANT DATA\n\n"
        f"**Credit Score**: {credit_score}\n\n"
        f"**Financial Metrics**:\n```json\n{json.dumps(metrics_dict, indent=2)}\n```\n\n"
    )

    if cross_check:
        prompt += f"**Cross-Check Results**:\n```json\n{json.dumps(cross_check, indent=2)}\n```\n\n"

    prompt += (
        "## YOUR TASK\n\n"
        "Evaluate every rule in the lending policy against the applicant data above. "
        "Return your structured evaluation."
    )

    return prompt


def _parse_llm_response(response: LLMPolicyResponse) -> LLMPolicyEvaluation:
    """Convert the Pydantic LLM response into our internal evaluation type."""
    # Map string decision to enum
    try:
        decision = Decision(response.decision.lower())
    except ValueError:
        logger.warning(f"LLM returned unknown decision '{response.decision}', defaulting to REFER")
        decision = Decision.REFER

    # Map fired rules
    fired_rules = []
    for r in response.fired_rules:
        try:
            tier = RuleTier(r.tier.lower())
        except ValueError:
            tier = RuleTier.REFER
        fired_rules.append(
            FiredRule(
                rule_id=r.rule_id,
                tier=tier,
                message=r.message,
                fired=r.fired,
            )
        )

    return LLMPolicyEvaluation(
        decision=decision,
        fired_rules=fired_rules,
        override_applied=response.override_applied,
        rationale_text=response.rationale_text,
        advisory_notes=response.advisory_notes,
    )


def evaluate_with_llm(
    metrics: FinancialMetrics,
    credit_score: int,
    cross_check: dict[str, Any] | None = None,
    policy_path: Path = DEFAULT_POLICY_PATH,
) -> tuple[LLMPolicyEvaluation, dict]:
    """Evaluate the lending policy using the strong LLM.

    Returns:
        A tuple of (LLMPolicyEvaluation, usage_dict) where usage_dict
        contains input_tokens, output_tokens, and model name for cost
        tracking.

    Raises:
        Any exception from the LLM call — the caller (the graph node) is
        responsible for catching and falling back to the deterministic engine.
    """
    from src.llm.models import STRONG_MODEL_NAME, get_strong_model

    # Load raw YAML text for the prompt
    policy_yaml_text = Path(policy_path).read_text(encoding="utf-8")

    model = get_strong_model()
    structured_model = model.with_structured_output(LLMPolicyResponse)

    user_prompt = _build_user_prompt(policy_yaml_text, metrics, credit_score, cross_check)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    response: LLMPolicyResponse = structured_model.invoke(messages)

    # Extract token usage from the raw LLM response metadata
    # Note: with_structured_output wraps the response; usage may be on
    # response_metadata of the underlying AIMessage stored by langchain.
    usage_meta = {}
    if hasattr(response, "response_metadata"):
        rm = response.response_metadata
        usage_meta = rm.get("token_usage", rm.get("usage", {}))

    # Langchain's with_structured_output returns the parsed Pydantic object
    # directly, so we check if we got a Pydantic model or need to extract
    # usage from elsewhere.
    input_tokens = usage_meta.get("prompt_tokens", usage_meta.get("input_tokens", 0))
    output_tokens = usage_meta.get("completion_tokens", usage_meta.get("output_tokens", 0))

    evaluation = _parse_llm_response(response)

    usage = {
        "model": STRONG_MODEL_NAME,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }

    return evaluation, usage
