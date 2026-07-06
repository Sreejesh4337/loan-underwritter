"""Token -> USD cost lookup.

Prices are per-million tokens, matched to the models named in
src/llm/models.py. Update here (and only here) if pricing changes — nodes
never hardcode a per-token rate.
"""

from __future__ import annotations

# USD per 1M tokens (input, output). Adjust to current provider pricing as needed.
_PRICING_PER_MILLION = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}


def estimate_cost_usd(model_name: str, input_tokens: int, output_tokens: int) -> float:
    input_rate, output_rate = _PRICING_PER_MILLION.get(model_name, (0.0, 0.0))
    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate
