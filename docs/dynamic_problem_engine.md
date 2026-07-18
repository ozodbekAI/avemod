# Dynamic Problem Definition Engine

Date: 2026-07-06

Status: target architecture, no runtime behavior changed.

Related inventory: `docs/dynamic_problem_definition_baseline.md`.

## Purpose

The Dynamic Problem Definition Engine replaces scattered hardcoded business
problem cards with admin-defined, versioned, testable problem rules.

Admins should be able to define new product/business problems by selecting
predefined metrics, composing safe formulas, previewing historical impact, and
publishing rules that generate product-level problem instances with evidence,
re-check rules, and mapped actions.

The engine must integrate with Product 360, Action Center, Money, Pricing, Ads,
Purchase Plan, and Data Fix without breaking existing API contracts during the
migration.

## Non-Goals

- No raw SQL authoring by admins.
- No Python expressions or Python `eval`.
- No direct external Wildberries writes from a problem rule.
- No replacement of existing Control Tower, Money, DQ, or Portal APIs in the
  first implementation phase.
- No removal of existing hardcoded cards until dynamic rules have shadow-run
  parity and UI integration.

## Main Concepts

### Metric Catalog

The Metric Catalog is the only source of values that rule formulas may read.
Each metric is a backend-owned, typed, documented value with a known source,
grain, trust behavior, and null semantics.

Metric examples:

- `unit_cost_confirmed`
- `unit_cost_effective`
- `current_discounted_price`
- `min_safe_price`
- `break_even_price`
- `safe_price_gap`
- `net_profit_after_ads`
- `net_profit_per_unit`
- `ad_spend`
- `ads_allocation_status`
- `available_stock_units`
- `days_of_stock`
- `sales_velocity_daily`
- `lead_time_days`
- `safety_stock_days`
- `stock_value`
- `promo_discount_percent`
- `promo_active`
- `promo_profit_after_discount`
- `finance_reconciliation_status`
- `open_blocking_dq_issue_count`

Metric fields:

```text
key                 Stable unique code, for example days_of_stock.
label               Human-readable admin label.
description         Meaning, source, and caveats.
scope               account, product, sku, campaign, cost_row, dq_issue.
value_type          decimal, integer, boolean, string, enum, date, datetime.
unit                rub, percent, units, days, ratio, count, none.
grain               daily, window, latest_snapshot, current_state.
source_module       money, control_tower, pricing, ads, stock, dq, costs.
source_endpoint     Optional existing endpoint for traceability.
source_table        Optional backend table/view name for engineering trace.
resolver            Backend resolver function name.
nullable            Whether null is expected.
null_behavior       block_rule, evaluate_false, fallback_zero, fallback_metric.
trust_strategy      confirmed_only, inherit_source, calculated, estimated.
allowed_scopes      Entity scopes where metric can be used.
allowed_aggregates  none, sum, avg, min, max, count, latest.
data_freshness_ttl  Maximum age before metric becomes provisional.
version             Metric contract version.
status              active, deprecated, disabled.
owner               Engineering owner/module.
```

Metric catalog rules:

- Admin formulas may reference only `active` metrics.
- Metric keys are stable and cannot be reused for different semantics.
- Deprecated metrics remain readable for old rule versions until archived.
- Metric resolvers run in backend services, not in user expressions.
- All returned metric values must include value, source, as-of date, freshness,
  confidence, and trust metadata for evidence.

### Problem Definition

A Problem Definition is the admin-visible business problem. It contains stable
identity, scope, default copy, impact type, allowed actions, and one or more
immutable Rule Versions.

Definition fields:

```text
code                Stable unique problem code.
title               Business title shown to operators.
description         Admin explanation.
scope               account, product, sku, campaign, cost_row, dq_issue.
impact_type         One of the allowed impact types.
default_severity    critical, high, medium, low.
default_priority    P0, P1, P2, P3, P4.
status              draft, testing, active, paused, archived.
owner_team          Backend/business owner.
created_by          User id.
updated_by          User id.
active_version_id   Current published version, nullable.
visibility          operator, admin_only, seller_visible.
dedupe_strategy     per_entity, per_entity_per_window, per_metric_signature.
cooldown_hours      Suppress duplicate instances for this period.
tags                finance, stock, pricing, ads, data_quality, promo.
```

Problem definition statuses:

- `draft`: editable, not runnable outside validation.
- `testing`: can run backtests and shadow runs, generated instances are
  `test_only`.
- `active`: published and eligible to generate live instances.
- `paused`: published definition is temporarily not evaluated.
- `archived`: immutable historical definition, not evaluated.

