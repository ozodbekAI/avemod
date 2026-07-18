# Finance Metric Dictionary

Generated from Section 03 static formula audit on 2026-06-25.

## Source Of Truth

Primary source is Finance PostgreSQL. WB API is not a calculation source except through persisted sync tables and raw response snapshots.

Main calculation files:

- `backend/app/core/expense_taxonomy.py`
- `backend/app/core/manual_cost_math.py`
- `backend/app/services/marts.py`
- `backend/app/services/dashboard.py`
- `backend/app/services/money_management.py`
- `backend/app/services/trust.py`

## Canonical Metrics

| Metric | Formula / Rule | Canonical Code | Notes |
| --- | --- | --- | --- |
| revenue | `revenue_final(source)` preference: explicit `revenue_final`, `final_revenue`, `realized_revenue`, `finance_revenue`, then `operational_revenue` | `app/core/expense_taxonomy.py` | Use signed/normalized mart revenue; final source is visible in revenue source block |
| for_pay | WB finance `for_pay` aggregated from realization reports/marts | `money_management._build_card_money` and mart services | Displayed separately from profit formula; validate against realization rows |
| WB expenses | normalized WB direct expense categories: commission, payment processing, PVZ reward, logistics, logistics rebill, storage, acceptance, penalties, deductions, loyalty, other/unclassified | `normalized_wb_expenses_total`, `_wb_expenses_total`, `_expense_components_from_profit_rows` | Marketing deduction is treated as finance-backed ad spend to avoid double counting |
| COGS | `seller_cogs + seller_other_expense`; legacy `estimated_cogs` fallback only when explicit seller fields are absent | `total_seller_costs`, `manual_cost_total_unit_cost`, `MartService._manual_cost_amounts` | Seller other expense replaces old packaging/inbound fallback when present |
| ads spend | Prefer finance report marketing deduction when present; else explicit `ad_spend_final`; else operational ads API spend; else legacy `ad_spend` | `ad_spend_finance`, `ad_spend_operational`, `ad_spend_final` | Finance-backed ad spend is final; operational allocation can be provisional |
| estimated profit | `revenue + additional_income - WB expenses - seller costs - extra ad spend not in WB expenses` | `_build_card_money`, `_build_profit_cascade` | Account summary invariant validates against `net_profit_after_all_expenses` |
| owner profit | `net_profit_after_overhead = net_profit_after_ads/source_ads - allocated account-level overhead` | `_profit_variants`, `_allocated_overhead`, summary KPI construction | Use revenue-share allocation for overhead |
| margin | `profit_after_source_ads / revenue * 100` | `_build_card_money` | Denominator is revenue, guarded to 0 when denominator <= 0 |
| ROI | `profit_after_source_ads / estimated_cogs * 100` | `_build_card_money` | Denominator is COGS, guarded to 0 when denominator <= 0 |
| average order value | revenue/orders, where available in dashboard/money blocks | money/dashboard services | Runtime DB recomputation required |
| return rate | `returns_count / sales_count * 100`; fallback can use return units/gross units | `_article_summary_block`, money list/detail builders | Existing unit coverage expects 4 returns / 25 sales = 16% |
| stock value | `stock_qty * unit_cost`; unit cost from row stock value/qty or estimated COGS/net units | `_stock_value_components` | Confidence depends on cost truth: supplier confirmed, operator baseline, placeholder, missing |
| days of stock | stock quantity / daily sales velocity, or persisted `days_of_stock` when available | `_row_sales_velocity_daily`, stock/control services | Zero/null guarded |
| money at risk | action and stock-risk money effects, including affected stock value, protected revenue, expected profit impact | `_action_from_recommendation`, control tower services | Runtime recomputation depends on action payload/source rows |

## Profit Invariant

For account-level summary:

```text
net_profit_after_all_expenses
≈ revenue
- seller_cogs
- seller_other_expense
- WB expenses
- ad_spend_final
+ additional_income
```

Allowed tolerance in current cascade validation: `0.01`.

The master prompt’s simplified invariant:

```text
estimated_profit ≈ for_pay - COGS - ads_spend - allocated_other_expenses
```

is not the only formula used by this product. Current product formula names revenue, WB expenses, seller costs, ads, additional income, and overhead separately. `for_pay` remains visible and auditable but is not the sole profit base in the canonical cascade.

## Null, Zero, Rounding, Timezone, Grain Rules

- `Decimal` is used in core formula helpers; floats are mostly output formatting.
- Null numeric inputs generally become zero in arithmetic helpers.
- Unknown/non-computable values must be represented in trust/finality/status fields rather than fake final confidence.
- Margin/ROI/percent denominators are guarded to 0 when denominator is zero or negative.
- Date windows are explicit `date_from` / `date_to`; runtime audit must confirm inclusive boundaries against DB queries.
- Finance rows and marts must be audited at the right grain: account, date, nm_id, SKU/barcode where applicable.
- Ads can be article/nm-level and allocated to SKU rows by revenue, then units, then even share.
- Returns and negative amounts must preserve sign semantics through revenue/final profit and DQ checks.

## Required Runtime Samples

Runtime Section 03 acceptance requires recomputation for:

- product `nm_id=245405620`;
- at least 20 additional sample products;
- account-level summary for the selected date window;
- both product/article and SKU grains where variants exist.
