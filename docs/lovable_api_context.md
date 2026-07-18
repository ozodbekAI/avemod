# Lovable API/UI Context Package

Date: 2026-07-10

Source bundle:
`audit_bundles/full_page_audit_20260710_005730`

This document is the handoff contract for building UI in Lovable without
inventing endpoints, routes, states, or problem-flow semantics.

## Evidence Boundary

There are two evidence types in the bundle:

- Fixture/mock UI evidence:
  - Source: `frontend/e2e/full-page-audit.spec.ts` using
    `frontend/e2e/mock-api.ts`.
  - Bundle metadata says: `deterministic Playwright no-network fixture`.
  - Use this for UI states, route behavior, sample shapes, screenshots and
    product flow.
  - Demo identifiers such as `account_id=1`, `nm_id=245405620`, `sku_id=101`
    and `SKU-DEMO` are fixture values.
- Live DB evidence:
  - Source: `audit_bundles/full_page_audit_20260710_005730/database`.
  - Use this only for schema/table existence and row-count reality checks.
  - Do not use live sample rows as seller UI copy or product truth.

Do not copy tokens, cookies, emails, phone numbers, addresses, buyer data or raw
WB payloads into UI. The bundle redacts secret-like fields, but Lovable should
still treat request headers and DB samples as internal evidence only.

## Core Product Loop

The MVP seller flow is:

`Обзор бизнеса -> Центр действий -> доказательства -> рабочий экран -> статус/комментарий -> перепроверка -> результат`

The canonical dynamic-problem identity is:

- `problem_instance_id`
- `problem_code`
- `source_module=problem_engine`
- `nm_id`

Do not key problem timelines only by `problem_code` or `nm_id` when
`problem_instance_id` is present.

## Key Pages

| Page | Route | Primary API | What Lovable Should Build |
|---|---|---|---|
| Login | `/login` | auth login endpoint outside this bundle | Plain auth entry. No product data. |
| Обзор бизнеса | `/dashboard` | `/money/summary`, `/money/data-blockers`, `/portal/actions` | Executive control panel with blockers, money summary and next actions. |
| Деньги | `/money` | `/money/summary`, `/money/articles`, `/money/actions/today` | Money state, blockers, financial readiness, articles/products. |
| Товары | `/products` | `/portal/products` | Product list with quality/money/action signals. |
| Product360 | `/products/:nm_id` | `/portal/products/{nm_id}` | Product detail with money, data quality, card quality, problems and result preview. |
| Центр действий | `/action-center` | `/portal/actions`, `/portal/results` | Operational task desk. This is the main problem-solving surface. |
| Task drawer | `/action-center?problem_instance_id=42` | `/portal/actions`, `/portal/problems/{id}/results` | Auto-open exact task drawer when URL identifies a task. |
| Evidence drawer | Same Action Center route | embedded `evidence_ledger` | Seller-readable formula, facts, sources, missing data, trust notes and re-check rule. |
| Качество данных | `/data-fix` | `/dq/issues`, `/money/data-blockers` | Guided fixes for data blockers; preserve task return context. |
| Себестоимость | `/costs` | `/costs/missing`, `/costs/rows` | Missing-cost workbench and inline cost repair. |
| Results | `/results` | `/portal/problems/{id}/results` or `/portal/results` | Problem/result timelines with correlation disclaimer. |
| Checker | `/checker/:nm_id` | `/portal/products/{nm_id}/quality` | Card quality fixes; WB writes require preview/confirm. |
| Ads | `/ads` | `/ads/efficiency`, `/ads/campaigns`, `/ads/stats` | Ads context for allocation/profitability tasks. |
| Остатки и регионы | `/stock-control` | stock/supply endpoints plus shared data health | Supply planner and regional stock controls. |
| Настройки | `/settings` | `/settings/business`, `/portal/modules/health` | Business settings and module health. |

Secondary/beta pages can exist under `Ещё` for allowed users:
`/reputation`, `/claims`, `/photo-studio`, `/ab-tests`, `/grouping`,
`/stock-control`. If shown in navigation, show a `Бета` badge plus write-state
clarity such as `Запись`, `Чтение`, `Черновик` or `Безопасно`.

## Route Query Params

Shared context params:

