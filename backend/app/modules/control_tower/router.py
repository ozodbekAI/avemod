from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.core.pagination import Page
from app.core.time import utcnow
from app.models.auth import AuthUser
from app.schemas.control_tower import (
    ActionRecommendationListItem,
    ActionRecommendationBulkUpdateRequest,
    ActionRecommendationRead,
    ActionRecommendationUpdateRequest,
    AdsEfficiencyPage,
    AlertBulkUpdateRequest,
    AlertRead,
    AlertUpdateRequest,
    BulkMutationResponse,
    BusinessPoliciesRead,
    BusinessSettingsRead,
    BusinessSettingsUpdateRequest,
    ControlTowerSkuDetail,
    ControlTowerSkuRow,
    OwnerDashboardRead,
    PriceSafetyPage,
    PriceSimulationRequest,
    PriceSimulationResponse,
    PurchasePlanPage,
)
from app.schemas.meta import EnumOption, EnumOptionListResponse
from app.services.auth import get_current_superuser
from app.services.control_tower import ControlTowerService
from app.services.money_snapshots import MoneyEndpointSnapshotService
from app.services.operator_snapshots import OperatorEndpointSnapshotService

router = APIRouter(tags=["control-tower"])
service = ControlTowerService()
money_snapshot_service = MoneyEndpointSnapshotService()
snapshot_service = OperatorEndpointSnapshotService()
snapshot_service.control_tower = service
logger = logging.getLogger(__name__)


