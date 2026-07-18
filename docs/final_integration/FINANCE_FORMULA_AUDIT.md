# Finance Formula Audit

Generated as a static/runtime-gated report on 2026-06-25.

## Static Audit Result

The codebase already contains a substantial Finance calculation layer:

- centralized expense taxonomy;
- manual cost unit formulas;
- mart refresh and DQ checks;
- money summary/detail builders;
- profit cascade validation;
- trust/finality separation for provisional versus financial-final results.

The main visible formula invariant is implemented in `MoneyManagementService._build_profit_cascade()`:

```text
expected_profit =
  gross_revenue
  - seller_cogs
  - seller_other_expense
  - total_wb_expenses
  - ad_spend_final
  + additional_income
```

Validation passes when expected profit and reported net profit differ by no more than `0.01`.

## Existing Regression Evidence

Discovered tests cover:

- profit cascade invariant and WB child/group deltas;
- null/zero money-card behavior;
- margin and ROI zero-denominator guards;
- return rate calculation;
- stock value rendering;
- seller costs excluding WB logistics;
- manual cost formula `cost_price + seller_other_expense`;
- normalized expense category mapping;
- ad double-count risk;
- negative unexpected expense DQ issue;
- large logistics share DQ issue;
- finance reconciliation blocker metadata.

Representative files:

- `backend/tests/unit/test_money_management_service.py`
- `backend/tests/unit/test_etap3_money_acceptance.py`
- `backend/tests/unit/test_marts_and_quality.py`
- `backend/tests/unit/test_dashboard_service.py`
- `backend/tests/unit/test_control_tower_service.py`

## Runtime Audit Not Completed

This pass did not connect to the configured PostgreSQL database. Therefore these Section 03 requirements remain blocked:

- recompute real DB revenue;
- recompute real DB `for_pay`;
- recompute real DB WB expenses;
- recompute real DB COGS;
- recompute real DB ads spend;
- recompute real DB profit/margin/ROI;
- recompute real DB return metrics;
- recompute real DB stock value/days of stock;
- recompute product `nm_id=245405620`;
- recompute at least 20 sample products.

## Runtime Recalculation Plan

For a chosen account and date window:

1. Pull source rows from realization report, marts, manual costs, ads, stock, orders/sales.
2. Recompute account summary with Decimal arithmetic.
3. Recompute product `nm_id=245405620`.
4. Select at least 20 additional active products across revenue/profit/cost states.
5. Compare recomputed values to API outputs:
   - `/money/summary`
   - `/money/profit-cascade`
   - `/money/articles/{nm_id}`
   - `/portal/products/{nm_id}`
6. Mark each metric as `pass`, `warning`, `blocked`, or `fail`.

## Runtime SQL Skeleton

Use exact table/column names from migrations/models for the deployed DB.

```sql
-- Account/product sample frame
select account_id, nm_id, sum(finance_revenue) as revenue
from mart_sku_daily
where account_id = :account_id
  and stat_date between :date_from and :date_to
group by account_id, nm_id
order by revenue desc nulls last
limit 25;

-- Finance report cross-check
select account_id, nm_id, sum(retail_amount) as retail_amount, sum(for_pay) as for_pay
from wb_realization_report_rows
where account_id = :account_id
  and rr_date between :date_from and :date_to
group by account_id, nm_id;

-- Sync freshness context
select account_id, domain, status, max(finished_at) as latest_finished_at
from wb_sync_runs
where account_id = :account_id
group by account_id, domain, status;
```

## Audit Checklist

| Check | Static Status | Runtime Status |
| --- | --- | --- |
| Revenue source precedence documented | pass | needs DB |
| `for_pay` visible and auditable | pass | needs DB |
| WB expenses categorized | pass | needs DB |
| Marketing deduction avoids ad double count | pass | needs DB |
| COGS includes seller other expense | pass | needs DB |
| WB logistics excluded from seller costs | pass | needs DB |
| Profit cascade invariant implemented | pass | needs DB |
| Margin denominator is revenue | pass | needs DB |
| ROI denominator is COGS | pass | needs DB |
| Percent denominator zero guard | pass | needs DB |
| Return rate formula covered | pass | needs DB |
| Stock value formula covered | pass | needs DB |
| Date boundary/timezone verified | partial | needs DB |
| Duplicate report rows verified | partial | needs DB |
| Article/SKU allocation verified | partial | needs DB |
| Negative amount behavior verified | partial | needs DB |
| Provisional/final distinction present | pass | needs DB |

## Follow-Up Fix Targets

Only after real DB recomputation:

- fix any formula mismatch larger than `0.01` for money totals;
- add a focused test for each mismatch;
- update the metric dictionary if business formula differs from the current code;
- preserve provisional/final trust states when data is incomplete rather than forcing fake final zeroes.
