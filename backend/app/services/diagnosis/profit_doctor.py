from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import WBAccount
from app.schemas.operator import (
    ActionType,
    DiagnosisOut,
    DiagnosisType,
    ModuleHealthOut,
    OperatorModule,
    Priority,
    ProfitDoctorOut,
    SignalOut,
    SignalType,
    TrustState,
    UnifiedActionOut,
)
from app.schemas.portal import PortalModuleHealth, PortalProductQualityRead
from app.services.card_quality import CardQualityAnalysisService
from app.services.checker_adapter import CheckerAdapter
from app.services.guided_fixes import GuidedFixMapper
from app.services.module_registry import ModuleRegistryService
from app.services.money_snapshots import MoneyEndpointSnapshotService
from app.services.reputation_adapter import ReputationAdapter


@dataclass
class ProductContext:
    raw: dict[str, Any]
    nm_id: int | None
    sku_id: int | None
    vendor_code: str | None
    title: str
    revenue: float
    profit: float | None
    ads_spend: float
    stock_qty: float | None
    days_of_stock: float | None
    sales_velocity_daily: float | None
    missing_cost: bool


class ProfitDoctorService:
    """Rule-based v1 for the legacy profit diagnostics surface."""

    HIGH_REVENUE_FLOOR = 10_000.0
    MISSING_COST_P0_REVENUE = 100_000.0
    LOW_QUALITY_SCORE = 70
    LOW_STOCK_QTY = 3.0
    LOW_DAYS_OF_STOCK = 7.0
    HIGH_STOCK_QTY = 100.0
    HIGH_DAYS_OF_STOCK = 60.0

    def __init__(
        self,
        *,
        money: MoneyEndpointSnapshotService | None = None,
        checker: CheckerAdapter | None = None,
        card_quality: CardQualityAnalysisService | None = None,
        module_registry: ModuleRegistryService | None = None,
        reputation_adapter: Any | None = None,
        claims_adapter: Any | None = None,
    ) -> None:
        self.money = money or MoneyEndpointSnapshotService()
        self.checker = checker or CheckerAdapter()
        self.card_quality = card_quality
        self.module_registry = module_registry or ModuleRegistryService(
            checker=self.checker
        )
        self.reputation_adapter = reputation_adapter or ReputationAdapter()
        self.claims_adapter = claims_adapter
        self.guided_fixes = GuidedFixMapper()

    async def diagnose(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        nm_id: int | None = None,
        limit: int = 100,
    ) -> ProfitDoctorOut:
        unavailable: list[str] = []
        warnings: list[str] = []
        summary_payload = await self._safe_source(
            unavailable,
            "money_summary",
            self.money.summary(
                session, account_id=account_id, date_from=date_from, date_to=date_to
            ),
        )
        product_not_found = False
        if nm_id is not None:
            article_detail = await self._exact_product_detail(
                session,
                unavailable=unavailable,
                account_id=account_id,
                date_from=date_from,
                date_to=date_to,
                nm_id=nm_id,
            )
            articles_page = (
                {"items": [article_detail]}
                if article_detail is not None
                else {"items": []}
            )
            product_not_found = article_detail is None
        else:
            articles_page = await self._safe_source(
                unavailable,
                "money_articles",
                self.money.articles(
                    session,
                    account_id=account_id,
                    date_from=date_from,
                    date_to=date_to,
                    search=None,
                    limit=limit,
                    offset=0,
                    sort_by="priority_score",
                    sort_dir="desc",
                ),
            )
        blockers = await self._safe_source(
            unavailable,
            "money_data_blockers",
            self.money.data_blockers(
                session, account_id=account_id, date_from=date_from, date_to=date_to
            ),
        )

        products = self._product_contexts(self._items(articles_page), nm_id=nm_id)
        if nm_id is not None and not products:
            product_not_found = True
        total_revenue = sum(product.revenue for product in products)
        high_revenue_threshold = max(
            self.HIGH_REVENUE_FLOOR,
            total_revenue * 0.2 if total_revenue else self.HIGH_REVENUE_FLOOR,
        )

        account = await self._safe_account(session, account_id=account_id)
        module_health = await self._module_health(session=session, account=account)
        signals: list[SignalOut] = []
        diagnoses: list[DiagnosisOut] = []
        actions: list[UnifiedActionOut] = []

        self._add_data_blocker_rules(
            account_id=account_id,
            requested_nm_id=nm_id,
            blockers=blockers,
            signals=signals,
            diagnoses=diagnoses,
            actions=actions,
        )

        for product in products:
            self._add_product_finance_rules(
                account_id=account_id,
                product=product,
                high_revenue_threshold=high_revenue_threshold,
                signals=signals,
                diagnoses=diagnoses,
                actions=actions,
            )
            self._add_experiment_opportunity_rule(
                account_id=account_id,
                product=product,
                high_revenue_threshold=high_revenue_threshold,
                signals=signals,
                diagnoses=diagnoses,
                actions=actions,
            )

        await self._add_checker_rules(
            session=session,
            account=account,
            account_id=account_id,
            products=products,
            high_revenue_threshold=high_revenue_threshold,
            signals=signals,
            diagnoses=diagnoses,
            actions=actions,
            unavailable=unavailable,
        )
        await self._add_optional_adapter_rules(
            adapter=self.reputation_adapter,
            source="reputation",
            session=session,
            unavailable=unavailable,
            signals=signals,
            diagnoses=diagnoses,
            actions=actions,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            nm_id=nm_id,
        )
        await self._add_optional_adapter_rules(
            adapter=self.claims_adapter,
            source="claims",
            session=session,
            unavailable=unavailable,
            signals=signals,
            diagnoses=diagnoses,
            actions=actions,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            nm_id=nm_id,
        )
        if product_not_found:
            signals = []
            diagnoses = []
            actions = []

        actions = self._sorted_actions(actions)
        diagnoses = self._sorted_diagnoses(diagnoses)
        estimated_impact = self._estimated_impact(actions)
        trust_state = self._trust_state(
            summary_payload=summary_payload,
            blockers=blockers,
            unavailable=unavailable,
            diagnoses=diagnoses,
        )
        if trust_state in {TrustState.BLOCKED, TrustState.PROVISIONAL}:
            warnings.append(
                "Legacy-диагностика прибыли использует предварительные данные; проверьте блокеры данных перед финальными выводами."
            )
        if product_not_found:
            warnings.append(
                f"Товар nm_id={nm_id} не найден в финансовых данных за выбранный период."
            )
        status = (
            "empty"
            if product_not_found
            else "ok"
            if summary_payload is not None or products
            else "unavailable"
        )
        business_status = self._business_status(
            status=status, trust_state=trust_state, diagnoses=diagnoses
        )
        top_sections = self._top_sections(diagnoses)

        return ProfitDoctorOut(
            status=status,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            trust_state=trust_state,
            summary=(
                f"Legacy-диагностика прибыли не нашла товар nm_id={nm_id} в финансовых данных за выбранный период."
                if product_not_found
                else self._summary(
                    diagnoses=diagnoses, actions=actions, unavailable=unavailable
                )
            ),
            headline=self._headline(
                business_status=business_status,
                diagnoses=diagnoses,
                unavailable=unavailable,
            ),
            business_status=business_status,
            critical_count=sum(
                1 for item in diagnoses if item.priority in {Priority.P0, Priority.P1}
            ),
            money_at_risk_amount=estimated_impact,
            money_at_risk_confidence=self._amount_confidence(
                estimated_impact, trust_state=trust_state
            ),
            money_at_risk_calculation_note=self._calculation_note(
                estimated_impact, trust_state=trust_state
            ),
            top_sections=top_sections,
            today_plan_summary=self._today_plan_summary(actions),
            total_signals=len(signals),
            total_diagnoses=len(diagnoses),
            estimated_impact_amount=estimated_impact,
            estimated_impact_confidence=self._amount_confidence(
                estimated_impact, trust_state=trust_state
            ),
            estimated_impact_calculation_note=self._calculation_note(
                estimated_impact, trust_state=trust_state
            ),
            top_profit_leaks=[
                diagnosis
                for diagnosis in diagnoses
                if diagnosis.diagnosis_type
                in {
                    DiagnosisType.PROFIT_LEAK,
                    DiagnosisType.ADS_EATING_PROFIT,
                    DiagnosisType.COST_MISSING,
                }
            ][:5],
            root_causes=diagnoses[:8],
            today_plan=actions[:7],
            product_diagnoses=[
                diagnosis for diagnosis in diagnoses if diagnosis.nm_id is not None
            ],
            module_health=module_health,
            signals=signals,
            diagnoses=diagnoses,
            actions=actions,
            data={
                "total_products_analyzed": len(products),
                "requested_nm_id": nm_id,
                "product_found": not product_not_found,
                "total_revenue_analyzed": total_revenue,
                "high_revenue_threshold": high_revenue_threshold,
                "money_at_risk": {
                    "amount": estimated_impact,
                    "currency": "RUB",
                    "is_estimated": estimated_impact is not None,
                    "confidence": self._amount_confidence(
                        estimated_impact, trust_state=trust_state
                    ),
                    "calculation_note": self._calculation_note(
                        estimated_impact, trust_state=trust_state
                    ),
                    "label": "Оценка потенциального эффекта по правилам legacy-диагностики прибыли, не точный прогноз.",
                    "trust_state": trust_state.value
                    if hasattr(trust_state, "value")
                    else str(trust_state),
                },
            },
            warnings=warnings,
            unavailable_sources=self._dedupe(unavailable),
        )

    def _add_data_blocker_rules(
        self,
        *,
        account_id: int,
        requested_nm_id: int | None,
        blockers: Any,
        signals: list[SignalOut],
        diagnoses: list[DiagnosisOut],
        actions: list[UnifiedActionOut],
    ) -> None:
        payload = self._dump(blockers)
        for row in list(payload.get("blockers") or []) + list(
            payload.get("warnings") or []
        ):
            if not isinstance(row, dict):
                continue
            row_nm_id = self._int(row.get("nm_id") or row.get("nmId"))
            if requested_nm_id is not None and row_nm_id != requested_nm_id:
                continue
            code = str(row.get("code") or "").strip()
            if code not in {
                "missing_manual_cost",
                "manual_cost_unresolved_sku",
                "seller_other_expense_missing",
            }:
                if code == "finance_report_anomaly" or "report_anomaly" in code:
                    self._append_rule(
                        account_id=account_id,
                        nm_id=row_nm_id,
                        sku_id=self._int(row.get("sku_id") or row.get("skuId")),
                        source_module=OperatorModule.FINANCE,
                        signal_type=SignalType.DATA_QUALITY,
                        diagnosis_type=DiagnosisType.REPORT_ANOMALY,
                        action_type=ActionType.OPEN_CASE,
                        priority=Priority.P2,
                        title="Проверить аномалию финансового отчета",
                        reason=str(
                            row.get("business_impact")
                            or row.get("message")
                            or row.get("title")
                            or ""
                        ),
                        next_step="Открыть финансовую сверку и подготовить кейс, если требуется обращение в поддержку.",
                        impact=self._float(
                            row.get("affected_amount") or row.get("affectedAmount")
                        ),
                        signals=signals,
                        diagnoses=diagnoses,
                        actions=actions,
                        raw=row,
                    )
                continue
            impact = self._float(
                row.get("affected_amount")
                or row.get("affectedAmount")
                or row.get("affected_revenue")
                or row.get("affectedRevenue")
            )
            priority = (
                Priority.P0
                if (impact or 0) >= self.MISSING_COST_P0_REVENUE
                else Priority.P1
            )
            self._append_rule(
                account_id=account_id,
                nm_id=row_nm_id,
                sku_id=self._int(row.get("sku_id") or row.get("skuId")),
                source_module=OperatorModule.FINANCE,
                signal_type=SignalType.COST_COVERAGE,
                diagnosis_type=DiagnosisType.COST_MISSING,
                action_type=ActionType.FIX_COSTS,
                priority=priority,
                title="Заполнить себестоимость, чтобы увидеть реальную прибыль",
                reason=str(
                    row.get("business_impact")
                    or row.get("message")
                    or row.get("title")
                    or "Сейчас прибыль по части товаров не финальная: не хватает себестоимости."
                ),
                next_step="Сегодня внесите себестоимость в Costs/Data Fix и пересчитайте прибыль.",
                impact=impact,
                signals=signals,
                diagnoses=diagnoses,
                actions=actions,
                raw=row,
            )

    def _add_product_finance_rules(
        self,
        *,
        account_id: int,
        product: ProductContext,
        high_revenue_threshold: float,
        signals: list[SignalOut],
        diagnoses: list[DiagnosisOut],
        actions: list[UnifiedActionOut],
    ) -> None:
        if product.missing_cost:
            priority = (
                Priority.P0
                if product.revenue >= self.MISSING_COST_P0_REVENUE
                else Priority.P1
            )
            self._append_rule(
                account_id=account_id,
                product=product,
                source_module=OperatorModule.FINANCE,
                signal_type=SignalType.COST_COVERAGE,
                diagnosis_type=DiagnosisType.COST_MISSING,
                action_type=ActionType.FIX_COSTS,
                priority=priority,
                title="Заполнить себестоимость товара",
                reason="Нельзя точно понять прибыль по товару: в расчетах не хватает себестоимости.",
                next_step="Сегодня откройте Costs/Data Fix, внесите себестоимость и пересчитайте витрины.",
                impact=product.revenue,
                signals=signals,
                diagnoses=diagnoses,
                actions=actions,
            )

        if product.profit is not None and product.profit < 0:
            self._append_rule(
                account_id=account_id,
                product=product,
                source_module=OperatorModule.FINANCE,
                signal_type=SignalType.PROFIT,
                diagnosis_type=DiagnosisType.PROFIT_LEAK,
                action_type=ActionType.REVIEW_PROFIT,
                priority=Priority.P1,
                title="Товар продается в минус",
                reason=f"По текущему расчету товар теряет деньги: прибыль {product.profit:.2f} RUB.",
                next_step="Сегодня проверьте цену, себестоимость, логистику и рекламу; остановите расход, который не окупается.",
                impact=abs(product.profit),
                signals=signals,
                diagnoses=diagnoses,
                actions=actions,
            )
        ads_ratio = product.ads_spend / product.revenue if product.revenue > 0 else 0.0
        if product.ads_spend > 0 and (
            ads_ratio >= 0.25
            or (
                product.profit is not None
                and product.ads_spend > max(product.profit, 0) * 0.75
            )
        ):
            priority = (
                Priority.P1
                if ads_ratio >= 0.4
                or (product.profit is not None and product.profit <= 0)
                else Priority.P2
            )
            self._append_rule(
                account_id=account_id,
                product=product,
                source_module=OperatorModule.FINANCE,
                signal_type=SignalType.PROFIT,
                diagnosis_type=DiagnosisType.ADS_EATING_PROFIT,
                action_type=ActionType.REVIEW_PROFIT,
                priority=priority,
                title="Реклама съедает прибыль",
                reason=f"Расходы на рекламу составляют {ads_ratio:.0%} от выручки товара и могут перекрывать маржу.",
                next_step="Сегодня откройте Ads Efficiency, снизьте ставки или остановите кампании без окупаемости.",
                impact=product.ads_spend,
                signals=signals,
                diagnoses=diagnoses,
                actions=actions,
            )
        profitable_or_high_revenue = (
            product.profit or 0
        ) > 0 or product.revenue >= high_revenue_threshold
        low_stock = (
            product.stock_qty is not None
            and product.stock_qty <= self.LOW_STOCK_QTY
            or product.days_of_stock is not None
            and product.days_of_stock <= self.LOW_DAYS_OF_STOCK
        )
        if profitable_or_high_revenue and low_stock:
            priority = (
                Priority.P1
                if product.revenue >= high_revenue_threshold
                else Priority.P2
            )
            self._append_rule(
                account_id=account_id,
                product=product,
                source_module=OperatorModule.STOCKOPS,
                signal_type=SignalType.STOCK,
                diagnosis_type=DiagnosisType.STOCK_RISK,
                action_type=ActionType.STOCK_RECOMMENDATION,
                priority=priority,
                title="Риск потери продаж из-за низкого остатка",
                reason="У прибыльного или выручкообразующего товара мало остатков; продажи могут остановиться.",
                next_step="Сегодня проверьте закупку, перемещение и ближайшую поставку.",
                impact=max(product.profit or 0, product.revenue * 0.1),
                signals=signals,
                diagnoses=diagnoses,
                actions=actions,
            )
        high_stock = (
            product.stock_qty is not None
            and product.stock_qty >= self.HIGH_STOCK_QTY
            or product.days_of_stock is not None
            and product.days_of_stock >= self.HIGH_DAYS_OF_STOCK
        )
        low_sales = (
            product.sales_velocity_daily is not None
            and product.sales_velocity_daily <= 1
        )
        weak_profit = product.profit is None or product.profit <= 0
        if high_stock and (low_sales or weak_profit):
            priority = (
                Priority.P2
                if product.revenue >= high_revenue_threshold
                else Priority.P3
            )
            stock_value = (
                self._float(self._get(product.raw, "stock.stock_value", "stock_value"))
                or product.revenue * 0.1
            )
            self._append_rule(
                account_id=account_id,
                product=product,
                source_module=OperatorModule.STOCKOPS,
                signal_type=SignalType.STOCK,
                diagnosis_type=DiagnosisType.FROZEN_STOCK,
                action_type=ActionType.STOCK_RECOMMENDATION,
                priority=priority,
                title="Деньги заморожены в остатках",
                reason="Остаток высокий, а продажи или прибыль слабые; капитал лежит в товаре.",
                next_step="Сегодня проверьте цену, рекламу, перемещение или план распродажи остатка.",
                impact=stock_value,
                signals=signals,
                diagnoses=diagnoses,
                actions=actions,
            )

    def _add_experiment_opportunity_rule(
        self,
        *,
        account_id: int,
        product: ProductContext,
        high_revenue_threshold: float,
        signals: list[SignalOut],
        diagnoses: list[DiagnosisOut],
        actions: list[UnifiedActionOut],
    ) -> None:
        if product.nm_id is None or product.revenue < high_revenue_threshold:
            return
        self._append_rule(
            account_id=account_id,
            product=product,
            source_module=OperatorModule.EXPERIMENTS,
            signal_type=SignalType.EXPERIMENT,
            diagnosis_type=DiagnosisType.EXPERIMENT_OPPORTUNITY,
            action_type=ActionType.EXPERIMENT_REVIEW,
            priority=Priority.P3,
            title="Отследить результат следующего изменения",
            reason="Товар заметен в выручке; следующее изменение фото, цены, описания или рекламы стоит вести как before/after эксперимент.",
            next_step="Создайте эксперимент в Results, зафиксируйте baseline и точное время ручного изменения.",
            impact=None,
            signals=signals,
            diagnoses=diagnoses,
            actions=actions,
        )

    async def _add_checker_rules(
        self,
        *,
        session: AsyncSession,
        account: WBAccount | None,
        account_id: int,
        products: list[ProductContext],
        high_revenue_threshold: float,
        signals: list[SignalOut],
        diagnoses: list[DiagnosisOut],
        actions: list[UnifiedActionOut],
        unavailable: list[str],
    ) -> None:
        if account is None:
            unavailable.append("checker")
            return
        for product in products[:10]:
            if product.nm_id is None or product.revenue < high_revenue_threshold:
                continue
            try:
                quality = await self._product_quality_signal(
                    session=session,
                    account=account,
                    account_id=account_id,
                    nm_id=product.nm_id,
                )
            except Exception:
                unavailable.append("checker")
                return
            if quality.status in {"not_configured", "disabled"}:
                unavailable.append("checker")
                return
            if quality.status == "unavailable":
                unavailable.append("checker")
                continue
            score = self._quality_score(quality)
            if score is not None and score < self.LOW_QUALITY_SCORE:
                self._append_rule(
                    account_id=account_id,
                    product=product,
                    source_module=OperatorModule.CHECKER,
                    signal_type=SignalType.CARD_QUALITY,
                    diagnosis_type=DiagnosisType.CARD_QUALITY_RISK,
                    action_type=ActionType.CARD_QUALITY_FIX,
                    priority=Priority.P1,
                    title="У выручкообразующего товара слабая карточка",
                    reason=f"Товар приносит выручку, но качество карточки низкое: score {score}. Это может снижать конверсию.",
                    next_step="Сегодня откройте Product 360 -> Quality и исправьте критичные замечания карточки.",
                    impact=product.revenue * 0.05,
                    signals=signals,
                    diagnoses=diagnoses,
                    actions=actions,
                    raw=quality.model_dump(mode="json"),
                )

    async def _product_quality_signal(
        self,
        *,
        session: AsyncSession,
        account: WBAccount,
        account_id: int,
        nm_id: int,
    ) -> PortalProductQualityRead:
        if self.card_quality is not None:
            quality = await self.card_quality.product_quality(
                session, account_id=account_id, nm_id=nm_id
            )
            if quality.status not in {
                "not_analyzed",
                "unavailable",
                "not_configured",
                "disabled",
            }:
                return quality
        return await self.checker.product_quality(account, nm_id=nm_id)

    async def _add_optional_adapter_rules(
        self,
        *,
        adapter: Any | None,
        source: str,
        session: AsyncSession,
        unavailable: list[str],
        signals: list[SignalOut],
        diagnoses: list[DiagnosisOut],
        actions: list[UnifiedActionOut],
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        nm_id: int | None,
    ) -> None:
        if adapter is None:
            unavailable.append(source)
            return
        method = getattr(adapter, "profit_doctor_signals", None)
        if method is None:
            unavailable.append(source)
            return
        try:
            try:
                result = await method(
                    account_id=account_id,
                    date_from=date_from,
                    date_to=date_to,
                    nm_id=nm_id,
                    session=session,
                )
            except TypeError:
                result = await method(
                    account_id=account_id,
                    date_from=date_from,
                    date_to=date_to,
                    nm_id=nm_id,
                )
        except Exception:
            unavailable.append(source)
            return
        if not result and getattr(adapter, "is_configured", True) is False:
            unavailable.append(source)
            return
        for item in result or []:
            payload = self._dump(item)
            payload_nm_id = self._int(payload.get("nm_id") or payload.get("nmId"))
            if nm_id is not None and payload_nm_id != nm_id:
                continue
            diagnosis_type = (
                DiagnosisType.REPUTATION_RISK
                if source == "reputation"
                else DiagnosisType.CLAIM_OPPORTUNITY
                if str(
                    payload.get("action_type")
                    or payload.get("case_type")
                    or payload.get("diagnosis_type")
                    or ""
                ).strip()
                not in {"report_anomaly_candidate", "report_anomaly"}
                else DiagnosisType.REPORT_ANOMALY
            )
            action_type = (
                ActionType.DRAFT_REPLY
                if source == "reputation"
                else ActionType.DRAFT_CLAIM
            )
            self._append_rule(
                account_id=account_id,
                nm_id=payload_nm_id,
                sku_id=self._int(payload.get("sku_id") or payload.get("skuId")),
                source_module=OperatorModule.REPUTATION
                if source == "reputation"
                else OperatorModule.CLAIMS,
                signal_type=SignalType.REVIEW
                if source == "reputation"
                else SignalType.CLAIM,
                diagnosis_type=diagnosis_type,
                action_type=action_type,
                priority=self._priority(
                    payload.get("priority"),
                    default=Priority.P2 if source == "reputation" else Priority.P1,
                ),
                title=str(
                    payload.get("title")
                    or (
                        "Ответить на отзыв, который влияет на продажи"
                        if source == "reputation"
                        else "Проверить возможность компенсации по претензии"
                    )
                ),
                reason=str(
                    payload.get("reason")
                    or payload.get("summary")
                    or (
                        "Есть отзыв или вопрос, который может влиять на доверие к товару."
                        if source == "reputation"
                        else "Есть сигнал по претензии или компенсации; сумму нужно проверить по доказательствам."
                    )
                ),
                next_step=str(
                    payload.get("next_step")
                    or payload.get("nextStep")
                    or (
                        "Сегодня подготовьте черновик ответа и проверьте тон перед публикацией."
                        if source == "reputation"
                        else "Сегодня откройте кейс, проверьте доказательства и подготовьте черновик обращения."
                    )
                ),
                impact=self._float(
                    payload.get("estimated_impact_amount") or payload.get("impact")
                ),
                signals=signals,
                diagnoses=diagnoses,
                actions=actions,
                raw=payload,
            )

    def _append_rule(
        self,
        *,
        account_id: int,
        source_module: OperatorModule,
        signal_type: SignalType,
        diagnosis_type: DiagnosisType,
        action_type: ActionType,
        priority: Priority,
        title: str,
        reason: str,
        next_step: str,
        impact: float | None,
        signals: list[SignalOut],
        diagnoses: list[DiagnosisOut],
        actions: list[UnifiedActionOut],
        product: ProductContext | None = None,
        nm_id: int | None = None,
        sku_id: int | None = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        effective_nm_id = product.nm_id if product is not None else nm_id
        effective_sku_id = product.sku_id if product is not None else sku_id
        vendor_code = product.vendor_code if product is not None else None
        source_id = f"{source_module}:{diagnosis_type}:{effective_nm_id or effective_sku_id or len(diagnoses) + 1}"
        signal_id = f"signal:{source_id}"
        signals.append(
            SignalOut(
                id=signal_id,
                module=source_module,
                signal_type=signal_type,
                account_id=account_id,
                nm_id=effective_nm_id,
                sku_id=effective_sku_id,
                source_id=source_id,
                title=title,
                message=reason,
                value=impact,
                unit="RUB" if impact is not None else None,
                priority=priority,
                trust_state=TrustState.PROVISIONAL,
                data={
                    "vendor_code": vendor_code,
                    "product_title": product.title if product is not None else None,
                    "raw": raw or {},
                },
            )
        )
        diagnosis = DiagnosisOut(
            id=f"diagnosis:{source_id}",
            diagnosis_type=diagnosis_type,
            module=source_module,
            account_id=account_id,
            nm_id=effective_nm_id,
            sku_id=effective_sku_id,
            title=title,
            summary=reason,
            reason=reason,
            priority=priority,
            confidence="medium",
            trust_state=TrustState.PROVISIONAL,
            signal_ids=[signal_id],
            data={
                "estimated_impact_amount": impact,
                "calculation_note": self._rule_calculation_note(
                    diagnosis_type, impact=impact
                ),
                "next_step": next_step,
                "checks": self._rule_checks(diagnosis_type),
                "raw_code": diagnosis_type.value
                if hasattr(diagnosis_type, "value")
                else str(diagnosis_type),
                "vendor_code": vendor_code,
                "product_title": product.title if product is not None else None,
                "revenue_amount": product.revenue if product is not None else None,
                "profit_amount": product.profit if product is not None else None,
                "ads_spend_amount": product.ads_spend if product is not None else None,
                "ads_to_revenue_percent": (
                    product.ads_spend / product.revenue * 100
                    if product is not None and product.revenue > 0
                    else None
                ),
                "stock_qty": product.stock_qty if product is not None else None,
                "days_of_stock": product.days_of_stock if product is not None else None,
                "sales_velocity_daily": product.sales_velocity_daily
                if product is not None
                else None,
            },
        )
        diagnoses.append(diagnosis)
        actions.append(
            UnifiedActionOut(
                id=f"action:{source_id}",
                action_type=action_type,
                status="new",
                priority=priority,
                module=source_module,
                source_module=source_module,
                source_type="profit_doctor_rule",
                source_id=source_id,
                account_id=account_id,
                nm_id=effective_nm_id,
                sku_id=effective_sku_id,
                title=title,
                summary=reason,
                reason=reason,
                next_step=next_step,
                trust_state=TrustState.PROVISIONAL,
                expected_effect_amount=impact,
                confidence="medium",
                guided_fix=self.guided_fixes.to_operator(
                    source_module=getattr(source_module, "value", str(source_module)),
                    action_type=getattr(action_type, "value", str(action_type)),
                    title=title,
                    summary=next_step,
                    nm_id=effective_nm_id,
                    target_id=source_id,
                ),
                can_preview=False,
                can_confirm=False,
                marketplace_change=False,
                data={
                    "diagnosis_id": diagnosis.id,
                    "calculation_note": self._rule_calculation_note(
                        diagnosis_type, impact=impact
                    ),
                    "checks": self._rule_checks(diagnosis_type),
                    "raw_code": action_type.value
                    if hasattr(action_type, "value")
                    else str(action_type),
                    "vendor_code": vendor_code,
                    "product_title": product.title if product is not None else None,
                    "revenue_amount": product.revenue if product is not None else None,
                    "profit_amount": product.profit if product is not None else None,
                    "ads_spend_amount": product.ads_spend
                    if product is not None
                    else None,
                    "ads_to_revenue_percent": (
                        product.ads_spend / product.revenue * 100
                        if product is not None and product.revenue > 0
                        else None
                    ),
                    "stock_qty": product.stock_qty if product is not None else None,
                    "days_of_stock": product.days_of_stock
                    if product is not None
                    else None,
                    "sales_velocity_daily": product.sales_velocity_daily
                    if product is not None
                    else None,
                },
            )
        )

    async def _safe_source(
        self, unavailable: list[str], name: str, awaitable: Any
    ) -> Any:
        try:
            return await awaitable
        except Exception:
            unavailable.append(name)
            return None

    async def _exact_product_detail(
        self,
        session: AsyncSession,
        *,
        unavailable: list[str],
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        nm_id: int,
    ) -> Any | None:
        method = getattr(self.money, "article_detail", None)
        if method is None:
            method = getattr(getattr(self.money, "money", None), "article_detail", None)
        if method is None:
            unavailable.append("money_article_detail")
            return None
        try:
            return await method(
                session,
                account_id=account_id,
                nm_id=nm_id,
                date_from=date_from,
                date_to=date_to,
            )
        except Exception:
            return None

    async def _safe_account(
        self, session: AsyncSession, *, account_id: int
    ) -> WBAccount | None:
        try:
            return await session.get(WBAccount, account_id)
        except Exception:
            return None

    async def _module_health(
        self, *, session: AsyncSession, account: WBAccount | None
    ) -> list[ModuleHealthOut]:
        try:
            health = await self.module_registry.health(account=account, session=session)
        except Exception:
            return [
                ModuleHealthOut(
                    module=OperatorModule.FINANCE,
                    status="ok",
                    trust_state=TrustState.OPERATIONAL,
                    detail="finance core is available",
                )
            ]
        return self._module_health_out(health)

    def _module_health_out(self, health: PortalModuleHealth) -> list[ModuleHealthOut]:
        result: list[ModuleHealthOut] = []
        for module in (
            "finance",
            "checker",
            "stockops",
            "grouping",
            "reputation",
            "claims",
            "photo",
            "experiments",
        ):
            item = getattr(health, module)
            status = str(item.status)
            result.append(
                ModuleHealthOut(
                    module=OperatorModule(module),
                    status=status,
                    trust_state=TrustState.OPERATIONAL
                    if status == "ok"
                    else TrustState.UNAVAILABLE,
                    detail=item.message or item.detail,
                    warnings=list(item.warnings or []),
                    unavailable_sources=[] if status == "ok" else [module],
                    checked_at=item.last_checked_at,
                    data={"enabled": item.enabled, "configured": item.configured},
                )
            )
        return result

    def _product_contexts(
        self, items: list[Any], *, nm_id: int | None
    ) -> list[ProductContext]:
        contexts = [self._product_context(item) for item in items]
        contexts = [item for item in contexts if item.nm_id is not None]
        if nm_id is not None:
            contexts = [item for item in contexts if item.nm_id == nm_id]
        return contexts

    def _product_context(self, item: Any) -> ProductContext:
        raw = self._dump(item)
        product_nm_id = self._int(
            self._get(raw, "nm_id", "identity.nm_id", "raw.nm_id")
        )
        sku_id = self._int(self._get(raw, "sku_id", "identity.sku_id", "raw.sku_id"))
        revenue = (
            self._float(
                self._get(
                    raw,
                    "revenue",
                    "realized_revenue",
                    "money.revenue",
                    "money.sales.revenue",
                )
            )
            or 0.0
        )
        profit = self._float(
            self._get(
                raw,
                "estimated_profit",
                "net_profit",
                "money.profit.after_source_ads",
                "money.profit.after_ads",
                "money.profit.estimated_profit",
            )
        )
        ads_spend = (
            self._float(
                self._get(raw, "ads_spend", "ad_spend", "ads.spend", "money.ads.spend")
            )
            or 0.0
        )
        stock_qty = self._float(
            self._get(raw, "stock_qty", "stock.quantity", "stock.qty")
        )
        days_of_stock = self._float(
            self._get(raw, "days_of_stock", "stock.days_of_stock")
        )
        sales_velocity = self._float(
            self._get(raw, "sales_velocity_daily", "stock.sales_velocity_daily")
        )
        return ProductContext(
            raw=raw,
            nm_id=product_nm_id,
            sku_id=sku_id,
            vendor_code=self._str(
                self._get(raw, "vendor_code", "article", "identity.vendor_code")
            ),
            title=self._str(self._get(raw, "title", "name", "identity.title")) or "",
            revenue=revenue,
            profit=profit,
            ads_spend=ads_spend,
            stock_qty=stock_qty,
            days_of_stock=days_of_stock,
            sales_velocity_daily=sales_velocity,
            missing_cost=self._missing_cost(raw),
        )

    def _missing_cost(self, raw: dict[str, Any]) -> bool:
        if self._bool(self._get(raw, "missing_cost", "cost_missing")):
            return True
        reasons = (
            self._get(
                raw, "blocked_reasons", "data_trust.blocked_reasons", "finality.reasons"
            )
            or []
        )
        if isinstance(reasons, str):
            reasons = [reasons]
        if any("missing_manual_cost" in str(reason) for reason in reasons):
            return True
        cost_coverage = self._get(raw, "cost_coverage", "money.cost_coverage")
        if isinstance(cost_coverage, dict):
            missing_cost_revenue = (
                self._float(
                    cost_coverage.get("missing_cost_revenue")
                    or cost_coverage.get("missingCostRevenue")
                )
                or 0.0
            )
            if (
                cost_coverage.get("can_use_for_final_profit") is False
                and missing_cost_revenue > 0
            ):
                return True
            if (
                str(cost_coverage.get("status") or "").lower() in {"missing", "blocked"}
                and missing_cost_revenue > 0
            ):
                return True
        finality = self._get(raw, "finality")
        if isinstance(finality, dict) and finality.get("profit_final") is False:
            finality_reasons = finality.get("reasons") or []
            return any(
                "missing_manual_cost" in str(reason)
                or (
                    str(reason).lower() == "missing_cost"
                    and isinstance(cost_coverage, dict)
                    and (
                        self._float(
                            cost_coverage.get("missing_cost_revenue")
                            or cost_coverage.get("missingCostRevenue")
                        )
                        or 0.0
                    )
                    > 0
                )
                for reason in finality_reasons
            )
        return False

    def _items(self, page: Any) -> list[Any]:
        if page is None:
            return []
        if isinstance(page, dict):
            return list(page.get("items") or [])
        return list(getattr(page, "items", []) or [])

    def _dump(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return {key: self._dump_value(item) for key, item in value.items()}
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if hasattr(value, "__dict__"):
            return {
                key: self._dump_value(item)
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        return {}

    def _dump_value(self, value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return {key: self._dump_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._dump_value(item) for item in value]
        if hasattr(value, "__dict__") and not isinstance(value, (str, bytes)):
            return {
                key: self._dump_value(item)
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        return value

    def _get(self, payload: dict[str, Any], *paths: str) -> Any:
        for path in paths:
            current: Any = payload
            for part in path.split("."):
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    current = None
                if current is None:
                    break
            if current is not None:
                return current
        return None

    def _quality_score(self, quality: PortalProductQualityRead) -> int | None:
        if quality.score is not None:
            return int(quality.score)
        raw = quality.raw or {}
        return self._int(raw.get("score") or (raw.get("card") or {}).get("score"))

    def _priority(self, value: Any, *, default: Priority) -> Priority:
        try:
            return Priority(str(value))
        except ValueError:
            return default

    def _sorted_actions(
        self, actions: list[UnifiedActionOut]
    ) -> list[UnifiedActionOut]:
        return sorted(
            actions,
            key=lambda item: (
                self._priority_rank(item.priority),
                -(item.expected_effect_amount or 0),
                item.title,
            ),
        )

    def _sorted_diagnoses(self, diagnoses: list[DiagnosisOut]) -> list[DiagnosisOut]:
        return sorted(
            diagnoses,
            key=lambda item: (
                self._priority_rank(item.priority),
                -float((item.data or {}).get("estimated_impact_amount") or 0),
                item.title,
            ),
        )

    def _priority_rank(self, priority: Priority | str) -> int:
        return {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}.get(str(priority), 5)

    def _estimated_impact(self, actions: list[UnifiedActionOut]) -> float | None:
        total = sum(float(action.expected_effect_amount or 0) for action in actions)
        return total if total > 0 else None

    def _amount_confidence(
        self, amount: float | None, *, trust_state: TrustState
    ) -> str:
        if amount is None or trust_state in {
            TrustState.BLOCKED,
            TrustState.UNAVAILABLE,
        }:
            return "low"
        if trust_state == TrustState.FINAL:
            return "medium"
        return "low"

    def _calculation_note(
        self, amount: float | None, *, trust_state: TrustState
    ) -> str:
        if amount is None:
            return "Денежный эффект не рассчитан: нет достаточных сигналов по сумме."
        if trust_state == TrustState.FINAL:
            return "Сумма рассчитана по детерминированным правилам legacy-диагностики прибыли на основе финансовых данных; это оценка эффекта, а не гарантированный прогноз."
        return "Сумма предварительная: это эвристическая оценка по правилам legacy-диагностики прибыли, ее нужно проверять по витринам денег и качеству данных."

    def _rule_calculation_note(
        self, diagnosis_type: DiagnosisType, *, impact: float | None
    ) -> str:
        if impact is None:
            return (
                "Эффект не рассчитан: источник не передал сумму или метрику для оценки."
            )
        if diagnosis_type == DiagnosisType.COST_MISSING:
            return "Оценка основана на выручке или затронутой сумме: без себестоимости точная прибыль не финальная."
        if diagnosis_type == DiagnosisType.PROFIT_LEAK:
            return (
                "Оценка равна текущему отрицательному финансовому результату по товару."
            )
        if diagnosis_type == DiagnosisType.ADS_EATING_PROFIT:
            return (
                "Оценка равна рекламному расходу, который требует проверки окупаемости."
            )
        if diagnosis_type == DiagnosisType.CARD_QUALITY_RISK:
            return "Эвристика: 5% выручки товара с высоким оборотом и низким score карточки."
        if diagnosis_type in {DiagnosisType.STOCK_RISK, DiagnosisType.FROZEN_STOCK}:
            return "Эвристика по прибыли, выручке или стоимости остатка; это ориентир для приоритизации."
        if diagnosis_type in {
            DiagnosisType.REPUTATION_RISK,
            DiagnosisType.CLAIM_OPPORTUNITY,
            DiagnosisType.REPORT_ANOMALY,
        }:
            return "Предварительная оценка из внешнего модуля; сумму нужно проверить по доказательствам и истории."
        return "Предварительная оценка по правилам legacy-диагностики прибыли."

    def _rule_checks(self, diagnosis_type: DiagnosisType) -> list[str]:
        if diagnosis_type == DiagnosisType.ADS_EATING_PROFIT:
            return [
                "Открыть товар в Product 360 → Money и сверить выручку, рекламу, прибыль после рекламы.",
                "Открыть Ads Efficiency и найти кампании по этому nm_id с расходом без окупаемости.",
                "Если DRR высокий и прибыль после рекламы ≤ 0 — снизить ставки или остановить кампанию.",
                "После изменения рекламы пересчитать витрины и проверить, ушел ли риск.",
            ]
        if diagnosis_type == DiagnosisType.PROFIT_LEAK:
            return [
                "Разложить прибыль по водопаду: цена, себестоимость, комиссия, логистика, реклама.",
                "Проверить, не устарела ли себестоимость или цена продажи.",
                "Если маржа отрицательная — поднять цену, снизить расход или временно остановить продвижение.",
            ]
        if diagnosis_type == DiagnosisType.COST_MISSING:
            return [
                "Открыть Costs/Data Fix и заполнить supplier-confirmed себестоимость.",
                "Проверить barcode/vendor_code/tech_size, если себестоимость есть у похожего SKU.",
                "Пересчитать витрины денег и убедиться, что profit стал final.",
            ]
        if diagnosis_type in {DiagnosisType.STOCK_RISK, DiagnosisType.FROZEN_STOCK}:
            return [
                "Проверить текущий остаток, скорость продаж и дни запаса.",
                "Для низкого остатка — создать закупку или перемещение.",
                "Для замороженного остатка — проверить цену, рекламу и план распродажи.",
            ]
        if diagnosis_type == DiagnosisType.REPUTATION_RISK:
            return [
                "Открыть отзывы/вопросы по товару и сгруппировать повторяющиеся причины.",
                "Исправить карточку, описание или качество товара по самым частым жалобам.",
                "Отследить изменение рейтинга и конверсии после правки.",
            ]
        if diagnosis_type in {
            DiagnosisType.CLAIM_OPPORTUNITY,
            DiagnosisType.REPORT_ANOMALY,
        }:
            return [
                "Открыть доказательства по кейсу и сверить сумму с отчетом WB.",
                "Если есть подтверждение — подготовить обращение или claim.",
                "После отправки отметить действие в Action Center.",
            ]
        return [
            "Открыть связанную карточку товара и проверить первичные метрики.",
            "Сверить причину риска с источником данных.",
            "Зафиксировать решение в Action Center.",
        ]

    def _trust_state(
        self,
        *,
        summary_payload: Any,
        blockers: Any,
        unavailable: list[str],
        diagnoses: list[DiagnosisOut],
    ) -> TrustState:
        summary = self._dump(summary_payload)
        trust = summary.get("trust") or summary.get("data_trust") or {}
        if isinstance(trust, dict):
            raw_state = str(
                trust.get("trust_state") or trust.get("state") or ""
            ).lower()
            if raw_state in {"final", "trusted"}:
                return TrustState.FINAL
            if "blocked" in raw_state:
                return TrustState.BLOCKED
        blocker_payload = self._dump(blockers)
        if blocker_payload.get("overall_state") == "blocked" or any(
            diagnosis.diagnosis_type
            in {DiagnosisType.COST_MISSING, DiagnosisType.DATA_BLOCKER}
            for diagnosis in diagnoses
        ):
            return TrustState.BLOCKED
        if "money_summary" in unavailable or "money_articles" in unavailable:
            return TrustState.UNAVAILABLE
        if unavailable:
            return TrustState.PROVISIONAL
        return TrustState.OPERATIONAL

    def _business_status(
        self, *, status: str, trust_state: TrustState, diagnoses: list[DiagnosisOut]
    ) -> str:
        if status == "empty":
            return "empty"
        if status == "unavailable" or trust_state == TrustState.UNAVAILABLE:
            return "unavailable"
        if trust_state == TrustState.BLOCKED or any(
            item.diagnosis_type
            in {DiagnosisType.DATA_BLOCKER, DiagnosisType.COST_MISSING}
            and item.priority in {Priority.P0, Priority.P1}
            for item in diagnoses
        ):
            return "blocked"
        if diagnoses or trust_state == TrustState.PROVISIONAL:
            return "risk"
        return "ok"

    def _headline(
        self,
        *,
        business_status: str,
        diagnoses: list[DiagnosisOut],
        unavailable: list[str],
    ) -> str:
        if business_status == "empty":
            return "Товар не найден в финансовых данных"
        if business_status == "unavailable":
            return "Недостаточно данных для диагностики прибыли"
        if business_status == "blocked":
            return "Сначала разблокируйте данные по прибыли"
        if business_status == "ok":
            return "Критичных утечек прибыли не найдено"
        top = diagnoses[0] if diagnoses else None
        if top is not None:
            return f"Найден риск для прибыли: {top.title}"
        if unavailable:
            return "Диагностика частичная: часть модулей недоступна"
        return "Есть риски, которые стоит проверить сегодня"

    def _top_sections(self, diagnoses: list[DiagnosisOut]) -> dict[str, Any]:
        return {
            "profit_leaks": self._section(
                diagnoses,
                {
                    DiagnosisType.PROFIT_LEAK,
                    DiagnosisType.ADS_EATING_PROFIT,
                    DiagnosisType.COST_MISSING,
                },
            ),
            "reputation_risks": self._section(
                diagnoses, {DiagnosisType.REPUTATION_RISK}
            ),
            "claims_opportunities": self._section(
                diagnoses,
                {DiagnosisType.CLAIM_OPPORTUNITY, DiagnosisType.REPORT_ANOMALY},
            ),
            "data_blockers": self._section(
                diagnoses,
                {
                    DiagnosisType.DATA_BLOCKER,
                    DiagnosisType.COST_MISSING,
                    DiagnosisType.REPORT_ANOMALY,
                },
            ),
            "stock_risks": self._section(
                diagnoses, {DiagnosisType.STOCK_RISK, DiagnosisType.FROZEN_STOCK}
            ),
        }

    def _section(
        self, diagnoses: list[DiagnosisOut], diagnosis_types: set[DiagnosisType]
    ) -> dict[str, Any]:
        items = [item for item in diagnoses if item.diagnosis_type in diagnosis_types]
        amount = sum(
            float((item.data or {}).get("estimated_impact_amount") or 0)
            for item in items
        )
        return {
            "count": len(items),
            "money_at_risk_amount": amount if amount > 0 else None,
            "items": [item.model_dump(mode="json") for item in items[:5]],
        }

    def _today_plan_summary(self, actions: list[UnifiedActionOut]) -> str:
        if not actions:
            return "На сегодня нет срочных действий. Проверьте витрины после обновления данных."
        critical = sum(
            1 for item in actions if item.priority in {Priority.P0, Priority.P1}
        )
        if critical:
            return f"Сегодня: {len(actions[:7])} действий, из них срочных - {critical}. Начните с первого пункта."
        return f"Сегодня: {len(actions[:7])} действий без критичных блокеров. Можно разобрать по приоритету."

    def _summary(
        self,
        *,
        diagnoses: list[DiagnosisOut],
        actions: list[UnifiedActionOut],
        unavailable: list[str],
    ) -> str:
        if not diagnoses:
            if unavailable and "money_article_detail" in unavailable:
                return "Legacy-диагностика прибыли не нашла выбранный товар в финансовых данных за период."
            if unavailable:
                return "Legacy-диагностика прибыли построила неполную диагностику: часть источников недоступна."
            return "Legacy-диагностика прибыли не нашла срочных утечек прибыли в проанализированных данных."
        top = diagnoses[0]
        return f"Legacy-диагностика прибыли нашла {len(diagnoses)} пункт(ов) для проверки. Главный приоритет: {top.title}."

    def _float(self, value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _int(self, value: Any) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _str(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _dedupe(self, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result
