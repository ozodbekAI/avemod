from __future__ import annotations

from datetime import date

from app.core.parsing import parse_date


def test_parse_date_handles_rfc3339_datetime_string() -> None:
    assert parse_date("2026-05-13T00:00:00Z") == date(2026, 5, 13)
