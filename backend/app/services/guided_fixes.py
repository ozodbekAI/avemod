from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.operator import (
    ActionStatus,
    GuidedFixOut,
    GuidedFixStepOut,
    OperatorModule,
    TrustState,
)


GUIDED_FIX_METHODS = {
    "open_product_360",
    "upload_costs",
    "open_data_fix",
    "open_card_quality",
    "open_photo_studio",
    "open_photo_fix",
    "open_media_quality_fix",
    "photo_fix",
    "media_quality_fix",
    "open_reputation_item",
    "generate_reputation_draft",
    "create_claim_case_from_signal",
    "open_claim_case",
    "generate_claim_draft",
    "open_stock_planner",
    "open_grouping_preview",
    "open_ads_review",
    "open_pricing_review",
    "open_result_tracking",
}


@dataclass(frozen=True)
class GuidedFixTarget:
    method: str
    route_key: str
    label: str
    module: str
    legacy_method: str | None = None
    section: str | None = None
    safety_note: str | None = None


class GuidedFixMapper:
    def map(
        self,
        *,
        source_module: str | None,
        action_type: str | None,
        nm_id: int | None = None,
        target_id: str | None = None,
        module_status: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        target = self._target(
            source_module=source_module, action_type=action_type, nm_id=nm_id
        )
        normalized_status = str(module_status or "ok")
        enabled = normalized_status in {"ok", "empty", "beta", "degraded"}
        disabled_reason = (
            None if enabled else f"{target.module}_module_{normalized_status}"
        )
        safe_message = message or (
            None if enabled else f"{target.module} module is {normalized_status}"
        )
        target_ref = str(nm_id or target_id or "")
        source_ref = str(target_id or "")
        confirm_required = self._confirm_required(target)
        marketplace_change = False
        step = {
            "type": target.method,
            "route_key": target.route_key,
            "route_hint": target.route_key,
            "target_module": target.route_key,
            "target_id": target_ref,
            "source_id": source_ref,
            "source_issue_id": source_ref,
            "nm_id": nm_id,
            "label": target.label,
            "method": target.method,
            "safety_note": target.safety_note,
            "marketplace_change": marketplace_change,
            "confirm_required": confirm_required,
        }
        fix = {
            "method": target.method,
            "type": target.method,
            "route_key": target.route_key,
            "route_hint": target.route_key,
            "target_module": target.route_key,
            "target_id": target_ref,
            "source_id": source_ref,
            "source_issue_id": source_ref,
            "nm_id": nm_id,
            "label": target.label,
            "module": target.module,
            "section": target.section,
            "status": "enabled" if enabled else normalized_status,
            "enabled": enabled,
            "message": safe_message,
            "disabled_reason": disabled_reason,
            "requires_confirmation": confirm_required,
            "confirm_required": confirm_required,
            "marketplace_change": marketplace_change,
            "safety_note": target.safety_note,
            "steps": [step],
        }
        if target.legacy_method:
            fix["legacy_method"] = target.legacy_method
        return fix

    def to_operator(
        self,
        *,
        source_module: str | None,
        action_type: str | None,
        title: str,
        summary: str,
        nm_id: int | None = None,
        target_id: str | None = None,
        module_status: str | None = None,
        message: str | None = None,
    ) -> GuidedFixOut:
        fix = self.map(
            source_module=source_module,
            action_type=action_type,
            nm_id=nm_id,
            target_id=target_id,
            module_status=module_status,
            message=message,
        )
        module = self._operator_module(fix["module"])
        enabled = bool(fix["enabled"])
        return GuidedFixOut(
            module=module,
            title=title,
            summary=summary,
            status=ActionStatus.NEW if enabled else ActionStatus.BLOCKED,
            trust_state=TrustState.PROVISIONAL if enabled else TrustState.UNAVAILABLE,
            steps=[
                GuidedFixStepOut(
                    title=str(fix["label"]),
                    description=summary,
                    status=ActionStatus.NEW if enabled else ActionStatus.BLOCKED,
                    required=True,
                    data=fix,
                )
            ],
            confirm_required=bool(fix["confirm_required"]),
            audit_required=bool(fix["confirm_required"]),
            marketplace_change=bool(fix["marketplace_change"]),
            safety_note=fix.get("safety_note"),
            data=fix,
            warnings=[] if enabled else [str(fix["disabled_reason"])],
        )

    def _target(
        self, *, source_module: str | None, action_type: str | None, nm_id: int | None
    ) -> GuidedFixTarget:
        source = self._normalize(source_module)
        action = self._normalize(action_type)

        if source == "finance" and action == "review_profit":
            return GuidedFixTarget(
                "open_product_360",
                "product_360",
                "Open Product 360 Money",
                "finance",
                "open_product",
                "money",
            )
        if source == "finance" and action == "fix_costs":
            return GuidedFixTarget(
                "upload_costs",
                "costs",
                "Open Costs / Data Fix",
                "finance",
                "upload_cost",
                "costs",
            )
        if source == "finance" and action == "fix_data":
            return GuidedFixTarget(
                "open_data_fix",
                "data_fix",
                "Open Data Fix",
                "finance",
                "open_page",
                "data_quality",
            )
        if (
            source in {"costs", "manual_costs"}
            or "cost" in action
            or "себесто" in action
        ):
            return GuidedFixTarget(
                "upload_costs",
                "costs",
                "Open Costs / Data Fix",
                "finance",
                "upload_cost",
                "costs",
            )
        if (
            source == "data_quality"
            or "data_fix" in action
            or action
            in {
                "fix_data",
                "fix_stock_sync",
                "fix_ad_allocation",
                "fix_price_mapping",
                "map_unmatched_sku",
                "reconcile_finance",
                "reconciliation_review",
            }
        ):
            return GuidedFixTarget(
                "open_data_fix",
                "data_fix",
                "Open Data Fix",
                "finance",
                "open_page",
                "data_quality",
            )
        if source == "checker" and ("media" in action or "video" in action):
            return GuidedFixTarget(
                "media_quality_fix",
                "photo_studio",
                "Fix media",
                "photo",
                "open_product",
                "media",
                "Photo Studio is a guided draft workflow in MVP. Uploading or applying media to WB must require preview, explicit confirmation, permission checks, and audit.",
            )
        if source == "checker" and ("photo" in action or "image" in action):
            return GuidedFixTarget(
                "photo_fix",
                "photo_studio",
                "Fix photo",
                "photo",
                "open_product",
                "photo",
                "Photo Studio is a guided draft workflow in MVP. Uploading or applying media to WB must require preview, explicit confirmation, permission checks, and audit.",
            )
        if source == "checker" or "card" in action or "quality" in action:
            return GuidedFixTarget(
                "open_card_quality",
                "card_quality",
                "Open Product 360 Quality",
                "checker",
                "open_product",
                "quality",
                "MVP opens a read-only quality workflow. Any future card apply/publish action must require preview and manual confirmation.",
            )
        if source == "photo" or "photo" in action or "image" in action:
            return GuidedFixTarget(
                "photo_fix",
                "photo_studio",
                "Fix photo",
                "photo",
                "open_product",
                "photo",
                "Photo generation is local/draft-only in MVP. Publishing media must require manual confirmation.",
            )
        if "ads" in action or "ad_" in action:
            return GuidedFixTarget(
                "open_ads_review",
                "ads",
                "Open ads review",
                "finance",
                "open_page",
                "ads",
            )
        if "price" in action or "pricing" in action:
            return GuidedFixTarget(
                "open_pricing_review",
                "pricing",
                "Open pricing review",
                "finance",
                "open_page",
                "pricing",
            )
        if source == "reputation" and ("draft" in action or "reply" in action):
            return GuidedFixTarget(
                "generate_reputation_draft",
                "reputation",
                "Open reply draft editor",
                "reputation",
                "generate_draft",
                "reputation",
                "Drafting is safe. Publishing a reply must stay behind confirm=true and ENABLE_REPUTATION_PUBLISH.",
            )
        if (
            source == "reputation"
            or "negative_review" in action
            or "question" in action
            or "chat" in action
        ):
            return GuidedFixTarget(
                "open_reputation_item",
                "reputation",
                "Open reputation item",
                "reputation",
                "generate_draft",
                "reputation",
                "Replies are draft-only until a user manually confirms publishing.",
            )
        if source == "claims" and "draft" in action:
            return GuidedFixTarget(
                "generate_claim_draft",
                "claims",
                "Open claim draft",
                "claims",
                "open_case",
                "claims",
                "Drafting is safe. Submitting a claim/support ticket must stay behind confirm=true and ENABLE_CLAIMS_SUBMIT.",
            )
        if source == "claims" and action == "open_case":
            return GuidedFixTarget(
                "open_claim_case",
                "claims",
                "Open Claims Center",
                "claims",
                "open_case",
                "claims",
                "Claims Center is local in MVP. External submission requires proof-check and manual confirmation.",
            )
        if (
            source == "claims"
            or "claim" in action
            or "case" in action
            or "compensation" in action
            or "pretrial" in action
        ):
            return GuidedFixTarget(
                "create_claim_case_from_signal",
                "claims",
                "Create claim case",
                "claims",
                "open_case",
                "claims",
                "Creating a local case is safe. Submitting to support must require proof-check and manual confirmation.",
            )
        if (
            source == "stockops"
            or "stock" in action
            or action
            in {"reorder", "protect_stock", "liquidate_stock", "do_not_reorder"}
        ):
            return GuidedFixTarget(
                "open_stock_planner",
                "stock",
                "Open Stock Planner",
                "stockops",
                "open_page",
                "stock",
                "StockOps is recommendation-only in MVP. Any WB stock operation must require manual confirmation.",
            )
        if source in {"grouping", "grouping_beta"} or "grouping" in action:
            return GuidedFixTarget(
                "open_grouping_preview",
                "grouping_beta",
                "Open Grouping Beta preview",
                "grouping",
                "open_page",
                "grouping",
                "Grouping is preview-only in MVP. merge-wb/apply must remain disabled without manual confirmation.",
            )
        if source == "experiments" or "result" in action or "tracking" in action:
            return GuidedFixTarget(
                "open_result_tracking",
                "result_history",
                "Open Results / History",
                "experiments",
                "open_page",
                "results",
            )
        if nm_id is not None:
            return GuidedFixTarget(
                "open_product_360",
                "product_360",
                "Open Product 360",
                "finance",
                "open_product",
                "overview",
            )
        return GuidedFixTarget(
            "open_result_tracking",
            "actions",
            "Open action details",
            "finance",
            "open_page",
            "actions",
        )

    def _confirm_required(self, target: GuidedFixTarget) -> bool:
        if not target.safety_note:
            return False
        return target.module in {
            "checker",
            "photo",
            "reputation",
            "claims",
            "stockops",
            "grouping",
        }

    def _operator_module(self, value: str) -> OperatorModule:
        aliases = {
            "grouping_beta": "grouping",
            "stock": "stockops",
            "card_quality": "checker",
            "photo_studio": "photo",
        }
        try:
            return OperatorModule(aliases.get(value, value))
        except ValueError:
            return OperatorModule.FINANCE

    def _normalize(self, value: Any) -> str:
        return str(value or "").strip().lower().replace("-", "_")