| Param | Meaning | Used By |
|---|---|---|
| `account_id` | Active seller account for backend API queries. | Most API calls. |
| `date_from`, `date_to` | Reporting window. | Money, dashboard, products, DQ, results list. |
| `problem_instance_id` | Canonical dynamic problem instance. | Action Center, Results, Data Fix, Costs, Product360, Checker, Ads, Stock Control. |
| `action_id` | Legacy/unified action id. | Action Center and Results fallback. |
| `nm_id` | WB product identity. | Product360, Data Fix, Costs, Ads, Stock Control. |
| `source`, `source_id`, `code` | Fallback Action Center identity. | Return-to-task links. |

Important route-specific params:

- `/action-center`
  - `problem_instance_id`: auto-opens matching task drawer.
  - `action_id`: auto-opens matching legacy/unified task drawer.
  - `status`, `source_module`, `priority`, `problem_code`, `trust_state`,
    `impact_type`, `nm_id`: filters.
  - `include_beta=true`: admin-only for beta/test Action Center rows.
- `/results`
  - `problem_instance_id`: fetch exact problem timeline and fill
    `problem_code`/`nm_id` from returned problem identity.
  - `action_id`, `problem_code`, `nm_id`, `source_module`, `event_type`:
    generic result filters.
- `/products/:nm_id`
  - `tab=price|promo|...`: opens contextual Product360 tab.
  - `problem_instance_id`: shows return link to exact Action Center drawer.
- `/data-fix`
  - `problem_instance_id`, `nm_id`, `code`: focus a data issue/workbench.
- `/costs`
  - `focus=missing-costs|other-expenses|relink-sku`
  - `problem_instance_id`, `nm_id`: preserve task context.
- `/checker/:nm_id`
  - `problem_instance_id`: return link and result context.
- `/ads`
  - `problem_instance_id`, `nm_id`, `focus`, `rowFilter`.
- `/stock-control`
  - `tab=supply|return|balance|history|settings`
  - `problem_instance_id`, `nm_id`.

## Endpoint Contracts

All API paths below are under `/api/v1`. Use the existing auth client; do not
hardcode tokens.

### Common Shell

| Endpoint | Method | Purpose | Key Fields |
|---|---|---|---|
| `/auth/me` | GET | Current user and account roles. | `id`, `is_superuser`, `accounts[].role`. |
| `/accounts?include_inactive=true` | GET | Account selector. | account id/name/status. |
| `/portal/modules/health?account_id=` | GET | Feature visibility/runtime state. | `modules.{key}.status`, `visible`, `beta`, `runtime_status`. |
| `/portal/data-sync/status?account_id=` | GET | Global sync/freshness strip. | source freshness/status. |

### MVP Seller Surfaces

| Endpoint | Method | Purpose | Query |
|---|---|---|---|
| `/money/summary` | GET | Money KPIs and trust/finality. | `account_id`, `date_from`, `date_to`. |
| `/money/data-blockers` | GET | Financial blockers preventing final money. | same date window. |
| `/money/articles` | GET | Product/article money rows. | `account_id`, date window, `limit`. |
| `/money/actions/today` | GET | Money tasks for dashboard. | `account_id`, date window, `limit`. |
| `/portal/products` | GET | Product list. | `account_id`, date window, `search`, `card_quality_status`, `sort_by`, `sort_dir`, `limit`, `offset`. |
| `/portal/products/{nm_id}` | GET | Product360. | `account_id`, date window, optional limits. |
| `/portal/products/{nm_id}/quality` | GET | Checker/card quality detail. | `account_id`. |
| `/dq/issues/summary` | GET | Data quality counters. | `account_id`, date window. |
| `/dq/issues` | GET | Data quality issues. | `account_id`, date window, `only_open`, `financial_final_blocker`, `limit`. |
| `/costs/missing` | GET | Missing cost workbench. | `account_id`, `limit`, `offset`, date window, `only_revenue`. |
| `/costs/rows` | GET | Existing manual costs. | `account_id`, `limit`, `offset`. |
| `/costs/inline-save` | POST | Safe inline cost save. | JSON body with SKU/cost fields. |

Money control-panel fields Lovable should depend on:

- `/money/summary.control_panel`: normalized Money UI contract with
  `confirmed_money`, `provisional_sales`, `probable_risks`, `blocked_cash`,
  `calculation_blockers`, `growth_opportunities`, `source_coverage`,
  `grouped_problems`, and aggregate `unit_economics`.
