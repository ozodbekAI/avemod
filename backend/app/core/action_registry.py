from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class ActionRegistryEntry:
    action_code: str
    label: str
    module: str
    category: str
    is_navigation_only: bool
    is_local_only: bool
    is_external_write: bool
    is_dangerous: bool
    requires_preview: bool
    requires_confirm: bool
    requires_permission: bool
    requires_audit: bool
    allowed_in_rule_builder: bool
    allowed_for_seller: bool
    disabled_reason: str | None = None
    target_route_template: str | None = None

    def model_dump(self) -> dict[str, object]:
        return asdict(self)


DIRECT_EXTERNAL_WRITE_DISABLED = (
    "Direct WB write actions must be opened through a safe preview/confirm workflow."
)
CHECKER_WB_APPLY_DISABLED = (
    "WB card writes require Checker preview, diff, confirm, permission, and audit."
)


ACTION_REGISTRY: dict[str, ActionRegistryEntry] = {
    "create_task": ActionRegistryEntry(
        action_code="create_task",
        label="Create task",
        module="action_center",
        category="workflow",
        is_navigation_only=False,
        is_local_only=True,
        is_external_write=False,
        is_dangerous=False,
        requires_preview=False,
        requires_confirm=False,
        requires_permission=True,
        requires_audit=True,
        allowed_in_rule_builder=True,
        allowed_for_seller=True,
        target_route_template="/action-center",
    ),
    "open_data_fix": ActionRegistryEntry(
        action_code="open_data_fix",
        label="Open Data Fix",
        module="data_fix",
        category="data_fix",
        is_navigation_only=True,
        is_local_only=True,
        is_external_write=False,
        is_dangerous=False,
        requires_preview=False,
        requires_confirm=False,
        requires_permission=False,
        requires_audit=False,
        allowed_in_rule_builder=True,
        allowed_for_seller=True,
        target_route_template="/data-fix",
    ),
    "upload_cost": ActionRegistryEntry(
        action_code="upload_cost",
        label="Upload cost",
        module="data_fix",
        category="data_fix",
        is_navigation_only=False,
        is_local_only=True,
        is_external_write=False,
        is_dangerous=False,
        requires_preview=True,
        requires_confirm=True,
        requires_permission=True,
        requires_audit=True,
        allowed_in_rule_builder=True,
        allowed_for_seller=True,
        target_route_template="/costs?focus=missing-costs",
    ),
    "map_sku": ActionRegistryEntry(
        action_code="map_sku",
        label="Map SKU",
        module="data_fix",
        category="data_fix",
        is_navigation_only=False,
        is_local_only=True,
        is_external_write=False,
        is_dangerous=False,
        requires_preview=True,
        requires_confirm=True,
        requires_permission=True,
        requires_audit=True,
        allowed_in_rule_builder=True,
        allowed_for_seller=True,
        target_route_template="/data-fix?code=unmatched_sku",
    ),
    "classify_expense": ActionRegistryEntry(
        action_code="classify_expense",
        label="Classify expense",
        module="data_fix",
        category="data_fix",
        is_navigation_only=False,
        is_local_only=True,
        is_external_write=False,
        is_dangerous=False,
        requires_preview=True,
        requires_confirm=True,
        requires_permission=True,
        requires_audit=True,
        allowed_in_rule_builder=True,
        allowed_for_seller=True,
        disabled_reason=None,
        target_route_template="/data-fix?code=expense_unclassified",
    ),
    "open_price_review": ActionRegistryEntry(
        action_code="open_price_review",
        label="Open price review",
        module="money",
        category="price",
        is_navigation_only=True,
        is_local_only=True,
        is_external_write=False,
        is_dangerous=False,
        requires_preview=True,
        requires_confirm=False,
        requires_permission=False,
        requires_audit=False,
        allowed_in_rule_builder=True,
        allowed_for_seller=True,
        target_route_template="/products/{nm_id}?tab=price",
    ),
    "open_promo_planner": ActionRegistryEntry(
        action_code="open_promo_planner",
        label="Open promo planner",
        module="money",
        category="promo",
        is_navigation_only=True,
        is_local_only=True,
        is_external_write=False,
        is_dangerous=False,
        requires_preview=True,
        requires_confirm=False,
        requires_permission=False,
        requires_audit=False,
        allowed_in_rule_builder=True,
        allowed_for_seller=True,
        target_route_template="/products/{nm_id}?tab=promo",
    ),
    "open_ads_dashboard": ActionRegistryEntry(
        action_code="open_ads_dashboard",
        label="Open ads dashboard",
        module="ads",
        category="ads",
        is_navigation_only=True,
        is_local_only=True,
        is_external_write=False,
        is_dangerous=False,
        requires_preview=True,
        requires_confirm=False,
        requires_permission=False,
        requires_audit=False,
        allowed_in_rule_builder=True,
        allowed_for_seller=True,
        target_route_template="/ads",
    ),
    "open_supply_planner": ActionRegistryEntry(
        action_code="open_supply_planner",
        label="Open supply planner",
        module="stock",
        category="supply",
        is_navigation_only=True,
        is_local_only=True,
        is_external_write=False,
        is_dangerous=False,
        requires_preview=False,
        requires_confirm=False,
        requires_permission=False,
        requires_audit=False,
        allowed_in_rule_builder=True,
        allowed_for_seller=True,
        target_route_template="/stock-control?tab=supply",
    ),
    "run_checker": ActionRegistryEntry(
        action_code="run_checker",
        label="Run Checker",
        module="checker",
        category="checker",
        is_navigation_only=True,
        is_local_only=True,
        is_external_write=False,
        is_dangerous=False,
        requires_preview=False,
        requires_confirm=False,
        requires_permission=False,
        requires_audit=False,
        allowed_in_rule_builder=True,
        allowed_for_seller=True,
        target_route_template="/checker/{nm_id}",
    ),
    "open_results": ActionRegistryEntry(
        action_code="open_results",
        label="Open results",
        module="results",
        category="results",
        is_navigation_only=True,
        is_local_only=True,
        is_external_write=False,
        is_dangerous=False,
        requires_preview=False,
        requires_confirm=False,
        requires_permission=False,
        requires_audit=False,
        allowed_in_rule_builder=True,
        allowed_for_seller=True,
        target_route_template="/results",
    ),
    "recheck": ActionRegistryEntry(
        action_code="recheck",
        label="Re-check",
        module="problem_engine",
        category="workflow",
        is_navigation_only=False,
        is_local_only=True,
        is_external_write=False,
        is_dangerous=False,
        requires_preview=False,
        requires_confirm=False,
        requires_permission=True,
        requires_audit=True,
        allowed_in_rule_builder=True,
        allowed_for_seller=True,
    ),
    "dismiss": ActionRegistryEntry(
        action_code="dismiss",
        label="Dismiss",
        module="action_center",
        category="workflow",
        is_navigation_only=False,
        is_local_only=True,
        is_external_write=False,
        is_dangerous=False,
        requires_preview=False,
        requires_confirm=True,
        requires_permission=True,
        requires_audit=True,
        allowed_in_rule_builder=True,
        allowed_for_seller=True,
    ),
    "send_to_wb": ActionRegistryEntry(
        action_code="send_to_wb",
        label="Send to WB",
        module="checker",
        category="checker_wb_apply",
        is_navigation_only=False,
        is_local_only=False,
        is_external_write=True,
        is_dangerous=True,
        requires_preview=True,
        requires_confirm=True,
        requires_permission=True,
        requires_audit=True,
        allowed_in_rule_builder=False,
        allowed_for_seller=False,
        disabled_reason=CHECKER_WB_APPLY_DISABLED,
    ),
    "update_price": ActionRegistryEntry(
        action_code="update_price",
        label="Update WB price",
        module="money",
        category="price",
        is_navigation_only=False,
        is_local_only=False,
        is_external_write=True,
        is_dangerous=True,
        requires_preview=True,
        requires_confirm=True,
        requires_permission=True,
        requires_audit=True,
        allowed_in_rule_builder=False,
        allowed_for_seller=False,
        disabled_reason=DIRECT_EXTERNAL_WRITE_DISABLED,
    ),
    "apply_promo": ActionRegistryEntry(
        action_code="apply_promo",
        label="Apply WB promo",
        module="money",
        category="promo",
        is_navigation_only=False,
        is_local_only=False,
        is_external_write=True,
        is_dangerous=True,
        requires_preview=True,
        requires_confirm=True,
        requires_permission=True,
        requires_audit=True,
        allowed_in_rule_builder=False,
        allowed_for_seller=False,
        disabled_reason=DIRECT_EXTERNAL_WRITE_DISABLED,
    ),
    "pause_ads": ActionRegistryEntry(
        action_code="pause_ads",
        label="Pause WB ads",
        module="ads",
        category="ads",
        is_navigation_only=False,
        is_local_only=False,
        is_external_write=True,
        is_dangerous=True,
        requires_preview=True,
        requires_confirm=True,
        requires_permission=True,
        requires_audit=True,
        allowed_in_rule_builder=False,
        allowed_for_seller=False,
        disabled_reason=DIRECT_EXTERNAL_WRITE_DISABLED,
    ),
}