### Rule Version

A Rule Version is an immutable formula package attached to a Problem Definition.
Publishing creates a new version rather than mutating the old one.

Rule version fields:

```text
definition_id       Parent problem definition.
version             Monotonic integer.
status              draft, testing, active, retired.
formula_ast         Validated JSON AST.
formula_text        Optional admin-readable expression, never executed.
precondition_ast    Optional condition required before trigger evaluation.
severity_ast        Optional formula returning severity.
priority_ast        Optional formula returning priority.
impact_amount_ast   Optional formula returning money/quantity impact.
confidence_ast      Optional formula returning confidence.
required_metrics    Materialized metric keys referenced by all ASTs.
required_actions    Whitelisted action codes this rule may emit.
recheck_policy      JSON re-check policy.
entity_selector     Scope and candidate filtering, no SQL.
window_config       Date/window configuration.
thresholds          Named admin parameters used by formula.
copy_template       Title/reason/next step templates.
evidence_template   Required evidence fields.
published_by        User id.
published_at        Timestamp.
change_note         Required note for publish.
```

Rule version rules:

- Versions are immutable after publish.
- Draft versions may be edited only while the parent definition is `draft` or
  `testing`.
- Admin-created versions generate `test_only` instances until explicitly
  published.
- A rule cannot become active until it passes validation, safety checks,
  evidence checks, action whitelist checks, and at least one backtest.

### Problem Instance

A Problem Instance is the generated occurrence of a Problem Definition for a
specific entity and evaluation run.

Instance fields:

```text
id                  Primary key.
definition_id       Source definition.
rule_version_id     Source version.
problem_code        Denormalized code.
entity_scope        product, sku, account, campaign, cost_row, dq_issue.
account_id          Required.
nm_id               Product id when applicable.
sku_id              SKU id when applicable.
campaign_id         Campaign id when applicable.
source_entity_id    Generic source id for cost/DQ/checker rows.
status              Instance lifecycle status.
trust_state         confirmed, provisional, estimated, opportunity, blocked, test_only.
impact_type         confirmed_loss, probable_loss, blocked_cash, etc.
severity            critical, high, medium, low.
priority            P0, P1, P2, P3, P4.
confidence          high, medium, low.
title               Rendered title.
summary             Rendered short reason.
business_reason     Rendered detailed reason.
next_step           Rendered next step.
impact_amount       Numeric amount, nullable.
impact_currency     RUB or null.
dedupe_key          Stable unique idempotency key.
formula_result      Boolean trigger result and calculated values.
evidence_ledger     Required evidence object.
allowed_actions     Actions allowed for this instance.
selected_action     Optional currently recommended action.
recheck_at          Optional next re-check timestamp.
resolved_at         Resolution timestamp.
dismissed_at        Dismissal timestamp.
created_by_run_id   Engine run id.
last_seen_run_id    Last engine run where condition remained true.
first_seen_at       Timestamp.
last_seen_at        Timestamp.
created_at          Timestamp.
updated_at          Timestamp.
```

Problem instance statuses:

- `new`: generated and not yet reviewed.
- `acknowledged`: user saw/accepted the issue exists.
- `in_progress`: user is working on it.
- `done`: user completed the mapped action.
- `postponed`: user intentionally delayed it.
- `ignored`: user chose not to act for now.
- `blocked`: action cannot proceed due to missing data/system/user blocker.
- `resolved`: re-check confirms the problem no longer exists.
- `dismissed`: user/admin permanently dismissed this instance.

Status rules:

- Engine may create `new`, update `last_seen_*`, and auto-transition to
  `resolved` when re-check passes.
- Users may set `acknowledged`, `in_progress`, `done`, `postponed`, `ignored`,
  and `dismissed`.
- Engine may set `blocked` only when a rule's required metrics or guardrails are
  unavailable.
- Published rule changes create new instances only when the dedupe key changes
  or prior instances are resolved/dismissed outside cooldown.

### Evidence Ledger

Every generated instance must have an `evidence_ledger`. Instances without
evidence are invalid and must not be shown in Product 360 or Action Center.

Evidence ledger shape:

