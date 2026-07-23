from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db_session
from app.main import app
from app.models.accounts import WBAccount
from app.modules.portal import router as portal_router
from app.schemas.portal import PortalActionRead, PortalActionsPage, PortalActionSourceUpdateRequest
from app.services.auth import get_current_user


class _FakeExecuteResult:
    def __init__(self, *, rows=None, scalars=None):
        self._rows = rows or []
        self._scalars = scalars or []

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self._scalars)


class _FakeSession:
    def __init__(
        self,
        *,
        allowed_account_ids: set[int] | None = None,
        account_roles: dict[int, str] | None = None,
    ) -> None:
        self.accounts = {
            1: SimpleNamespace(id=1, name="Account 1", seller_name=None, external_account_id=None, timezone="Europe/Moscow", is_active=True),
            2: SimpleNamespace(id=2, name="Account 2", seller_name=None, external_account_id=None, timezone="Europe/Moscow", is_active=True),
        }
        self.allowed_account_ids = allowed_account_ids if allowed_account_ids is not None else {1}
        self.account_roles = account_roles or {}

    async def get(self, model, key):
        if model is WBAccount:
            return self.accounts.get(int(key))
        return None

    async def execute(self, stmt):
        accounts = [self.accounts[account_id] for account_id in sorted(self.allowed_account_ids) if account_id in self.accounts]
        rows = [(account.id, self.account_roles.get(int(account.id), "viewer")) for account in accounts]
        return _FakeExecuteResult(rows=rows, scalars=accounts)


def _session_factory(*, allowed_account_ids: set[int] | None = None, account_roles: dict[int, str] | None = None):
    async def _override_session():
        yield _FakeSession(allowed_account_ids=allowed_account_ids, account_roles=account_roles)

    return _override_session


def _normal_user():
    return SimpleNamespace(id=7, is_superuser=False)


def _superuser():
    return SimpleNamespace(id=1, is_superuser=True)