ACTION_ALIASES: dict[str, str] = {
    "assign": "create_task",
    "trigger_recheck": "recheck",
    "mark_system_wait": "recheck",
    "data_fix": "open_data_fix",
    "open_costs": "upload_cost",
    "cost_review": "upload_cost",
    "review_cost": "upload_cost",
    "mark_cost_upload_started": "upload_cost",
    "price_review": "open_price_review",
    "review_price": "open_price_review",
    "pricing_review": "open_price_review",
    "wb_price_change": "open_price_review",
    "promo_planner": "open_promo_planner",
    "review_promo": "open_promo_planner",
    "review_promotion": "open_promo_planner",
    "safe_promo": "open_promo_planner",
    "reduce_promo": "open_promo_planner",
    "bundle": "open_promo_planner",
    "promotion_create": "open_promo_planner",
    "promotion_creation": "open_promo_planner",
    "promotion_start": "open_promo_planner",
    "promotion_stop": "open_promo_planner",
    "plan_supply": "open_supply_planner",
    "supply_review": "open_supply_planner",
    "reduce_ads": "open_ads_dashboard",
    "lower_ads": "open_ads_dashboard",
    "review_ads": "open_ads_dashboard",
    "ads_review": "open_ads_dashboard",
    "review_bids": "open_ads_dashboard",
    "ad_bid_change": "open_ads_dashboard",
    "check_card_quality": "run_checker",
    "review_content": "run_checker",
    "content_check": "run_checker",
    "wb_content_apply": "run_checker",
    "mark_admin_investigation": "create_task",
    "admin_investigation": "create_task",
}