- `control_panel.source_coverage[]`: source readiness for
  `finance_reports_wb`, `orders_sales`, `cost_price`, `expenses`, `ads`,
  `stocks`, `prices`, and `documents`; each item has `status`,
  `last_synced_at`, `blocks_calculation[]`, and `action_hint`.
- `control_panel.grouped_problems.{reconciliation|cost|margin_profit|expenses|ads|documents|data_blockers|system_checks}`:
  renderable finance problem/action rows with `problem_instance_id`,
  `action_id`, `title`, `explanation`, `recommendation`, `amount`,
  `trust_state`, `impact_type`, `evidence_ledger`, `action_center_href`,
  `data_fix_href`, `results_href`, and `recheck_available`.
- Product money blocks expose `money.unit_economics` with `price`,
  `cost_price`, `commission`, `logistics`, `ads`, `other_expenses`,
  `unit_profit`, `margin_pct`, `trust_state`, and `blockers`.

Product360 control-panel fields Lovable should depend on:

- `product_identity`: `title`, `nm_id`, `vendor_code`, `barcode`, `image`, `category`, `price`, `stock`, `sync_freshness`.
- `health_summary`: aggregate status, open/resolved problem counts, data blocker count, checker score, sync freshness.
- `problem_instances[]`: dynamic problem rows for the product, each with `problem_instance_id`, `problem_code`, `status`, `trust_state`, `evidence_ledger`, `allowed_actions`, `action_center_href`, `results_href`, `recheck_available`.
- `grouped_problems.{profitability|stock|price|ads_promo|card_quality|data_blockers|system_checks}`: renderable problem buckets with normalized item shape.
- `result_preview`: canonical result ledger preview for linked problem instances.
- `checker_summary`: score, open issue count, top issues, `checker_href`.
- `data_blockers`: count, top blockers, `data_fix_href`.

### Action Center

| Endpoint | Method | Purpose |
|---|---|---|
| `/portal/actions` | GET | Unified Action Center rows. |
| `/portal/assignable-users` | GET | Users assignable to tasks. Requires operator role. |
| `/portal/actions/by-source` | PATCH | Source-aware task update for dynamic problems and source-backed actions. |
| `/portal/actions/{action_id}` | PATCH | Legacy/unified task update. |
| `/portal/problems/{problem_id}/recheck` | POST | Re-run dynamic problem rule and update status/result. |

`GET /portal/actions` query:

`account_id`, `date_from`, `date_to`, `status`, `source_module`, `priority`,
`nm_id`, `action_type`, `problem_code`, `trust_state`, `impact_type`,
`include_beta`, `limit`, `offset`.

Action item fields Lovable should depend on:

- identity: `id`, `action_id`, `source_module`, `source_id`,
  `problem_instance_id`, `problem_code`, `nm_id`, `vendor_code`;
- seller copy: `title`, `short_explanation`, `recommendation`, `next_step`;
- task state: `status`, `priority`, `severity`, `assigned_to_user_id`,
  `assigned_to_user_name`, `deadline_at`, `sla_state`, `is_overdue`;
- evidence/result: `evidence_ledger`, `money_trust`, `impact_type`,
  `trust_state`, `result_summary`, `history_summary`;
- actions: `allowed_actions`, `allowed_action_items`, `solve_map`.

### Results

| Endpoint | Method | Purpose |
|---|---|---|
| `/portal/problems/{problem_instance_id}/results` | GET | Canonical exact dynamic problem timeline. Prefer this when `problem_instance_id` is present. |
| `/portal/actions/{action_id}/results` | GET | Legacy/unified action timeline. |
| `/portal/results` | GET | Generic result-event search/list. |
| `/portal/actions/{action_id}/result-event` | POST | Manual/legacy result event creation. |

Result query fields:

`account_id`, `action_id`, `problem_instance_id`, `problem_code`, `nm_id`,
`source_module`, `event_type`, `limit`, `offset`.

The Results page must never show stale `problem_code` or `nm_id` when
`problem_instance_id` is present. Fetch the exact problem timeline and use the
returned `problem`/`summary` identity even when `items` is empty.

### Secondary/Beta Modules

| Page | Primary Endpoints |
|---|---|
| `/reputation` | `/portal/reputation/summary`, `/portal/reputation/settings`, `/portal/reputation/inbox`. |
| `/claims` | `/portal/cases`, `/portal/claims/candidates`, `/portal/claims/support/categories`. |
| `/photo-studio` | `/portal/photo/projects`, `/portal/photo/status`, `/portal/photo/settings`. |
| `/ab-tests` | `/promotion/running`, `/promotion/pending`, `/promotion/finished`, `/promotion/failed`. |
| `/grouping` | `/portal/actions?source_module=grouping`, `/portal/products/{nm_id}/grouping`. |
| `/ads` | `/ads/efficiency`, `/ads/campaigns`, `/ads/stats`. |