```json
{
  "formula_code": "negative_unit_profit.v3",
  "formula_human": "net_profit_per_unit < 0 and unit_cost_confirmed = true",
  "rule_version_id": 123,
  "evaluation_run_id": 456,
  "entity": {
    "scope": "product",
    "account_id": 1,
    "nm_id": 987654
  },
  "result": true,
  "triggered_at": "2026-07-06T00:00:00Z",
  "metrics": [
    {
      "key": "net_profit_per_unit",
      "value": -42.15,
      "unit": "rub",
      "trust_state": "confirmed",
      "source_module": "money",
      "source_endpoint": "/money/articles/{nm_id}",
      "source_as_of": "2026-07-06",
      "freshness": "fresh"
    }
  ],
  "calculation": {
    "operands": {
      "net_profit_after_ads": -4215.0,
      "net_units": 100
    },
    "derived_values": {
      "net_profit_per_unit": -42.15
    }
  },
  "safety": {
    "guards_passed": ["cost_present", "min_safe_price_respected"],
    "guards_blocked": []
  }
}
```

Evidence rules:

- Store metric values used by the formula, not the whole source row.
- Store source module, source endpoint/table, as-of date, and freshness.
- Store derived formula values used for severity, priority, and impact.
- Store guardrail results.
- Evidence must be serializable and stable enough for audit and UI display.

### Rule Backtest

A Rule Backtest evaluates a draft/testing rule version over historical windows
without creating live instances.

Backtest outputs:

```text
definition_id
rule_version_id
date_from
date_to
scope
sample_size
evaluated_entity_count
triggered_count
blocked_count
estimated_total_impact
severity_distribution
priority_distribution
trust_distribution
top_examples
false_positive_review_notes
metric_coverage_report
runtime_ms
created_by
created_at
```

Backtest requirements:

- Backtests must run with the same evaluator and metric resolvers as production.
- Backtests cannot call external write APIs.
- Backtests can produce preview-only instances with `trust_state=test_only`.
- Admin UI must show examples with evidence, not only counts.
- Publishing requires at least one successful backtest after the latest formula
  edit.

### Re-check

Re-check determines whether an existing problem is still active, should remain
open, should become blocked, or can be resolved.

Re-check policy fields:

```text
mode                on_metric_change, scheduled, manual, on_action_done.
interval_hours      Scheduled re-check cadence.
success_ast         Formula that resolves the problem.
still_active_ast    Optional formula that keeps it open.
blocked_ast         Optional formula that marks it blocked.
max_attempts        Optional limit for automatic re-checks.
cooldown_hours      Optional silence period after resolution/dismissal.
```

Re-check rules:

- `done` is a user/action state; `resolved` is a verified data state.
- If an action is marked `done`, the engine schedules a re-check.
- If the trigger formula becomes false and success formula is true, status moves
  to `resolved`.
- If required metrics become unavailable, status moves to `blocked` with
  evidence.
- Dismissed instances remain dismissed unless a new dedupe key is created.

### Allowed Actions

Allowed Actions are backend-owned action templates that problem definitions may
map to.

Action template fields:

```text
action_code         Stable code, for example FIX_COST_TRUST.
action_group        data_fix, pricing, stock, ads, promo, content, review.
label               Admin/operator label.
description         What the action does.
external_write      true when it can write to WB or another external system.
requires_preview    Required for all external writes.
requires_diff       Required for all external writes.
requires_confirm    Required for all external writes.
requires_audit      Required for all external writes.
allowed_scopes      Product/SKU/account/campaign scopes.
route_template      UI deep link template.
payload_schema      JSON schema for action payload.
```

Initial action whitelist:

- `FIX_COST_TRUST`
- `MAP_UNMATCHED_SKU`
- `FIX_STOCK_SYNC`
- `RECONCILE_FINANCE`
- `FIX_AD_ALLOCATION`
- `FIX_PRICE_MAPPING`
- `REORDER`
- `PROTECT_STOCK`
- `DO_NOT_REORDER`
- `LIQUIDATE_STOCK`
- `PRICE_INCREASE_REVIEW`
- `PRICE_DECREASE_REVIEW`
- `AD_PAUSE_REVIEW`
- `AD_SCALE_REVIEW`
- `PROMO_STOP_REVIEW`
- `PROMO_PRICE_REVIEW`
- `CARD_CONTENT_REVIEW`
- `DATA_FIX_REQUIRED`
- `MANUAL_REVIEW`

Action mapping rules:

- Problem definitions may select only whitelisted actions.
- External write actions require preview, diff, confirm, and audit.
- The engine emits recommended action metadata; execution remains owned by
  existing action modules.
- Product 360 and Action Center consume the mapped action in the same shape as
  current Portal actions during migration.

## Required Enums

Problem definition status:

- `draft`
- `testing`
- `active`
- `paused`
- `archived`

Problem instance status:

- `new`
- `acknowledged`
- `in_progress`
- `done`
- `postponed`
- `ignored`
- `blocked`
- `resolved`
- `dismissed`

Trust states:

- `confirmed`: all required source metrics are final/accepted.
- `provisional`: source metrics are operationally usable but not final.
- `estimated`: one or more values are modeled/fallback estimates.
- `opportunity`: upside recommendation, not a confirmed loss.
- `blocked`: required data is missing or unsafe to compute.
- `test_only`: generated by draft/testing/admin-preview rules.

Impact types:

- `confirmed_loss`
- `probable_loss`
- `blocked_cash`
- `lost_sales_risk`
- `opportunity`
- `data_blocker`
- `system_warning`

## Safe Expression Model

Rules should be stored and executed as validated JSON AST, not as raw executable
strings. `formula_text` can exist only as admin-readable display text.

Allowed AST node types:

- `metric_ref`: references a Metric Catalog key.
- `const`: number, string, boolean, or null.
- `param_ref`: references a named threshold in the rule version.
- `compare`: compares two expressions.
- `boolean`: `and`, `or`.
- `not`: boolean negation.
- `arithmetic`: add, subtract, multiply, divide.
- `coalesce`: first non-null expression.
- `case`: if/then/else expression.
- `function`: whitelisted pure functions only.

Allowed comparison operators:

- `eq`
- `neq`
- `gt`
- `gte`
- `lt`
- `lte`
- `in`
- `not_in`

Allowed arithmetic operators:

- `add`
- `sub`
- `mul`
- `div`

Allowed functions:

- `abs`
- `min`
- `max`
- `round`
- `floor`
- `ceil`
- `is_null`
- `is_not_null`
- `percent`

Disallowed:

- SQL fragments.
- Python/JavaScript code.
- Attribute access.
- Function names not in the whitelist.
- Network calls.
- File reads/writes.
- Dynamic imports.
- Regex until explicitly reviewed and bounded.
- Any expression that references a metric not present in the catalog.

Null semantics:

- Arithmetic with null returns null unless wrapped in `coalesce`.
- Comparison with null returns false unless using `is_null` or `is_not_null`.
- A rule may declare required metrics. If a required metric is null and its
  metric `null_behavior` is `block_rule`, the instance becomes `blocked` rather
  than false.

Example formula AST:

```json
{
  "type": "boolean",
  "op": "and",
  "args": [
    {
      "type": "compare",
      "op": "eq",
      "left": { "type": "metric_ref", "key": "unit_cost_confirmed" },
      "right": { "type": "const", "value": true }
    },
    {
      "type": "compare",
      "op": "lt",
      "left": { "type": "metric_ref", "key": "net_profit_per_unit" },
      "right": { "type": "const", "value": 0 }
    }
  ]
}
```

## Safety Rules

Required safety constraints:

- No raw SQL from admin rules.
- No Python `eval`.
- Only whitelisted metrics.
- Only whitelisted operators.
- Only whitelisted actions.
- Every generated issue must have `evidence_ledger`.
- Admin-created rules are `test_only` until published.
- External WB write actions require preview, diff, confirm, and audit.
- Negative profit cannot be shown if cost data is missing.
- Price decrease recommendations must respect `min_safe_price`.

Additional safety constraints:

- All rule versions require schema validation before save.
- All rule versions require metric coverage validation before backtest.
- All monetary calculations use decimals server-side.
- Evaluator has per-rule and per-run timeout limits.
- Evaluator records runtime errors as blocked/test errors, not user-visible
  financial advice.
- Rule publishing requires RBAC permission and audit event.
- Rules cannot lower severity/action guardrails below platform minimums.
- UI must show trust state and evidence for every instance.
- External action execution remains outside the formula evaluator.

## First Dynamic Problem Codes

### `missing_cost_blocks_profit`

Scope: product or SKU.

Impact type: `data_blocker`.

Trust state: `blocked` for live rules, `test_only` for testing rules.

Trigger sketch:

```text
unit_cost_confirmed = false
or unit_cost_effective is null
```

Required metrics:

- `unit_cost_confirmed`
- `unit_cost_effective`
- `revenue`
- `net_units`
- `stock_value`

Allowed actions:

- `FIX_COST_TRUST`
- `DATA_FIX_REQUIRED`

Evidence:

- Cost source/truth level.
- Affected revenue.
- Affected SKU/product count.
- Current missing cost fields.

### `negative_unit_profit`

Scope: product or SKU.

Impact type: `confirmed_loss` or `probable_loss`.

Trust state:

- `confirmed` when cost and finance are final.
- `provisional` when operationally trusted but finance is not final.
- `blocked` when cost is missing.

Trigger sketch:

```text
unit_cost_confirmed = true
and net_units > 0
and net_profit_per_unit < 0
```

Required metrics:

- `unit_cost_confirmed`
- `net_units`
- `net_profit_after_ads`
- `net_profit_per_unit`
- `current_discounted_price`
- `min_safe_price`

Allowed actions:

- `PRICE_INCREASE_REVIEW`
- `DO_NOT_REORDER`
- `FIX_AD_ALLOCATION`
- `MANUAL_REVIEW`

Safety:

- Must not be displayed as negative profit when cost is missing.
- If ads allocation is not final, prefer data/action review before financial
  loss copy.

### `overstock_slow_moving`

Scope: product or SKU.

Impact type: `blocked_cash`.

Trust state: `confirmed`, `provisional`, or `estimated` based on stock/cost.

Trigger sketch:

```text
available_stock_units > 0
and days_of_stock >= overstock_days_threshold
and sales_velocity_daily <= slow_velocity_threshold
```

Required metrics:

- `available_stock_units`
- `days_of_stock`
- `sales_velocity_daily`
- `stock_value`
- `min_safe_price`

Allowed actions:

- `LIQUIDATE_STOCK`
- `PRICE_DECREASE_REVIEW`
- `DO_NOT_REORDER`

Safety:

- Any price decrease action must respect `min_safe_price`.
- If `stock_value` is not computable, impact amount becomes estimated or
  blocked depending on cost trust.

### `low_stock_risk`

Scope: product or SKU.

Impact type: `lost_sales_risk`.

Trust state: `confirmed`, `provisional`, or `opportunity`.

Trigger sketch:

```text
sales_velocity_daily > 0
and days_of_stock <= low_stock_days_threshold
and net_profit_per_unit > 0
```

Required metrics:

- `available_stock_units`
- `days_of_stock`
- `sales_velocity_daily`
- `lead_time_days`
- `safety_stock_days`
- `net_profit_per_unit`
- `recommended_reorder_qty`
- `required_cash`

Allowed actions:

- `REORDER`
- `PROTECT_STOCK`

Safety:

- If profit is not computable, generate `blocked` or data-fix first rather than
  a reorder profit claim.

### `ads_spend_without_profit`

Scope: product or campaign.

Impact type: `probable_loss`.

Trust state: `confirmed`, `provisional`, or `blocked`.

Trigger sketch:

```text
ad_spend > 0
and ads_allocation_status in ["linked", "article_level_only"]
and net_profit_after_ads <= 0
```

Required metrics:

- `ad_spend`
- `ads_allocation_status`
- `net_profit_after_ads`
- `drr_percent`
- `attributed_revenue`

Allowed actions:

- `AD_PAUSE_REVIEW`
- `FIX_AD_ALLOCATION`
- `MANUAL_REVIEW`

Safety:

- If ads allocation is unallocated or overallocated, emit data-fix action before
  pause advice.

### `promo_not_profitable`

Scope: product or promotion campaign.

Impact type: `probable_loss`.

Trust state: `provisional` until promo attribution and cost are confirmed.

Trigger sketch:

```text
promo_active = true
and unit_cost_confirmed = true
and promo_profit_after_discount < 0
```

Required metrics:

- `promo_active`
- `promo_discount_percent`
- `promo_profit_after_discount`
- `unit_cost_confirmed`
- `current_discounted_price`
- `min_safe_price`
- `promo_revenue`
- `promo_units`

Allowed actions:

- `PROMO_STOP_REVIEW`
- `PROMO_PRICE_REVIEW`
- `PRICE_INCREASE_REVIEW`

Safety:

- No external promo stop/update without preview, diff, confirm, and audit.
- Do not call it unprofitable if cost is missing.

### `price_below_safe_margin`

Scope: product or SKU.

Impact type: `probable_loss`.

Trust state: `confirmed`, `provisional`, or `blocked`.

Trigger sketch:

```text
unit_cost_confirmed = true
and current_discounted_price < min_safe_price
```

Required metrics:

- `unit_cost_confirmed`
- `current_discounted_price`
- `break_even_price`
- `target_margin_price`
- `min_safe_price`
- `safe_price_gap`

Allowed actions:

- `PRICE_INCREASE_REVIEW`
- `FIX_PRICE_MAPPING`

Safety:

- If price data is missing, generate data-fix/price mapping action instead.

### `dead_stock`

Scope: product or SKU.

Impact type: `blocked_cash`.