def normalize_action_code(action_code: str | None) -> str | None:
    code = str(action_code or "").strip().lower()
    if not code:
        return None
    return ACTION_ALIASES.get(code, code)


def get_action(action_code: str | None) -> ActionRegistryEntry | None:
    normalized = normalize_action_code(action_code)
    if normalized is None:
        return None
    return ACTION_REGISTRY.get(normalized)


def is_known_action(action_code: str | None) -> bool:
    return get_action(action_code) is not None


def normalize_action_codes(
    actions: Iterable[str],
    *,
    allowed_for_seller: bool | None = None,
    allowed_in_rule_builder: bool | None = None,
) -> list[str]:
    normalized: list[str] = []
    for action in actions:
        entry = get_action(action)
        if entry is None:
            continue
        if (
            allowed_for_seller is not None
            and entry.allowed_for_seller != allowed_for_seller
        ):
            continue
        if (
            allowed_in_rule_builder is not None
            and entry.allowed_in_rule_builder != allowed_in_rule_builder
        ):
            continue
        if entry.action_code not in normalized:
            normalized.append(entry.action_code)
    return normalized


def unknown_action_codes(actions: Iterable[str]) -> list[str]:
    return sorted(
        {
            str(action)
            for action in actions
            if str(action).strip() and not is_known_action(str(action))
        }
    )


def disallowed_rule_builder_actions(actions: Iterable[str]) -> list[str]:
    disallowed: set[str] = set()
    for action in actions:
        text = str(action or "").strip()
        entry = get_action(text)
        if entry is not None and not entry.allowed_in_rule_builder:
            disallowed.add(text)
    return sorted(disallowed)


def dangerous_action_codes(actions: Iterable[str]) -> list[str]:
    dangerous: set[str] = set()
    for action in actions:
        text = str(action or "").strip()
        entry = get_action(text)
        if entry is not None and entry.is_dangerous:
            dangerous.add(text)
    return sorted(dangerous)


def canonical_registry_items() -> list[ActionRegistryEntry]:
    return [ACTION_REGISTRY[action_code] for action_code in sorted(ACTION_REGISTRY)]


ACTION_CENTER_ALLOWED_ACTIONS = frozenset(
    action_code
    for action_code, entry in ACTION_REGISTRY.items()
    if entry.allowed_for_seller
    and (entry.allowed_in_rule_builder or entry.is_navigation_only)
)


RULE_BUILDER_KNOWN_ACTIONS = frozenset(ACTION_REGISTRY).union(ACTION_ALIASES)
RULE_BUILDER_PRICE_PROMO_ADS_ACTIONS = frozenset(
    action_code
    for action_code, entry in ACTION_REGISTRY.items()
    if entry.category in {"price", "promo", "ads"}
).union(
    alias
    for alias, canonical in ACTION_ALIASES.items()
    if ACTION_REGISTRY[canonical].category in {"price", "promo", "ads"}
)