class _ActionCenterContractService:
    beta_sources = {"grouping_beta", "reputation", "claims", "stockops", "experiments"}

    def __init__(self) -> None:
        self.items = [
            PortalActionRead(
                id="finance:10",
                action_id=10,
                source="finance_actions",
                source_module="finance",
                source_id="10",
                account_id=1,
                action_type="FINANCE_REVIEW",
                title="Проверить финансы",
                priority="P1",
                severity="high",
                status="new",
                reason="Маржа ниже плана.",
                next_step="Открыть финансовую карточку.",
                expected_effect_amount=1500.0,
                confidence="high",
                nm_id=1001,
                can_update=True,
                can_update_status=True,
                payload={"source_references": [{"table": "action_recommendations", "id": 10}]},
            ),
            PortalActionRead(
                id="unified:20",
                action_id=20,
                source="unified_actions",
                source_module="manual",
                source_id="manual:20",
                account_id=1,
                action_type="MANUAL_REVIEW",
                title="Manual owner task",
                priority="P2",
                severity="medium",
                status="in_progress",
                reason="Нужно решение владельца.",
                next_step="Назначить ответственного.",
                expected_impact_amount=500.0,
                confidence="medium",
                nm_id=1002,
                can_update=True,
                can_update_status=True,
            ),
            PortalActionRead(
                id="data_quality:30",
                source="dq_issues",
                source_module="data_quality",
                source_id="30",
                account_id=1,
                action_type="DATA_FIX",
                title="Исправить качество данных",
                priority="P0",
                severity="critical",
                status="new",
                reason="Нет связанной себестоимости.",
                next_step="Открыть Data Quality.",
                expected_effect_amount=2500.0,
                confidence="high",
                nm_id=1001,
                can_update=True,
                can_update_status=True,
            ),
            PortalActionRead(
                id="checker:40",
                source="checker_issues",
                source_module="checker",
                source_id="card:40",
                account_id=1,
                action_type="CARD_QUALITY_FIX",
                title="Исправить карточку",
                priority="P2",
                severity="medium",
                status="new",
                reason="Контент снижает конверсию.",
                next_step="Открыть Checker.",
                confidence="medium",
                nm_id=1003,
                can_update=True,
                can_update_status=True,
                raw={"evidence": [{"field": "title", "score_impact": 12}]},
            ),
            PortalActionRead(
                id="costs:50",
                source="costs_unresolved",
                source_module="costs",
                source_id="50",
                account_id=1,
                action_type="COST_FIX",
                title="Разобрать себестоимость",
                priority="P0",
                severity="critical",
                status="new",
                reason="Себестоимость не привязана.",
                next_step="Открыть Costs.",
                expected_effect_amount=900.0,
                confidence="high",
                nm_id=1004,
                can_update=True,
                can_update_status=True,
            ),
            PortalActionRead(
                id="grouping:60",
                source="grouping_beta",
                source_module="grouping_beta",
                source_id="candidate:60",
                account_id=1,
                action_type="GROUPING_REVIEW",
                title="Beta grouping candidate",
                priority="P3",
                severity="low",
                status="new",
                reason="Beta recommendation.",
                next_step="Open grouping beta.",
                confidence="low",
                nm_id=2001,
                can_update=True,
                can_update_status=True,
            ),
        ]

    async def actions(
        self,
        session,
        *,
        account_id: int | None,
        status: str | None,
        source_module: list[str] | None,
        priority: list[str] | None,
        nm_id: int | None,
        include_beta: bool,
        limit: int,
        offset: int,
        **kwargs,
    ) -> PortalActionsPage:
        items = [item for item in self.items if item.account_id == account_id]
        if not include_beta:
            items = [item for item in items if item.source_module not in self.beta_sources]
        if status:
            items = [item for item in items if item.status == status]
        if source_module:
            allowed = {str(value) for value in source_module}
            items = [item for item in items if item.source_module in allowed]
        if priority:
            allowed_priority = {str(value).upper() for value in priority}
            items = [item for item in items if item.priority in allowed_priority]
        if nm_id is not None:
            items = [item for item in items if item.nm_id == nm_id]
        return PortalActionsPage(total=len(items), limit=limit, offset=offset, items=items[offset : offset + limit])

    async def update_action_by_source(
        self,
        session,
        *,
        payload: PortalActionSourceUpdateRequest,
        user_id: int | None,
    ) -> PortalActionRead:
        item = next(
            (
                candidate
                for candidate in self.items
                if candidate.account_id == payload.account_id
                and candidate.source_module == payload.source_module
                and str(candidate.source_id) == str(payload.source_id)
            ),
            None,
        )
        if item is None:
            item = PortalActionRead(
                id=f"{payload.source_module}:{payload.source_id}",
                source="shadow_source_update",
                source_module=payload.source_module,  # type: ignore[arg-type]
                source_id=payload.source_id,
                account_id=payload.account_id,
                action_type="MANUAL_REVIEW",
                title="Local action",
                can_update=True,
                can_update_status=True,
            )
            self.items.append(item)

        now = datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc)
        review_status = payload.review_status
        closed_at = item.closed_at
        dismissed_at = item.dismissed_at
        if payload.status == "done":
            review_status = review_status or "closed"
            closed_at = now
            dismissed_at = None
        elif payload.status == "ignored":
            review_status = review_status or "dismissed"
            dismissed_at = now
            closed_at = None
        elif payload.status == "in_progress":
            review_status = review_status or "in_progress"
            closed_at = None
            dismissed_at = None
        else:
            review_status = review_status or "review"
            closed_at = None
            dismissed_at = None

        updated = item.model_copy(
            update={
                "status": payload.status,
                "assigned_to_user_id": payload.assigned_to_user_id,
                "deadline_at": payload.deadline_at,
                "last_comment": payload.comment,
                "status_reason": payload.status_reason or payload.comment,
                "review_status": review_status,
                "closed_at": closed_at,
                "dismissed_at": dismissed_at,
                "can_update": True,
                "can_update_status": True,
            }
        )
        self.items[self.items.index(item)] = updated
        return updated


@pytest.fixture()
def action_center_service(monkeypatch):
    service = _ActionCenterContractService()
    monkeypatch.setattr(portal_router.service, "actions", service.actions)
    monkeypatch.setattr(portal_router.service, "update_action_by_source", service.update_action_by_source)
    return service


def _install_overrides(*, user, allowed_account_ids: set[int] | None = None, roles: dict[int, str] | None = None) -> None:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = _session_factory(
        allowed_account_ids=allowed_account_ids,
        account_roles=roles,
    )