## Sample Requests And Responses

These are scrubbed, short samples from fixture evidence and current source
contracts. They are shape examples, not production data.

### `GET /portal/actions`

Request:

```http
GET /api/v1/portal/actions?account_id=1&date_from=2026-06-09&date_to=2026-07-09
Authorization: Bearer <REDACTED>
```

Response excerpt:

```json
{
  "status": "ok",
  "total": 5,
  "items": [
    {
      "id": "problem_engine:42",
      "source_module": "problem_engine",
      "source_id": "42",
      "problem_instance_id": 42,
      "problem_code": "low_stock_risk",
      "title": "Риск потери продаж по товару",
      "short_explanation": "Остатка хватит меньше чем на три дня при текущем спросе.",
      "recommendation": "Проверьте поставку и перепроверьте после обновления остатков.",
      "status": "new",
      "priority": "P1",
      "severity": "high",
      "nm_id": 245405620,
      "impact_type": "lost_sales_risk",
      "trust_state": "provisional",
      "money_trust": {
        "state": "provisional",
        "impact_kind": "lost_sales_risk",
        "display_label": "Риск потери продаж",
        "saved_money_claimed": false
      },
      "solve_map": {
        "title": "Карта решения: риск низкого остатка",
        "steps": [
          {
            "step_id": "supply_plan",
            "order": 2,
            "title": "Открыть поставки",
            "status": "available",
            "action_code": "open_supply_planner",
            "target_href": "/stock-control?tab=supply&problem_instance_id=42&nm_id=245405620"
          }
        ]
      }
    }
  ]
}
```

### `PATCH /portal/actions/by-source`

Use this for dynamic problem updates and source-aware actions.

Request:

```json
{
  "account_id": 1,
  "source_module": "problem_engine",
  "source_id": "42",
  "status": "in_progress",
  "assigned_to_user_id": 1,
  "deadline_at": "2026-07-11T12:00:00Z",
  "comment": "Проверяем поставку",
  "event_type": "status_changed"
}
```

Expected response: a full `PortalActionRead` object with updated `status`,
assignment/deadline fields and appended history.

### `GET /portal/problems/{problem_instance_id}/results`

Request:

```http
GET /api/v1/portal/problems/42/results?limit=50&offset=0
```

Response shape:

```json
{
  "status": "ok",
  "total": 0,
  "problem": {
    "problem_instance_id": 42,
    "problem_code": "low_stock_risk",
    "nm_id": 245405620,
    "title": "Риск потери продаж по товару"
  },
  "summary": {
    "status": "pending_data",
    "problem_instance_id": 42,
    "problem_code": "low_stock_risk",
    "nm_id": 245405620,
    "title": "Риск потери продаж по товару",
    "calculation_note": "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе."
  },
  "items": []
}
```

If `items` is empty, UI must still show the header identity and a waiting state:
`Пока нет данных`.

### `POST /portal/problems/{problem_id}/recheck`

Request:

```http
POST /api/v1/portal/problems/42/recheck
```

Response: updated `PortalActionRead`. UI should refresh the Action Center row,
drawer history and result timeline.

### `GET /dq/issues`

Request:

```http
GET /api/v1/dq/issues?account_id=1&only_open=true&financial_final_blocker=true&limit=100
```

Response excerpt:

```json
{
  "status": "ok",
  "total": 1,
  "items": [
    {
      "id": 430,
      "code": "missing_manual_cost",
      "domain": "costs",
      "sku_id": 101,
      "nm_id": 245405620,
      "severity": "high",
      "status": "open",
      "message": "Не хватает себестоимости",
      "business_impact": "Без себестоимости нельзя подтвердить прибыльность товара.",
      "resolver": {
        "owner_type": "user",
        "component_type": "cost_inline_editor",
        "required_inputs": ["cost_price"]
      },
      "money_trust": {
        "state": "blocked",
        "impact_kind": "data_blocker",
        "saved_money_claimed": false
      }
    }
  ]
}
```

### `GET /dq/issues/{issue_id}/resolution-context`

