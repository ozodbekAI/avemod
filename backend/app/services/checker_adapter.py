from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.models.accounts import WBAccount
from app.schemas.portal import PortalActionRead, PortalProductQualityRead
from app.services.guided_fixes import GuidedFixMapper


class CheckerAdapter:
    """Read-only adapter for the card quality checker service."""

    READ_ONLY_ENDPOINTS = (
        "GET /health",
        "GET /stores/{store_id}/cards",
        "GET /stores/{store_id}/cards/{card_id}",
        "GET /stores/{store_id}/cards/{card_id}/issues",
        "GET /stores/{store_id}/issues/grouped",
    )

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.guided_fixes = GuidedFixMapper()

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url)

    async def health(self, account: WBAccount | None = None) -> tuple[str, str | None]:
        if not self.is_configured:
            return "not_configured", "checker_base_url is not configured"
        if account is not None and self.resolve_store_id(account) is None:
            return "not_configured", "checker store is not mapped for this account"
        try:
            await self._request("GET", "/health", auth=False)
        except Exception:
            return "unavailable", "checker service is not reachable"
        return "ok", None

    def resolve_store_id(self, account: WBAccount) -> int | None:
        mapping = self.settings.checker_store_map or {}
        for key in (
            str(account.id),
            str(account.external_account_id or "").strip(),
            str(account.name or "").strip(),
        ):
            if key and key in mapping:
                return int(mapping[key])
        try:
            return int(str(account.external_account_id or "").strip())
        except (TypeError, ValueError):
            return None

    async def product_quality(
        self, account: WBAccount, *, nm_id: int
    ) -> PortalProductQualityRead:
        if not self.is_configured:
            return PortalProductQualityRead(
                status="not_configured", nm_id=nm_id, message="Checker не подключён"
            )
        store_id = self.resolve_store_id(account)
        if store_id is None:
            return PortalProductQualityRead(
                status="not_configured", nm_id=nm_id, message="Checker не подключён"
            )

        try:
            card = await self._find_card(store_id=store_id, nm_id=nm_id)
            if card is None:
                return PortalProductQualityRead(
                    status="empty",
                    store_id=store_id,
                    nm_id=nm_id,
                    message="card is not present in checker",
                )
            card_id = self._int(card.get("id"))
            detail = (
                await self._card_detail(store_id=store_id, card_id=card_id)
                if card_id is not None
                else card
            )
            issues = (
                await self._card_issues(store_id=store_id, card_id=card_id)
                if card_id is not None
                else []
            )
        except Exception:
            return PortalProductQualityRead(
                status="unavailable",
                store_id=store_id,
                nm_id=nm_id,
                message="checker service is unavailable",
            )

        return self._quality_from_checker_payload(
            store_id=store_id, nm_id=nm_id, card=detail or card, issues=issues
        )

    async def quality_actions(
        self, account: WBAccount, *, limit: int = 100
    ) -> tuple[list[PortalActionRead], str | None]:
        if not self.is_configured:
            return [], None
        store_id = self.resolve_store_id(account)
        if store_id is None:
            return [], None
        try:
            payload = await self._request(
                "GET",
                f"/stores/{store_id}/issues/grouped",
                params={
                    "limit": max(10, min(limit, 100)),
                    "bucket": "all",
                    "skip_validation": "true",
                },
            )
        except Exception:
            return [], "checker_issues"
        issues = self._flatten_grouped_issues(payload)
        return [
            self._action_from_issue(account_id=account.id, issue=issue)
            for issue in issues
            if isinstance(issue, dict)
        ], None

    async def _find_card(self, *, store_id: int, nm_id: int) -> dict[str, Any] | None:
        payload = await self._request(
            "GET",
            f"/stores/{store_id}/cards",
            params={"search": str(nm_id), "limit": 10, "page": 1},
        )
        items = payload.get("items") if isinstance(payload, dict) else []
        for item in items or []:
            if self._int((item or {}).get("nm_id")) == nm_id:
                return item
        return None

    async def _card_detail(self, *, store_id: int, card_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/stores/{store_id}/cards/{card_id}")

    async def _card_issues(
        self, *, store_id: int, card_id: int
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            f"/stores/{store_id}/cards/{card_id}/issues",
            params={"status": "pending", "bucket": "all"},
        )
        return (
            [item for item in payload if isinstance(item, dict)]
            if isinstance(payload, list)
            else []
        )

    def _flatten_grouped_issues(self, payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for key in ("critical", "warnings", "media", "postponed"):
            rows = payload.get(key) if isinstance(payload.get(key), list) else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                marker = str(row.get("id") or row.get("code") or len(result))
                if marker in seen:
                    continue
                seen.add(marker)
                result.append(row)
        return result

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        base_url = self._base_url
        if not base_url:
            raise RuntimeError("checker is not configured")
        headers: dict[str, str] = {}
        if auth and self.settings.checker_internal_token:
            headers["Authorization"] = f"Bearer {self.settings.checker_internal_token}"
        timeout = httpx.Timeout(float(self.settings.checker_http_timeout_seconds))
        async with httpx.AsyncClient(
            base_url=base_url, timeout=timeout, headers=headers
        ) as client:
            response = await client.request(method, path, params=params)
            response.raise_for_status()
            return response.json()

    @property
    def _base_url(self) -> str:
        return str(self.settings.checker_base_url or "").strip().rstrip("/")

    def _quality_from_checker_payload(
        self,
        *,
        store_id: int,
        nm_id: int,
        card: dict[str, Any],
        issues: list[dict[str, Any]],
    ) -> PortalProductQualityRead:
        category_counts: dict[str, int] = {}
        normalized_issues = [self._quality_issue(issue) for issue in issues]
        for issue in normalized_issues:
            category = str(issue.get("category") or "other")
            category_counts[category] = category_counts.get(category, 0) + 1
        critical_count = sum(
            1 for issue in normalized_issues if issue.get("severity") == "critical"
        )
        recommendations = [
            recommendation
            for recommendation in (
                issue.get("suggested_value")
                or issue.get("ai_suggested_value")
                or issue.get("description")
                for issue in normalized_issues
            )
            if recommendation
        ]
        return PortalProductQualityRead(
            status="ok",
            store_id=store_id,
            card_id=self._int(card.get("id")),
            nm_id=nm_id,
            score=self._int(card.get("score")),
            updated_at=self._datetime(card.get("updated_at") or card.get("checked_at")),
            score_breakdown=card.get("score_breakdown")
            if isinstance(card.get("score_breakdown"), dict)
            else {},
            critical_issue_count=self._int(card.get("critical_issues_count"))
            or critical_count,
            warning_issue_count=self._int(card.get("warnings_count"))
            or max(len(normalized_issues) - critical_count, 0),
            issues_by_category=category_counts,
            title_issues=[
                issue for issue in normalized_issues if issue.get("category") == "title"
            ],
            description_issues=[
                issue
                for issue in normalized_issues
                if issue.get("category") == "description"
            ],
            characteristics_issues=[
                issue
                for issue in normalized_issues
                if issue.get("category") == "characteristics"
            ],
            photo_video_issues=[
                issue
                for issue in normalized_issues
                if issue.get("category") in {"photos", "photo", "video", "media"}
            ],
            issues=normalized_issues,
            recommendations=recommendations[:10],
            raw={
                "card": self._safe_card_payload(card),
                "issue_count": len(normalized_issues),
            },
        )

    def _quality_issue(self, issue: dict[str, Any]) -> dict[str, Any]:
        category = self._quality_category(
            issue.get("category"), issue.get("field_path"), issue.get("code")
        )
        recommendation = (
            issue.get("recommendation")
            or issue.get("suggested_value")
            or issue.get("ai_suggested_value")
        )
        return {
            "id": issue.get("id"),
            "code": issue.get("code"),
            "type": category,
            "severity": self._quality_severity(issue.get("severity")),
            "category": category,
            "title": issue.get("title"),
            "description": issue.get("description"),
            "recommendation": recommendation,
            "field_path": issue.get("field_path"),
            "current_value": issue.get("current_value"),
            "suggested_value": issue.get("suggested_value"),
            "ai_suggested_value": issue.get("ai_suggested_value"),
            "ai_reason": issue.get("ai_reason_short") or issue.get("ai_reason"),
            "ai_reason_short": issue.get("ai_reason_short"),
            "ai_reason_full": issue.get("ai_reason_full"),
            "ai_confidence": issue.get("ai_confidence"),
            "allowed_values": issue.get("allowed_values")
            if isinstance(issue.get("allowed_values"), list)
            else [],
            "error_details": issue.get("error_details")
            if isinstance(issue.get("error_details"), list)
            else [],
            "alternatives": issue.get("alternatives")
            if isinstance(issue.get("alternatives"), list)
            else [],
            "ai_alternatives": issue.get("ai_alternatives")
            if isinstance(issue.get("ai_alternatives"), list)
            else [],
            "suggestion_kind": issue.get("suggestion_kind"),
            "has_confirmed_suggestion": issue.get("has_confirmed_suggestion"),
            "is_user_actionable": issue.get("is_user_actionable"),
            "ai_evidence": issue.get("ai_evidence")
            if isinstance(issue.get("ai_evidence"), dict)
            else {},
            "ai_used_sources": issue.get("ai_used_sources")
            if isinstance(issue.get("ai_used_sources"), list)
            else [],
            "photo_evidence": issue.get("photo_evidence")
            if isinstance(issue.get("photo_evidence"), list)
            else [],
            "score_impact": self._int(issue.get("score_impact")) or 0,
            "status": issue.get("status"),
            "requires_human_check": bool(issue.get("requires_human_check")),
            "photo_evidence": issue.get("photo_evidence")
            if isinstance(issue.get("photo_evidence"), list)
            else [],
        }

    def _action_from_issue(
        self, *, account_id: int, issue: dict[str, Any]
    ) -> PortalActionRead:
        severity = self._quality_severity(issue.get("severity"))
        category = self._quality_category(
            issue.get("category"), issue.get("field_path"), issue.get("code")
        )
        score_impact = self._int(issue.get("score_impact")) or 0
        priority = "P2" if severity == "critical" or score_impact >= 15 else "P4"
        nm_id = self._int(issue.get("card_nm_id"))
        source_issue_id = (
            str(issue.get("id"))
            if issue.get("id") is not None
            else str(issue.get("code") or "")
        )
        action_type = self._action_type_for_issue(
            category=category, code=issue.get("code")
        )
        guided_fix = self.guided_fixes.map(
            source_module="checker",
            action_type=action_type,
            nm_id=nm_id,
            target_id=source_issue_id,
        )
        return PortalActionRead(
            id=f"checker:{issue.get('id') or issue.get('code')}",
            source="checker_issues",
            source_module="checker",
            source_id=source_issue_id,
            account_id=account_id,
            action_type=action_type,
            title=str(issue.get("title") or self._default_action_title(action_type)),
            priority=priority,
            severity="high" if priority == "P2" else "low",
            status=self._portal_status(issue.get("status")),
            reason=str(
                issue.get("description")
                or issue.get("ai_reason_short")
                or issue.get("ai_reason")
                or ""
            ),
            next_step=str(
                issue.get("suggested_value")
                or issue.get("ai_suggested_value")
                or guided_fix.get("label")
                or "Открыть карточку и проверить рекомендацию"
            ),
            expected_effect_amount=None,
            confidence="medium" if issue.get("requires_human_check") else "high",
            nm_id=nm_id,
            sku_id=None,
            created_at=self._datetime(issue.get("created_at")),
            linked_entity={"nm_id": nm_id, "card_id": self._int(issue.get("card_id"))},
            payload={
                "category": category,
                "code": issue.get("code"),
                "field_path": issue.get("field_path"),
                "score_impact": score_impact,
                "card_title": issue.get("card_title"),
                "card_vendor_code": issue.get("card_vendor_code"),
                "guided_fix": guided_fix,
            },
            guided_fix=guided_fix,
            raw=self._safe_issue_payload(issue),
        )

    def _action_type_for_issue(self, *, category: str, code: Any) -> str:
        normalized_code = str(code or "").strip().lower()
        if (
            category in {"photos", "photo"}
            or "photo" in normalized_code
            or "image" in normalized_code
        ):
            return "photo_fix"
        if (
            category in {"video", "media"}
            or "video" in normalized_code
            or "media" in normalized_code
        ):
            return "media_quality_fix"
        return "CARD_QUALITY_FIX"

    def _default_action_title(self, action_type: str) -> str:
        if action_type == "photo_fix":
            return "Исправить фото карточки"
        if action_type == "media_quality_fix":
            return "Исправить медиа карточки"
        return "Проверить качество карточки"

    def _safe_card_payload(self, card: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in card.items()
            if key
            not in {
                "api_key",
                "token",
                "access_token",
                "refresh_token",
                "authorization",
            }
        }

    def _safe_issue_payload(self, issue: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in issue.items()
            if key
            not in {
                "api_key",
                "token",
                "access_token",
                "refresh_token",
                "authorization",
            }
        }

    def _quality_severity(self, value: Any) -> str:
        normalized = str(getattr(value, "value", value) or "").strip().lower()
        return "critical" if normalized == "critical" else "warning"

    def _quality_category(self, category: Any, field_path: Any, code: Any) -> str:
        normalized = str(category or "").strip().lower()
        if normalized in {
            "title",
            "description",
            "characteristics",
            "photos",
            "photo",
            "video",
            "media",
        }:
            return normalized
        field = str(field_path or "").strip().lower()
        issue_code = str(code or "").strip().lower()
        if field == "title" or issue_code.startswith("title"):
            return "title"
        if field == "description" or issue_code.startswith("description"):
            return "description"
        if field.startswith("characteristics."):
            return "characteristics"
        if field.startswith("photos") or issue_code in {
            "no_photos",
            "few_photos",
            "add_more_photos",
        }:
            return "photos"
        if field.startswith("videos") or issue_code == "no_video":
            return "video"
        return normalized or "other"

    def _portal_status(self, value: Any) -> str:
        normalized = str(value or "pending").strip().lower()
        return {
            "pending": "new",
            "fixed": "done",
            "auto_fixed": "done",
            "skipped": "ignored",
            "postponed": "postponed",
        }.get(normalized, "new")

    def _int(self, value: Any) -> int | None:
        try:
            return int(value) if value is not None and value != "" else None
        except (TypeError, ValueError):
            return None

    def _datetime(self, value: Any) -> datetime | str | None:
        if value is None or isinstance(value, datetime):
            return value
        return str(value)
