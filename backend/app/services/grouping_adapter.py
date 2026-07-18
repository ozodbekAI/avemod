from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.models.accounts import WBAccount
from app.schemas.portal import (
    PortalActionRead,
    PortalGroupingPreviewRead,
    PortalProductGroupingRead,
)


class GroupingAdapter:
    """Beta read-only adapter for the external grouping recommendation service."""

    SAFE_REFERENCE_ENDPOINTS = (
        "GET /api/health",
        "GET /api/dashboard",
        "GET /api/recommendations",
        "POST /api/recommendations/autofill?dry_run=true",
    )
    BLOCKED_DANGEROUS_ENDPOINTS = (
        "POST /api/groups/merge-wb",
        "POST /api/products/sync-wb",
        "POST /api/recommendations/autofill?dry_run=false",
        "POST /api/recommendations/upload?dry_run=false",
        "PUT /api/recommendations/{source_nmid}",
    )

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.grouping_enabled and self._base_url)

    async def health(self, account: WBAccount | None = None) -> tuple[str, str | None]:
        allowed, reason = self._account_allowed(account)
        if not allowed:
            return self._blocked_status(reason), reason
        try:
            payload = await self._request("GET", "/api/health", auth=False)
        except Exception:
            return "unavailable", "grouping beta service is not reachable"
        status = (
            str((payload or {}).get("status") or "").strip().lower()
            if isinstance(payload, dict)
            else ""
        )
        if status and status != "ok":
            return "unavailable", f"grouping beta health status is {status}"
        return "beta", "Grouping Beta is enabled for this test account"

    async def preview(
        self,
        account: WBAccount | None,
        *,
        nm_id: int | None,
        preset_key: str | None,
        recommendation_scenario_id: int | None,
        custom_config: dict[str, Any],
    ) -> PortalGroupingPreviewRead:
        allowed, reason = self._account_allowed(account)
        account_id = account.id if account is not None else None
        if not allowed:
            return PortalGroupingPreviewRead(
                status=self._blocked_status(reason),
                account_id=account_id,
                nm_id=nm_id,
                message=reason,
            )

        params: dict[str, Any] = {"dry_run": "true", "replace_existing": "false"}
        if preset_key:
            params["preset_key"] = preset_key
        if recommendation_scenario_id is not None:
            params["recommendation_scenario_id"] = recommendation_scenario_id
        try:
            summary = await self._request(
                "POST",
                "/api/recommendations/autofill",
                params=params,
                json_body={"custom_config": custom_config or {}},
            )
            product_recommendations = (
                await self.product_grouping(account, nm_id=nm_id)
                if nm_id is not None
                else None
            )
        except Exception:
            return PortalGroupingPreviewRead(
                status="unavailable",
                account_id=account_id,
                nm_id=nm_id,
                message="grouping beta service is unavailable",
            )

        recommendations = (
            product_recommendations.recommendations
            if product_recommendations is not None
            else []
        )
        return PortalGroupingPreviewRead(
            status="beta",
            account_id=account_id,
            nm_id=nm_id,
            summary=self._safe_payload(summary) if isinstance(summary, dict) else {},
            recommendations=recommendations,
            raw={
                "safe_reference_endpoints": list(self.SAFE_REFERENCE_ENDPOINTS),
                "blocked_dangerous_endpoints": list(self.BLOCKED_DANGEROUS_ENDPOINTS),
            },
        )

    async def product_grouping(
        self, account: WBAccount | None, *, nm_id: int
    ) -> PortalProductGroupingRead:
        allowed, reason = self._account_allowed(account)
        account_id = account.id if account is not None else None
        if not allowed:
            return PortalProductGroupingRead(
                status=self._blocked_status(reason),
                account_id=account_id,
                nm_id=nm_id,
                message=reason,
            )
        try:
            payload = await self._request(
                "GET",
                "/api/recommendations",
                params={"search": str(nm_id), "skip": 0, "limit": 50},
            )
        except Exception:
            return PortalProductGroupingRead(
                status="unavailable",
                account_id=account_id,
                nm_id=nm_id,
                message="grouping beta service is unavailable",
            )

        groups = payload.get("items") if isinstance(payload, dict) else []
        match = self._find_product_group(groups or [], nm_id=nm_id)
        if match is None:
            return PortalProductGroupingRead(
                status="empty",
                account_id=account_id,
                nm_id=nm_id,
                message="no grouping recommendations for this product",
                raw=self._safe_payload(payload) if isinstance(payload, dict) else {},
            )

        recommendations = [self._normalized_recommendation(match)]
        return PortalProductGroupingRead(
            status="beta",
            account_id=account_id,
            nm_id=nm_id,
            source=self._product_mini(match.get("source") or {}),
            recommendations=recommendations,
            recommendation_count=len(recommendations),
            raw=self._safe_payload(match),
        )

    async def recommendation_actions(
        self, account: WBAccount, *, limit: int = 50
    ) -> tuple[list[PortalActionRead], str | None]:
        allowed, _ = self._account_allowed(account)
        if not allowed:
            return [], None
        try:
            payload = await self._request(
                "GET",
                "/api/recommendations",
                params={"skip": 0, "limit": max(1, min(limit, 100))},
            )
        except Exception:
            return [], "grouping_recommendations"
        groups = payload.get("items") if isinstance(payload, dict) else []
        actions = []
        for group in groups or []:
            if not isinstance(group, dict):
                continue
            normalized = self._normalized_recommendation(group)
            if normalized["risk_level"] == "high" and not normalized["review_needed"]:
                continue
            actions.append(
                self._action_from_group(
                    account_id=account.id, group=group, normalized=normalized
                )
            )
        return actions, None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        base_url = self._base_url
        if not base_url:
            raise RuntimeError("grouping is not configured")
        headers: dict[str, str] = {}
        if auth and self.settings.grouping_internal_token:
            headers["Authorization"] = f"Bearer {self.settings.grouping_internal_token}"
        timeout = httpx.Timeout(float(self.settings.grouping_http_timeout_seconds))
        async with httpx.AsyncClient(
            base_url=base_url, timeout=timeout, headers=headers
        ) as client:
            response = await client.request(method, path, params=params, json=json_body)
            response.raise_for_status()
            return response.json()

    @property
    def _base_url(self) -> str:
        return str(self.settings.grouping_base_url or "").strip().rstrip("/")

    def _account_allowed(self, account: WBAccount | None) -> tuple[bool, str | None]:
        if not self.settings.grouping_enabled:
            return False, "grouping beta is disabled"
        if not self._base_url:
            return False, "grouping_base_url is not configured"
        if account is None:
            return False, "account is required for grouping beta"
        allowed_ids = {int(item) for item in self.settings.grouping_test_account_ids}
        if not allowed_ids or int(account.id) not in allowed_ids:
            return False, "grouping beta is enabled only for configured test accounts"
        return True, None

    def _blocked_status(self, reason: str | None) -> str:
        return "disabled" if reason == "grouping beta is disabled" else "not_configured"

    def _find_product_group(
        self, groups: list[Any], *, nm_id: int
    ) -> dict[str, Any] | None:
        for group in groups:
            if not isinstance(group, dict):
                continue
            source = (
                group.get("source") if isinstance(group.get("source"), dict) else {}
            )
            if self._int(source.get("nmid")) == nm_id:
                return group
            for target in group.get("targets") or []:
                if isinstance(target, dict) and self._int(target.get("nmid")) == nm_id:
                    return group
        return None

    def _action_from_group(
        self,
        *,
        account_id: int,
        group: dict[str, Any],
        normalized: dict[str, Any] | None = None,
    ) -> PortalActionRead:
        normalized = normalized or self._normalized_recommendation(group)
        source = group.get("source") if isinstance(group.get("source"), dict) else {}
        targets = [
            target for target in group.get("targets") or [] if isinstance(target, dict)
        ]
        source_nmid = self._int(source.get("nmid"))
        risk_level = str(normalized.get("risk_level") or "low")
        severity = risk_level if risk_level in {"high", "medium", "low"} else "low"
        confidence = self._action_confidence(normalized.get("confidence"))
        return PortalActionRead(
            id=f"grouping:{source_nmid or 'source'}",
            source="grouping_recommendations",
            source_module="grouping",
            source_id=str(normalized.get("candidate_group_id") or source_nmid)
            if (normalized.get("candidate_group_id") or source_nmid) is not None
            else None,
            account_id=account_id,
            nm_id=source_nmid,
            action_type="GROUPING_RECOMMENDATION",
            title="Проверить Beta-рекомендацию группировки",
            priority="P4",
            severity=severity,
            confidence=confidence,
            status="new",
            reason="Beta-рекомендация для связей карточек. Это только предпросмотр, без автослияния в WB.",
            next_step="Открыть предпросмотр группировки и проверить рекомендации вручную",
            created_at=self._datetime(group.get("updated_at")),
            can_update_status=True,
            can_update=True,
            payload={
                "beta": True,
                "beta_notice": "Beta / recommendation only. WB merge/apply is disabled.",
                "auto_merge_enabled": False,
                "candidate_group_id": normalized["candidate_group_id"],
                "nm_ids": normalized["nm_ids"],
                "risk_level": normalized["risk_level"],
                "risk_reasons": normalized["risk_reasons"],
                "expected_effect_note": normalized["expected_effect_note"],
                "preview_payload_available": normalized["preview_payload_available"],
                "review_needed": normalized["review_needed"],
                "recommendation_count": len(targets),
                "source": self._product_mini(source),
                "targets": [self._product_mini(target) for target in targets[:10]],
            },
            raw=self._safe_payload(group),
        )

    def _product_mini(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "nm_id": self._int(payload.get("nmid") or payload.get("nm_id")),
            "article": payload.get("article"),
            "subject": payload.get("subject"),
            "brand": payload.get("brand"),
            "color": payload.get("color"),
        }

    def _normalized_recommendation(self, group: dict[str, Any]) -> dict[str, Any]:
        source = group.get("source") if isinstance(group.get("source"), dict) else {}
        targets = [
            target for target in group.get("targets") or [] if isinstance(target, dict)
        ]
        primary_target = targets[0] if targets else {}
        source_nmid = self._int(source.get("nmid") or source.get("nm_id"))
        target_nmids = [
            item
            for item in (
                self._int(target.get("nmid") or target.get("nm_id"))
                for target in targets
            )
            if item is not None
        ]
        nm_ids = [item for item in [source_nmid, *target_nmids] if item is not None]
        candidate_group_id = self._first_present(
            group.get("candidate_group_id"),
            group.get("group_id"),
            group.get("id"),
            source_nmid,
        )
        confidence = self._first_present(
            group.get("confidence"), group.get("score"), group.get("match_score"), "low"
        )
        risk_level, risk_reasons = self._risk(group, source=source, targets=targets)
        expected_effect_note = str(
            self._first_present(
                group.get("expected_effect_note"),
                group.get("effect_note"),
                "Manual review may improve cross-card navigation; no WB changes will be applied by Finance.",
            )
        )
        return {
            "candidate_group_id": str(candidate_group_id)
            if candidate_group_id is not None
            else None,
            "nm_ids": nm_ids,
            "confidence": confidence,
            "risk_level": risk_level,
            "risk_reasons": risk_reasons,
            "expected_effect_note": expected_effect_note,
            "preview_payload_available": bool(targets),
            "auto_merge_enabled": False,
            "review_needed": self._bool(
                group.get("review_needed") or group.get("requires_review")
            ),
            **self._product_mini(primary_target),
            "source": self._product_mini(source),
            "targets": [self._product_mini(target) for target in targets],
        }

    def _risk(
        self,
        group: dict[str, Any],
        *,
        source: dict[str, Any],
        targets: list[dict[str, Any]],
    ) -> tuple[str, list[str]]:
        explicit = str(group.get("risk_level") or "").strip().lower()
        raw_reasons = group.get("risk_reasons")
        reasons = (
            [str(item) for item in raw_reasons if item]
            if isinstance(raw_reasons, list)
            else []
        )
        if explicit in {"low", "medium", "high"}:
            return explicit, reasons

        if not targets:
            reasons.append("no target cards in preview payload")
        if len(targets) > 20:
            reasons.append("candidate exceeds grouping service max links per source")
        source_subject = str(source.get("subject") or "").strip().lower()
        target_subjects = {
            str(target.get("subject") or "").strip().lower()
            for target in targets
            if target.get("subject")
        }
        if source_subject and any(
            subject and subject != source_subject for subject in target_subjects
        ):
            reasons.append("candidate mixes product subjects")

        if any(
            "exceeds" in reason or "mixes" in reason or "no target" in reason
            for reason in reasons
        ):
            return "high", reasons
        if reasons:
            return "medium", reasons
        return "low", []

    def _safe_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        secret_tokens = (
            "token",
            "api_key",
            "access_token",
            "refresh_token",
            "authorization",
            "secret",
            "password",
            "credential",
        )
        safe: dict[str, Any] = {}
        for key, value in payload.items():
            if any(token in key.lower() for token in secret_tokens):
                continue
            if isinstance(value, dict):
                safe[key] = self._safe_payload(value)
            elif isinstance(value, list):
                safe[key] = [
                    self._safe_payload(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                safe[key] = value
        return safe

    def _first_present(self, *values: Any) -> Any:
        for value in values:
            if value is not None and value != "":
                return value
        return None

    def _bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "y", "review_needed"}

    def _action_confidence(self, value: Any) -> str:
        if isinstance(value, (int, float)):
            if value >= 0.8:
                return "high"
            if value >= 0.5:
                return "medium"
            return "low"
        text = str(value or "").strip().lower()
        return text if text in {"high", "medium", "low"} else "low"

    def _int(self, value: Any) -> int | None:
        try:
            return int(value) if value is not None and value != "" else None
        except (TypeError, ValueError):
            return None

    def _datetime(self, value: Any) -> datetime | str | None:
        if value is None or isinstance(value, datetime):
            return value
        return str(value)