Use this endpoint for the Data Fix Workbench. It returns the full
problem-to-result context so the frontend does not infer ownership or allowed
actions from issue codes.

Key top-level fields:

- `issue_id`, `problem_instance_id`, `issue_code`, `title`, `explanation`,
  `why_it_matters`
- `owner_type`: `user`, `system`, `admin`, or `mixed`
- `can_user_fix_inside_platform`, `fix_component_type`, `required_inputs`
- `affected_rows[]` normalized to `nm_id`, `vendor_code`, `barcode`, `source`,
  `current_value`, `missing_or_invalid_value`, `suggested_fix`, `confidence`,
  `row_status`
- `evidence_ledger`, `preview_available`, `apply_available`,
  `recheck_available`, `disabled_reason`
- `action_center_href`, `results_href`

`raw_payload` appears in `affected_rows[]` only for superusers/account admins
when `include_debug=true`; regular Workbench calls receive normalized rows only.

Safe apply rules:

- cost fill/upload points to existing `/costs/inline-save` or upload/confirm
  flows, followed by Data Fix re-check;
- SKU mapping and expense classification use
  `POST /dq/issues/{issue_id}/guided-action`;
- WB finance facts are read-only in Data Fix;
- `finance_reconciliation_mismatch` is system/admin investigation;
- `price_jump` is check-only and never auto-changes WB prices.

## UI States

Global page states:

- loading skeleton while page data is pending;
- `NoAccountSelected` when no active account exists;
- `EndpointError` with retry when endpoint fails;
- global data freshness strip from `/portal/data-sync/status`;
- module disabled/not configured state from `/portal/modules/health`;
- no raw backend English errors in seller-visible surfaces.

Action Center states:

- list loaded with summary cards and filters;
- empty list under filters;
- drawer open from row click or URL query;
- task not found from URL:
  `Задача не найдена или больше не активна`;
- evidence drawer open from `Как посчитано?`;
- unsafe action disabled with `disabled_reason`;
- assignment/deadline/status/comment save;
- re-check requested/completed;
- result waiting, improved, worse, unchanged, no-data.

Evidence UI:

- separate source confidence and business impact:
  - `Доверие к данным: Подтверждено / Предварительно / Не хватает данных`;
  - `Тип влияния: Риск потери продаж / Вероятный риск / Замороженные деньги / Блокер данных`;
- microcopy:
  `Данные могут быть подтверждены, но денежный эффект остаётся оценкой до результата после действия.`
- raw JSON hidden for sellers.

Results UI:

- always show correlation disclaimer;
- exact problem identity when `problem_instance_id` is present;
- waiting state with `Пока нет данных` when no events exist;
- before/action/re-check/after timeline when events exist;
- no saved-money claim unless measured after-data and confidence are visible.

## Primary Actions And Destination Hrefs

The Action Center primary button should use `solve_map.steps[].target_href` when
present. If absent, use the local mapping below.

| Action Code | Destination |
|---|---|
| `open_data_fix` | `/data-fix?problem_instance_id=<id>&nm_id=<nm_id>` |
| `upload_cost` | `/costs?focus=missing-costs&problem_instance_id=<id>&nm_id=<nm_id>` |
| `map_sku` | `/data-fix?code=unmatched_sku&problem_instance_id=<id>` |
| `open_supply_planner` | `/stock-control?tab=supply&problem_instance_id=<id>&nm_id=<nm_id>` |
| `open_price_review` | `/products/<nm_id>?tab=price&problem_instance_id=<id>` |
| `open_promo_planner` | `/products/<nm_id>?tab=promo&problem_instance_id=<id>` |
| `open_ads_dashboard` | `/ads?problem_instance_id=<id>&nm_id=<nm_id>` |
| `run_checker` | `/checker/<nm_id>?problem_instance_id=<id>` |
| `open_results` | `/results?problem_instance_id=<id>` or `/results?action_id=<action_id>` |
| `open_product` | `/products/<nm_id>?problem_instance_id=<id>` |
| `recheck`, `assign`, `create_task`, `dismiss` | In-drawer action, no navigation. |

All destination pages that receive task context should render
`ActionCenterReturnLink`, returning to:

`/action-center?problem_instance_id=<id>` or `/action-center?action_id=<id>`.

## Screenshots Index

All screenshots are full-page PNGs under the audit bundle. They are fixture UI
evidence, not live DB screenshots.

