from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redaction import scrub_sensitive_payload
from app.core.time import utcnow
from app.models.agent import (
    AgentActionPreview,
    AgentScenario,
    AgentScenarioRun,
    AgentUsageLedger,
)
from app.schemas.agent import (
    AgentFinanceSummary,
    AgentScenarioCreate,
    AgentScenarioListResponse,
    AgentScenarioRead,
    AgentScenarioRunCreate,
    AgentScenarioRunListResponse,
    AgentScenarioRunRead,
    AgentScenarioTemplate,
    AgentScenarioTemplatesResponse,
    AgentScenarioUpdate,
)


SCENARIO_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "key": "reputation_negative_reviews",
        "title": "Ответы на негативные отзывы",
        "description": (
            "Собирает отзывы, готовит безопасные черновики ответов, подсвечивает "
            "темы негатива и требует ручного подтверждения перед публикацией."
        ),
        "scenario_type": "reputation",
        "default_schedule_json": {"type": "daily", "hour": 9, "minute": 0},
        "default_guardrails_json": {
            "publish_to_wb": False,
            "require_human_approval": True,
            "max_drafts_per_run": 25,
            "tone": "вежливо, по делу, без обещаний вне политики бренда",
        },
        "default_actions_json": [
            {"api_action_key": "reputation.summary"},
            {"api_action_key": "reputation.inbox"},
            {"api_action_key": "reputation.drafts"},
        ],
    },
    {
        "key": "pricing_guarded_repricer",
        "title": "Умное изменение цен без риска маржи",
        "description": (
            "Проверяет цену, маржу, дни запаса, тренд заказов и отзывы. "
            "Готовит рекомендации, но не меняет цены без preview и подтверждения."
        ),
        "scenario_type": "pricing",
        "default_schedule_json": {"type": "daily", "hour": 10, "minute": 30},
        "default_guardrails_json": {
            "direct_price_update": False,
            "require_margin_check": True,
            "min_interval_hours": 2,
            "max_daily_price_step_pct": 5,
            "stop_loss": {
                "conversion_drop_pct": 12,
                "orders_drop_pct": 20,
                "fresh_negative_reviews": True,
            },
        },
        "default_actions_json": [
            {"api_action_key": "pricing.safety"},
            {"api_action_key": "analytics.overview"},
            {"api_action_key": "stock_control.status"},
            {"api_action_key": "reputation.summary"},
        ],
    },
    {
        "key": "ads_budget_watchdog",
        "title": "Контроль рекламы и бюджета",
        "description": (
            "Смотрит эффективность кампаний, расход и статистику. "
            "Остановки/изменения ставок оформляет только через подтверждаемое действие."
        ),
        "scenario_type": "ads",
        "default_schedule_json": {"type": "daily", "hour": 11, "minute": 0},
        "default_guardrails_json": {
            "direct_budget_change": False,
            "require_human_approval": True,
            "max_budget_change_pct": 10,
            "min_observation_days": 3,
        },
        "default_actions_json": [
            {"api_action_key": "ads.efficiency"},
            {"api_action_key": "ads.campaigns"},
            {"api_action_key": "ads.stats"},
        ],
    },
    {
        "key": "stock_oos_guard",
        "title": "Контроль остатков и OOS",
        "description": (
            "Находит риск нулевого остатка, избыток и потребность в поставках. "
            "Запуск операций склада остаётся через безопасный preview."
        ),
        "scenario_type": "stock",
        "default_schedule_json": {"type": "daily", "hour": 8, "minute": 30},
        "default_guardrails_json": {
            "direct_stock_operation": False,
            "min_days_to_zero": 14,
            "excess_stock_days": 60,
            "require_human_approval": True,
        },
        "default_actions_json": [
            {"api_action_key": "stock_control.status"},
            {"api_action_key": "inventory.purchase_plan"},
            {"api_action_key": "inventory.stock_snapshots"},
        ],
    },
    {
        "key": "complex_growth_strategy",
        "title": "Комплексная стратегия роста",
        "description": (
            "Собирает деньги, аналитику, цены, отзывы и остатки в один "
            "еженедельный план действий с guardrails."
        ),
        "scenario_type": "strategy",
        "default_schedule_json": {"type": "weekly", "weekday": 1, "hour": 9, "minute": 30},
        "default_guardrails_json": {
            "direct_marketplace_writes": False,
            "require_metric_evidence": True,
            "guard_metrics": [
                "маржа",
                "конверсия",
                "заказы",
                "дни запаса",
                "негативные отзывы",
            ],
        },
        "default_actions_json": [
            {"api_action_key": "money.summary"},
            {"api_action_key": "analytics.overview"},
            {"api_action_key": "pricing.safety"},
            {"api_action_key": "stock_control.status"},
            {"api_action_key": "reputation.summary"},
        ],
    },
)


