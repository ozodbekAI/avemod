# Dynamic Problem Legacy Migration Map

This document records the current migration stance for hardcoded seller-facing
business/product alerts. Dynamic problem instances take precedence when they
exist for the same `(account_id, nm_id, problem_code)`. Legacy cards remain as
fallback only while `show_legacy_problem_cards=true`.

## Feature Flags

- `dynamic_problem_engine_enabled`: global kill switch for dynamic problem
  generation and portal display.
- `dynamic_problem_engine_test_account_ids`: optional rollout allowlist. When
  non-empty, only these accounts receive dynamic problem generation/display.
- `show_legacy_problem_cards`: keeps mapped legacy problem cards as fallback.
  When false, mapped legacy problem cards are hidden even if no dynamic issue
  exists.

## Migration Rules

| Area | Legacy hardcoded source | Dynamic problem code | Disposition |
| --- | --- | --- | --- |
| Money / profit doctor | `profit_leak`, negative profit copy, price/profit review actions | `negative_unit_profit` | Dynamic takes precedence; legacy fallback only. |
| Money / costs | `cost_missing`, `missing_manual_cost`, cost blocker cards | `missing_cost_blocks_profit` | Dynamic/Data Fix bridge takes precedence; legacy fallback only. |
| Money / stock | `frozen_stock`, `overstock`, `LIQUIDATE_STOCK`, discount-to-clear copy | `overstock_slow_moving` | Dynamic takes precedence; legacy fallback only. |
| Money / stock | `stock_risk`, `low_stock`, reorder/restock copy | `low_stock_risk` | Dynamic takes precedence; legacy fallback only. |
| Money / ads | `ads_eating_profit`, `ADS_REVIEW`, ad spend/profit review copy | `ads_spend_without_profit` | Dynamic takes precedence; legacy fallback only. |
| Pricing | `PRICE_INCREASE_REVIEW`, `safe_price_gap`, price below target/break-even copy | `price_below_safe_margin` | Dynamic definition/rule is seeded; legacy fallback only while rollout stabilizes. |
| Promo | promo review/safe promo/discount risk copy | `promo_not_profitable` | Dynamic definition/rule is seeded; legacy fallback only while rollout stabilizes. |
| Stock | dead stock labels | `dead_stock` | Dynamic definition/rule is seeded; legacy fallback only while rollout stabilizes. |
| Stock | fast depletion labels | `fast_stock_depletion` | Dynamic definition/rule is seeded; legacy fallback only while rollout stabilizes. |
| Data Quality | `manual_cost_unresolved_sku` | `manual_cost_unresolved_sku` | Data Fix bridge creates dynamic instance. |
| Data Quality | `manual_cost_ambiguous_match` | `manual_cost_ambiguous_match` | Data Fix bridge creates dynamic instance. |
| Data Quality | `unmatched_sku` | `unmatched_sku` | Data Fix bridge creates dynamic instance. |
| Data Quality | `expense_unclassified`, `unclassified_finance_expense` | `expense_unclassified` | Data Fix bridge creates dynamic instance. |
| Data Quality | `finance_reconciliation_mismatch` | `finance_reconciliation_mismatch` | Data Fix bridge creates dynamic instance; system/admin issue. |
| Data Quality | `sale_without_finance` | `sale_without_finance` | Data Fix bridge creates dynamic instance; system wait issue. |
| Data Quality | `finance_without_sale` | `finance_without_sale` | Data Fix bridge creates dynamic instance; system wait issue. |
| Checker / card quality | checker/card quality field issues | none yet | Legacy/internal card-quality workflow; not migrated to business problem engine until metric/rule parity exists. |
| Product 360 | product-level legacy action rows from money, DQ, costs, checker, stock, pricing, promo | mapped by `PortalService.LEGACY_DYNAMIC_PROBLEM_MAP` | Product Doctor shows dynamic first, legacy fallback only. |
| Action Center | unified legacy action rows and generated profit doctor rows | mapped by `PortalService.LEGACY_DYNAMIC_PROBLEM_MAP` | Dynamic rows are canonical for status; matching legacy rows are suppressed. |

## Current Non-Removal Policy

No legacy generator is deleted in this migration step. The portal/action layer is
the compatibility boundary:

1. Dynamic problem rows are loaded when the rollout flag allows it.
2. Matching legacy rows are hidden when a dynamic row exists.
3. If dynamic rows are unavailable and legacy fallback is enabled, mapped legacy
   rows remain visible.
4. If `show_legacy_problem_cards=false`, mapped legacy rows are hidden.