| ID | Screenshot | Proves |
|---|---|---|
| `00_login` | `audit_bundles/full_page_audit_20260710_005730/pages/00_login/screenshot_full_page.png` | Login route renders without authenticated data. |
| `01_dashboard` | `audit_bundles/full_page_audit_20260710_005730/pages/01_dashboard/screenshot_full_page.png` | Business overview shell, money/data/action widgets and global strips. |
| `02_money` | `audit_bundles/full_page_audit_20260710_005730/pages/02_money/screenshot_full_page.png` | Money page uses summary, blockers, articles and today's actions. |
| `03_products` | `audit_bundles/full_page_audit_20260710_005730/pages/03_products/screenshot_full_page.png` | Product list route and product cards/table. |
| `04_product360` | `audit_bundles/full_page_audit_20260710_005730/pages/04_product360/screenshot_full_page.png` | Product360 identity, money, data quality, card quality and problems. |
| `05_product360_price_context` | `audit_bundles/full_page_audit_20260710_005730/pages/05_product360_price_context/screenshot_full_page.png` | Product360 opens with price/task context. |
| `06_action_center` | `audit_bundles/full_page_audit_20260710_005730/pages/06_action_center/screenshot_full_page.png` | Action Center list, summary cards and filters. |
| `07_action_center_task` | `audit_bundles/full_page_audit_20260710_005730/pages/07_action_center_task/screenshot_full_page.png` | Direct task URL opens task context/drawer. |
| `08_action_center_evidence` | `audit_bundles/full_page_audit_20260710_005730/pages/08_action_center_evidence/screenshot_full_page.png` | Evidence drawer is seller-readable. |
| `09_data_fix` | `audit_bundles/full_page_audit_20260710_005730/pages/09_data_fix/screenshot_full_page.png` | Data Fix opens with problem and product context. |
| `10_costs_missing` | `audit_bundles/full_page_audit_20260710_005730/pages/10_costs_missing/screenshot_full_page.png` | Costs page focuses missing-cost workbench. |
| `11_results` | `audit_bundles/full_page_audit_20260710_005730/pages/11_results/screenshot_full_page.png` | Results timeline route with problem context. |
| `12_checker` | `audit_bundles/full_page_audit_20260710_005730/pages/12_checker/screenshot_full_page.png` | Checker/card quality route with task context. |
| `13_ads` | `audit_bundles/full_page_audit_20260710_005730/pages/13_ads/screenshot_full_page.png` | Ads workbench route with task context. |
| `14_stock_control_supply` | `audit_bundles/full_page_audit_20260710_005730/pages/14_stock_control_supply/screenshot_full_page.png` | Stock Control supply tab opens from low-stock problem. |
| `15_settings` | `audit_bundles/full_page_audit_20260710_005730/pages/15_settings/screenshot_full_page.png` | Settings and module health surface. |
| `16_reputation` | `audit_bundles/full_page_audit_20260710_005730/pages/16_reputation/screenshot_full_page.png` | Reputation beta module shell. |
| `17_claims` | `audit_bundles/full_page_audit_20260710_005730/pages/17_claims/screenshot_full_page.png` | Claims beta module shell. |
| `18_photo_studio` | `audit_bundles/full_page_audit_20260710_005730/pages/18_photo_studio/screenshot_full_page.png` | Photo Studio project list/empty state. |
| `19_photo_project` | `audit_bundles/full_page_audit_20260710_005730/pages/19_photo_project/screenshot_full_page.png` | Photo project detail route. |
| `20_ab_tests` | `audit_bundles/full_page_audit_20260710_005730/pages/20_ab_tests/screenshot_full_page.png` | A/B tests route and status columns. |
| `21_ab_test_detail` | `audit_bundles/full_page_audit_20260710_005730/pages/21_ab_test_detail/screenshot_full_page.png` | A/B test detail route. |
| `22_grouping` | `audit_bundles/full_page_audit_20260710_005730/pages/22_grouping/screenshot_full_page.png` | Grouping beta route. |
| `23_admin` | `audit_bundles/full_page_audit_20260710_005730/pages/23_admin/screenshot_full_page.png` | Admin route for superusers. |
| `24_analytics` | `audit_bundles/full_page_audit_20260710_005730/pages/24_analytics/screenshot_full_page.png` | Analytics/admin-support route. |
| `25_cards` | `audit_bundles/full_page_audit_20260710_005730/pages/25_cards/screenshot_full_page.png` | Legacy cards route remains available for admin/support. |
| `26_card_detail` | `audit_bundles/full_page_audit_20260710_005730/pages/26_card_detail/screenshot_full_page.png` | Legacy card detail route. |
| `27_catalog` | `audit_bundles/full_page_audit_20260710_005730/pages/27_catalog/screenshot_full_page.png` | Catalog admin/support route. |
| `28_doctor` | `audit_bundles/full_page_audit_20260710_005730/pages/28_doctor/screenshot_full_page.png` | Legacy doctor route redirects seller concept toward Action Center. |
| `29_expenses` | `audit_bundles/full_page_audit_20260710_005730/pages/29_expenses/screenshot_full_page.png` | Expenses route. |
| `30_finance` | `audit_bundles/full_page_audit_20260710_005730/pages/30_finance/screenshot_full_page.png` | Finance route. |
| `31_marts` | `audit_bundles/full_page_audit_20260710_005730/pages/31_marts/screenshot_full_page.png` | Marts route. |
| `32_operations` | `audit_bundles/full_page_audit_20260710_005730/pages/32_operations/screenshot_full_page.png` | Operations route. |
| `33_pricing` | `audit_bundles/full_page_audit_20260710_005730/pages/33_pricing/screenshot_full_page.png` | Pricing route. |
| `34_purchase_plan` | `audit_bundles/full_page_audit_20260710_005730/pages/34_purchase_plan/screenshot_full_page.png` | Purchase plan route. |
| `35_sku` | `audit_bundles/full_page_audit_20260710_005730/pages/35_sku/screenshot_full_page.png` | SKU list route. |
| `36_sku_detail` | `audit_bundles/full_page_audit_20260710_005730/pages/36_sku_detail/screenshot_full_page.png` | SKU detail route. |
| `37_stock` | `audit_bundles/full_page_audit_20260710_005730/pages/37_stock/screenshot_full_page.png` | Legacy stock route. |
| `38_actions_legacy` | `audit_bundles/full_page_audit_20260710_005730/pages/38_actions_legacy/screenshot_full_page.png` | Legacy actions route. |

