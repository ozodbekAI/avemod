from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.redaction import redact_sensitive_text
from app.core.time import utcnow
from app.models.accounts import WBAPICategory, WBAPIToken, WBAccount
from app.models.claims import ClaimCandidate, ClaimDetectionRun
from app.models.experiments import (
    Experiment,
    ExperimentMetricSnapshot,
    ExperimentSettings,
)
from app.models.operator import PortalIntegration
from app.models.card_quality import CardQualityIssue, CardQualitySnapshot
from app.models.photo_studio import PhotoProject
from app.models.product_cards import WBProductCard
from app.models.reputation import ReputationItem
from app.schemas.portal import (
    PortalModuleHealth,
    PortalModuleHealthItem,
    PortalModuleName,
    PortalStatus,
)
from app.services.checker_adapter import CheckerAdapter
from app.services.grouping_adapter import GroupingAdapter
from app.services.grouping import GroupingBetaService
from app.services.reputation_adapter import ReputationAdapter
from app.services.stock_control import StockControlService
from app.services.stockops_adapter import StockOpsAdapter


REGISTRY_STATUS_VALUES = {"ok", "disabled", "not_configured", "degraded", "unavailable"}
MVP_MODULES = {
    "finance",
    "expenses",
    "doctor",
    "actions",
    "products",
    "checker",
    "results",
}
BETA_MODULES = {"reputation", "claims", "photo", "experiments", "grouping", "stockops"}