def _parse_json_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_action_center_get_requires_authorized_account_access(action_center_service) -> None:
    _install_overrides(user=_normal_user(), allowed_account_ids={1}, roles={1: "operator"})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/actions?account_id=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_action_center_capabilities_returns_jvo_like_contract() -> None:
    _install_overrides(user=_normal_user(), allowed_account_ids={1}, roles={1: "viewer"})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/action-center/capabilities?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["protocol"] == "action-center-capabilities-v1"
    assert payload["summary"]["execute_missing_wb_write"] >= 2
    domains = {domain["key"]: domain for domain in payload["domains"]}
    assert {"data_blockers", "price", "ads_promo", "manual_tasks"}.issubset(domains)
    assert any(
        capability["key"] == "wb_price_discount_write"
        and capability["execute_status"] == "missing_wb_write"
        for capability in domains["price"]["capabilities"]
    )
    price_write = next(
        capability
        for capability in domains["price"]["capabilities"]
        if capability["key"] == "wb_price_discount_write"
    )
    assert price_write["wb_tracking_status"] == "write_gap"
    assert (
        "https://discounts-prices-api.wildberries.ru/api/v2/upload/task"
        in price_write["wb_api_endpoints"]
    )
    assert price_write["implementation_gaps"]
    card_text = next(
        capability
        for capability in domains["card_quality"]["capabilities"]
        if capability["key"] == "card_text_inline_fix"
    )
    assert card_text["wb_tracking_status"] == "tracked"
    assert "product_cards.update_card" in card_text["wb_connector_ids"]


def test_action_center_get_returns_stable_contract_and_default_mvp_scope(action_center_service) -> None:
    required_fields = {
        "id",
        "source",
        "source_module",
        "source_id",
        "account_id",
        "action_type",
        "title",
        "priority",
        "severity",
        "status",
        "reason",
        "next_step",
        "expected_effect_amount",
        "expected_impact_amount",
        "confidence",
        "can_update_status",
        "can_update",
        "can_update_reason",
        "guided_fix",
        "evidence_ledger",
        "evidence_state",
        "source_references",
        "recheck_rule",
        "impact_type",
        "trust_state",
        "source_sync_state",
        "last_status_changed_at",
        "last_actor_user_id",
        "status_reason",
        "is_overdue",
        "due_in_hours",
        "sla_state",
        "payload",
    }
    _install_overrides(user=_normal_user(), allowed_account_ids={1}, roles={1: "viewer"})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/actions?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    modules = {item["source_module"] for item in body["items"]}
    assert {"finance", "manual", "data_quality", "checker", "costs"} <= modules
    assert "grouping_beta" not in modules
    for item in body["items"]:
        assert required_fields <= set(item)
        assert item["source_id"]
        assert item["account_id"] == 1
        assert item["evidence_ledger"]
        assert item["evidence_state"] in {
            "full_evidence",
            "partial_evidence",
            "missing_evidence",
            "read_only_signal",
        }
        assert item["source_references"]
        assert item["recheck_rule"]
        assert item["impact_type"]
        assert item["trust_state"]


def test_action_center_include_beta_requires_admin_or_superuser(action_center_service) -> None:
    _install_overrides(user=_normal_user(), allowed_account_ids={1}, roles={1: "viewer"})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/actions?account_id=1&include_beta=true")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_action_center_include_beta_true_includes_beta_sources_for_admin(action_center_service) -> None:
    _install_overrides(user=_normal_user(), allowed_account_ids={1}, roles={1: "admin"})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/actions?account_id=1&include_beta=true")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "grouping_beta" in {item["source_module"] for item in response.json()["items"]}


@pytest.mark.parametrize(
    ("query", "expected_ids"),
    [
        ("status=in_progress", {"unified:20"}),
        ("source_module=data_quality", {"data_quality:30"}),
        ("priority=P0", {"data_quality:30", "costs:50"}),
        ("nm_id=1001", {"finance:10", "data_quality:30"}),
    ],
)
def test_action_center_get_supports_filters(action_center_service, query: str, expected_ids: set[str]) -> None:
    _install_overrides(user=_normal_user(), allowed_account_ids={1}, roles={1: "viewer"})
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/portal/actions?account_id=1&{query}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} == expected_ids


