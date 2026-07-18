from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.modules.exports.router import _excel_scalar
from app.services.exports import ExportService


def test_excel_scalar_converts_timezone_aware_datetime_to_iso_string() -> None:
    value = datetime(2026, 5, 18, 12, 30, tzinfo=timezone.utc)

    converted = _excel_scalar(value)

    assert converted == "2026-05-18T12:30:00+00:00"


async def _async_bytes_call(service: ExportService) -> tuple[bytes, str]:
    payload, cache_status = await service.export_cached(
        session=None,  # type: ignore[arg-type]
        export_type="stock",
        account_id=1,
        date_from=None,
        date_to=None,
        headers=["a"],
        rows=[(1,)],
        data_version_hash="hash-1",
    )
    return payload, cache_status


def test_export_service_cache_returns_hit_for_repeated_export() -> None:
    service = ExportService()

    first_payload, first_status = asyncio.run(_async_bytes_call(service))
    second_payload, second_status = asyncio.run(_async_bytes_call(service))

    assert first_status == "miss"
    assert second_status == "hit"
    assert first_payload == second_payload


class _FakeExecuteResult:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class _FakeSession:
    def __init__(self, row):
        self._row = row

    async def execute(self, _stmt):
        return _FakeExecuteResult(self._row)


def test_table_signature_without_date_column_does_not_require_max_date_attribute() -> None:
    service = ExportService()
    row = SimpleNamespace(row_count=3, updated_at=datetime(2026, 5, 28, tzinfo=timezone.utc))

    signature = asyncio.run(
        service._table_signature(  # type: ignore[arg-type]
            _FakeSession(row),
            model=SimpleNamespace(__tablename__="fake_table", account_id=1, updated_at=None),
            account_id=1,
            date_column=None,
        )
    )

    assert isinstance(signature, str)
    assert len(signature) == 40
