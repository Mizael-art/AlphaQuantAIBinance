from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.scheduler import seconds_until_next_boundary


def _dt(h, m, s=0, us=0):
    return datetime(2026, 1, 1, h, m, s, us, tzinfo=timezone.utc)


class TestSecondsUntilNextBoundary:
    def test_mid_interval_waits_until_next_boundary(self):
        # 10:07:30 com passo de 15min -> próximo boundary é 10:15:00
        secs = seconds_until_next_boundary(15, now=_dt(10, 7, 30))
        assert secs == pytest.approx(7 * 60 + 30)

    def test_just_after_boundary_waits_nearly_full_interval(self):
        secs = seconds_until_next_boundary(15, now=_dt(10, 0, 1))
        assert secs == pytest.approx(14 * 60 + 59)

    def test_exact_boundary_returns_zero(self):
        secs = seconds_until_next_boundary(15, now=_dt(10, 30, 0, 0))
        assert secs == 0.0

    def test_hour_rollover(self):
        # 10:58 com passo de 15min -> próximo boundary é 11:00 (não 10:60)
        secs = seconds_until_next_boundary(15, now=_dt(10, 58, 0))
        assert secs == pytest.approx(2 * 60)

    def test_supports_non_15_intervals(self):
        secs = seconds_until_next_boundary(60, now=_dt(10, 40, 0))  # próxima hora cheia
        assert secs == pytest.approx(20 * 60)

    def test_rejects_non_positive_interval(self):
        with pytest.raises(ValueError):
            seconds_until_next_boundary(0, now=_dt(10, 0, 0))

    def test_naive_datetime_treated_as_utc(self):
        naive = datetime(2026, 1, 1, 10, 7, 30)
        secs = seconds_until_next_boundary(15, now=naive)
        assert secs == pytest.approx(7 * 60 + 30)
