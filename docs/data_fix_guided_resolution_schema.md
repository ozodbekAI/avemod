# Data Fix Guided Resolution Schema

## Problem

`/dashboard` shows critical data problems, but the current flow sends the user to `/data-fix` even when the problem is not user-fixable. This creates three practical issues:

- aggregate blockers do not map to a concrete editable task;
- system/import/sync problems look like manual user work;
- numeric business fixes, especially cost-related fixes, are not presented as an easy spreadsheet-like flow.

The goal is to turn every blocker into one of a small set of fix task types. The user should see only what they can actually do, with simple buttons and inline editing where it is safe.

## Current Sources

Dashboard critical problems come from two backend sources:

- `GET /money/data-blockers`
  - `blockers[]`
  - `warnings[]`
  - `data_quality_summary`
- `GET /money/summary`
  - `risk_summary.risks[]`

`/money/data-blockers` is built from:

- global `DashboardDataHealth.blocked_reasons`;
- `DashboardDataHealth.issue_buckets`;
- ad allocation warning metrics.

Important aggregate blocker codes:

- `supplier_cost_coverage_below_threshold`
- `unmatched_sku_detected`
- `latest_stocks_not_completed`
- `open_blocking_dq_issues`
- `failed_sync_domains`

Important DQ issue codes:

- `missing_manual_cost`
- `manual_cost_unresolved_sku`
- `manual_cost_ambiguous_match`
- `seller_other_expense_missing`
- `unmatched_sku`
- `expense_unclassified`
- `unclassified_finance_expense`
- `expense_logistics_missing`
- `expense_finance_report_missing`
- `expense_ad_double_count_risk`
- `finance_reconciliation_mismatch`
- `sale_without_finance`
- `finance_without_sale`
- `stocks_task_not_ready`
- `price_jump`
- `price_zero_or_too_low`

## Main Rule

Never send the user to a generic problem list as the primary fix.

Every visible blocker must become a `FixTask` with:

- a clear owner;
- a concrete screen/component;
- exact rows or fields to change;
- one primary button;
- a re-check rule;
- a success condition.

## FixTask Contract

```json
{
  "task_id": "cost.missing_manual_cost.account_1",
  "account_id": 1,
  "code": "missing_manual_cost",
  "source_kind": "dq_issue_group",
  "source_issue_ids": [101, 102, 103],
  "title": "Sotilgan tovarlarda себестоимость yo'q",
  "why_it_matters": "Foyda va окупаемость noto'g'ri chiqadi.",
  "owner_type": "user",
  "fix_mode": "spreadsheet_edit",
  "priority": "critical",
  "editable": true,
  "safe_to_apply": true,
  "rows_total": 18,
  "affected_revenue": 1250000,
  "primary_action": {
    "label": "Jadvalda to'ldirish",
    "action_type": "open_spreadsheet"
  },
  "secondary_actions": [
    { "label": "Excel yuklash", "action_type": "upload_file" },
    { "label": "Qayta tekshirish", "action_type": "recheck" }
  ],
  "columns": [
    { "key": "sku_id", "label": "SKU", "editable": false },
    { "key": "nm_id", "label": "nm_id", "editable": false },
    { "key": "vendor_code", "label": "Artikul", "editable": false },
    { "key": "cost_price", "label": "Sotib olish narxi", "type": "money", "editable": true, "required": true },
    { "key": "seller_other_expense", "label": "Qo'shimcha xarajat", "type": "money", "editable": true },
    { "key": "supplier", "label": "Yetkazib beruvchi", "type": "text", "editable": true },
    { "key": "is_supplier_confirmed", "label": "Tasdiqlangan", "type": "boolean", "editable": true }
  ],
  "validation": [
    "cost_price > 0",
    "seller_other_expense >= 0",
    "at least one identifier exists: sku_id, nm_id, vendor_code, barcode"
  ],
  "apply_endpoint": "POST /api/v1/dq/fix-tasks/{task_id}/apply",
  "recheck_endpoint": "POST /api/v1/dq/fix-tasks/{task_id}/recheck",
  "success_state": "financial_final_blocker_count == 0 for this task code"
}
```

## Owner Types

`user`

The seller/operator can fix it directly in the platform. Show this in the main critical list.

`system`

The user must not edit numbers. The system must wait, sync, or reconcile. Show separately as "Sistema tekshiryapti".

`admin`

Requires admin/integration investigation. Show separately with "Adminga yuborildi" or "Admin tekshiruvi kerak".

`mixed`

The user can try a safe action first; if it fails, it becomes admin/system.

## Fix Modes

`spreadsheet_edit`

Inline Excel-like table. Use for user-owned numeric/business fields.

Examples:

- missing cost;
- seller other expense;
- accepted temporary cost;
- supplier confirmed cost.

`upload_file`

User uploads CSV/XLSX and confirms preview.

Examples:

- cost import;
- bulk cost update.

`select_mapping`

User chooses one candidate from buttons or enters an ID.

Examples:

- unmatched SKU;
- ambiguous manual cost match;
- unresolved manual cost row.

`category_select`

User picks a category from chips/dropdown.

Examples:

- unclassified expense.

`run_sync`

System/admin action. User may press "Qayta sync" only if role allows it.

Examples:

- latest stocks not completed;
- failed critical sync domain.

`wait_for_source`

System-only. No manual edit.

Examples:

- sale without finance;
- finance without sale;
- fresh WB report delay.

`admin_investigation`

No seller edit. Send to admin queue with evidence.

Examples:

- ad over-allocation;
- finance reconciliation mismatch after sync;
- formula/import mismatch.

`external_wb_edit`

User must change data in WB cabinet, then run sync/recheck.

Examples:

