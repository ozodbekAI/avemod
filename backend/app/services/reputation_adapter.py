from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.time import utcnow
from app.models.accounts import WBAccount
from app.schemas.operator import (
    ActionStatus,
    DraftOut,
    DraftType,
    ExternalStatus,
    OperatorModule,
    Priority,
    ResultEventOut,
    TrustState,
)
from app.schemas.portal import PortalActionRead, PortalDataBlock, PortalModuleHealthItem
from app.schemas.reputation import (
    ReputationDraftDecisionRequest,
    ReputationDraftMutationOut,
    ReputationInboxOut,
    ReputationItemOut,
    ReputationNoReplyRequest,
    ReputationPublishRequest,
    ReputationSettingsOut,
    ReputationSettingsUpdateRequest,
    ReputationSummaryOut,
    ReputationSyncOut,
)


class ReputationAdapter:
    """Optional adapter for the external reviews/questions/chats backend.

    The public contract stays in finance. The external service is used only as
    an internal integration and never receives or exposes finance JWTs or WB
    tokens through portal responses.
    """

    SAFE_REFERENCE_ENDPOINTS = (
        "GET /feedbacks/{shop_id}",
        "GET /feedbacks/{shop_id}/{wb_id}",
        "POST /feedbacks/{shop_id}/sync",
        "POST /feedbacks/{shop_id}/{wb_id}/draft",
        "GET /feedbacks/{shop_id}/{wb_id}/draft/latest",
        "POST /feedbacks/{shop_id}/{wb_id}/publish",
        "POST /feedbacks/{shop_id}/{wb_id}/no-reply-needed",
        "GET /questions/{shop_id}",
        "GET /questions/{shop_id}/{wb_id}",
        "POST /questions/{shop_id}/sync",
        "POST /questions/{shop_id}/{wb_id}/draft",
        "POST /questions/{shop_id}/{wb_id}/publish",
        "POST /questions/{shop_id}/{wb_id}/reject",
        "POST /questions/{shop_id}/{wb_id}/view",
        "GET /chats/page",
        "GET /chats/{shop_id}",
        "GET /chats/{shop_id}/{chat_id}/events",
        "POST /chats/{shop_id}/sync",
        "POST /chats/{shop_id}/{chat_id}/draft",
        "POST /chats/{shop_id}/{chat_id}/send",
        "GET /settings/{shop_id}",
        "PUT /settings/{shop_id}",
        "GET /drafts/{shop_id}/drafts",
        "GET /drafts/{shop_id}/drafts/pending",
        "GET /drafts/{shop_id}/drafts/stats",
        "GET /drafts/{shop_id}/drafts/{draft_id}",
        "PUT /drafts/{shop_id}/drafts/{draft_id}",
        "POST /drafts/{shop_id}/drafts/{draft_id}/regenerate",
        "POST /drafts/{shop_id}/drafts/{draft_id}/reject",
    )
    DANGEROUS_REFERENCE_ENDPOINTS = (
        "POST /drafts/{shop_id}/drafts/{draft_id}/approve",
        "POST /drafts/{shop_id}/drafts/approve-all",
    )

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.reputation_enabled and self._base_url)

    def runtime_status(self) -> dict[str, Any]:
        configured = bool(self.settings.reputation_enabled and self._base_url)
        return {
            "runtime_mode": "external_adapter" if configured else "disabled",
            "dangerous_actions_enabled": bool(
                self.settings.enable_reputation_publish
                or self.settings.enable_reputation_write_actions
            ),
            "publish_enabled": bool(self.settings.enable_reputation_publish),
            "auto_publish_enabled": False,
            "chat_send_enabled": bool(self.settings.enable_reputation_publish),
        }

    def resolve_shop_id(self, account: WBAccount) -> int | None:
        mapping = self.settings.reputation_shop_map or {}
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

    async def get_module_status(
        self, account: WBAccount | None = None
    ) -> PortalModuleHealthItem:
        if not self.settings.reputation_enabled:
            return PortalModuleHealthItem(
                module="reputation",
                status="disabled",
                enabled=False,
                configured=False,
                message="reputation module is disabled",
                **self.runtime_status(),
            )
        if not self._base_url:
            return PortalModuleHealthItem(
                module="reputation",
                status="not_configured",
                enabled=True,
                configured=False,
                message="reputation_base_url is not configured",
                **self.runtime_status(),
            )
        if account is not None and self.resolve_shop_id(account) is None:
            return PortalModuleHealthItem(
                module="reputation",
                status="degraded",
                enabled=True,
                configured=True,
                message="reputation service is configured, but this account has no reputation shop mapping",
                warnings=["reputation_shop_map is missing for this account"],
                **self.runtime_status(),
            )
        try:
            await self._request("GET", "/health", auth=False)
        except Exception:
            return PortalModuleHealthItem(
                module="reputation",
                status="unavailable",
                enabled=True,
                configured=True,
                message="reputation service is unavailable",
                **self.runtime_status(),
            )
        return PortalModuleHealthItem(
            module="reputation",
            status="ok",
            enabled=True,
            configured=True,
            message="reputation service is available",
            **self.runtime_status(),
        )

    async def health(self, account: WBAccount | None = None) -> tuple[str, str | None]:
        item = await self.get_module_status(account)
        return item.status, item.message

    async def sync_reputation(self, account: WBAccount) -> ReputationSyncOut:
        shop_id, blocked = self._shop_or_block(account)
        if blocked is not None:
            return ReputationSyncOut(account_id=account.id, **blocked)
        unavailable: list[str] = []
        job_ids: list[str] = []
        for kind, path in (
            ("reviews", f"/feedbacks/{shop_id}/sync"),
            ("questions", f"/questions/{shop_id}/sync"),
            ("chats", f"/chats/{shop_id}/sync"),
        ):
            try:
                payload = await self._request("POST", path, json_body={})
                job_id = self._str(
                    (payload or {}).get("job_id") or (payload or {}).get("id")
                )
                if job_id:
                    job_ids.append(f"{kind}:{job_id}")
            except Exception:
                unavailable.append(kind)
        status = "ok" if len(unavailable) < 3 else "unavailable"
        return ReputationSyncOut(
            status=status,
            account_id=account.id,
            job_id=",".join(job_ids) if job_ids else None,
            message="reputation sync requested"
            if status == "ok"
            else "reputation sync is unavailable",
            data={
                "job_ids": job_ids,
                "safe_reference_endpoints": list(self.SAFE_REFERENCE_ENDPOINTS),
                "dangerous_reference_endpoints": list(
                    self.DANGEROUS_REFERENCE_ENDPOINTS
                ),
            },
            unavailable_sources=unavailable,
            trust_state=TrustState.OPERATIONAL
            if status == "ok"
            else TrustState.UNAVAILABLE,
        )

    async def list_inbox(
        self,
        account: WBAccount,
        *,
        item_type: str | None = None,
        status: str | None = None,
        rating: int | None = None,
        sentiment: str | None = None,
        priority: str | None = None,
        nm_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ReputationInboxOut:
        shop_id, blocked = self._shop_or_block(account)
        if blocked is not None:
            return ReputationInboxOut(
                account_id=account.id, limit=limit, offset=offset, **blocked
            )
        types = self._item_types(item_type)
        unavailable: list[str] = []
        items: list[ReputationItemOut] = []
        for kind in types:
            try:
                payload = await self._list_external(
                    kind, shop_id=shop_id, limit=limit + offset
                )
            except Exception:
                unavailable.append(kind)
                continue
            rows = self._rows(payload)
            items.extend(
                self._item_from_payload(account_id=account.id, kind=kind, payload=row)
                for row in rows
            )
        filtered = [
            item
            for item in items
            if (nm_id is None or item.nm_id == nm_id)
            and (status is None or item.status == self._status(status))
            and (rating is None or item.rating == rating)
            and (sentiment is None or item.sentiment == sentiment)
            and (priority is None or item.priority == self._priority_value(priority))
            and self._within_date_range(
                item.received_at, date_from=date_from, date_to=date_to
            )
        ]
        filtered.sort(
            key=lambda item: (
                self._priority_rank(item.priority),
                -self._sort_timestamp(item.received_at),
            ),
            reverse=False,
        )
        page = filtered[offset : offset + limit]
        summary = self._summary(filtered)
        return ReputationInboxOut(
            status="ok" if not unavailable or page else "unavailable",
            account_id=account.id,
            total=len(filtered),
            limit=limit,
            offset=offset,
            items=page,
            summary=summary,
            trust_state=TrustState.OPERATIONAL
            if not unavailable
            else TrustState.PROVISIONAL,
            unavailable_sources=unavailable,
        )

    async def summary(
        self,
        account: WBAccount,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> ReputationSummaryOut:
        inbox = await self.list_inbox(
            account, date_from=date_from, date_to=date_to, limit=200, offset=0
        )
        if inbox.status not in {"ok", "empty"}:
            return ReputationSummaryOut(
                status=inbox.status,
                account_id=account.id,
                unavailable_sources=list(inbox.unavailable_sources),
                warnings=list(inbox.warnings),
                trust_state=inbox.trust_state,
                **self.runtime_status(),
            )
        ratings = [item.rating for item in inbox.items if item.rating is not None]
        sentiment_counts: dict[str, int] = {}
        priority_counts: dict[str, int] = {}
        for item in inbox.items:
            if item.sentiment:
                sentiment_counts[item.sentiment] = (
                    sentiment_counts.get(item.sentiment, 0) + 1
                )
            priority_key = (
                item.priority.value
                if hasattr(item.priority, "value")
                else str(item.priority)
            )
            priority_counts[priority_key] = priority_counts.get(priority_key, 0) + 1
        return ReputationSummaryOut(
            status="ok",
            account_id=account.id,
            unanswered_reviews_count=int(
                inbox.summary.get("unanswered_reviews_count") or 0
            ),
            unanswered_questions_count=int(
                inbox.summary.get("unanswered_questions_count") or 0
            ),
            unread_chats_count=int(inbox.summary.get("unread_chats_count") or 0),
            negative_unanswered_count=int(
                inbox.summary.get("negative_unanswered_count") or 0
            ),
            draft_ready_count=sum(
                1 for item in inbox.items if item.status in {"draft_ready", "approved"}
            ),
            average_rating=sum(ratings) / len(ratings) if ratings else None,
            sentiment=sentiment_counts,
            priority=priority_counts,
            data={"total": inbox.total},
            trust_state=inbox.trust_state,
            **self.runtime_status(),
        )

    async def get_item(self, account: WBAccount, *, item_id: str) -> ReputationItemOut:
        shop_id, blocked = self._shop_or_block(account)
        kind, external_id = self._split_item_id(item_id)
        if blocked is not None:
            return ReputationItemOut(
                id=item_id,
                item_type=kind or "review",
                account_id=account.id,
                status="failed",
                trust_state=TrustState.UNAVAILABLE,
                warnings=blocked.get("warnings", []),
            )
        try:
            payload = await self._detail_external(
                kind, shop_id=shop_id, external_id=external_id
            )
        except Exception:
            return ReputationItemOut(
                id=item_id,
                item_type=kind,
                external_id=external_id,
                account_id=account.id,
                status="failed",
                trust_state=TrustState.UNAVAILABLE,
                warnings=["reputation service is unavailable"],
            )
        return self._item_from_payload(
            account_id=account.id, kind=kind, payload=payload
        )

    async def generate_draft(
        self,
        account: WBAccount,
        *,
        item_id: str,
        draft_type: DraftType | str | None = None,
    ) -> ReputationDraftMutationOut:
        shop_id, blocked = self._shop_or_block(account)
        kind, external_id = self._split_item_id(item_id)
        if blocked is not None:
            return ReputationDraftMutationOut(account_id=account.id, **blocked)
        effective_type = self._draft_type(kind, draft_type)
        try:
            payload = await self._request(
                "POST",
                self._draft_path(kind, shop_id=shop_id, external_id=external_id),
                json_body={},
            )
        except Exception:
            return ReputationDraftMutationOut(
                status="unavailable",
                account_id=account.id,
                message="reputation draft generation is unavailable",
                unavailable_sources=["reputation"],
            )
        draft = self._draft_from_payload(
            account_id=account.id,
            kind=kind,
            external_id=external_id,
            draft_type=effective_type,
            payload=payload,
        )
        return ReputationDraftMutationOut(
            status="ok",
            account_id=account.id,
            draft=draft,
            trust_state=TrustState.PROVISIONAL,
        )

    async def approve_draft(
        self, account: WBAccount, *, draft_id: str
    ) -> ReputationDraftMutationOut:
        shop_id, blocked = self._shop_or_block(account)
        if blocked is not None:
            return ReputationDraftMutationOut(account_id=account.id, **blocked)
        kind, external_id = self._split_item_id(draft_id)
        draft = self._draft_from_payload(
            account_id=account.id,
            kind=kind,
            external_id=external_id,
            draft_type=self._draft_type(kind, None),
            payload={
                "id": draft_id,
                "source_type": kind,
                "source_id": external_id,
                "status": "approved",
            },
            approved=True,
        )
        return ReputationDraftMutationOut(
            status="ok",
            account_id=account.id,
            draft=draft,
            message="Draft approved locally in finance; publishing remains behind manual confirm.",
            warnings=["reputation_external_approve_not_used"],
            trust_state=TrustState.PROVISIONAL,
        )

    async def regenerate_draft(
        self,
        account: WBAccount,
        *,
        draft_id: str,
        request: ReputationDraftDecisionRequest | None = None,
    ) -> ReputationDraftMutationOut:
        shop_id, blocked = self._shop_or_block(account)
        if blocked is not None:
            return ReputationDraftMutationOut(account_id=account.id, **blocked)
        try:
            payload = await self._request(
                "POST",
                f"/drafts/{shop_id}/drafts/{draft_id}/regenerate",
                json_body=(request.payload if request is not None else {}),
            )
        except Exception:
            return ReputationDraftMutationOut(
                status="unavailable",
                account_id=account.id,
                message="reputation draft regeneration is unavailable",
                unavailable_sources=["reputation"],
            )
        draft = self._draft_from_payload(
            account_id=account.id,
            kind=self._kind_from_payload(payload) or self._split_item_id(draft_id)[0],
            external_id=self._str(
                (payload or {}).get("source_id") or (payload or {}).get("wb_id")
            ),
            draft_type=self._draft_type(
                self._kind_from_payload(payload) or self._split_item_id(draft_id)[0],
                None,
            ),
            payload=payload,
        )
        return ReputationDraftMutationOut(
            status="ok",
            account_id=account.id,
            draft=draft,
            trust_state=TrustState.PROVISIONAL,
        )

    async def reject_draft(
        self,
        account: WBAccount,
        *,
        draft_id: str,
        request: ReputationDraftDecisionRequest | None = None,
    ) -> ReputationDraftMutationOut:
        shop_id, blocked = self._shop_or_block(account)
        if blocked is not None:
            return ReputationDraftMutationOut(account_id=account.id, **blocked)
        try:
            payload = await self._request(
                "POST",
                f"/drafts/{shop_id}/drafts/{draft_id}/reject",
                json_body={"reason": request.reason, **(request.payload or {})}
                if request is not None
                else {},
            )
        except Exception:
            return ReputationDraftMutationOut(
                status="unavailable",
                account_id=account.id,
                message="reputation draft rejection is unavailable",
                unavailable_sources=["reputation"],
            )
        draft = self._draft_from_payload(
            account_id=account.id,
            kind=self._kind_from_payload(payload) or self._split_item_id(draft_id)[0],
            external_id=self._str(
                (payload or {}).get("source_id") or (payload or {}).get("wb_id")
            ),
            draft_type=self._draft_type(
                self._kind_from_payload(payload) or self._split_item_id(draft_id)[0],
                None,
            ),
            payload=payload,
        )
        if draft is not None:
            draft.status = ActionStatus.IGNORED
        return ReputationDraftMutationOut(
            status="ok",
            account_id=account.id,
            draft=draft,
            trust_state=TrustState.PROVISIONAL,
        )

    async def mark_no_reply_needed(
        self,
        account: WBAccount,
        *,
        item_id: str,
        request: ReputationNoReplyRequest,
    ) -> ResultEventOut:
        if not request.confirm:
            return ResultEventOut(
                module=OperatorModule.REPUTATION,
                event_type="no_reply_blocked_confirmation_required",
                account_id=account.id,
                title="Требуется ручное подтверждение",
                message="Отметка «ответ не нужен» требует явного confirm=true.",
                success=False,
                occurred_at=utcnow(),
                data={
                    "item_id": item_id,
                    "external_submit_attempted": False,
                    "external_write_enabled": bool(
                        self.settings.enable_reputation_write_actions
                    ),
                    "local_only": False,
                },
                warnings=["manual_confirm_required"],
            )
        kind, external_id = self._split_item_id(item_id)
        if kind != "review":
            return ResultEventOut(
                module=OperatorModule.REPUTATION,
                event_type="no_reply_marked_local",
                account_id=account.id,
                title="No reply needed",
                message="Item marked as no-reply-needed in finance; upstream no-reply endpoint is only available for reviews.",
                success=True,
                occurred_at=utcnow(),
                data={
                    "item_id": item_id,
                    "item_type": kind,
                    "reason": request.reason,
                    "external_submit_attempted": False,
                    "external_write_enabled": bool(
                        self.settings.enable_reputation_write_actions
                    ),
                    "local_only": True,
                },
            )
        if not self.settings.enable_reputation_write_actions:
            return ResultEventOut(
                module=OperatorModule.REPUTATION,
                event_type="no_reply_recorded_local",
                account_id=account.id,
                title="No reply needed recorded locally",
                message="Item marked as no-reply-needed in finance only; external reputation writes are disabled.",
                success=True,
                occurred_at=utcnow(),
                data={
                    "item_id": item_id,
                    "item_type": kind,
                    "reason": request.reason,
                    "external_submit_attempted": False,
                    "external_write_enabled": False,
                    "local_only": True,
                },
                warnings=["external_reputation_write_disabled"],
            )
        shop_id, blocked = self._shop_or_block(account)
        if blocked is not None:
            return ResultEventOut(
                module=OperatorModule.REPUTATION,
                event_type="no_reply_unavailable",
                account_id=account.id,
                title="No-reply action unavailable",
                message=str(
                    blocked.get("message") or "reputation module is unavailable"
                ),
                success=False,
                occurred_at=utcnow(),
                data={
                    "item_id": item_id,
                    "item_type": kind,
                    "external_submit_attempted": False,
                    "external_write_enabled": True,
                    "local_only": False,
                },
                warnings=list(blocked.get("warnings") or []),
            )
        try:
            payload = await self._request(
                "POST",
                f"/feedbacks/{shop_id}/{external_id}/no-reply-needed",
                json_body={"reason": request.reason, **(request.payload or {})},
            )
        except Exception:
            return ResultEventOut(
                module=OperatorModule.REPUTATION,
                event_type="no_reply_failed",
                account_id=account.id,
                title="No-reply action failed",
                message="reputation service could not mark no-reply-needed",
                success=False,
                occurred_at=utcnow(),
                data={
                    "item_id": item_id,
                    "item_type": kind,
                    "external_submit_attempted": True,
                    "external_write_enabled": True,
                    "local_only": False,
                    "unavailable_sources": ["reputation"],
                },
                warnings=["reputation_unavailable"],
            )
        return ResultEventOut(
            module=OperatorModule.REPUTATION,
            event_type="no_reply_marked",
            external_status=ExternalStatus.CLOSED,
            account_id=account.id,
            title="No reply needed",
            message="Item marked as no-reply-needed after manual confirmation.",
            success=True,
            occurred_at=utcnow(),
            data={
                "item_id": item_id,
                "item_type": kind,
                "external_submit_attempted": True,
                "external_write_enabled": True,
                "local_only": False,
                "external_result": self._safe_payload(payload or {}),
            },
        )

    async def get_settings(self, account: WBAccount) -> ReputationSettingsOut:
        shop_id, blocked = self._shop_or_block(account)
        if blocked is not None:
            return ReputationSettingsOut(account_id=account.id, **blocked)
        try:
            payload = await self._request("GET", f"/settings/{shop_id}")
        except Exception:
            return ReputationSettingsOut(
                status="unavailable",
                account_id=account.id,
                message="reputation settings are unavailable",
                unavailable_sources=["reputation"],
                **self.runtime_status(),
            )
        return self._settings_from_payload(account_id=account.id, payload=payload)

    async def update_settings(
        self,
        account: WBAccount,
        *,
        request: ReputationSettingsUpdateRequest,
    ) -> ReputationSettingsOut:
        shop_id, blocked = self._shop_or_block(account)
        if blocked is not None:
            return ReputationSettingsOut(account_id=account.id, **blocked)
        body = self._settings_update_payload(request)
        try:
            payload = await self._request("PUT", f"/settings/{shop_id}", json_body=body)
        except Exception:
            return ReputationSettingsOut(
                status="unavailable",
                account_id=account.id,
                message="reputation settings update is unavailable",
                unavailable_sources=["reputation"],
                **self.runtime_status(),
            )
        return self._settings_from_payload(
            account_id=account.id, payload=payload, warnings=["auto_publish_forced_off"]
        )

    async def publish_reply(
        self,
        account: WBAccount,
        *,
        draft_id: str,
        request: ReputationPublishRequest,
    ) -> ResultEventOut:
        if not request.confirm:
            return ResultEventOut(
                module=OperatorModule.REPUTATION,
                event_type="publish_blocked_confirmation_required",
                account_id=account.id,
                draft_id=draft_id,
                title="Требуется ручное подтверждение",
                message="Публикация требует явного confirm=true.",
                success=False,
                occurred_at=utcnow(),
                data={
                    "draft_id": draft_id,
                    "external_submit_attempted": False,
                    "external_write_enabled": bool(
                        self.settings.enable_reputation_publish
                    ),
                    "local_only": False,
                },
                warnings=["manual_confirm_required"],
            )
        if not self.settings.enable_reputation_publish:
            return ResultEventOut(
                module=OperatorModule.REPUTATION,
                event_type="publish_disabled_by_feature_flag",
                account_id=account.id,
                draft_id=draft_id,
                title="Публикация ответа отключена",
                message="Публикация ответов отключена настройкой ENABLE_REPUTATION_PUBLISH=false.",
                success=False,
                occurred_at=utcnow(),
                data={
                    "draft_id": draft_id,
                    "external_submit_attempted": False,
                    "external_write_enabled": False,
                    "local_only": True,
                },
                warnings=["reputation_publish_disabled"],
            )
        shop_id, blocked = self._shop_or_block(account)
        if blocked is not None:
            return ResultEventOut(
                module=OperatorModule.REPUTATION,
                event_type="publish_unavailable",
                account_id=account.id,
                draft_id=draft_id,
                title="Reputation publish unavailable",
                message=str(
                    blocked.get("message") or "reputation module is unavailable"
                ),
                success=False,
                occurred_at=utcnow(),
                data={
                    "draft_id": draft_id,
                    "external_submit_attempted": False,
                    "external_write_enabled": True,
                    "local_only": False,
                },
                warnings=list(blocked.get("warnings") or []),
            )
        kind, external_id = self._draft_target(draft_id, request.payload)
        try:
            body = {"text": request.text} if request.text else {}
            form = None
            if kind == "chat":
                form = {
                    "message": request.text or "",
                    "use_latest_draft": "true" if not request.text else "false",
                }
                body = None
            payload = await self._request(
                "POST",
                self._publish_path(kind, shop_id=shop_id, external_id=external_id),
                json_body=body,
                form_data=form,
            )
        except Exception:
            return ResultEventOut(
                module=OperatorModule.REPUTATION,
                event_type="publish_failed",
                account_id=account.id,
                draft_id=draft_id,
                title="Reputation publish failed",
                message="reputation service could not publish the reply",
                success=False,
                occurred_at=utcnow(),
                data={
                    "source_type": kind,
                    "source_id": external_id,
                    "unavailable_sources": ["reputation"],
                },
                warnings=["reputation_unavailable"],
            )
        return ResultEventOut(
            module=OperatorModule.REPUTATION,
            event_type="publish_confirmed",
            external_status=ExternalStatus.SUBMITTED,
            account_id=account.id,
            draft_id=draft_id,
            title="Reply published",
            message="Reply was published after manual confirmation.",
            success=True,
            occurred_at=utcnow(),
            data={
                "source_type": kind,
                "source_id": external_id,
                "external_result": self._safe_payload(payload or {}),
            },
        )

    async def reputation_actions(
        self, account: WBAccount, *, limit: int = 50
    ) -> tuple[list[PortalActionRead], str | None]:
        inbox = await self.list_inbox(account, limit=limit, offset=0)
        if inbox.status in {"not_configured", "disabled"}:
            return [], None
        if inbox.status == "unavailable":
            return [], "reputation"
        return [
            self._action_from_item(item) for item in inbox.items if item.needs_reply
        ], None

    async def profit_doctor_signals(
        self,
        *,
        account_id: int,
        date_from: Any = None,
        date_to: Any = None,
        nm_id: int | None = None,
    ) -> list[dict[str, Any]]:
        account = self._account_stub(account_id)
        inbox = await self.list_inbox(
            account,
            item_type=None,
            nm_id=nm_id,
            date_from=date_from,
            date_to=date_to,
            limit=100,
            offset=0,
        )
        if inbox.status not in {"ok", "empty"}:
            return []
        signals: list[dict[str, Any]] = []
        for item in inbox.items:
            if not item.needs_reply:
                continue
            if (
                item.item_type == "review"
                and item.rating is not None
                and item.rating > 3
            ):
                continue
            signals.append(
                {
                    "nm_id": item.nm_id,
                    "priority": item.priority,
                    "title": self._action_title(item),
                    "reason": item.text or item.title,
                    "next_step": "Open Reputation Operator and prepare a manual reply draft.",
                    "impact": self._impact(item),
                    "source_id": item.id,
                }
            )
        return signals

    async def product_360(
        self, *, account_id: int, nm_id: int, **_: Any
    ) -> PortalDataBlock:
        account = self._account_stub(account_id)
        inbox = await self.list_inbox(account, nm_id=nm_id, limit=50, offset=0)
        if inbox.status not in {"ok", "empty"}:
            return PortalDataBlock(
                status=inbox.status,
                data={
                    "status": inbox.status,
                    "unanswered_reviews_count": None,
                    "unanswered_questions_count": None,
                    "negative_unanswered_count": None,
                    "unread_chats_count": None,
                    "last_items": [],
                    "draft_ready_count": None,
                    "next_reputation_action": None,
                    "trust_state": inbox.trust_state.value
                    if hasattr(inbox.trust_state, "value")
                    else str(inbox.trust_state),
                    "unavailable_sources": list(inbox.unavailable_sources),
                    "warnings": list(inbox.warnings),
                },
                message="reputation data is unavailable",
            )
        items = list(inbox.items)
        actions = [
            self._action_from_item(item).model_dump(mode="json")
            for item in items
            if item.needs_reply
        ]
        actions.sort(
            key=lambda item: (
                {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}.get(
                    str(item.get("priority") or "P3").upper(), 9
                ),
                item.get("created_at") or "",
            )
        )
        summary = dict(inbox.summary or self._summary(items))
        return PortalDataBlock(
            status="ok" if inbox.items else "empty",
            data={
                "status": "ok" if inbox.items else "empty",
                "unanswered_reviews_count": int(
                    summary.get("unanswered_reviews_count") or 0
                ),
                "unanswered_questions_count": int(
                    summary.get("unanswered_questions_count") or 0
                ),
                "negative_unanswered_count": int(
                    summary.get("negative_unanswered_count") or 0
                ),
                "unread_chats_count": int(summary.get("unread_chats_count") or 0),
                "last_items": [item.model_dump(mode="json") for item in items[:10]],
                "draft_ready_count": sum(
                    1
                    for item in items
                    if item.status in {"draft_ready", "approved"}
                    or item.draft is not None
                ),
                "next_reputation_action": actions[0] if actions else None,
                "trust_state": inbox.trust_state.value
                if hasattr(inbox.trust_state, "value")
                else str(inbox.trust_state),
                "summary": summary,
                "items": [item.model_dump(mode="json") for item in items],
                "actions": actions,
                "unavailable_sources": list(inbox.unavailable_sources),
                "warnings": list(inbox.warnings),
            },
        )

    async def _list_external(self, kind: str, *, shop_id: int, limit: int) -> Any:
        if kind == "review":
            return await self._request(
                "GET", f"/feedbacks/{shop_id}", params={"limit": limit, "offset": 0}
            )
        if kind == "question":
            return await self._request(
                "GET", f"/questions/{shop_id}", params={"limit": limit, "offset": 0}
            )
        return await self._request(
            "GET", f"/chats/{shop_id}", params={"limit": limit, "offset": 0}
        )

    async def _detail_external(
        self, kind: str, *, shop_id: int, external_id: str
    ) -> Any:
        if kind == "review":
            return await self._request("GET", f"/feedbacks/{shop_id}/{external_id}")
        if kind == "question":
            return await self._request("GET", f"/questions/{shop_id}/{external_id}")
        events = await self._request("GET", f"/chats/{shop_id}/{external_id}/events")
        return {"chat_id": external_id, "events": events}

    def _draft_path(self, kind: str, *, shop_id: int, external_id: str) -> str:
        if kind == "review":
            return f"/feedbacks/{shop_id}/{external_id}/draft"
        if kind == "question":
            return f"/questions/{shop_id}/{external_id}/draft"
        return f"/chats/{shop_id}/{external_id}/draft"

    def _publish_path(self, kind: str, *, shop_id: int, external_id: str) -> str:
        if kind == "review":
            return f"/feedbacks/{shop_id}/{external_id}/publish"
        if kind == "question":
            return f"/questions/{shop_id}/{external_id}/publish"
        return f"/chats/{shop_id}/{external_id}/send"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        if not self._base_url:
            raise RuntimeError("reputation is not configured")
        headers: dict[str, str] = {}
        if auth and self.settings.reputation_internal_token:
            headers["Authorization"] = (
                f"Bearer {self.settings.reputation_internal_token}"
            )
        timeout = httpx.Timeout(float(self.settings.reputation_http_timeout_seconds))
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout, headers=headers
        ) as client:
            response = await client.request(
                method, path, params=params, json=json_body, data=form_data
            )
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return {}

    @property
    def _base_url(self) -> str:
        return str(self.settings.reputation_base_url or "").strip().rstrip("/")

    def _shop_or_block(
        self, account: WBAccount
    ) -> tuple[int | None, dict[str, Any] | None]:
        if not self.settings.reputation_enabled:
            return None, self._blocked("disabled", "reputation module is disabled")
        if not self._base_url:
            return None, self._blocked(
                "not_configured", "reputation_base_url is not configured"
            )
        shop_id = self.resolve_shop_id(account)
        if shop_id is None:
            return None, self._blocked(
                "not_configured",
                "reputation shop is not mapped for this account",
                ["reputation_shop_map is missing for this account"],
            )
        return shop_id, None

    def _blocked(
        self, status: str, message: str, warnings: list[str] | None = None
    ) -> dict[str, Any]:
        trust_state = (
            TrustState.UNAVAILABLE
            if status in {"disabled", "not_configured", "unavailable"}
            else TrustState.PROVISIONAL
        )
        return {
            "status": status,
            "message": message,
            "warnings": warnings or [],
            "unavailable_sources": ["reputation"],
            "trust_state": trust_state,
            **self.runtime_status(),
        }

    def _item_types(self, item_type: str | None) -> list[str]:
        normalized = str(item_type or "").strip().lower()
        aliases = {
            "all": "",
            "feedback": "review",
            "feedbacks": "review",
            "reviews": "review",
            "questions": "question",
            "chats": "chat",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized in {"review", "question", "chat"}:
            return [normalized]
        return ["review", "question", "chat"]

    def _rows(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in (
            "items",
            "results",
            "feedbacks",
            "questions",
            "chats",
            "sessions",
            "data",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = self._rows(value)
                if nested:
                    return nested
        return []

    def _item_from_payload(
        self, *, account_id: int, kind: str, payload: dict[str, Any]
    ) -> ReputationItemOut:
        external_id = self._external_id(kind, payload)
        answer = (
            payload.get("answer")
            or payload.get("answer_text")
            or payload.get("reply")
            or payload.get("last_answer")
        )
        rating = self._int(payload.get("rating") or payload.get("productValuation"))
        if rating is None:
            rating = self._int(payload.get("product_valuation"))
        status = self._item_status(kind=kind, payload=payload, answer=answer)
        nm_id = self._nm_id(payload)
        text = self._text(kind, payload)
        received_at = self._datetime(
            payload.get("created_date")
            or payload.get("createdDate")
            or payload.get("created_at")
            or payload.get("createdAt")
            or payload.get("updated_at")
            or payload.get("updatedAt")
            or payload.get("last_message_at")
            or payload.get("lastMessageAt")
            or payload.get("date")
        )
        safe_payload = self._safe_payload(payload)
        draft_payload = (
            payload.get("draft") if isinstance(payload.get("draft"), dict) else None
        )
        draft_id = payload.get("draft_id") or payload.get("latest_draft_id")
        return ReputationItemOut(
            id=f"{kind}:{external_id}",
            item_type=kind,
            item_id=f"{kind}:{external_id}",
            kind=kind,
            external_id=external_id,
            external_status=self._external_status(status),
            account_id=account_id,
            nm_id=nm_id,
            rating=rating,
            buyer_name=self._masked_name(
                payload.get("user_name")
                or payload.get("client_name")
                or payload.get("buyer_name")
            ),
            title=self._title(kind, payload),
            text=text,
            sentiment=self._sentiment(rating=rating, text=text, payload=payload),
            priority=self._priority(kind=kind, rating=rating, status=status),
            status=status,
            trust_state=TrustState.PROVISIONAL,
            received_at=received_at,
            created_at=received_at,
            replied_at=self._datetime(
                payload.get("answer_created_at") or payload.get("replied_at")
            ),
            needs_reply=status in {"new", "needs_reply", "failed"},
            draft=self._draft_from_payload(
                account_id=account_id,
                kind=kind,
                external_id=external_id,
                draft_type=self._draft_type(kind, None),
                payload=draft_payload
                or {"id": draft_id, "text": payload.get("draft_text")},
            )
            if draft_payload or draft_id or payload.get("draft_text")
            else None,
            data=safe_payload,
            source_payload=safe_payload,
        )

    def _draft_from_payload(
        self,
        *,
        account_id: int,
        kind: str,
        external_id: str | None,
        draft_type: DraftType,
        payload: Any,
        approved: bool = False,
    ) -> DraftOut:
        raw = payload if isinstance(payload, dict) else {}
        draft_id = self._str(
            raw.get("id")
            or raw.get("draft_id")
            or raw.get("draftId")
            or f"{kind}:{external_id}"
        )
        text = (
            self._str(
                raw.get("text")
                or raw.get("answer")
                or raw.get("body")
                or raw.get("message")
            )
            or ""
        )
        return DraftOut(
            id=draft_id,
            draft_type=draft_type,
            external_status=ExternalStatus.DRAFT_READY,
            account_id=account_id,
            source_type=kind,
            source_id=external_id,
            title="Reply draft",
            text=text,
            status=ActionStatus.IN_PROGRESS if approved else ActionStatus.NEW,
            trust_state=TrustState.PROVISIONAL,
            requires_confirmation=True,
            data=self._safe_payload(raw),
        )

    def _action_from_item(self, item: ReputationItemOut) -> PortalActionRead:
        return PortalActionRead(
            id=f"reputation:{item.id}",
            source="reputation_adapter",
            source_module="reputation",
            source_id=item.id,
            account_id=item.account_id,
            nm_id=item.nm_id,
            action_type=self._action_type(item),
            title=self._action_title(item),
            priority=item.priority.value
            if hasattr(item.priority, "value")
            else str(item.priority),
            severity="high"
            if item.priority in {Priority.P1, Priority.P2}
            else "medium",
            status="new",
            reason=item.text or item.title,
            next_step="Создайте черновик ответа, проверьте текст и публикуйте только после ручного подтверждения.",
            expected_effect_amount=self._impact(item),
            confidence="medium",
            linked_entity={
                "item_id": item.id,
                "item_type": item.item_type,
                "external_id": item.external_id,
            },
            payload={"sentiment": item.sentiment, "rating": item.rating},
            can_update=False,
            can_update_status=False,
            can_update_reason="external_reputation_recommendation",
            guided_fix={
                "route_key": "reputation",
                "target_id": item.id,
                "label": "Подготовить черновик ответа",
                "method": "generate_draft",
            },
        )

    def _summary(self, items: list[ReputationItemOut]) -> dict[str, Any]:
        return {
            "total": len(items),
            "unanswered_reviews_count": sum(
                1 for item in items if item.item_type == "review" and item.needs_reply
            ),
            "unanswered_questions_count": sum(
                1 for item in items if item.item_type == "question" and item.needs_reply
            ),
            "unread_chats_count": sum(
                1 for item in items if self._chat_is_unread(item)
            ),
            "negative_unanswered_count": sum(
                1
                for item in items
                if item.needs_reply
                and item.item_type == "review"
                and item.rating is not None
                and item.rating <= 3
            ),
        }

    def _chat_is_unread(self, item: ReputationItemOut) -> bool:
        if item.item_type != "chat":
            return False
        unread_count = self._int((item.data or {}).get("unread_count"))
        if unread_count is not None:
            return unread_count > 0
        return item.needs_reply

    def _split_item_id(self, item_id: str) -> tuple[str, str]:
        if ":" in item_id:
            kind, external_id = item_id.split(":", 1)
        else:
            kind, external_id = "review", item_id
        kind = self._item_types(kind)[0]
        return kind, external_id

    def _draft_target(self, draft_id: str, payload: dict[str, Any]) -> tuple[str, str]:
        source_type = self._str(payload.get("source_type") or payload.get("item_type"))
        source_id = self._str(
            payload.get("source_id")
            or payload.get("item_id")
            or payload.get("external_id")
        )
        if source_type and source_id:
            if ":" in source_id:
                return self._split_item_id(source_id)
            return self._item_types(source_type)[0], source_id
        return self._split_item_id(draft_id)

    def _draft_type(self, kind: str, value: DraftType | str | None) -> DraftType:
        if value:
            try:
                return DraftType(str(value))
            except ValueError:
                pass
        return {
            "review": DraftType.REVIEW_REPLY,
            "question": DraftType.QUESTION_REPLY,
            "chat": DraftType.CHAT_REPLY,
        }.get(kind, DraftType.REVIEW_REPLY)

    def _kind_from_payload(self, payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        raw = (
            str(
                payload.get("source_type")
                or payload.get("item_type")
                or payload.get("kind")
                or ""
            )
            .strip()
            .lower()
        )
        return self._item_types(raw)[0] if raw else None

    def _external_id(self, kind: str, payload: dict[str, Any]) -> str:
        if kind == "chat":
            value = (
                payload.get("chat_id") or payload.get("id") or payload.get("event_id")
            )
        elif kind == "question":
            value = (
                payload.get("wb_id") or payload.get("question_id") or payload.get("id")
            )
        else:
            value = (
                payload.get("wb_id") or payload.get("feedback_id") or payload.get("id")
            )
        return str(value or "unknown")

    def _item_status(self, *, kind: str, payload: dict[str, Any], answer: Any) -> str:
        raw = (
            str(
                payload.get("status")
                or payload.get("state")
                or payload.get("answer_state")
                or ""
            )
            .strip()
            .lower()
        )
        if (
            payload.get("draft")
            or payload.get("draft_id")
            or payload.get("latest_draft_id")
            or payload.get("draft_text")
        ):
            return "draft_ready"
        if raw in {"published", "answered", "done"} or answer:
            return "published"
        if raw in {"approved"}:
            return "approved"
        if raw in {"draft_ready", "draft", "drafted"}:
            return "draft_ready"
        if raw in {"no_reply_needed", "ignored"}:
            return "no_reply_needed"
        if raw in {"failed", "error"}:
            return "failed"
        if (
            kind == "chat"
            and self._int(payload.get("unread_count")) == 0
            and payload.get("last_message") is None
        ):
            return "published"
        return "needs_reply"

    def _status(self, value: str) -> str:
        normalized = str(value or "").strip().lower()
        aliases = {
            "new": "needs_reply",
            "in_progress": "draft_ready",
            "done": "published",
            "ignored": "no_reply_needed",
            "blocked": "failed",
        }
        normalized = aliases.get(normalized, normalized)
        allowed = {
            "new",
            "needs_reply",
            "draft_ready",
            "approved",
            "published",
            "no_reply_needed",
            "failed",
        }
        return normalized if normalized in allowed else "needs_reply"

    def _priority_value(self, value: str) -> Priority:
        try:
            return Priority(str(value).strip().upper())
        except ValueError:
            return Priority.P3

    def _within_date_range(
        self,
        received_at: datetime | None,
        *,
        date_from: date | None,
        date_to: date | None,
    ) -> bool:
        if received_at is None:
            return date_from is None and date_to is None
        if date_from is not None and received_at < datetime.combine(
            date_from, time.min, tzinfo=received_at.tzinfo
        ):
            return False
        if date_to is not None and received_at > datetime.combine(
            date_to, time.max, tzinfo=received_at.tzinfo
        ):
            return False
        return True

    def _external_status(self, status: str) -> ExternalStatus:
        if status == "published":
            return ExternalStatus.SUBMITTED
        if status in {"draft_ready", "approved"}:
            return ExternalStatus.DRAFT_READY
        if status == "no_reply_needed":
            return ExternalStatus.CLOSED
        return ExternalStatus.NOT_CREATED

    def _priority(self, *, kind: str, rating: int | None, status: str) -> Priority:
        if status == "failed":
            return Priority.P2
        if kind == "review" and rating is not None and rating <= 2:
            return Priority.P1
        if kind in {"question", "chat"} and status in {"new", "needs_reply"}:
            return Priority.P2
        if kind == "review" and rating is not None and rating <= 3:
            return Priority.P2
        return Priority.P3

    def _action_type(self, item: ReputationItemOut) -> str:
        return {
            "review": "negative_review_unanswered"
            if item.rating is not None and item.rating <= 3
            else "review_unanswered",
            "question": "question_unanswered",
            "chat": "chat_unanswered",
        }.get(item.item_type, "top_product_reputation_risk")

    def _action_title(self, item: ReputationItemOut) -> str:
        if item.item_type == "review":
            return (
                "Ответить на негативный отзыв"
                if item.rating is not None and item.rating <= 3
                else "Ответить на отзыв"
            )
        if item.item_type == "question":
            return "Ответить на вопрос покупателя"
        return "Ответить в чат покупателя"

    def _impact(self, item: ReputationItemOut) -> float | None:
        if item.priority == Priority.P1:
            return 5000.0
        if item.priority == Priority.P2:
            return 2500.0
        return None

    def _title(self, kind: str, payload: dict[str, Any]) -> str:
        product = self._dict_value(payload, "product_details", "productDetails")
        if kind == "chat":
            good_card = self._dict_value(payload, "good_card", "goodCard")
            return (
                self._str(
                    good_card.get("imtName")
                    or good_card.get("title")
                    or payload.get("product_title")
                )
                or "Chat"
            )
        return (
            self._str(
                product.get("productName")
                or product.get("name")
                or payload.get("title")
            )
            or kind.title()
        )

    def _text(self, kind: str, payload: dict[str, Any]) -> str:
        if kind == "review":
            parts = [payload.get("text"), payload.get("pros"), payload.get("cons")]
            return "\n".join(
                str(part).strip() for part in parts if str(part or "").strip()
            )
        if kind == "question":
            return self._str(payload.get("text") or payload.get("question")) or ""
        message = (
            payload.get("last_message")
            if isinstance(payload.get("last_message"), dict)
            else {}
        )
        return self._str(message.get("text") or payload.get("text")) or ""

    def _nm_id(self, payload: dict[str, Any]) -> int | None:
        product = self._dict_value(payload, "product_details", "productDetails")
        good_card = self._dict_value(payload, "good_card", "goodCard")
        return self._int(
            payload.get("nm_id")
            or payload.get("nmId")
            or payload.get("nmID")
            or product.get("nmId")
            or product.get("nmID")
            or product.get("nm_id")
            or good_card.get("nmID")
            or good_card.get("nmId")
            or good_card.get("nm_id")
        )

    def _dict_value(self, payload: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        return {}

    def _sentiment(
        self, *, rating: int | None, text: str, payload: dict[str, Any] | None = None
    ) -> str | None:
        raw = (
            str(
                (payload or {}).get("review_sentiment")
                or (payload or {}).get("sentiment")
                or ""
            )
            .strip()
            .lower()
        )
        if raw in {"positive", "negative", "neutral", "mixed", "unknown"}:
            return raw
        if rating is not None:
            if rating <= 2:
                return "negative"
            if rating == 3:
                return "neutral"
            return "positive"
        return None if not text else "unknown"

    def _priority_rank(self, priority: Priority | str) -> int:
        return {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}.get(str(priority), 9)

    def _sort_timestamp(self, value: datetime | None) -> float:
        if value is None:
            return 0.0
        try:
            return value.timestamp()
        except (OverflowError, OSError, ValueError):
            return 0.0

    def _settings_from_payload(
        self,
        *,
        account_id: int,
        payload: Any,
        warnings: list[str] | None = None,
    ) -> ReputationSettingsOut:
        raw = payload if isinstance(payload, dict) else {}
        safe = self._safe_payload(raw)
        runtime_status = self.runtime_status()
        return ReputationSettingsOut(
            status="ok",
            account_id=account_id,
            reply_mode=self._str(raw.get("reply_mode")),
            tone=self._str(raw.get("tone")),
            language=self._str(raw.get("language")),
            signature=self._str(raw.get("signature")),
            templates=[
                item for item in raw.get("templates") or [] if isinstance(item, dict)
            ],
            signatures=[
                item for item in raw.get("signatures") or [] if isinstance(item, dict)
            ],
            auto_publish_enabled=runtime_status["auto_publish_enabled"],
            automation_enabled=False,
            chat_auto_reply_enabled=False,
            runtime_mode=runtime_status["runtime_mode"],
            dangerous_actions_enabled=runtime_status["dangerous_actions_enabled"],
            publish_enabled=runtime_status["publish_enabled"],
            chat_send_enabled=runtime_status["chat_send_enabled"],
            data={
                **safe,
                "auto_publish": False,
                "automation_enabled": False,
                "chat_auto_reply": False,
            },
            warnings=warnings or [],
            trust_state=TrustState.PROVISIONAL,
        )

    def _settings_update_payload(
        self, request: ReputationSettingsUpdateRequest
    ) -> dict[str, Any]:
        body = dict(request.payload or {})
        for key in (
            "reply_mode",
            "tone",
            "language",
            "signature",
            "templates",
            "signatures",
        ):
            value = getattr(request, key)
            if value is not None:
                body[key] = value
        body["auto_publish"] = False
        body["automation_enabled"] = False
        body["chat_auto_reply"] = False
        body["questions_auto_publish"] = False
        return self._safe_payload(body)

    def _account_stub(self, account_id: int) -> WBAccount:
        return WBAccount(
            id=account_id,
            name=str(account_id),
            external_account_id=None,
            timezone="Europe/Moscow",
            is_active=True,
        )

    def _safe_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        secret_tokens = {
            "token",
            "api_key",
            "authorization",
            "secret",
            "password",
            "jwt",
            "credential",
            "headers",
        }
        private_tokens = {
            "phone",
            "email",
            "passport",
            "address",
            "buyer",
            "customer",
            "user_name",
            "client_name",
            "client_id",
            "full_name",
            "fio",
        }
        safe: dict[str, Any] = {}
        for key, value in payload.items():
            lowered = str(key).lower()
            if any(token in lowered for token in secret_tokens | private_tokens):
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

    def _masked_name(self, value: Any) -> str | None:
        text = self._str(value)
        if not text:
            return None
        return text[:1] + "***" if len(text) > 1 else "*"

    def _datetime(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    def _int(self, value: Any) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _str(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
