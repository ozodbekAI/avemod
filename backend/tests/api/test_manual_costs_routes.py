from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.db import get_db_session
from app.main import app
from app.models.accounts import WBAccount
from app.modules.manual_costs import router as manual_costs_router
from app.services.auth import get_current_user


class _FakeExecuteResult:
    def __init__(self, *, rows=None, scalars=None):
        self._rows = rows or []
        self._scalars = scalars or []

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def scalar_one(self):
        return len(self._scalars)

    def __iter__(self):
        return iter(self._scalars)


class _FakeSession:
    def __init__(self, *, allowed_account_ids={1}, account_roles=None):
        self.accounts = {
            1: SimpleNamespace(
                id=1,
                name="Account 1",
                seller_name=None,
                external_account_id=None,
                timezone="Europe/Moscow",
                is_active=True,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            2: SimpleNamespace(
                id=2,
                name="Account 2",
                seller_name=None,
                external_account_id=None,
                timezone="Europe/Moscow",
                is_active=True,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        }
        self.allowed_account_ids = allowed_account_ids
        self.account_roles = account_roles or {1: "viewer"}

    async def get(self, model, key):
        if model is WBAccount:
            return self.accounts.get(int(key))
        return None

    async def execute(self, stmt):
        allowed_accounts = [self.accounts[account_id] for account_id in sorted(self.allowed_account_ids)]
        rows = [(account.id, self.account_roles.get(int(account.id), "viewer")) for account in allowed_accounts]
        return _FakeExecuteResult(rows=rows, scalars=allowed_accounts)

    async def commit(self):
        return None

    async def refresh(self, row):
        return None

    def add(self, row):
        return None


def _session_factory(**kwargs):
    async def _override_session():
        yield _FakeSession(**kwargs)

    return _override_session


def _normal_user():
    return SimpleNamespace(id=2, is_superuser=False)


def test_cost_template_allows_own_account_reader(monkeypatch) -> None:
    async def _fake_csv(session, **kwargs):
        return "vendorCode,nmId\nSKU-1,1001\n"

    monkeypatch.setattr(manual_costs_router.service, "build_template_csv", _fake_csv)
    app.dependency_overrides[get_current_user] = _normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "viewer"})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/costs/template?account_id=1&format=csv&mode=all")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "account_1_all" in response.headers["content-disposition"]


def test_cost_template_rejects_forbidden_account(monkeypatch) -> None:
    async def _fake_csv(session, **kwargs):
        raise AssertionError("service should not run for forbidden account")

    monkeypatch.setattr(manual_costs_router.service, "build_template_csv", _fake_csv)
    app.dependency_overrides[get_current_user] = _normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "viewer"})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/costs/template?account_id=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_costs_missing_returns_account_scoped_payload(monkeypatch) -> None:
    async def _fake_missing(session, **kwargs):
        return {
            "total": 1,
            "limit": kwargs["limit"],
            "offset": kwargs["offset"],
            "summary": {
                "missing_sku_count": 1,
                "affected_revenue": 28606.0,
                "revenue_cost_coverage_percent": 99.6213,
            },
            "items": [
                {
                    "sku_id": 123,
                    "nm_id": 123456789,
                    "vendor_code": "SKU-1",
                    "barcode": "BC-1",
                    "tech_size": "42",
                    "product_title": "Product",
                    "affected_revenue": 28606.0,
                    "recommended_action": "Заполнить себестоимость",
                }
            ],
        }

    monkeypatch.setattr(manual_costs_router.service, "list_missing_costs", _fake_missing)
    app.dependency_overrides[get_current_user] = _normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "viewer"})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/costs/missing?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["summary"]["missing_sku_count"] == 1


def test_manager_can_save_inline_costs_and_trigger_recalc(monkeypatch) -> None:
    calls = {"save": None, "marts": 0, "dq": 0, "money": 0, "operator": 0}
    saved_row = SimpleNamespace(
        id=9,
        account_id=1,
        upload_id=None,
        sku_id=123,
        vendor_code="SKU-1",
        nm_id=123456789,
        barcode="BC-1",
        tech_size="42",
        unit_cost=321.0,
        cost_price=321.0,
        seller_other_expense=0.0,
        packaging_cost=0.0,
        inbound_logistics_cost=0.0,
        supplier="OPERATOR_TRUSTED_COST",
        currency="RUB",
        valid_from=None,
        valid_to=None,
        source_file_name="inline-platform",
        uploaded_by_user_id=2,
        uploaded_at=None,
        match_rule="sku_id",
        cost_source="operator_trusted_manual",
        is_ambiguous=False,
        is_placeholder=False,
        is_business_trusted=True,
        is_supplier_confirmed=False,
        supplier_confirmed_at=None,
        supplier_confirmed_by_user_id=None,
        comment="Заполнено вручную в платформе",
    )

    async def _fake_save(session, **kwargs):
        calls["save"] = kwargs
        return [saved_row]

    async def _fake_marts(session, **kwargs):
        calls["marts"] += 1

    async def _fake_dq(session, **kwargs):
        calls["dq"] += 1

    async def _fake_money(session, **kwargs):
        calls["money"] += 1

    async def _fake_operator(session, **kwargs):
        calls["operator"] += 1

    monkeypatch.setattr(manual_costs_router.service, "save_inline_costs", _fake_save)
    monkeypatch.setattr(manual_costs_router.mart_service, "refresh_account", _fake_marts)
    monkeypatch.setattr(manual_costs_router.data_quality_service, "run_checks", _fake_dq)
    monkeypatch.setattr(manual_costs_router.money_snapshot_service, "invalidate_snapshots", _fake_money)
    monkeypatch.setattr(manual_costs_router.operator_snapshot_service, "invalidate_snapshots", _fake_operator)
    app.dependency_overrides[get_current_user] = _normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "manager"})
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/costs/inline-save",
                json={
                    "account_id": 1,
                    "rows": [{"sku_id": 123, "cost_price": "321.00"}],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["changed_count"] == 1
    assert response.json()["recalculated"] is True
    assert calls["save"]["account_id"] == 1
    assert calls["save"]["rows"][0].sku_id == 123
    assert calls["marts"] == 1
    assert calls["dq"] == 1
    assert calls["money"] == 1
    assert calls["operator"] == 1


def test_viewer_cannot_save_inline_costs(monkeypatch) -> None:
    async def _fake_save(*args, **kwargs):
        raise AssertionError("inline save service should not run for viewer")

    monkeypatch.setattr(manual_costs_router.service, "save_inline_costs", _fake_save)
    app.dependency_overrides[get_current_user] = _normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "viewer"})
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/costs/inline-save",
                json={"account_id": 1, "rows": [{"sku_id": 123, "cost_price": "321.00"}]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_viewer_cannot_upload_costs(monkeypatch) -> None:
    async def _fake_import(*args, **kwargs):
        raise AssertionError("upload service should not run for viewer")

    monkeypatch.setattr(manual_costs_router.service, "import_costs", _fake_import)
    app.dependency_overrides[get_current_user] = _normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "viewer"})
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/costs/upload",
                data={"account_id": "1", "commit_rows": "false"},
                files={"file": ("costs.csv", b"vendorCode,cost_price\nSKU,10\n", "text/csv")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