class AgentScenarioService:
    DEFAULT_LIMIT = 50
    DEFAULT_OPENAI_INPUT_USD_PER_MILLION = Decimal("0.25")
    DEFAULT_OPENAI_OUTPUT_USD_PER_MILLION = Decimal("2.00")

    @staticmethod
    def templates() -> AgentScenarioTemplatesResponse:
        return AgentScenarioTemplatesResponse(
            items=[AgentScenarioTemplate.model_validate(item) for item in SCENARIO_TEMPLATES]
        )

    async def create_scenario(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        payload: AgentScenarioCreate,
        user_id: int | None,
    ) -> AgentScenarioRead:
        template = self._template_for_type(payload.scenario_type)
        schedule_json = self._merged_json(
            template.get("default_schedule_json"), payload.schedule_json
        )
        guardrails_json = self._merged_json(
            template.get("default_guardrails_json"), payload.guardrails_json
        )
        actions_json = self._validate_actions_json(
            payload.actions_json or list(template.get("default_actions_json") or [])
        )
        row = AgentScenario(
            account_id=account_id,
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
            name=payload.name.strip(),
            description=payload.description,
            scenario_type=payload.scenario_type,
            status="active" if payload.auto_execute_enabled else "draft",
            approval_policy=payload.approval_policy,
            auto_execute_enabled=payload.auto_execute_enabled,
            source_prompt=payload.source_prompt,
            scope_json=self._safe_json(payload.scope_json),
            schedule_json=self._safe_json(schedule_json),
            trigger_json=self._safe_json(payload.trigger_json),
            guardrails_json=self._safe_json(guardrails_json),
            actions_json=actions_json,
            notification_json=self._safe_json(payload.notification_json),
            ai_plan_json=self._safe_json(payload.ai_plan_json),
            next_run_at=self._next_run_at(schedule_json)
            if payload.auto_execute_enabled
            else None,
        )
        session.add(row)
        await session.flush()
        return AgentScenarioRead.model_validate(row)

    async def create_from_agent_prompt(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        user_id: int | None,
        prompt: str,
        assistant_message: str | None,
        scope_json: dict[str, Any],
        scenario_type: str = "general",
    ) -> AgentScenarioRead:
        payload = AgentScenarioCreate(
            account_id=account_id,
            name=self._scenario_name(prompt=prompt, scenario_type=scenario_type),
            description=assistant_message
            or "Сценарий создан AI-оператором и требует ручной проверки.",
            scenario_type=scenario_type,  # type: ignore[arg-type]
            source_prompt=prompt,
            scope_json=scope_json,
            ai_plan_json={
                "source": "agent_chat",
                "assistant_message": assistant_message,
                "safety": {
                    "direct_marketplace_writes": False,
                    "preview_first": True,
                },
            },
            approval_policy="manual_review",
            auto_execute_enabled=False,
        )
        return await self.create_scenario(
            session, account_id=account_id, payload=payload, user_id=user_id
        )

    async def list_scenarios(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        status: str | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> AgentScenarioListResponse:
        limit = self._limit(limit)
        offset = max(0, int(offset))
        filters = [AgentScenario.account_id == account_id]
        if status:
            filters.append(AgentScenario.status == status)
        total = (
            await session.execute(select(func.count()).select_from(AgentScenario).where(*filters))
        ).scalar_one()
        rows = list(
            (
                await session.execute(
                    select(AgentScenario)
                    .where(*filters)
                    .order_by(AgentScenario.updated_at.desc(), AgentScenario.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars()
        )
        return AgentScenarioListResponse(
            status="ok" if rows else "empty",
            total=int(total or 0),
            limit=limit,
            offset=offset,
            items=[AgentScenarioRead.model_validate(row) for row in rows],
        )

    async def get_scenario(
        self, session: AsyncSession, *, account_id: int, scenario_id: int
    ) -> AgentScenarioRead:
        row = await self._get_scenario_row(
            session, account_id=account_id, scenario_id=scenario_id
        )
        return AgentScenarioRead.model_validate(row)

    async def update_scenario(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        scenario_id: int,
        payload: AgentScenarioUpdate,
        user_id: int | None,
    ) -> AgentScenarioRead:
        row = await self._get_scenario_row(
            session, account_id=account_id, scenario_id=scenario_id
        )
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            if key in {
                "scope_json",
                "schedule_json",
                "trigger_json",
                "guardrails_json",
                "notification_json",
                "ai_plan_json",
            }:
                setattr(row, key, self._safe_json(value or {}))
            elif key == "actions_json":
                setattr(row, key, self._validate_actions_json(value or []))
            else:
                setattr(row, key, value)
        row.updated_by_user_id = user_id
        if "schedule_json" in data or "auto_execute_enabled" in data or "status" in data:
            row.next_run_at = (
                self._next_run_at(row.schedule_json)
                if row.auto_execute_enabled and row.status == "active"
                else None
            )
        await session.flush()
        return AgentScenarioRead.model_validate(row)

    async def run_scenario(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        scenario_id: int,
        payload: AgentScenarioRunCreate,
        user_id: int | None = None,
    ) -> AgentScenarioRunRead:
        scenario = await self._get_scenario_row(
            session, account_id=account_id, scenario_id=scenario_id
        )
        if payload.dry_run is not True:
            raise HTTPException(
                status_code=400,
                detail=(
                    "AI-сценарии сейчас выполняются только в dry-run режиме. "
                    "Передайте dry_run=true."
                ),
            )
        started_at = utcnow()
        try:
            previews = self._build_action_preview_payloads(scenario)
        except ValueError as exc:
            previews = []
            validation_error = str(exc)
        else:
            validation_error = None
        row = AgentScenarioRun(
            account_id=account_id,
            scenario_id=int(scenario.id),
            requested_by_user_id=user_id,
            trigger=payload.trigger,
            status="completed" if previews else "blocked",
            dry_run=True,
            started_at=started_at,
            finished_at=utcnow(),
            input_json=self._safe_json(payload.input_json),
            output_json={
                "summary": validation_error or self._run_summary(scenario, previews),
                "direct_marketplace_writes": False,
                "preview_first": True,
                "next_step": "Проверьте action previews и подтвердите только безопасные действия.",
            },
            actions_preview_json=previews,
            actions_executed=0,
            actions_blocked=sum(1 for item in previews if item.get("confirm_required")),
            log_text=(
                "Сценарий выполнен в безопасном режиме dry-run. "
                "Созданы preview-действия, прямых записей в WB не было."
            ),
            error_code="invalid_action_catalog" if validation_error else None,
            error_summary=validation_error,
        )
        session.add(row)
        await session.flush()

        preview_rows = [
            AgentActionPreview(
                account_id=account_id,
                scenario_id=int(scenario.id),
                run_id=int(row.id),
                api_action_key=item.get("api_action_key"),
                title=str(item.get("title") or "AI action preview"),
                status="pending_confirmation"
                if item.get("confirm_required")
                else "ready",
                confirm_required=bool(item.get("confirm_required")),
                idempotency_key=f"agent:{scenario.id}:{row.id}:{index}",
                before_json={},
                after_json={},
                payload_json=self._safe_json(item),
                risk_json=self._safe_json(item.get("risk") or {}),
            )
            for index, item in enumerate(previews, start=1)
        ]
        for item in preview_rows:
            session.add(item)

        scenario.last_run_at = row.finished_at
        scenario.last_run_status = row.status
        scenario.next_run_at = (
            self._next_run_at(scenario.schedule_json, after=row.finished_at)
            if scenario.auto_execute_enabled and scenario.status == "active"
            else None
        )
        await session.flush()
        return AgentScenarioRunRead.model_validate(row).model_copy(
            update={
                "action_previews": [
                    self._preview_read(preview) for preview in preview_rows
                ]
            }
        )

    async def list_runs(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        scenario_id: int | None = None,
        status: str | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> AgentScenarioRunListResponse:
        limit = self._limit(limit)
        offset = max(0, int(offset))
        filters = [AgentScenarioRun.account_id == account_id]
        if scenario_id:
            filters.append(AgentScenarioRun.scenario_id == scenario_id)
        if status:
            filters.append(AgentScenarioRun.status == status)
        total = (
            await session.execute(
                select(func.count()).select_from(AgentScenarioRun).where(*filters)
            )
        ).scalar_one()
        rows = list(
            (
                await session.execute(
                    select(AgentScenarioRun)
                    .where(*filters)
                    .order_by(
                        AgentScenarioRun.created_at.desc(),
                        AgentScenarioRun.id.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars()
        )
        return AgentScenarioRunListResponse(
            status="ok" if rows else "empty",
            total=int(total or 0),
            limit=limit,
            offset=offset,
            items=[AgentScenarioRunRead.model_validate(row) for row in rows],
        )

    async def finance_summary(
        self, session: AsyncSession, *, account_id: int
    ) -> AgentFinanceSummary:
        since = utcnow() - timedelta(days=30)
        scenarios_total = (
            await session.execute(
                select(func.count())
                .select_from(AgentScenario)
                .where(AgentScenario.account_id == account_id)
            )
        ).scalar_one()
        active_scenarios = (
            await session.execute(
                select(func.count())
                .select_from(AgentScenario)
                .where(
                    AgentScenario.account_id == account_id,
                    AgentScenario.status == "active",
                )
            )
        ).scalar_one()
        runs_total = (
            await session.execute(
                select(func.count())
                .select_from(AgentScenarioRun)
                .where(AgentScenarioRun.account_id == account_id)
            )
        ).scalar_one()
        runs_last_30d = (
            await session.execute(
                select(func.count())
                .select_from(AgentScenarioRun)
                .where(
                    AgentScenarioRun.account_id == account_id,
                    AgentScenarioRun.created_at >= since,
                )
            )
        ).scalar_one()
        failed_runs_last_30d = (
            await session.execute(
                select(func.count())
                .select_from(AgentScenarioRun)
                .where(
                    AgentScenarioRun.account_id == account_id,
                    AgentScenarioRun.created_at >= since,
                    AgentScenarioRun.status.in_(("failed", "blocked")),
                )
            )
        ).scalar_one()
        usage = (
            await session.execute(
                select(
                    func.coalesce(func.sum(AgentUsageLedger.prompt_tokens), 0),
                    func.coalesce(func.sum(AgentUsageLedger.completion_tokens), 0),
                    func.coalesce(func.sum(AgentUsageLedger.total_tokens), 0),
                    func.coalesce(func.sum(AgentUsageLedger.estimated_cost_usd), 0),
                ).where(AgentUsageLedger.account_id == account_id)
            )
        ).one()
        ledger_rows = list(
            (
                await session.execute(
                    select(AgentUsageLedger)
                    .where(AgentUsageLedger.account_id == account_id)
                    .order_by(
                        AgentUsageLedger.created_at.desc(),
                        AgentUsageLedger.id.desc(),
                    )
                    .limit(20)
                )
            ).scalars()
        )
        return AgentFinanceSummary(
            account_id=account_id,
            scenarios_total=int(scenarios_total or 0),
            active_scenarios=int(active_scenarios or 0),
            runs_total=int(runs_total or 0),
            runs_last_30d=int(runs_last_30d or 0),
            failed_runs_last_30d=int(failed_runs_last_30d or 0),
            prompt_tokens=int(usage[0] or 0),
            completion_tokens=int(usage[1] or 0),
            total_tokens=int(usage[2] or 0),
            estimated_cost_usd=Decimal(str(usage[3] or "0")),
            ledger_items=[
                {
                    "id": int(item.id),
                    "source": item.source,
                    "model": item.model,
                    "total_tokens": int(item.total_tokens or 0),
                    "estimated_cost_usd": str(item.estimated_cost_usd or Decimal("0")),
                    "created_at": item.created_at,
                }
                for item in ledger_rows
            ],
        )

    async def process_due_scenarios(
        self, session: AsyncSession, *, limit: int = 10
    ) -> list[AgentScenarioRunRead]:
        now = utcnow()
        query = (
            select(AgentScenario)
            .where(
                AgentScenario.status == "active",
                AgentScenario.auto_execute_enabled.is_(True),
                AgentScenario.next_run_at <= now,
            )
            .order_by(AgentScenario.next_run_at.asc(), AgentScenario.id.asc())
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True, of=AgentScenario)
        )
        rows = list(
            (
                await session.execute(query)
            ).scalars()
        )
        runs: list[AgentScenarioRunRead] = []
        for scenario in rows:
            runs.append(
                await self.run_scenario(
                    session,
                    account_id=int(scenario.account_id),
                    scenario_id=int(scenario.id),
                    payload=AgentScenarioRunCreate(trigger="scheduler", dry_run=True),
                    user_id=None,
                )
            )
        return runs

    async def record_usage(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        user_id: int | None = None,
        scenario_id: int | None = None,
        run_id: int | None = None,
        source: str = "chat",
        provider: str = "openai",
        model: str | None = None,
        usage: dict[str, Any] | None = None,
        request_id: str | None = None,
        payload_json: dict[str, Any] | None = None,
    ) -> AgentUsageLedger | None:
        tokens = self._usage_tokens(usage)
        if tokens["total_tokens"] <= 0:
            return None
        row = AgentUsageLedger(
            account_id=account_id,
            user_id=user_id,
            scenario_id=scenario_id,
            run_id=run_id,
            provider=provider,
            model=model,
            source=source,
            prompt_tokens=tokens["prompt_tokens"],
            completion_tokens=tokens["completion_tokens"],
            total_tokens=tokens["total_tokens"],
            estimated_cost_usd=self._estimate_openai_cost(
                model=model,
                prompt_tokens=tokens["prompt_tokens"],
                completion_tokens=tokens["completion_tokens"],
            ),
            request_id=request_id,
            payload_json=self._safe_json(payload_json or {}),
        )
        session.add(row)
        return row

    @staticmethod
    def _preview_read(row: AgentActionPreview):
        from app.schemas.agent import AgentActionPreviewRead

        return AgentActionPreviewRead.model_validate(row)

    @staticmethod
    def _template_for_type(scenario_type: str) -> dict[str, Any]:
        for item in SCENARIO_TEMPLATES:
            if item["scenario_type"] == scenario_type:
                return item
        return {
            "default_schedule_json": {"type": "manual"},
            "default_guardrails_json": {
                "direct_marketplace_writes": False,
                "require_human_approval": True,
            },
            "default_actions_json": [{"api_action_key": "portal.overview"}],
        }

    @staticmethod
    def _merged_json(base: Any, override: Any) -> dict[str, Any]:
        result = dict(base or {})
        result.update(dict(override or {}))
        return result

    @staticmethod
    def _safe_json(value: Any) -> dict[str, Any]:
        scrubbed = scrub_sensitive_payload(value or {})
        return scrubbed if isinstance(scrubbed, dict) else {}

    @staticmethod
    def _safe_list(value: Any) -> list[dict[str, Any]]:
        scrubbed = scrub_sensitive_payload(value or [])
        if not isinstance(scrubbed, list):
            return []
        return [item for item in scrubbed if isinstance(item, dict)]

    def _validate_actions_json(self, value: Any) -> list[dict[str, Any]]:
        items = self._safe_list(value)
        if not items:
            raise HTTPException(
                status_code=422,
                detail="actions_json must contain at least one allow-listed action",
            )
        validated: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            action_key = str(item.get("api_action_key") or "").strip()
            if not action_key:
                raise HTTPException(
                    status_code=422,
                    detail=f"actions_json[{index}].api_action_key is required",
                )
            spec = self._catalog_spec(action_key)
            if not spec:
                raise HTTPException(
                    status_code=422,
                    detail=f"actions_json[{index}].api_action_key is not allow-listed",
                )
            params = item.get("api_action_params")
            if params is not None and not isinstance(params, dict):
                raise HTTPException(
                    status_code=422,
                    detail=f"actions_json[{index}].api_action_params must be an object",
                )
            missing = self._missing_action_params(spec, params if isinstance(params, dict) else {})
            if missing:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"actions_json[{index}] is missing required params: "
                        f"{', '.join(missing)}"
                    ),
                )
            validated.append({**item, "api_action_key": action_key})
        return validated

    @staticmethod
    def _limit(value: int) -> int:
        return max(1, min(200, int(value or AgentScenarioService.DEFAULT_LIMIT)))

    @staticmethod
    def _scenario_name(*, prompt: str, scenario_type: str) -> str:
        clean = " ".join(str(prompt or "").split())
        if clean:
            return clean[:120]
        title_by_type = {
            "pricing": "Сценарий умных цен",
            "reputation": "Сценарий отзывов",
            "ads": "Сценарий рекламы",
            "stock": "Сценарий остатков",
            "strategy": "Сценарий стратегии",
        }
        return title_by_type.get(scenario_type, "AI-сценарий")

    async def _get_scenario_row(
        self, session: AsyncSession, *, account_id: int, scenario_id: int
    ) -> AgentScenario:
        row = await session.get(AgentScenario, int(scenario_id))
        if row is None or int(row.account_id) != int(account_id):
            raise HTTPException(status_code=404, detail="agent scenario not found")
        return row

    def _build_action_preview_payloads(
        self, scenario: AgentScenario
    ) -> list[dict[str, Any]]:
        previews: list[dict[str, Any]] = []
        for index, item in enumerate(scenario.actions_json or [], start=1):
            action_key = str(item.get("api_action_key") or "")
            spec = self._catalog_spec(action_key)
            if not spec:
                raise ValueError(
                    f"Сценарий содержит неизвестное действие #{index}: {action_key or 'empty'}."
                )
            title = str(item.get("title") or spec.get("title") or action_key or "AI action")
            write_policy = str(spec.get("write_policy") or item.get("write_policy") or "read")
            confirm_required = bool(
                spec.get("confirm_required")
                or item.get("confirm_required")
                or write_policy not in {"read", "download_only"}
            )
            previews.append(
                {
                    "position": index,
                    "api_action_key": action_key or None,
                    "title": title,
                    "description": str(
                        item.get("description") or spec.get("description") or ""
                    ),
                    "method": str(spec.get("method") or item.get("method") or "GET"),
                    "path": spec.get("path") or item.get("path"),
                    "write_policy": write_policy,
                    "confirm_required": confirm_required,
                    "risk": {
                        "level": "medium" if confirm_required else "low",
                        "direct_marketplace_writes": False,
                        "requires_human_approval": confirm_required,
                    },
                    "scope": scenario.scope_json,
                }
            )
        return previews

    @staticmethod
    def _catalog_spec(action_key: str) -> dict[str, Any]:
        if not action_key:
            return {}
        try:
            from app.services.agent.orchestrator import AGENT_API_ACTION_CATALOG
        except Exception:
            return {}
        return dict(AGENT_API_ACTION_CATALOG.get(action_key) or {})

    @staticmethod
    def _missing_action_params(
        spec: dict[str, Any], params: dict[str, Any] | None
    ) -> list[str]:
        values = params or {}
        missing: list[str] = []
        for key in spec.get("required_params", []):
            value = values.get(str(key))
            if value is None or value == "":
                missing.append(str(key))
        return missing

    @staticmethod
    def _usage_tokens(usage: dict[str, Any] | None) -> dict[str, int]:
        raw = usage or {}
        prompt = int(
            raw.get("input_tokens")
            or raw.get("prompt_tokens")
            or raw.get("prompt")
            or 0
        )
        completion = int(
            raw.get("output_tokens")
            or raw.get("completion_tokens")
            or raw.get("completion")
            or 0
        )
        total = int(raw.get("total_tokens") or prompt + completion)
        if total < prompt + completion:
            total = prompt + completion
        return {
            "prompt_tokens": max(0, prompt),
            "completion_tokens": max(0, completion),
            "total_tokens": max(0, total),
        }

    def _estimate_openai_cost(
        self, *, model: str | None, prompt_tokens: int, completion_tokens: int
    ) -> Decimal:
        input_price, output_price = self._openai_prices_for_model(model)
        input_cost = (Decimal(prompt_tokens) / Decimal(1_000_000)) * input_price
        output_cost = (Decimal(completion_tokens) / Decimal(1_000_000)) * output_price
        return (input_cost + output_cost).quantize(Decimal("0.000001"))

    @classmethod
    def _openai_prices_for_model(cls, model: str | None) -> tuple[Decimal, Decimal]:
        _ = model
        settings = get_settings()
        return (
            Decimal(str(settings.agent_openai_input_usd_per_million)),
            Decimal(str(settings.agent_openai_output_usd_per_million)),
        )

    @staticmethod
    def _run_summary(
        scenario: AgentScenario, previews: list[dict[str, Any]]
    ) -> str:
        if not previews:
            return (
                f"Сценарий «{scenario.name}» не выполнил действий: "
                "не настроены безопасные action previews."
            )
        return (
            f"Сценарий «{scenario.name}» подготовил {len(previews)} preview-действий. "
            "Прямых записей в Wildberries не было."
        )

    @staticmethod
    def _next_run_at(
        schedule_json: dict[str, Any], *, after=None
    ):
        schedule_type = str((schedule_json or {}).get("type") or "manual")
        if schedule_type == "manual":
            return None
        base = after or utcnow()
        if schedule_type == "hourly":
            return base + timedelta(hours=1)
        if schedule_type == "every_n_hours":
            hours = int(schedule_json.get("hours") or 6)
            return base + timedelta(hours=max(1, min(24, hours)))
        hour = max(0, min(23, int(schedule_json.get("hour") or 9)))
        minute = max(0, min(59, int(schedule_json.get("minute") or 0)))
        candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if schedule_type == "daily":
            return candidate if candidate > base else candidate + timedelta(days=1)
        if schedule_type == "weekly":
            weekday = max(1, min(7, int(schedule_json.get("weekday") or 1)))
            target_weekday = weekday - 1
            days_ahead = (target_weekday - base.weekday()) % 7
            candidate = candidate + timedelta(days=days_ahead)
            return candidate if candidate > base else candidate + timedelta(days=7)
        return None