class ModuleRegistryService:
    """Read model for Seller Portal module health.

    Account-level DB configuration is authoritative when present. Environment
    settings remain the global fallback so existing deployments keep working
    while modules migrate into the finance-owned modular monolith.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        checker: CheckerAdapter | None = None,
        stockops: StockOpsAdapter | None = None,
        grouping: GroupingAdapter | None = None,
        reputation: ReputationAdapter | None = None,
        stock_control: StockControlService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.checker = checker or CheckerAdapter(self.settings)
        self.stockops = stockops or StockOpsAdapter(self.settings)
        self.grouping = grouping or GroupingAdapter(self.settings)
        self.grouping_beta = GroupingBetaService()
        self.reputation = reputation or ReputationAdapter(self.settings)
        self.stock_control = stock_control or StockControlService()

    async def health(
        self, *, account: WBAccount | None = None, session: AsyncSession | None = None
    ) -> PortalModuleHealth:
        db_states = await self._db_integration_states(session=session, account=account)
        return PortalModuleHealth(
            finance=self._item(
                module="finance",
                status="ok",
                enabled=True,
                configured=True,
                message="finance core is required and configured",
            ),
            expenses=self._item(
                module="expenses",
                status="ok",
                enabled=True,
                configured=True,
                message="Expenses use WB finance reports and money marts",
            ),
            doctor=self._item(
                module="doctor",
                status="ok" if self.settings.enable_legacy_diagnostics else "disabled",
                enabled=bool(self.settings.enable_legacy_diagnostics),
                configured=bool(self.settings.enable_legacy_diagnostics),
                message=(
                    "Legacy profit diagnostics use finance data"
                    if self.settings.enable_legacy_diagnostics
                    else "Legacy profit diagnostics are hidden; Action Center is the primary problem surface"
                ),
            ),
            actions=self._item(
                module="actions",
                status="ok",
                enabled=True,
                configured=True,
                message="Action Center uses finance database",
            ),
            products=self._item(
                module="products",
                status="ok",
                enabled=True,
                configured=True,
                message="Products and Product 360 use finance data",
            ),
            checker=db_states.get("checker")
            or await self._local_card_quality_health(session=session, account=account)
            or await self._checker_health(account),
            stockops=db_states.get("stockops")
            or await self._local_stock_control_health(session=session, account=account)
            or await self._stockops_health(),
            grouping=db_states.get("grouping")
            or await self._local_grouping_health(session=session, account=account)
            or await self._grouping_health(account),
            reputation=await self._local_reputation_health(
                session=session, account=account
            )
            or db_states.get("reputation")
            or await self._reputation_health(account),
            claims=db_states.get("claims") or await self._local_claims_health(session=session, account=account) or self._external_config_health(
                module="claims",
                enabled=self.settings.claims_enabled,
                base_url=self.settings.claims_base_url,
            ),
            photo=db_states.get("photo")
            or await self._local_photo_health(session=session, account=account)
            or self._external_config_health(
                module="photo",
                enabled=self.settings.photo_enabled,
                base_url=self.settings.photo_base_url,
            ),
            experiments=await self._local_experiments_health(
                session=session, account=account
            )
            or self._experiments_health(),
            results=self._item(
                module="results",
                status="ok",
                enabled=True,
                configured=True,
                message="Result tracking uses finance database",
            ),
        )

    async def _db_integration_states(
        self,
        *,
        session: AsyncSession | None,
        account: WBAccount | None,
    ) -> dict[str, PortalModuleHealthItem]:
        if session is None or account is None:
            return {}
        result = await session.execute(
            select(PortalIntegration).where(
                PortalIntegration.account_id == int(account.id)
            )
        )
        items: dict[str, PortalModuleHealthItem] = {}
        for integration in result.scalars():
            module = str(getattr(integration, "module", "") or "").strip().lower()
            if module not in {
                "checker",
                "stockops",
                "grouping",
                "reputation",
                "claims",
                "photo",
            }:
                continue
            item = self._db_integration_item(integration, module=module)  # type: ignore[arg-type]
            items[module] = item
        return items

    async def _local_card_quality_health(
        self,
        *,
        session: AsyncSession | None,
        account: WBAccount | None,
    ) -> PortalModuleHealthItem | None:
        if session is None or account is None or not hasattr(session, "execute"):
            return None
        try:
            snapshots_result = await session.execute(
                select(func.count(func.distinct(CardQualitySnapshot.nm_id))).where(
                    CardQualitySnapshot.account_id == int(account.id)
                )
            )
            if not hasattr(snapshots_result, "scalar"):
                return None
            snapshots = int(snapshots_result.scalar() or 0)
            if snapshots <= 0:
                return None
            eligible_result = await session.execute(
                select(func.count(func.distinct(WBProductCard.nm_id))).where(
                    WBProductCard.account_id == int(account.id)
                )
            )
            eligible = (
                int(eligible_result.scalar() or 0)
                if hasattr(eligible_result, "scalar")
                else 0
            )
            issues_result = await session.execute(
                select(func.count())
                .select_from(CardQualityIssue)
                .where(
                    CardQualityIssue.account_id == int(account.id),
                    CardQualityIssue.resolved_at.is_(None),
                    CardQualityIssue.status.in_(("new", "in_progress", "postponed")),
                    CardQualityIssue.severity != "info",
                )
            )
            if not hasattr(issues_result, "scalar"):
                return None
            open_issues = int(issues_result.scalar() or 0)
            info_result = await session.execute(
                select(func.count())
                .select_from(CardQualityIssue)
                .where(
                    CardQualityIssue.account_id == int(account.id),
                    CardQualityIssue.severity == "info",
                )
            )
            info_count = (
                int(info_result.scalar() or 0) if hasattr(info_result, "scalar") else 0
            )
            latest_result = await session.execute(
                select(CardQualitySnapshot.analyzed_at)
                .where(CardQualitySnapshot.account_id == int(account.id))
                .order_by(CardQualitySnapshot.analyzed_at.desc().nullslast())
                .limit(1)
            )
            if not hasattr(latest_result, "scalar"):
                return None
            latest = latest_result.scalar()
        except Exception:
            return None
        item = self._item(
            module="checker",
            status="ok" if open_issues else "empty",
            enabled=True,
            configured=True,
            message=f"local card quality: analyzed={snapshots}, open_issues={open_issues}",
            warnings=[
                "local",
                f"last_success_at:{latest.isoformat() if latest else 'unknown'}",
            ],
        )
        item.mode = "local"
        item.eligible_products = eligible
        item.unique_products_analyzed = snapshots
        item.coverage_percent = (
            round((snapshots / eligible) * 100, 2) if eligible else 0
        )
        item.actionable_open_issues = open_issues
        item.informational_observations = info_count
        item.last_success_at = latest
        return item

    async def _local_photo_health(
        self,
        *,
        session: AsyncSession | None,
        account: WBAccount | None,
    ) -> PortalModuleHealthItem | None:
        if session is None or account is None or not hasattr(session, "execute"):
            return None
        try:
            projects = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(PhotoProject)
                        .where(PhotoProject.account_id == int(account.id))
                    )
                ).scalar()
                or 0
            )
            return self._item(
                module="photo",
                status="ok",
                enabled=True,
                configured=True,
                message=f"local Photo Studio: projects={projects}",
                warnings=["local", "manual_upload_available", "wb_apply_disabled"],
            )
        except Exception:
            return None

    def _db_integration_item(
        self, integration: PortalIntegration, *, module: PortalModuleName
    ) -> PortalModuleHealthItem:
        status = self._normalize_db_status(
            str(integration.status or ""), enabled=bool(integration.enabled)
        )
        configured = bool(
            integration.enabled and status not in {"disabled", "not_configured"}
        )
        warnings: list[str] = []
        if integration.mode == "local":
            warnings.append("local")
        elif integration.mode:
            warnings.append(f"mode:{self._safe_message(integration.mode)}")
        if integration.last_error_code:
            warnings.append(
                f"last_error_code:{self._safe_message(integration.last_error_code)}"
            )
        message = self._db_integration_message(
            integration, module=module, status=status
        )
        item = self._item(
            module=module,
            status=status,
            enabled=bool(integration.enabled),
            configured=configured,
            message=message,
            warnings=warnings,
        )
        if module == "checker" and integration.mode == "local":
            metadata = getattr(integration, "metadata_json", None) or {}
            item.mode = "local"
            item.eligible_products = metadata.get("eligible_products")
            item.unique_products_analyzed = metadata.get("unique_products_analyzed")
            item.coverage_percent = metadata.get("coverage_percent")
            item.actionable_open_issues = metadata.get("actionable_open_issues")
            item.informational_observations = metadata.get("informational_observations")
            item.last_success_at = getattr(integration, "last_success_at", None)
        return item

    async def _local_reputation_health(
        self,
        *,
        session: AsyncSession | None,
        account: WBAccount | None,
    ) -> PortalModuleHealthItem | None:
        if session is None or account is None or not hasattr(session, "execute"):
            return None
        try:
            feedbacks_questions_token_count = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(WBAPIToken)
                        .where(
                            WBAPIToken.account_id == int(account.id),
                            WBAPIToken.category
                            == WBAPICategory.FEEDBACKS_QUESTIONS.value,
                            WBAPIToken.is_active.is_(True),
                        )
                    )
                ).scalar()
                or 0
            )
            buyer_chat_token_count = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(WBAPIToken)
                        .where(
                            WBAPIToken.account_id == int(account.id),
                            WBAPIToken.category == WBAPICategory.BUYER_CHAT.value,
                            WBAPIToken.is_active.is_(True),
                        )
                    )
                ).scalar()
                or 0
            )
            item_count = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(ReputationItem)
                        .where(ReputationItem.account_id == int(account.id))
                    )
                ).scalar()
                or 0
            )
            open_count = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(ReputationItem)
                        .where(
                            ReputationItem.account_id == int(account.id),
                            ReputationItem.needs_reply.is_(True),
                            ReputationItem.status.in_(
                                ("new", "needs_reply", "draft_ready", "in_progress")
                            ),
                        )
                    )
                ).scalar()
                or 0
            )
        except Exception:
            return None
        status = "ok" if item_count else "empty"
        warnings = ["local"]
        if not feedbacks_questions_token_count:
            warnings.append("wb_feedbacks_questions_token_not_configured")
        if not buyer_chat_token_count:
            warnings.append("wb_buyer_chat_token_not_configured")
        item = self._item(
            module="reputation",
            status=status,  # type: ignore[arg-type]
            enabled=True,
            configured=True,
            message="local reputation operator uses finance database",
            warnings=warnings,
        )
        item.mode = "local"
        item.actionable_open_issues = open_count
        item.unique_products_analyzed = item_count
        item.source_freshness = {
            "required_token_categories": [
                WBAPICategory.FEEDBACKS_QUESTIONS.value,
                WBAPICategory.BUYER_CHAT.value,
            ],
            "configured_token_categories": [
                category
                for category, count in (
                    (
                        WBAPICategory.FEEDBACKS_QUESTIONS.value,
                        feedbacks_questions_token_count,
                    ),
                    (WBAPICategory.BUYER_CHAT.value, buyer_chat_token_count),
                )
                if count
            ],
            "missing_token_categories": [
                category
                for category, count in (
                    (
                        WBAPICategory.FEEDBACKS_QUESTIONS.value,
                        feedbacks_questions_token_count,
                    ),
                    (WBAPICategory.BUYER_CHAT.value, buyer_chat_token_count),
                )
                if not count
            ],
        }
        return item

    async def _local_claims_health(
        self,
        *,
        session: AsyncSession | None,
        account: WBAccount | None,
    ) -> PortalModuleHealthItem | None:
        if session is None or account is None or not hasattr(session, "execute"):
            return None
        try:
            run_count = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(ClaimDetectionRun)
                        .where(ClaimDetectionRun.account_id == int(account.id))
                    )
                ).scalar()
                or 0
            )
            active_runs = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(ClaimDetectionRun)
                        .where(
                            ClaimDetectionRun.account_id == int(account.id),
                            ClaimDetectionRun.status.in_(("queued", "running")),
                        )
                    )
                ).scalar()
                or 0
            )
            failed_runs = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(ClaimDetectionRun)
                        .where(
                            ClaimDetectionRun.account_id == int(account.id),
                            ClaimDetectionRun.status == "failed",
                        )
                    )
                ).scalar()
                or 0
            )
            open_candidates = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(ClaimCandidate)
                        .where(
                            ClaimCandidate.account_id == int(account.id),
                            ClaimCandidate.status.in_(("new", "reviewing", "accepted")),
                        )
                    )
                ).scalar()
                or 0
            )
            latest_success = (
                await session.execute(
                    select(ClaimDetectionRun.finished_at)
                    .where(
                        ClaimDetectionRun.account_id == int(account.id),
                        ClaimDetectionRun.status == "completed",
                    )
                    .order_by(
                        ClaimDetectionRun.finished_at.desc().nullslast(),
                        ClaimDetectionRun.id.desc(),
                    )
                    .limit(1)
                )
            ).scalar()
            latest_run_id = (
                await session.execute(
                    select(ClaimDetectionRun.id)
                    .where(ClaimDetectionRun.account_id == int(account.id))
                    .order_by(
                        ClaimDetectionRun.created_at.desc().nullslast(),
                        ClaimDetectionRun.id.desc(),
                    )
                    .limit(1)
                )
            ).scalar()
        except Exception:
            return None
        if active_runs:
            status: PortalStatus = "running"
        elif failed_runs and not run_count:
            status = "unavailable"
        elif failed_runs:
            status = "degraded"
        elif open_candidates:
            status = "ok"
        else:
            status = "empty"
        item = self._item(
            module="claims",
            status=status,
            enabled=True,
            configured=True,
            message="local claims detection uses finance database",
            warnings=["local", "wb_submit_disabled"],
        )
        item.mode = "local"
        item.actionable_open_issues = open_candidates
        item.last_success_at = latest_success
        item.last_run_id = latest_run_id
        return item

    async def _local_experiments_health(
        self,
        *,
        session: AsyncSession | None,
        account: WBAccount | None,
    ) -> PortalModuleHealthItem | None:
        if not self.settings.experiments_enabled:
            return None
        if session is None or account is None or not hasattr(session, "execute"):
            return None
        try:
            settings_count = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(ExperimentSettings)
                        .where(ExperimentSettings.account_id == int(account.id))
                    )
                ).scalar()
                or 0
            )
            active_count = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(Experiment)
                        .where(
                            Experiment.account_id == int(account.id),
                            Experiment.status.in_(
                                (
                                    "planned",
                                    "baseline_collecting",
                                    "ready_for_change",
                                    "change_recorded",
                                    "post_collecting",
                                    "ready_for_evaluation",
                                )
                            ),
                        )
                    )
                ).scalar()
                or 0
            )
            due_count = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(Experiment)
                        .where(
                            Experiment.account_id == int(account.id),
                            Experiment.status.in_(
                                ("post_collecting", "ready_for_evaluation")
                            ),
                            Experiment.evaluation_due_at <= utcnow(),
                        )
                    )
                ).scalar()
                or 0
            )
            latest_snapshot = (
                await session.execute(
                    select(func.max(ExperimentMetricSnapshot.created_at)).where(
                        ExperimentMetricSnapshot.account_id == int(account.id)
                    )
                )
            ).scalar()
        except Exception:
            return None
        status: PortalStatus = (
            "collecting"
            if due_count
            else ("ok" if active_count or settings_count else "empty")
        )
        item = self._item(
            module="experiments",
            status=status,
            enabled=True,
            configured=True,
            message="local experiments use finance marts and metric snapshots",
            warnings=["local", "observational_not_causal"],
        )
        item.mode = "local"
        item.actionable_open_issues = due_count
        item.unique_products_analyzed = active_count
        item.last_success_at = latest_snapshot
        return item

    def _normalize_db_status(self, value: str, *, enabled: bool) -> PortalStatus:
        if not enabled:
            return "disabled"
        normalized = value.strip().lower()
        if normalized in {
            "ok",
            "not_configured",
            "unavailable",
            "empty",
            "beta",
            "disabled",
            "degraded",
        }:
            return normalized  # type: ignore[return-value]
        return "unavailable"

    def _db_integration_message(
        self,
        integration: PortalIntegration,
        *,
        module: PortalModuleName,
        status: PortalStatus,
    ) -> str:
        if integration.last_error_message:
            return (
                self._safe_message(integration.last_error_message)
                or f"{module} integration is {status}"
            )
        if status == "disabled":
            return f"{module} integration is disabled for this account"
        if status == "not_configured":
            return f"{module} integration is not configured for this account"
        if status == "empty":
            return f"{module} integration is configured and has no current data"
        if status == "beta":
            return f"{module} integration is configured in beta mode"
        return f"{module} integration is configured from finance database"

    async def _checker_health(
        self, account: WBAccount | None
    ) -> PortalModuleHealthItem:
        if not self._configured_url(self.settings.checker_base_url):
            return self._item(
                module="checker",
                status="not_configured",
                enabled=True,
                configured=False,
                message="checker_base_url is not configured",
            )
        if account is not None and self.checker.resolve_store_id(account) is None:
            return self._item(
                module="checker",
                status="not_configured",
                enabled=True,
                configured=False,
                message="checker service is configured, but this account has no checker store mapping",
                warnings=["checker_account_store_mapping is missing for this account"],
            )
        return await self._adapter_health(
            module="checker",
            enabled=True,
            configured=True,
            awaitable=self.checker.health(account),
        )

    async def _stockops_health(self) -> PortalModuleHealthItem:
        if not self._configured_url(self.settings.stockops_base_url):
            return self._item(
                module="stockops",
                status="not_configured",
                enabled=True,
                configured=False,
                message="stockops_base_url is not configured",
            )
        return await self._adapter_health(
            module="stockops",
            enabled=True,
            configured=True,
            awaitable=self.stockops.health(),
        )

    async def _local_grouping_health(
        self,
        *,
        session: AsyncSession | None,
        account: WBAccount | None,
    ) -> PortalModuleHealthItem | None:
        if session is None or account is None or not hasattr(session, "execute"):
            return None
        try:
            status = await self.grouping_beta.health(
                session, account_id=int(account.id)
            )
        except Exception:
            return None
        item = self._item(
            module="grouping",
            status=status.get("status") or "empty",
            enabled=bool(status.get("enabled", True)),
            configured=bool(status.get("configured", True)),
            message=str(
                status.get("message")
                or "local grouping beta uses Finance product cards"
            ),
            warnings=["local", "recommendation_only"],
        )
        item.mode = "local"
        item.eligible_products = status.get("eligible_products")
        item.unique_products_analyzed = status.get("unique_products_analyzed")
        item.last_run_id = status.get("last_run_id")
        item.last_success_at = status.get("last_success_at")
        return item

    async def _local_stock_control_health(
        self,
        *,
        session: AsyncSession | None,
        account: WBAccount | None,
    ) -> PortalModuleHealthItem | None:
        if session is None or account is None or not hasattr(session, "execute"):
            return None
        try:
            status = await self.stock_control.status(
                session, account_id=int(account.id)
            )
        except Exception:
            return self._item(
                module="stockops",
                status="unavailable",
                enabled=True,
                configured=True,
                message="local stock control health is unavailable",
                warnings=["stock_control"],
            ).model_copy(update={"mode": "local"})

        latest_run = status.latest_run
        if latest_run is None:
            module_status: PortalStatus = "empty"
            message = "local stock control is configured; no runs yet"
        elif latest_run.status in {"failed", "cancelled"}:
            module_status = "degraded"
            message = "local stock control has recent runs with warnings"
        elif latest_run.status in {"queued", "running"}:
            module_status = "running"
            message = "local stock control run is queued or running"
        else:
            module_status = "ok"
            message = "local stock control is available"

        summary = dict(status.summary or {})
        mapping = dict(status.mapping_summary or {})
        item = self._item(
            module="stockops",
            status=module_status,
            enabled=True,
            configured=True,
            message=message,
            warnings=status.warnings,
        )
        return item.model_copy(
            update={
                "mode": "local",
                "last_run_id": latest_run.id if latest_run is not None else None,
                "last_success_at": latest_run.finished_at
                if latest_run is not None and latest_run.status == "completed"
                else None,
                "unique_products_analyzed": summary.get("analyzed_products"),
                "analyzed_products": summary.get("analyzed_products"),
                "regions_count": summary.get("regions"),
                "movements_count": summary.get("movements"),
                "unmapped_warehouses": mapping.get("unmapped_warehouses"),
                "source_freshness": status.source_freshness,
            }
        )

    async def _grouping_health(
        self, account: WBAccount | None
    ) -> PortalModuleHealthItem:
        if not self.settings.grouping_enabled:
            return self._item(
                module="grouping",
                status="disabled",
                enabled=False,
                configured=False,
                message="grouping beta is disabled",
            )
        if not self._configured_url(self.settings.grouping_base_url):
            return self._item(
                module="grouping",
                status="not_configured",
                enabled=True,
                configured=False,
                message="grouping_base_url is not configured",
            )
        allowed_ids = {int(item) for item in self.settings.grouping_test_account_ids}
        if account is None:
            return self._item(
                module="grouping",
                status="degraded",
                enabled=True,
                configured=True,
                message="grouping beta is configured, but account context is required",
                warnings=["account_id is required for grouping beta health"],
            )
        if not allowed_ids or int(account.id) not in allowed_ids:
            return self._item(
                module="grouping",
                status="degraded",
                enabled=True,
                configured=True,
                message="grouping beta is configured, but this account is not in grouping_test_account_ids",
                warnings=["grouping beta is enabled only for configured test accounts"],
            )
        return await self._adapter_health(
            module="grouping",
            enabled=True,
            configured=True,
            awaitable=self.grouping.health(account),
            beta=True,
        )

    async def _reputation_health(
        self, account: WBAccount | None
    ) -> PortalModuleHealthItem:
        if not self.settings.reputation_enabled:
            return self._item(
                module="reputation",
                status="disabled",
                enabled=False,
                configured=False,
                message="reputation module is disabled",
            )
        if not self._configured_url(self.settings.reputation_base_url):
            return self._item(
                module="reputation",
                status="not_configured",
                enabled=True,
                configured=False,
                message="reputation_base_url is not configured",
            )
        if account is not None and self.reputation.resolve_shop_id(account) is None:
            return self._item(
                module="reputation",
                status="degraded",
                enabled=True,
                configured=True,
                message="reputation service is configured, but this account has no reputation shop mapping",
                warnings=["reputation_shop_map is missing for this account"],
            )
        return await self._adapter_health(
            module="reputation",
            enabled=True,
            configured=True,
            awaitable=self.reputation.health(account),
        )

    def _external_config_health(
        self,
        *,
        module: PortalModuleName,
        enabled: bool,
        base_url: str | None,
    ) -> PortalModuleHealthItem:
        if not enabled:
            return self._item(
                module=module,
                status="disabled",
                enabled=False,
                configured=False,
                message=f"{module} module is disabled",
            )
        if not self._configured_url(base_url):
            return self._item(
                module=module,
                status="not_configured",
                enabled=True,
                configured=False,
                message=f"{module}_base_url is not configured",
            )
        return self._item(
            module=module,
            status="degraded",
            enabled=True,
            configured=True,
            message=f"{module} module is configured, but a live adapter health probe is not wired yet",
            warnings=["config-only integration health"],
        )

    def _experiments_health(self) -> PortalModuleHealthItem:
        if not self.settings.experiments_enabled:
            return self._item(
                module="experiments",
                status="disabled",
                enabled=False,
                configured=False,
                message="experiments module is disabled",
            )
        return self._item(
            module="experiments",
            status="ok",
            enabled=True,
            configured=True,
            message="experiments module uses finance database",
        )

    async def _adapter_health(
        self,
        *,
        module: PortalModuleName,
        enabled: bool,
        configured: bool,
        awaitable: Awaitable[tuple[str, str | None]],
        beta: bool = False,
    ) -> PortalModuleHealthItem:
        try:
            raw_status, detail = await awaitable
        except Exception:
            return self._item(
                module=module,
                status="unavailable",
                enabled=enabled,
                configured=configured,
                message=f"{module} module is unavailable",
            )
        status, warnings = self._normalize_status(raw_status, beta=beta)
        return self._item(
            module=module,
            status=status,
            enabled=enabled,
            configured=configured,
            message=detail,
            warnings=warnings,
        )

    def _normalize_status(
        self, value: str | None, *, beta: bool = False
    ) -> tuple[PortalStatus, list[str]]:
        normalized = str(value or "").strip().lower()
        warnings: list[str] = []
        if beta or normalized == "beta":
            warnings.append("beta")
        if normalized in {"ok", "beta"}:
            return "ok", warnings
        if normalized in {"disabled", "not_configured", "unavailable", "degraded"}:
            return normalized, warnings
        if normalized == "empty":
            return "degraded", warnings
        return "unavailable", warnings

    def _item(
        self,
        *,
        module: PortalModuleName,
        status: PortalStatus,
        enabled: bool,
        configured: bool,
        message: str | None = None,
        warnings: list[str] | None = None,
    ) -> PortalModuleHealthItem:
        safe_message = self._safe_message(message)
        runtime_fields: dict[str, Any] = {}
        if module == "reputation":
            adapter_runtime_status = getattr(self.reputation, "runtime_status", None)
            runtime_fields = (
                adapter_runtime_status() if callable(adapter_runtime_status) else {}
            )
        runtime_status = self._module_runtime_status(
            module=module,
            status=status,
            enabled=enabled,
            configured=configured,
        )
        runtime_fields.setdefault("runtime_status", runtime_status)
        runtime_fields.setdefault(
            "marketplace_write_policy",
            self._marketplace_write_policy(
                module=module, runtime_status=runtime_status
            ),
        )
        policy = self._visibility_policy(
            module=module,
            status=status,
            enabled=enabled,
            configured=configured,
            message=safe_message,
            warnings=warnings or [],
        )
        return PortalModuleHealthItem(
            module=module,
            status=status,
            enabled=enabled,
            configured=configured,
            visible=policy["visible"],
            beta=policy["beta"],
            navigation_group=policy["navigation_group"],
            reason=policy["reason"],
            required_env_keys=policy["required_env_keys"],
            last_checked_at=utcnow(),
            message=safe_message,
            detail=safe_message,
            warnings=warnings or [],
            **runtime_fields,
        )

    def _module_runtime_status(
        self,
        *,
        module: PortalModuleName,
        status: PortalStatus,
        enabled: bool,
        configured: bool,
    ) -> str:
        if not enabled or status == "disabled":
            return "disabled"
        if not configured or status == "not_configured":
            return "not_configured"
        if module == "grouping":
            return "beta_readonly"
        if module == "photo":
            return "beta_draft_only"
        if module == "experiments":
            return "beta_draft_only"
        if module == "stockops":
            return "beta_draft_only"
        if module == "claims":
            return (
                "enabled_write_actions"
                if self.settings.enable_claims_submit
                else "beta_draft_only"
            )
        if module == "reputation":
            if (
                self.settings.enable_reputation_publish
                or self.settings.enable_reputation_write_actions
            ):
                return "enabled_write_actions"
            return "beta_draft_only"
        return "enabled_safe" if module in MVP_MODULES else "beta_readonly"

    def _marketplace_write_policy(
        self,
        *,
        module: PortalModuleName,
        runtime_status: str,
    ) -> dict[str, Any]:
        beta = module in BETA_MODULES
        marketplace_module = module in BETA_MODULES or module == "checker"
        write_enabled = runtime_status == "enabled_write_actions"
        return {
            "runtime_status": runtime_status,
            "marketplace_write_actions_enabled": write_enabled,
            "requires_permission_check": marketplace_module,
            "requires_preview_diff": marketplace_module,
            "requires_explicit_confirm": marketplace_module,
            "requires_audit_log": marketplace_module,
            "result_status_required": marketplace_module,
            "beta_module": beta,
            "wb_apply_enabled": write_enabled,
            "required_token_categories": self._required_token_categories(module),
            "safe_mode_reason": self._runtime_safe_mode_reason(
                module, runtime_status=runtime_status
            ),
        }

    def _required_token_categories(self, module: str) -> list[str]:
        return {
            "reputation": [
                WBAPICategory.FEEDBACKS_QUESTIONS.value,
                WBAPICategory.BUYER_CHAT.value,
            ],
            "claims": [WBAPICategory.BUYER_RETURNS.value],
            "photo": [WBAPICategory.CONTENT.value],
            "experiments": [WBAPICategory.PROMOTION.value, WBAPICategory.CONTENT.value],
            "grouping": [WBAPICategory.CONTENT.value],
            "stockops": [WBAPICategory.ANALYTICS.value, WBAPICategory.STATISTICS.value],
            "checker": [WBAPICategory.CONTENT.value],
        }.get(module, [])

    def _runtime_safe_mode_reason(self, module: str, *, runtime_status: str) -> str:
        if runtime_status == "disabled":
            return "module is disabled"
        if runtime_status == "not_configured":
            return "module is not configured"
        if module == "grouping":
            return "Grouping is recommendation-only until WB/apply merge has preview, confirm, audit, and verification."
        if module == "photo":
            return "Photo Studio is draft-only; media publish is disabled until preview, confirm, audit, and verification are wired."
        if module == "experiments":
            return "Promotion experiments require preview, budget check, token check, explicit confirm, and audit before WB writes."
        if module == "reputation":
            return "Reputation replies require feedbacks/questions or buyer-chat permissions, preview, explicit confirm, and audit."
        if module == "claims":
            return "Claims submissions require manager permission, previewed evidence, explicit confirm, and audit."
        if module == "stockops":
            return "Stock Control runs locally; marketplace-affecting actions stay draft/recommendation-only."
        return "module is safe for seller workflow"

    def _configured_url(self, value: str | None) -> bool:
        return bool(str(value or "").strip())

    def _safe_message(self, value: str | None) -> str | None:
        if value is None:
            return None
        result = str(value)
        for secret_name in (
            "checker_internal_token",
            "stockops_internal_token",
            "grouping_internal_token",
            "reputation_internal_token",
            "claims_internal_token",
            "photo_internal_token",
        ):
            result = result.replace(
                secret_name, f"{secret_name.split('_internal_token')[0]} credential"
            )
        return redact_sensitive_text(result)

    def _visibility_policy(
        self,
        *,
        module: PortalModuleName,
        status: PortalStatus,
        enabled: bool,
        configured: bool,
        message: str | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        policy_hints = [*warnings]
        if message:
            policy_hints.append(message)
        beta = module in BETA_MODULES
        visible = False
        group = "hidden"
        if module in {"finance", "expenses", "actions", "products"}:
            visible = True
            group = "core"
        elif module == "doctor":
            visible = bool(enabled and configured and status == "ok")
            group = "hidden" if not visible else "operator"
        elif module == "checker":
            visible = True
            group = "operator"
        elif module == "reputation":
            visible = bool(enabled or configured)
            group = "beta" if visible else "hidden"
        elif module == "claims":
            visible = bool(enabled or configured)
            group = "beta" if visible else "hidden"
        elif module == "grouping":
            blocked_by_beta_account = any(
                "grouping_test_account_ids" in str(item)
                or "configured test accounts" in str(item)
                for item in policy_hints
            )
            visible = bool(
                enabled
                and configured
                and status in {"ok", "degraded", "empty", "beta"}
                and not blocked_by_beta_account
            )
            group = "beta" if visible else "hidden"
        elif module == "stockops":
            visible = bool(enabled)
            group = "beta" if visible else "hidden"
        elif module == "photo":
            visible = bool(enabled and configured)
            group = "beta" if visible else "hidden"
        elif module == "experiments":
            visible = bool(enabled)
            group = "beta" if visible else "hidden"
        elif module == "results":
            visible = True
            group = "operator"
        return {
            "visible": visible,
            "beta": beta,
            "navigation_group": group,
            "reason": message
            or self._default_visibility_reason(
                module, status=status, visible=visible, warnings=warnings
            ),
            "required_env_keys": self._required_env_keys(
                module=module,
                status=status,
                enabled=enabled,
                configured=configured,
                warnings=policy_hints,
            ),
        }

    def _default_visibility_reason(
        self, module: str, *, status: str, visible: bool, warnings: list[str]
    ) -> str:
        if visible and status in {"ok", "degraded"}:
            return f"{module} is available for navigation"
        if warnings:
            return "; ".join(str(item) for item in warnings)
        return f"{module} is {status}"

    def _required_env_keys(
        self,
        *,
        module: str,
        status: str,
        enabled: bool,
        configured: bool,
        warnings: list[str],
    ) -> list[str]:
        keys: list[str] = []
        if module == "checker" and not configured:
            keys.append("CHECKER_BASE_URL")
            if any(
                "store mapping" in str(item) or "account_store_mapping" in str(item)
                for item in warnings
            ):
                keys.append("CHECKER_ACCOUNT_STORE_MAPPING")
        if module == "stockops" and not configured:
            keys.append("STOCKOPS_BASE_URL")
        if module == "grouping":
            if not enabled:
                keys.append("GROUPING_ENABLED")
            elif not configured:
                keys.append("GROUPING_BASE_URL")
            elif any("grouping_test_account_ids" in str(item) for item in warnings):
                keys.append("GROUPING_TEST_ACCOUNT_IDS")
        if module == "reputation":
            if not enabled:
                keys.append("REPUTATION_ENABLED")
            elif not configured:
                keys.append("REPUTATION_BASE_URL")
            elif any("reputation_shop_map" in str(item) for item in warnings):
                keys.append("REPUTATION_SHOP_MAP")
        if module == "claims":
            if not enabled:
                keys.append("CLAIMS_ENABLED")
            elif not configured:
                keys.append("CLAIMS_BASE_URL")
        if module == "photo":
            if not enabled:
                keys.append("PHOTO_ENABLED")
            elif not configured:
                keys.append("PHOTO_BASE_URL")
        return keys