## Live DB Evidence

The live DB export is in:

- `audit_bundles/full_page_audit_20260710_005730/database/DB_SCOPE.md`
- `audit_bundles/full_page_audit_20260710_005730/database/live_db_export.json`
- `audit_bundles/full_page_audit_20260710_005730/database/schema_inventory.json`

Relevant live table reality from the bundle:

| Area | Tables Present |
|---|---|
| Action Center | `unified_actions`, `problem_instances`, `problem_instance_history`, `result_events`. |
| Problem Rules | `problem_definitions`, `problem_rule_versions`, `problem_evaluation_run_logs`. |
| Data Fix/Costs | `data_quality_issues`, `manual_costs`. |
| Commerce Sources | `wb_accounts`, `wb_orders`, `wb_sales`, `wb_realization_report_rows`, `wb_ad_campaigns`. |
| Portal/Beta | `photo_projects`, `grouping_recommendations`, `reputation_items`; `stock_control_runs` exists but had zero rows in the export. |

Live DB is evidence that these areas exist and have records. It is not proof
that every screenshot state is backed by live data, because screenshots were
captured from deterministic frontend fixtures.

## Known Blockers

- The full-page audit screenshots are fixture/no-network evidence. Lovable must
  still validate against staging/live API before final signoff.
- The captured Results page in this bundle used generic
  `/portal/results?problem_instance_id=42`; current frontend source prefers
  `/portal/problems/{problem_instance_id}/results` for exact identity.
- Some live tables are absent in the export, including `product_cards`,
  `wb_stocks`, `wb_ad_stats`, `prices`, `manual_cost_imports`,
  `ab_tests`, and `claims_cases`. UI must support empty/not-configured states.
- `stock_control_runs` existed with zero rows in the live export, so Stock
  Control needs empty-history UX.
- Dynamic `problem_engine` is canonical; legacy pages/actions can still exist
  as adapters and should not drive the primary seller UX.
- WB write flows remain guarded. Any UI that changes WB cards, photos, ads,
  promos or prices must show preview/diff/confirm/audit state from the
  destination module.
- Do not show raw JSON to sellers. Keep debug/raw payloads admin-only.
- Do not call estimated impact saved money. Use result ledger measured data and
  confidence before presenting confirmed outcomes.
