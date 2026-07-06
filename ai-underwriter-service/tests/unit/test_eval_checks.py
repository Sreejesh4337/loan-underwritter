"""Unit tests for the eval harness's tolerance comparison and quality proxies."""

from __future__ import annotations

from eval.checks import metric_within_tolerance


class TestMetricWithinTolerance:
    def test_exact_match_within_absolute_tolerance(self):
        ok, delta = metric_within_tolerance(3, {"value": 3, "tolerance_abs": 0})
        assert ok is True
        assert delta == 0

    def test_outside_absolute_tolerance(self):
        ok, delta = metric_within_tolerance(5, {"value": 2, "tolerance_abs": 1})
        assert ok is False
        assert delta == 3

    def test_within_percentage_tolerance(self):
        ok, delta = metric_within_tolerance(102000, {"value": 100000, "tolerance_pct": 5})
        assert ok is True

    def test_outside_percentage_tolerance(self):
        ok, delta = metric_within_tolerance(120000, {"value": 100000, "tolerance_pct": 5})
        assert ok is False