Trust state: `confirmed`, `provisional`, or `estimated`.

Trigger sketch:

```text
available_stock_units > 0
and sales_velocity_daily = 0
and days_since_last_sale >= dead_stock_days_threshold
```

Required metrics:

- `available_stock_units`
- `sales_velocity_daily`
- `days_since_last_sale`
- `stock_value`
- `min_safe_price`

Allowed actions:

- `LIQUIDATE_STOCK`
- `PRICE_DECREASE_REVIEW`
- `CARD_CONTENT_REVIEW`
- `MANUAL_REVIEW`

Safety:

- Price decrease must respect `min_safe_price`.
- If stock value depends on missing cost, impact must be estimated or blocked.

### `fast_stock_depletion`

Scope: product or SKU.

Impact type: `lost_sales_risk`.

Trust state: `confirmed`, `provisional`, or `opportunity`.

Trigger sketch:

```text
sales_velocity_daily >= fast_velocity_threshold
and projected_stockout_days < lead_time_days + safety_stock_days
```

Required metrics:

- `sales_velocity_daily`
- `available_stock_units`
- `projected_stockout_days`
- `lead_time_days`
- `safety_stock_days`
- `recommended_reorder_qty`
- `required_cash`
- `net_profit_per_unit`

Allowed actions:

- `REORDER`
- `PROTECT_STOCK`

Safety:

- If unit economics are missing, show as opportunity/protection only, not as
  confirmed profit.

## Target Database Model

Table: `problem_metric_catalog`

```text
id
key unique
label
description
scope
value_type
unit
grain
source_module
source_endpoint
source_table
resolver
nullable
null_behavior
trust_strategy
allowed_scopes jsonb
allowed_aggregates jsonb
data_freshness_ttl_seconds
version
status
owner
created_at
updated_at
```

Table: `problem_definitions`

```text
id
code unique
title
description
scope
impact_type
default_severity
default_priority
status
owner_team
visibility
dedupe_strategy
cooldown_hours
tags jsonb
active_version_id nullable
created_by_user_id
updated_by_user_id
created_at
updated_at
archived_at nullable
```

Table: `problem_rule_versions`

```text
id
definition_id
version
status
formula_ast jsonb
formula_text
precondition_ast jsonb nullable
severity_ast jsonb nullable
priority_ast jsonb nullable
impact_amount_ast jsonb nullable
confidence_ast jsonb nullable
required_metrics jsonb
required_actions jsonb
recheck_policy jsonb
entity_selector jsonb
window_config jsonb
thresholds jsonb
copy_template jsonb
evidence_template jsonb
validation_report jsonb
published_by_user_id nullable
published_at nullable
change_note nullable
created_at
updated_at
```

Unique index: `(definition_id, version)`.

Table: `problem_instances`

```text
id
definition_id
rule_version_id
problem_code
entity_scope
account_id
nm_id nullable
sku_id nullable
campaign_id nullable
source_entity_id nullable
status
trust_state
impact_type
severity
priority
confidence
title
summary
business_reason
next_step
impact_amount numeric nullable
impact_currency nullable
dedupe_key unique
formula_result jsonb
evidence_ledger jsonb not null
allowed_actions jsonb
selected_action jsonb nullable
recheck_at nullable
resolved_at nullable
dismissed_at nullable
created_by_run_id
last_seen_run_id
first_seen_at
last_seen_at
created_at
updated_at
```

Recommended indexes:

- `(account_id, status, priority)`
- `(account_id, nm_id, status)`
- `(account_id, sku_id, status)`
- `(problem_code, status)`
- `(recheck_at) where status in ('done', 'in_progress', 'blocked')`

Table: `problem_instance_events`

```text
id
problem_instance_id
event_type
from_status nullable
to_status nullable
comment nullable
payload jsonb
created_by_user_id nullable
created_at
```

Table: `problem_engine_runs`

```text
id
run_type live, shadow, backtest, manual_recheck
account_id nullable
definition_id nullable
rule_version_id nullable
date_from nullable
date_to nullable
status
started_at
finished_at nullable
evaluated_count
created_count
updated_count
resolved_count
blocked_count
error_count
error_report jsonb
created_by_user_id nullable
```

Table: `problem_backtest_runs`

```text
id
definition_id
rule_version_id
account_id nullable
date_from
date_to
status
sample_size
evaluated_entity_count
triggered_count
blocked_count
estimated_total_impact
severity_distribution jsonb
priority_distribution jsonb
trust_distribution jsonb
metric_coverage_report jsonb
top_examples jsonb
runtime_ms
created_by_user_id
created_at
```