def test_action_center_patch_by_source_persists_task_fields_and_survives_get(action_center_service) -> None:
    deadline = "2026-06-30T09:30:00+00:00"
    _install_overrides(user=_normal_user(), allowed_account_ids={1}, roles={1: "operator"})
    try:
        with TestClient(app) as client:
            patch_response = client.patch(
                "/api/v1/portal/actions/by-source",
                json={
                    "account_id": 1,
                    "source_module": "manual",
                    "source_id": "manual:20",
                    "status": "blocked",
                    "assigned_to_user_id": 7,
                    "deadline_at": deadline,
                    "comment": "Waiting for owner approval",
                },
            )
            get_response = client.get("/api/v1/portal/actions?account_id=1&source_module=manual")
    finally:
        app.dependency_overrides.clear()

    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["status"] == "blocked"
    assert patched["assigned_to_user_id"] == 7
    assert _parse_json_datetime(patched["deadline_at"]) == _parse_json_datetime(deadline)
    assert patched["last_comment"] == "Waiting for owner approval"
    assert patched["status_reason"] == "Waiting for owner approval"
    assert patched["sla_state"] in {"ok", "due_soon", "overdue"}
    assert isinstance(patched["is_overdue"], bool)

    assert get_response.status_code == 200
    [item] = get_response.json()["items"]
    assert item["status"] == "blocked"
    assert item["assigned_to_user_id"] == 7
    assert _parse_json_datetime(item["deadline_at"]) == _parse_json_datetime(deadline)
    assert item["last_comment"] == "Waiting for owner approval"
    assert item["status_reason"] == "Waiting for owner approval"


def test_action_center_assignable_users_uses_portal_account_scope(monkeypatch) -> None:
    async def _fake_assignable_users(session, *, account_id, user):
        assert account_id == 1
        assert user.id == 7
        return [
            {
                "id": 7,
                "email": "operator@example.test",
                "full_name": "Мария Оператор",
                "display_name": "Мария Оператор",
                "role": "operator",
                "is_active": True,
                "is_superuser": False,
            },
            {
                "id": 8,
                "email": "manager@example.test",
                "full_name": "Иван Менеджер",
                "display_name": "Иван Менеджер",
                "role": "manager",
                "is_active": True,
                "is_superuser": False,
            },
        ]

    monkeypatch.setattr(portal_router.service, "assignable_users", _fake_assignable_users)
    _install_overrides(user=_normal_user(), allowed_account_ids={1}, roles={1: "operator"})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/assignable-users?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    items = response.json()
    assert [item["display_name"] for item in items] == ["Мария Оператор", "Иван Менеджер"]
    assert items[0]["role"] == "operator"


def test_action_center_done_and_ignored_are_auditable(action_center_service) -> None:
    _install_overrides(user=_normal_user(), allowed_account_ids={1}, roles={1: "operator"})
    try:
        with TestClient(app) as client:
            done_response = client.patch(
                "/api/v1/portal/actions/by-source",
                json={
                    "account_id": 1,
                    "source_module": "finance",
                    "source_id": "10",
                    "status": "done",
                    "comment": "Completed",
                },
            )
            ignored_response = client.patch(
                "/api/v1/portal/actions/by-source",
                json={
                    "account_id": 1,
                    "source_module": "data_quality",
                    "source_id": "30",
                    "status": "ignored",
                    "comment": "Not relevant",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert done_response.status_code == 200
    done = done_response.json()
    assert done["status"] == "done"
    assert done["review_status"] == "closed"
    assert done["closed_at"] is not None

    assert ignored_response.status_code == 200
    ignored = ignored_response.json()
    assert ignored["status"] == "ignored"
    assert ignored["review_status"] == "dismissed"
    assert ignored["dismissed_at"] is not None


def test_checker_content_action_does_not_inherit_finance_or_price_freshness() -> None:
    action = PortalActionRead(
        id="card_quality:173",
        source="card_quality_issues",
        source_module="checker",
        source_id="173",
        account_id=1,
        action_type="CARD_QUALITY_FIX",
        detector_code="title_missing",
        title="Название карточки отсутствует",
        priority="P1",
        severity="critical",
        status="new",
        reason="Название отсутствует.",
        next_step="Открыть товар.",
        confidence="medium",
        nm_id=12476203,
        trust_state="opportunity",
        impact_type="opportunity",
        payload={
            "content_quality_signal": True,
            "checker_problem_bridge": True,
            "data_freshness": {
                "required_sources": ["finance", "prices"],
                "source_status": "stale",
                "blocking_sources": ["finance"],
                "freshness_notes": ["legacy mixed freshness"],
            },
        },
    )

    assert action.data_freshness is not None
    assert action.data_freshness.required_sources == ["cards"]
    assert action.data_freshness.blocking_sources == []
    assert action.data_freshness.source_status == "fresh"
    assert action.payload["data_freshness"]["required_sources"] == ["cards"]
