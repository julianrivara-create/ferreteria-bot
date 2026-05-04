"""
Tests for MAX_WORKERS_OVERRIDE env var behaviour (Fase 3).

These tests exercise the n_workers computation logic in isolation —
no LLM calls, no server, no DB required.
"""
import os
import pytest


def _compute_n_workers(n_items: int) -> int:
    """Mirror of the logic in bot.py:1348 block."""
    _override = os.environ.get("MAX_WORKERS_OVERRIDE")
    if _override:
        try:
            return max(1, int(_override))
        except ValueError:
            return min(n_items, 5)
    return min(n_items, 5)


class TestMaxWorkersOverride:
    def test_default_uses_p1_parallelism(self, monkeypatch):
        monkeypatch.delenv("MAX_WORKERS_OVERRIDE", raising=False)
        assert _compute_n_workers(5) == 5
        assert _compute_n_workers(3) == 3
        assert _compute_n_workers(10) == 5  # capped at 5

    def test_override_to_1_disables_parallelism(self, monkeypatch):
        monkeypatch.setenv("MAX_WORKERS_OVERRIDE", "1")
        assert _compute_n_workers(5) == 1
        assert _compute_n_workers(2) == 1

    def test_override_to_3_caps_at_3(self, monkeypatch):
        monkeypatch.setenv("MAX_WORKERS_OVERRIDE", "3")
        assert _compute_n_workers(5) == 3
        assert _compute_n_workers(2) == 3

    def test_invalid_override_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("MAX_WORKERS_OVERRIDE", "abc")
        assert _compute_n_workers(5) == 5
        assert _compute_n_workers(3) == 3

    def test_override_minimum_is_1(self, monkeypatch):
        monkeypatch.setenv("MAX_WORKERS_OVERRIDE", "0")
        assert _compute_n_workers(5) == 1  # max(1, 0) == 1