- missing product card content;
- photo/content issues;
- invalid WB card fields.

## Mapping Rules

### Cost Coverage

`supplier_cost_coverage_below_threshold` must not be a generic Data Fix card.

Expand it into:

- `missing_manual_cost` rows;
- `seller_other_expense_missing` rows;
- `manual_cost_unresolved_sku` rows;
- `manual_cost_ambiguous_match` rows.

Primary UI:

1. "Jadvalda to'ldirish"
2. "Excel template yuklab olish"
3. "Excel yuklash"
4. "Qayta tekshirish"

Existing useful endpoints:

- `GET /costs/missing`
- `GET /costs/template?mode=missing`
- `POST /costs/upload`
- `PATCH /costs/{cost_id}`
- `POST /costs/{cost_id}/mark-supplier-confirmed`
- `POST /dq/run`

Missing endpoint needed:

- bulk create/update cost rows from spreadsheet edits.

### SKU Mapping

`unmatched_sku_detected` must normalize to DQ code `unmatched_sku`.

Primary UI:

1. show source row;
2. show candidate SKU buttons;
3. allow manual `sku_id` entry only with reason;
4. save mapping;
5. recheck.

Existing useful endpoint:

- `POST /dq/issues/{id}/guided-action` with `map_sku`

Current gap:

- aggregate blocker code differs from DQ issue code, so the workbench may not open.
- one blocker code can represent many rows; user needs a queue, not just one issue sample.

### Expense Classification

`expense_unclassified` and `unclassified_finance_expense` use `category_select`.

Primary UI:

1. show raw finance operation name;
2. show amount and source row;
3. category chips;
4. save category;
5. recheck.

Safety:

- do not edit WB finance amount;
- only edit taxonomy/category mapping or classification.

Current gap:

- guided action records classification on the DQ issue, but the durable taxonomy/mapping layer should also be updated, otherwise the next recheck can recreate the problem.

### Sync / Stock / Finance

`latest_stocks_not_completed`, `failed_sync_domains`, `stocks_task_not_ready`, `sale_without_finance`, `finance_without_sale`, and most `finance_reconciliation_mismatch` cases are not seller-editable.

Primary UI:

1. "Qayta sync qilish"
2. "Kutish kerak deb belgilash"
3. "Adminga yuborish"
4. "Qayta tekshirish"

Safety:

- never allow manual editing of sales, orders, finance rows, or WB report facts just to make totals match.

### Open Blocking DQ Issues

`open_blocking_dq_issues` is an aggregate label. It should not be shown as a fix card if underlying issue buckets exist.

Expand it into concrete issue groups:

- cost group;
- SKU mapping group;
- expense group;
- sync group;
- admin/system group.

If no underlying issue rows are available, show it as admin/system diagnostics, not as a user task.

## Frontend Flow

Dashboard button behavior:

1. If blocker is user-fixable, button label: `Tuzatish`.
2. If blocker is system/admin, button label: `Holatini ko'rish`.
3. If blocker is aggregate, button opens its expanded child tasks.

Data Fix page layout:

1. `Bugun tuzatiladiganlar`
   - only `owner_type=user|mixed` and `safe_to_apply=true`
2. `Sistema tekshiryapti`
   - `owner_type=system`
3. `Admin kerak`
   - `owner_type=admin`
4. `Ogohlantirishlar`
   - non-blocking warnings

Workbench flow:

1. Explain the problem in one sentence.
2. Show source rows.
3. Show editable fields or action buttons.
4. Preview what will change.
5. Apply.
6. Run recheck.
7. Show pass/fail.

## Backend Endpoints To Add

`GET /dq/fix-tasks`

Returns normalized tasks from data blockers, DQ issues, sync state, and cost coverage.

`GET /dq/fix-tasks/{task_id}`

Returns rows, columns, validation, source facts, and available actions.

`POST /dq/fix-tasks/{task_id}/apply`

Applies the task safely based on `fix_mode`.

`POST /dq/fix-tasks/{task_id}/recheck`

Runs only the relevant checks/marts/snapshots when possible.

`POST /costs/bulk-upsert`

Applies spreadsheet edits for cost rows.

`POST /expense-category-rules`

Creates or updates durable expense category mapping rules.

## Immediate Fixes In Current Code

1. Normalize blocker codes before matching DQ issues:

```ts
const BLOCKER_TO_ISSUE_CODE = {
  unmatched_sku_detected: "unmatched_sku",
  supplier_cost_coverage_below_threshold: "missing_manual_cost",
  ads_not_allocated_to_profitability: "ad_spend_without_sku",
};
```

2. Reclassify these as system/admin, not manual user tasks:

```ts
latest_stocks_not_completed -> system
failed_sync_domains -> system/admin
open_blocking_dq_issues -> aggregate
finance_reconciliation_mismatch -> system/admin
sale_without_finance -> system
finance_without_sale -> system
ads_overallocated_to_profitability -> admin
```

3. Do not show aggregate cards as the thing to fix. Expand them into child tasks.

4. Change Data Fix card CTA:

- `Tuzatish` only when `safe_to_apply=true`;
- `Qayta sync` for sync tasks;
- `Adminga yuborish` for admin tasks;
- `Kutamiz / qayta tekshiramiz` for WB delay tasks.

5. Add spreadsheet editor first for cost coverage, because this is the most user-fixable numeric blocker.

## Acceptance Criteria

The schema is complete when:

- every dashboard blocker maps to a `FixTask`;
- no system-only issue appears as "user must fix";
- numeric user-owned fields are editable in a table;
- WB financial facts are read-only;
- every action has a recheck button;
- a user can clear all user-owned blockers without opening admin-only screens;
- unresolved system/admin blockers explain who owns them and what will happen next.