@router.get("/dashboard/owner", response_model=OwnerDashboardRead)
async def owner_dashboard(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> OwnerDashboardRead:
    return await snapshot_service.owner_dashboard(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/dashboard/owner-ai-summary")
async def owner_ai_summary(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    owner = await snapshot_service.owner_dashboard(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
    )
    summary = await money_snapshot_service.summary(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
    )
    context = _owner_ai_context(owner=owner, summary=summary)
    fallback = _owner_ai_fallback(context)
    settings = get_settings()
    base = {
        "account_id": account_id,
        "date_from": context["period"]["from"],
        "date_to": context["period"]["to"],
        "generated_at": utcnow().isoformat(),
    }
    if not settings.openai_api_key:
        return {
            **base,
            "mode": "rule_based",
            "provider": "local",
            "configured": False,
            "model": None,
            "title": "Краткая сводка",
            "bullets": fallback,
            "warnings": ["openai_api_key_not_configured"],
        }

    prompt = {
        "dashboard_context": context,
        "requirements": [
            "Пиши на русском языке для владельца WB-бизнеса.",
            "Дай ровно 3 коротких пункта в порядке: 1) что происходит, 2) где главный риск, 3) что сделать первым.",
            "Пиши простым управленческим языком без внутренних названий полей, технических флагов и английских терминов.",
            "Деньги округляй до рублей или до 1 знака в млн ₽, проценты округляй до 1 знака.",
            "Каждый пункт должен быть не длиннее 150 символов и начинаться с действия или вывода, без префиксов '1)', 'Риск:' и похожих.",
            "Не придумывай факты и суммы. Используй только dashboard_context.",
            "Верни строго JSON: title:string, bullets:string[].",
        ],
    }
    payload = {
        "model": settings.openai_model,
        "instructions": (
            "Ты CFO-ассистент для владельца магазина Wildberries. "
            "Возвращай только JSON без markdown. "
            "Запрещены внутренние имена полей вроде financial_final, top_actions, overstock, cash_on_wb, SKU count. "
            "Не показывай копейки и длинные десятичные числа."
        ),
        "input": json.dumps(prompt, ensure_ascii=False),
    }
    try:
        async with httpx.AsyncClient(timeout=settings.openai_timeout_seconds) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json() if response.text else {}
        parsed = _load_json_object(_extract_openai_text(data))
        bullets = [
            str(item).strip() for item in parsed.get("bullets", []) if str(item).strip()
        ][:4]
        if not bullets:
            bullets = fallback
        return {
            **base,
            "mode": "ai",
            "provider": "openai",
            "configured": True,
            "model": settings.openai_model,
            "title": str(parsed.get("title") or "Краткая сводка").strip(),
            "bullets": bullets,
            "warnings": [],
        }
    except Exception as exc:  # pragma: no cover - network/provider fallback
        logger.warning("owner_ai_summary_failed: %s", exc.__class__.__name__)
        return {
            **base,
            "mode": "rule_based",
            "provider": "local",
            "configured": True,
            "model": settings.openai_model,
            "title": "Краткая сводка",
            "bullets": fallback,
            "warnings": [f"openai_summary_failed:{exc.__class__.__name__}"],
        }


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _float_attr(obj: Any, name: str) -> float:
    value = _attr(obj, name, 0.0)
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _owner_ai_context(*, owner: Any, summary: Any) -> dict[str, Any]:
    kpis = _attr(summary, "kpis")
    trust = _attr(owner, "trust")
    ad_spend_operational = _float_attr(kpis, "ad_spend_operational")
    ads_source_spend = _float_attr(kpis, "ads_source_spend")
    ad_spend_final = _float_attr(kpis, "ad_spend_final")
    ad_spend_primary = ad_spend_operational or ads_source_spend or ad_spend_final
    profit_primary = _float_attr(kpis, "net_profit_after_overhead") or _float_attr(
        kpis, "net_profit_after_all_expenses"
    )
    top_actions = [
        *_attr(owner, "next_actions_preview", [])[:4],
        *_attr(owner, "top_risks", [])[:3],
    ]
    return {
        "period": {
            "from": str(
                _attr(summary, "meta")
                and _attr(_attr(summary, "meta"), "date_from")
                or _attr(owner, "date_from")
            ),
            "to": str(
                _attr(summary, "meta")
                and _attr(_attr(summary, "meta"), "date_to")
                or _attr(owner, "date_to")
            ),
        },
        "money": {
            "revenue": _float_attr(kpis, "revenue"),
            "profit": profit_primary,
            "profit_finance_basis": _float_attr(kpis, "net_profit_after_all_expenses"),
            "margin_percent": _float_attr(kpis, "margin_after_overhead_percent"),
            "roi_percent": _float_attr(kpis, "roi_on_cogs_percent"),
            "wb_expenses": _float_attr(kpis, "wb_expenses_total"),
            "seller_costs": _float_attr(kpis, "total_seller_costs"),
            "ad_spend": ad_spend_primary,
            "ad_spend_finance": _float_attr(kpis, "ad_spend_finance") or ad_spend_final,
            "ad_spend_profit_basis": ad_spend_final,
            "cash_on_wb": _float_attr(kpis, "cash_on_wb_current"),
            "available_for_withdraw": _float_attr(
                kpis, "available_for_withdraw_current"
            ),
            "stock_value": _float_attr(kpis, "stock_value"),
            "overstock_value": _float_attr(kpis, "overstock_value"),
        },
        "risks": {
            "negative_profit_sku_count": int(
                _float_attr(kpis, "negative_profit_sku_count")
            ),
            "blocked_data_sku_count": int(_float_attr(kpis, "blocked_data_sku_count")),
            "out_of_stock_risk_count": int(
                _float_attr(owner, "out_of_stock_risk_count")
            ),
        },
        "trust": {
            "state": str(
                _attr(trust, "status", _attr(owner, "trust_state", "unknown"))
            ),
            "financial_final": bool(_attr(trust, "financial_final", False)),
            "operational_trusted": bool(_attr(trust, "operational_trusted", False)),
            "financial_final_blockers_total": int(
                _float_attr(trust, "financial_final_blockers_total")
            ),
            "blocking_open_issues_total": int(
                _float_attr(trust, "blocking_open_issues_total")
            ),
        },
        "owner_focus": {
            "title": str(
                _attr(_attr(owner, "owner_message"), "title", "")
                or _attr(owner, "primary_message", "")
            ),
            "reason": str(_attr(_attr(owner, "owner_message"), "reason", "")),
            "today_focus": str(_attr(_attr(owner, "owner_message"), "today_focus", "")),
        },
        "top_actions": [
            {
                "title": str(
                    _attr(action, "title", "") or _attr(action, "what_to_do", "")
                ),
                "category": str(
                    _attr(action, "category", "") or _attr(action, "action_type", "")
                ),
                "priority": str(_attr(action, "priority", "")),
                "expected_effect_amount": _float_attr(action, "expected_effect_amount"),
                "reason": str(_attr(action, "reason", "") or _attr(action, "why", "")),
            }
            for action in top_actions
        ],
    }


def _owner_ai_fallback(context: dict[str, Any]) -> list[str]:
    money = context.get("money", {})
    risks = context.get("risks", {})
    trust = context.get("trust", {})
    actions = context.get("top_actions", [])
    bullets: list[str] = []
    profit = float(money.get("profit") or 0)
    revenue = float(money.get("revenue") or 0)
    margin = float(money.get("margin_percent") or 0)
    overstock = float(money.get("overstock_value") or 0)
    blockers = int(trust.get("financial_final_blockers_total") or 0)
    risk_sku = (
        int(risks.get("negative_profit_sku_count") or 0)
        + int(risks.get("blocked_data_sku_count") or 0)
        + int(risks.get("out_of_stock_risk_count") or 0)
    )
    if profit >= 0:
        bullets.append(
            f"Бизнес в плюсе: прибыль {profit:,.0f} ₽ при выручке {revenue:,.0f} ₽, маржа {margin:.1f}%.".replace(
                ",", " "
            )
        )
    else:
        bullets.append(
            f"Бизнес в минусе: прибыль {profit:,.0f} ₽, сначала проверьте расходы и убыточные SKU.".replace(
                ",", " "
            )
        )
    if blockers > 0 or not trust.get("financial_final"):
        bullets.append(
            "Финальная прибыль ещё предварительная: есть блокеры данных или сверки, поэтому фиксируйте решения осторожно."
        )
    if overstock > 0:
        bullets.append(
            f"В остатках заморожено около {overstock:,.0f} ₽: проверьте распродажу, промо или план вывода остатков.".replace(
                ",", " "
            )
        )
    if risk_sku > 0:
        bullets.append(
            f"В риске {risk_sku} SKU: начните с убыточных карточек и товаров без данных."
        )
    if actions:
        first = actions[0]
        title = str(first.get("title") or "главную задачу")
        amount = float(first.get("expected_effect_amount") or 0)
        if amount > 0:
            bullets.append(
                f"Первое действие: {title}. Ожидаемый эффект около {amount:,.0f} ₽.".replace(
                    ",", " "
                )
            )
        else:
            bullets.append(f"Первое действие: {title}.")
    if not bullets:
        bullets.append(
            "Критических сигналов нет: следите за трендом прибыли, остатками и статусом данных."
        )
    return bullets[:4]


def _extract_openai_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    output = payload.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            content = item.get("content") if isinstance(item, dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
        if parts:
            return "\n".join(parts)
    return ""


def _load_json_object(text: str) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.strip("`")
        if clean.lower().startswith("json"):
            clean = clean[4:].strip()
    start = clean.find("{")
    end = clean.rfind("}")
    if start >= 0 and end >= start:
        clean = clean[start : end + 1]
    parsed = json.loads(clean)
    if not isinstance(parsed, dict):
        raise ValueError("OpenAI response is not a JSON object")
    return parsed


@router.get("/skus/statuses", response_model=EnumOptionListResponse)
async def list_control_sku_statuses(
    _: AuthUser = Depends(get_current_superuser),
) -> EnumOptionListResponse:
    return EnumOptionListResponse(
        items=[
            EnumOption(value=value, label=label)
            for value, label in service.list_sku_statuses().items()
        ]
    )


@router.get("/skus", response_model=Page[ControlTowerSkuRow])
async def list_control_skus(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    sku_status: list[str] | None = Query(default=None),
    trust_state: list[str] | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    preset: str | None = Query(default=None),
    has_open_actions: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> Page[ControlTowerSkuRow]:
    merged_sku_status = list(sku_status or [])
    if status:
        merged_sku_status.append(status)
    return await snapshot_service.control_skus(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
        sku_status=merged_sku_status or None,
        trust_state=trust_state,
        sort_by=sort_by,
        sort_dir=sort_dir,
        preset=preset,
        has_open_actions=has_open_actions,
        limit=limit,
        offset=offset,
    )


@router.get("/skus/{sku_id}", response_model=ControlTowerSkuDetail)
async def get_control_sku(
    sku_id: int,
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> ControlTowerSkuDetail:
    return await service.get_control_sku_detail(
        session,
        account_id=account_id,
        sku_id=sku_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/actions", response_model=Page[ActionRecommendationListItem])
async def list_actions(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> Page[ActionRecommendationListItem]:
    return await service.list_actions(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        action_type=action_type,
        limit=limit,
        offset=offset,
    )


@router.get("/actions/{action_id}", response_model=ActionRecommendationRead)
async def get_action_detail(
    action_id: int,
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> ActionRecommendationRead:
    return await service.get_action_detail(
        session,
        action_id=action_id,
    )


@router.patch("/actions/{action_id}", response_model=ActionRecommendationRead)
async def update_action(
    action_id: int,
    payload: ActionRecommendationUpdateRequest,
    current_user: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> ActionRecommendationRead:
    return await service.update_action(
        session,
        action_id=action_id,
        user_id=current_user.id,
        payload=payload,
    )


@router.post("/actions/bulk", response_model=BulkMutationResponse)
async def bulk_update_actions(
    payload: ActionRecommendationBulkUpdateRequest,
    current_user: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> BulkMutationResponse:
    updated_count = await service.bulk_update_actions(
        session,
        ids=payload.ids,
        user_id=current_user.id,
        status=payload.status,
        assigned_to=payload.assigned_to,
        comment=payload.comment,
    )
    await session.commit()
    return BulkMutationResponse(updated_count=updated_count)


@router.get("/inventory/purchase-plan", response_model=PurchasePlanPage)
async def purchase_plan(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    group_by: str = Query(default="article", pattern="^(article|sku)$"),
    include_blocked: bool = Query(default=True),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    status_filter: str | None = Query(default=None),
    search: str | None = Query(default=None),
    profit_filter: str | None = Query(default=None),
    data_filter: str | None = Query(default=None),
    stock_filter: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> PurchasePlanPage:
    return await snapshot_service.purchase_plan(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        group_by=group_by,
        include_blocked=include_blocked,
        sort_by=sort_by,
        sort_dir=sort_dir,
        status_filter=status_filter,
        search=search,
        profit_filter=profit_filter,
        data_filter=data_filter,
        stock_filter=stock_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/pricing/safety", response_model=PriceSafetyPage)
async def price_safety(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    only_risk: bool = Query(default=False),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> PriceSafetyPage:
    return await snapshot_service.price_safety(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        only_risk=only_risk,
        search=search,
        status=status,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.post("/pricing/simulate", response_model=PriceSimulationResponse)
async def simulate_price(
    payload: PriceSimulationRequest,
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> PriceSimulationResponse:
    return await service.simulate_price(session, payload=payload)


@router.get("/ads/efficiency", response_model=AdsEfficiencyPage)
async def ads_efficiency(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    campaign_id: int | None = Query(default=None),
    min_drr_percent: float | None = Query(default=None),
    max_drr_percent: float | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> AdsEfficiencyPage:
    return await snapshot_service.ads_efficiency(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        campaign_id=campaign_id,
        min_drr_percent=min_drr_percent,
        max_drr_percent=max_drr_percent,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/settings/business", response_model=BusinessSettingsRead)
async def business_settings(
    account_id: int = Query(...),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> BusinessSettingsRead:
    return await service.get_business_settings(session, account_id=account_id)


@router.get("/settings/business/policies", response_model=BusinessPoliciesRead)
async def business_settings_policies(
    _: AuthUser = Depends(get_current_superuser),
) -> BusinessPoliciesRead:
    return service.get_business_policies()


@router.patch("/settings/business", response_model=BusinessSettingsRead)
async def update_business_settings(
    account_id: int = Query(...),
    payload: BusinessSettingsUpdateRequest | None = None,
    current_user: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> BusinessSettingsRead:
    return await service.update_business_settings(
        session,
        account_id=account_id,
        user_id=current_user.id,
        payload=payload or BusinessSettingsUpdateRequest(settings={}),
    )


@router.get("/alerts", response_model=Page[AlertRead])
async def list_alerts(
    account_id: int = Query(...),
    severity: str | None = Query(default=None),
    alert_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> Page[AlertRead]:
    return await service.list_alerts(
        session,
        account_id=account_id,
        severity=severity,
        alert_type=alert_type,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.patch("/alerts/{alert_id}", response_model=AlertRead)
async def update_alert(
    alert_id: int,
    payload: AlertUpdateRequest,
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> AlertRead:
    return await service.update_alert(
        session,
        alert_id=alert_id,
        payload=payload,
    )


@router.post("/alerts/bulk", response_model=BulkMutationResponse)
async def bulk_update_alerts(
    payload: AlertBulkUpdateRequest,
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> BulkMutationResponse:
    updated_count = await service.bulk_update_alerts(
        session,
        ids=payload.ids,
        status=payload.status,
        snoozed_until=payload.snoozed_until,
    )
    await session.commit()
    return BulkMutationResponse(updated_count=updated_count)