Table: `problem_action_templates`

```text
id
action_code unique
action_group
label
description
external_write
requires_preview
requires_diff
requires_confirm
requires_audit
allowed_scopes jsonb
route_template
payload_schema jsonb
status
created_at
updated_at
```

## Target Backend Modules

Suggested package:

```text
backend/app/modules/problem_engine/router.py
backend/app/schemas/problem_engine.py
backend/app/models/problem_engine.py
backend/app/services/problem_engine/catalog.py
backend/app/services/problem_engine/compiler.py
backend/app/services/problem_engine/evaluator.py
backend/app/services/problem_engine/metric_resolvers.py
backend/app/services/problem_engine/engine.py
backend/app/services/problem_engine/backtest.py
backend/app/services/problem_engine/evidence.py
backend/app/services/problem_engine/actions.py
backend/app/services/problem_engine/integration.py
```

Service responsibilities:

- `catalog.py`: CRUD/read model for metric catalog and action templates.
- `compiler.py`: validates AST, extracts metric/action dependencies, rejects
  unsafe expressions.
- `evaluator.py`: pure safe expression evaluator.
- `metric_resolvers.py`: backend-owned metric loading from existing Money,
  Control Tower, Pricing, Ads, Stock, Costs, DQ, and Portal services.
- `engine.py`: live/shadow runs, idempotency, instance upsert, re-check.
- `backtest.py`: preview/backtest runs and sample generation.
- `evidence.py`: evidence ledger construction and validation.
- `actions.py`: action mapping and route/payload rendering.
- `integration.py`: adapters to Portal Action Center, Product 360, Money, and
  legacy `ActionRecommendation` compatibility.

## Target APIs

Admin APIs:

```text
GET    /problem-engine/metrics
GET    /problem-engine/actions/templates
GET    /problem-engine/definitions
POST   /problem-engine/definitions
GET    /problem-engine/definitions/{id}
PATCH  /problem-engine/definitions/{id}
POST   /problem-engine/definitions/{id}/versions
GET    /problem-engine/definitions/{id}/versions
POST   /problem-engine/rules/validate
POST   /problem-engine/definitions/{id}/versions/{version}/backtest
GET    /problem-engine/backtests/{id}
POST   /problem-engine/definitions/{id}/versions/{version}/publish
POST   /problem-engine/definitions/{id}/pause
POST   /problem-engine/definitions/{id}/archive
```

Runtime APIs:

```text
POST   /problem-engine/run
POST   /problem-engine/recheck
GET    /problem-engine/instances
GET    /problem-engine/instances/{id}
PATCH  /problem-engine/instances/{id}
POST   /problem-engine/instances/{id}/recheck
GET    /problem-engine/instances/{id}/evidence
GET    /problem-engine/products/{nm_id}/instances
GET    /problem-engine/action-center
```

Compatibility integration:

- Product 360 can include dynamic instances in `PortalProduct360Read.actions`
  and optionally a new `problems` or `dynamic_problems` section.
- Action Center can consume dynamic instances as `PortalActionRead` with
  `source_module="problem_engine"` and `source_id=problem_instance.id`.
- Money pages can keep using existing action shapes while dynamic instances are
  shadowed into `NextActionRead`/Portal action adapters.

## Engine Runtime Flow

1. Load active definitions and active rule versions.
2. For each rule, resolve the entity universe from `entity_selector`.
3. Batch-load required metrics through Metric Catalog resolvers.
4. Validate metric coverage and source freshness.
5. Evaluate precondition AST.
6. Evaluate trigger formula AST.
7. If true, calculate severity, priority, impact amount, confidence, trust, and
   rendered copy.
8. Build and validate evidence ledger.
9. Apply safety guardrails.
10. Generate stable dedupe key.
11. Upsert `problem_instances`.
12. Schedule re-check.
13. Emit instance events and run summary.
14. Expose instances to Portal/Product 360/Action Center adapters.

Dedupe key recommendation:

```text
account_id + problem_code + rule_version_major_identity + entity_scope +
entity_id + metric_signature_bucket
```

Use a stable metric signature bucket only when a materially different problem
should generate a new instance. Otherwise update the existing instance.

## Admin UI Requirements

Metric catalog screen:

- Search/filter metrics by source module, scope, unit, trust, and status.
- Show metric description, source, null behavior, sample values, and examples.

Problem definition editor:

- Create/edit definition shell.
- Select scope, impact type, default priority/severity, visibility, actions.
- Build formulas from metric chips, operators, constants, and thresholds.
- Show validation errors inline.
- Show required metrics/actions extracted from the AST.

Backtest/preview screen:

- Pick account/date window/sample size.
- Run preview.
- Show counts, distributions, top examples, blocked cases, and evidence.
- Compare new rule output with current hardcoded source when available.

Publish workflow:

- Require successful validation and backtest.
- Require change note.
- Show diff from previous version.
- Require publish permission.
- Record audit event.

Runtime/problem review:

- Product 360 shows dynamic problems by product with evidence.
- Action Center shows mapped actions and status controls.
- Evidence drawer shows formula, metric values, sources, trust, and guardrails.

## Product 360 Integration

Product 360 should display dynamic problems as first-class product signals:

- `dynamic_problems`: list of open problem instances scoped to `nm_id`.
- `next_best_action`: may be selected from highest-priority open instance.
- Existing `actions` section includes action-adapted instances.
- Each problem/action includes evidence and money trust.

Product 360 display fields:

```text
problem_code
title
summary
status
trust_state
impact_type
severity
priority
impact_amount
selected_action
evidence_ledger
recheck_at
```

## Action Center Integration

Action Center should treat dynamic problem instances as a source module:

```text
source = "dynamic_problem_engine"
source_module = "problem_engine"
source_id = problem_instance.id
action_type = selected_action.action_code
title = problem_instance.title
reason = problem_instance.summary
next_step = problem_instance.next_step
priority = problem_instance.priority
severity = problem_instance.severity
status = mapped instance status
expected_effect_amount = impact_amount
trust_state = problem_instance.trust_state
evidence_ledger = problem_instance.evidence_ledger
guided_fix = selected_action.route/payload
```

Status updates from Action Center should update `problem_instances.status` and
append `problem_instance_events`.

## Migration Plan

Phase 1: foundation

- Add models, schemas, metric catalog seed data, safe evaluator, validation, and
  admin-only APIs.
- No live UI behavior changes.

Phase 2: shadow definitions

- Seed the first dynamic problem definitions in `testing`.
- Run backtests and shadow engine runs.
- Compare dynamic output with current hardcoded actions/cards.

Phase 3: read integration

- Add dynamic problem instances to Product 360 and Action Center behind a
  feature flag or admin-only visibility.
- Keep existing hardcoded cards as primary.

Phase 4: controlled cutover

- Promote validated definitions to `active`.
- Route selected old hardcoded sources through dynamic definitions.
- Preserve existing response fields and adapters.

Phase 5: cleanup

- Remove duplicated frontend fallback classifiers.
- Retire hardcoded backend problem creation after parity and acceptance.

## Testing Requirements

Backend unit tests:

- Metric catalog validation.
- AST schema validation.
- Unsafe expression rejection.
- Evaluator arithmetic, boolean, null, and type behavior.
- Required metric extraction.
- Action whitelist validation.
- Evidence ledger required fields.
- Trust state derivation.
- Safety guardrails.

Backend integration tests:

- Engine run creates/upserts instances idempotently.
- Re-check resolves/blocks instances correctly.
- Backtest produces preview examples without live instances.
- Publish workflow requires validation, backtest, permission, and audit.
- Product 360 adapter includes dynamic problems.
- Action Center adapter updates instance status.
- Legacy response compatibility for mapped actions.

Frontend tests:

- Metric catalog browsing.
- Formula builder validation states.
- Backtest preview and evidence drawer.
- Publish diff/confirm flow.
- Product 360 dynamic problem rendering.
- Action Center status update for dynamic instances.
- Guardrail copy for blocked/test-only/estimated instances.

Security tests:

- SQL strings are rejected.
- Python/JavaScript-like expressions are rejected.
- Unknown metrics/operators/actions are rejected.
- External write action cannot execute without preview/diff/confirm/audit.
- Admin-created rules remain `test_only` before publish.

## Open Decisions

- Whether to keep dynamic problem instances separate from existing
  `ActionRecommendation`, or create a bridge table for gradual migration.
- Whether `definition.status=testing` should be runnable for all admins or only
  definition owners.
- Whether formulas should be authored only through a visual builder or also as
  text compiled into AST.
- How much historical metric materialization is needed for fast backtests.
- Whether promo attribution should be added to Metric Catalog before
  `promo_not_profitable` can be published live.

## Acceptance Check

- This document defines the concepts needed for DB models, backend services,
  frontend UI, and tests.
- It includes required statuses, trust states, impact types, first problem
  codes, and safety rules.
- It does not change product behavior.
