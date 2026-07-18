# Lovable uchun frontend promptlar — Etap 3 Money Control UI/UX

**Maqsad:** frontendni chiroyli dashboard emas, biznes egasi uchun haqiqiy **pul boshqaruvi pulti** qilish.

Dastur har bir sahifada 3 ta savolga aniq javob berishi kerak:

1. **Magazinning hozirgi holati qanday? Pul qayerda va qayerga ketayapti?**
2. **Card / article qancha pul olib kelyapti, qayerga pul sarflayapti, qanchalik foydali?**
3. **Endi nima qilish kerak?**

> Muhim: frontend “hammasi yaxshi” deb yashil signal bermasligi kerak, agar backend ichida finance mismatch, supplier-confirmed cost 0%, unallocated expenses, open DQ issues, ads allocation xatosi yoki provisional profit bo‘lsa.

---

# 0. Lovable’da ishlatish tartibi

Quyidagi promptlarni Lovable’ga **birma-bir** yuboring.

Tavsiya qilinadigan tartib:

1. **Prompt 1 — Global UI/data rules**
2. **Prompt 2 — API client va endpoint mapping**
3. **Prompt 3 — Money page**
4. **Prompt 4 — Cards / Articles list**
5. **Prompt 5 — Card / Article detail**
6. **Prompt 6 — Actions page**
7. **Prompt 7 — Data Fix page**
8. **Prompt 8 — Costs page**
9. **Prompt 9 — Ads page**
10. **Prompt 10 — Pricing / Purchase / Settings**
11. **Prompt 11 — Performance va loading UX**
12. **Prompt 12 — Final acceptance checklist**

---

# 1. GLOBAL PROMPT — asosiy product direction

```text
Refactor the frontend into a business-owner money control tower, not a complex analytics dashboard.

Main product rule:
Every page must answer one or more of these business questions:
1) What is the current store situation and where is the money?
2) Which cards/articles bring money, where do they spend money, and are they profitable?
3) What exactly should the owner do next?

Do not show a green “trusted / healthy / no risks” state if any of these are true in API data:
- finance reconciliation status is critical_mismatch / mismatch / partial;
- supplier_confirmed_revenue_coverage_percent is 0 or below 95%;
- unallocated_expenses is high;
- ads_allocation_percent is above 100% or source ads spend is not allocated correctly;
- open_issues_total is greater than 0;
- card profit_finality is provisional or blocked;
- data has open warning/error DQ issues.

Replace overly optimistic UI copy with honest business copy:
- “Business accepted data” means we can use it for operational decisions.
- “Final finance” means finance reconciliation is closed.
- “Supplier-confirmed cost” means real supplier cost is confirmed.
These are different statuses and must be displayed separately.

UI language:
Use simple business Russian/Uzbek-friendly labels. Avoid technical-only labels as the main text.
Examples:
- “Пул қаерда” / “Деньги в бизнесе”
- “Фойда тахминий” / “Прибыль предварительная”
- “Финансы не закрыты” / “Finance mismatch”
- “Что сделать сегодня”
- “Товар фойдали, лекин текшириш керак”

Keep existing authentication and layout structure. Do not remove working pages. Add improved components and endpoint mapping.
```

---

# 2. API CLIENT PROMPT — endpoint mapping va data qoidalari

```text
Create or update a central API mapping layer for the money-control frontend.

Use base URL from environment:
VITE_API_BASE_URL

All business pages must pass these query params where applicable:
- account_id
- date_from
- date_to
- limit
- offset
- search / subject_name / status filters when needed

Important endpoint mapping:

1) Money dashboard:
Preferred:
GET /api/v1/money/summary?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
Fallback if /money/summary is not available:
GET /api/v1/dashboard/owner
GET /api/v1/dashboard/data-health
GET /api/v1/balance
GET /api/v1/marts/account-expense-daily

2) Cards / articles list:
Preferred:
GET /api/v1/money/articles?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}&limit={limit}&offset={offset}
Fallback:
GET /api/v1/skus?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
But default UI must be grouped by nm_id/article, not raw sku/size.

3) Article detail:
Preferred:
GET /api/v1/money/articles/{nm_id}?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
Fallback:
GET /api/v1/dashboard/article-audit?account_id={accountId}&nm_id={nmId}&date_from={dateFrom}&date_to={dateTo}

4) SKU detail:
GET /api/v1/skus/{sku_id}?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
GET /api/v1/core-sku/{sku_id}?date_from={dateFrom}&date_to={dateTo}

5) Actions:
Preferred:
GET /api/v1/money/actions?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}&group_by=article&limit={limit}&offset={offset}
Fallback:
GET /api/v1/actions?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}&limit={limit}&offset={offset}
Update action:
PATCH /api/v1/actions/{action_id}

6) Data Fix:
Preferred:
GET /api/v1/money/data-blockers?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
Fallback:
GET /api/v1/dashboard/data-health?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
GET /api/v1/dq/issues?account_id={accountId}&only_open=true&date_from={dateFrom}&date_to={dateTo}

7) Costs:
GET /api/v1/costs/rows?account_id={accountId}&limit={limit}&offset={offset}
GET /api/v1/costs/imports
GET /api/v1/costs/unresolved?account_id={accountId}
GET /api/v1/costs/template?account_id={accountId}
POST /api/v1/costs/upload
GET /api/v1/costs/uploads/{upload_id}/preview
POST /api/v1/costs/uploads/{upload_id}/confirm
PATCH /api/v1/costs/{cost_id}

Important: costs/template returns CSV, not xlsx. Download it as .csv.

8) Ads:
GET /api/v1/ads/efficiency?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}&limit={limit}&offset={offset}
GET /api/v1/ads/stats?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
GET /api/v1/ads/campaigns?account_id={accountId}

9) Pricing:
GET /api/v1/pricing/safety?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}&limit={limit}&offset={offset}
POST /api/v1/pricing/simulate

10) Purchase plan:
GET /api/v1/inventory/purchase-plan?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}&limit={limit}&offset={offset}

11) Settings:
GET /api/v1/settings/business?account_id={accountId}
PATCH /api/v1/settings/business?account_id={accountId}
Important: use PATCH, not PUT.

12) Finance / reconciliation:
GET /api/v1/finance/report-rows?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
GET /api/v1/marts/finance-reconciliation?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
GET /api/v1/marts/account-expense-daily?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}

Data display rules:
- 0 means real zero only if API confirms the metric is computable.
- null / undefined means “not computed” or “data unavailable”. Show “Не рассчитано”, not “0 ₽”.
- If a metric has finality/confidence/trust_state, always show it.
- If supplier-confirmed cost is 0%, do not show profit as final.
- If finance mismatch exists, show profit as provisional.
- If unallocated expenses exist, show owner-level profit separately.
```

---

# 3. MONEY PAGE PROMPT — `/money`

```text
Rebuild the /money page as the main owner cockpit.

The top of the page must answer:
“What is the current store situation and where is the money?”

Use GET /api/v1/money/summary if available.
Fallback to dashboard/data-health + dashboard/owner + balance + account-expense-daily.

Page structure:

1) Top status banner
Show 3 separate statuses:
- Business accepted data: yes/no
- Final finance: matched / provisional / critical mismatch
- Cost trust: supplier-confirmed / operator baseline / missing

Do not show only one green “trusted” badge.
If finance mismatch or supplier-confirmed coverage is low, show warning:
“Операционные решения можно принимать, но финальная прибыль предварительная.”

2) Main KPI row
Show:
- Revenue
- Finance-confirmed revenue
- Difference amount and difference percent
- Profit after ads
- Owner profit after overhead/unallocated expenses
- Margin after ads
- Margin after overhead
- WB balance
- Stock value
- Overstock value
- In transit value
- Ads spend
- Unallocated expenses

If owner_profit_after_overhead is not returned, compute only for display:
owner_profit_after_overhead = net_profit_after_ads - unallocated_expenses
and mark as “estimated”.

3) Money waterfall
Create a simple waterfall block:
Revenue
- COGS
- Direct WB expenses
- Ads spend
= Card-level profit
- Unallocated/account-level expenses
= Owner-level estimated profit

4) Risk summary
Show business risks, not only data blockers:
- finance mismatch amount / percent
- supplier-confirmed cost coverage
- unallocated expenses
- ads allocation status
- overstock value
- negative profit cards/SKUs
- open data issues
- critical/warning issue count

If critical_count is 0 but finance mismatch exists, do not write “critical risks yo‘q”. Instead write:
“Global blocker yo‘q, lekin moliyaviy risklar bor.”

5) Top cards
Show top cards by:
- profit after ads
- owner profit after overhead
- overstock value
- finance mismatch
- ads spend risk

Default must be article/nm_id level.

6) Today’s next steps
Show top 10 grouped actions only.
Each action card must include:
- action type
- card title / nm_id
- why this action matters
- expected effect amount
- confidence
- deadline if exists
- button to open card
- button to mark done / snooze if backend supports it

Important UI copy:
Replace “Данные магазина готовы для управления деньгами” with conditional copy:
- If everything final: “Данные готовы для управления и финальная прибыль подтверждена.”
- If operational but provisional: “Операционно можно управлять, но финальная прибыль предварительная.”
- If blocked: “Сначала исправьте данные, бизнес-рекомендации ограничены.”
```

---

# 4. CARDS / ARTICLES PAGE PROMPT — `/cards`

```text
Rebuild /cards as an article-level money page.

Business definition:
A “card” for the owner means WB article / nm_id, not raw SKU/size/barcode.
Default page must show one row per nm_id.
Size/SKU breakdown must be inside card detail, not the default list.

Use:
GET /api/v1/money/articles?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
Fallback:
GET /api/v1/skus and group by nm_id on frontend only if /money/articles is unavailable.

Top counters must be split into:
- Economically profitable: profit_after_ads > 0
- Final profitable: profit_finality = final and profit > 0
- Economically loss-making
- Final loss-making
- Provisional
- Data fix required

Do not show “Прибыльных 0 / Убыточных 0” if API has economic profit/loss data.
If only provisional data exists, show:
“Фойдали кўринаётган: N” and “Финал тасдиқланган: 0/N”.

Table columns:
- Card title
- nm_id
- vendor_code
- subject_name
- revenue
- finance-confirmed revenue
- finance difference %
- profit after ads
- owner profit after overhead if available
- margin after ads
- ROI on COGS
- ad spend
- DРР
- stock value
- days of stock
- overstock value
- cancel rate
- return rate
- profit finality
- recommended next step

Filters:
- search
- subject_name
- business verdict / status
- profit_finality: final / provisional / blocked
- cost_finality
- finance_finality
- action type
- only overstock
- only ads risk
- only finance mismatch
- only loss-making

Row UI:
Use status badges:
- FINAL
- PROVISIONAL
- DATA FIX FIRST
- FINANCE MISMATCH
- SUPPLIER COST NOT CONFIRMED
- ADS RISK
- OVERSTOCK
- REORDER RISK

Clicking a row opens /cards/{nm_id}.
```

---

# 5. CARD DETAIL PROMPT — `/cards/:nmId`

```text
Rebuild card detail page around one question:
“Bu card bizga pul olib kelyaptimi va endi nima qilish kerak?”

Use:
GET /api/v1/money/articles/{nm_id}?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
Fallback:
GET /api/v1/dashboard/article-audit?account_id={accountId}&nm_id={nmId}&date_from={dateFrom}&date_to={dateTo}

Top section:
- product/card identity: title, nm_id, vendor_code, brand, subject
- main verdict: profitable / loss / provisional / data blocked
- main next step: one clear business action
- confidence/finality badge

If finance mismatch or supplier cost is not confirmed, show this banner:
“Bu card foydali ko‘rinmoqda, lekin final emas. Sabab: finance mismatch yoki supplier-confirmed cost yo‘q. Qarorni ehtiyotkorlik bilan qabul qiling.”

Required blocks:

1) Money answer
Show:
- revenue
- finance-confirmed revenue
- finance difference amount and percent
- for_pay
- COGS
- direct WB expenses
- ads spend
- profit before ads
- profit after ads
- allocated overhead if returned
- owner profit after overhead if returned
- margin
- ROI
- DРР

2) Price safety
Show:
- current price
- current discounted price
- average sale price
- break-even price
- target margin price
- safe price gap
- estimated_margin_at_current_price
If break-even or target price is null, show “Не рассчитано” and reason, not 0.

3) Stock and purchase
Show:
- total stock
- stock value
- in transit
- in way to client/from client
- days of stock
- sales velocity
- overstock risk
- out-of-stock risk
- recommended qty
- required cash only if action is reorder
For liquidation action, do not show required_cash. Show affected_stock_value and expected_cash_release.

4) Ads
Show:
- spend
- views
- clicks
- orders
- CTR if available
- CPC if available
- DРР
- profit after ads
- verdict: scale / review / pause / no data

5) Funnel
Show:
- opens
- carts
- orders
- buyouts
- cancels
- conversion rates
- cancel rate
- return rate
Important: cancel_rate must be one consistent value. If API returns conflicting cancel rates, show warning and use operations cancel rate.

6) Reconciliation
Show:
- mart revenue
- finance report revenue
- difference amount
- difference ratio
- pending/warning/error count
- root cause if available

7) SKU / size breakdown
List size/SKU rows inside detail:
- sku_id
- barcode
- size
- stock
- days_of_stock
- revenue
- profit
- recommended size-level action

8) Issues
List open DQ issues for this nm_id/SKU:
- issue code
- severity
- business meaning
- button to open Data Fix page filtered by this issue

At the bottom show “Decision block”:
- Do now
- Do later
- Do not do
- Data to fix first
```

---

# 6. ACTIONS PAGE PROMPT — `/actions`

```text
Rebuild /actions into “Today’s business work”, not a huge technical issue table.

Use:
GET /api/v1/money/actions?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}&group_by=article&limit=20
Fallback:
GET /api/v1/actions?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}

Page structure:

1) Top summary
Show:
- Top actions today
- raw actions count
- grouped actions count
- critical/high/medium/low count
- money saving actions
- growth actions
- data fix actions
- watch actions

2) Top-10 section first
Show only 10 most important grouped actions by default.
Group by:
(nm_id + action_type)
Do not show duplicate size-level actions first.

3) Action cards
Each action card must include:
- business action title
- card title and nm_id
- action type
- priority
- reason in simple language
- expected effect amount
- affected stock value, if liquidation
- required cash, only if reorder
- confidence
- trust/finality
- deadline
- buttons: Open card, Mark done, Snooze, Ignore

4) Action wording rules
Avoid technical-only titles like “RECONCILIATION_REVIEW”.
Convert to business labels:
- RECONCILIATION_REVIEW -> “Проверить расхождение WB-отчёта”
- DATA_FIX_REQUIRED -> “Сначала исправить данные”
- LIQUIDATE_STOCK -> “Распланировать распродажу остатка”
- REORDER -> “Дозаказать товар”
- DO_NOT_REORDER -> “Не закупать повторно”
- PRICE_REVIEW -> “Проверить цену”
- AD_REVIEW -> “Проверить рекламу”

5) Full list secondary
Below Top-10, add expandable “All actions” table with filters.
Do not force owner to look at thousands of actions first.
```

---

# 7. DATA FIX PAGE PROMPT — `/data-fix`

```text
Rebuild /data-fix so it separates global blockers from open warnings/issues.

Use:
GET /api/v1/money/data-blockers?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
Fallback:
GET /api/v1/dashboard/data-health?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
GET /api/v1/dq/issues?account_id={accountId}&only_open=true&date_from={dateFrom}&date_to={dateTo}

Top text must not say “no problems” when open_issues_total > 0.
Correct copy:
- If blockers = 0 but open issues exist:
“Global blocker yo‘q — biznes actionlar mumkin. Lekin N ta open data issue bor, final profit ishonchini pasaytiradi.”
- If blockers exist:
“Business actionlar cheklangan. Avval quyidagi blockerlarni yoping.”

Page blocks:

1) Global readiness
- business_trusted
- trust_state
- can_generate_business_actions
- blocked_reasons

2) Open issue summary
Show issue buckets:
- code
- severity
- count
- business meaning
- recommended fix

3) Top issue groups
Examples:
- finance_reconciliation_mismatch -> “Finance/mart revenue mos emas”
- order_without_sale_or_return -> “Order follow-up yo‘q”
- sales_without_stock -> “Sotuv bor, stock snapshot yo‘q”
- stock_without_sales -> “Qoldiq bor, sotuv yo‘q”
- missing_chrt_id -> “Size/variant mapping zaif”
- missing_manual_cost -> “Cost yo‘q”
- price_jump -> “Narx keskin o‘zgargan”

4) Issue table
Columns:
- severity
- code
- nm_id / sku_id
- message
- detected_at
- classification_status
- age_bucket
- business impact
- actions: investigate / classify / resolve / comment

5) Links
Each issue row must link to:
- card detail if nm_id exists
- SKU detail if sku_id exists
- finance reconciliation if finance issue
- costs page if cost issue

Do not hide warnings/errors just because global blocker is false.
```

---

# 8. COSTS PAGE PROMPT — `/costs`

```text
Rebuild Costs page so it never confuses “cost exists” with “supplier-confirmed cost exists”.

Use:
GET /api/v1/dashboard/data-health?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
GET /api/v1/costs/rows?account_id={accountId}
GET /api/v1/costs/imports
GET /api/v1/costs/unresolved?account_id={accountId}

Top KPI cards:
- SKU cost coverage percent
- Revenue cost coverage percent
- Business accepted cost coverage percent / trusted revenue cost coverage
- Supplier-confirmed revenue coverage percent
- Missing manual cost count
- Operator baseline count
- Supplier-confirmed count

If supplier_confirmed_revenue_coverage_percent < 95, show warning:
“Себестоимость есть, но supplier-confirmed coverage паст. Прибыль для управления можно использовать, но финальная прибыль предварительная.”

Cost type badges:
- SUPPLIER CONFIRMED
- OPERATOR BASELINE
- PLACEHOLDER
- MISSING

Upload flow:
1) Download template as CSV from /costs/template.
2) Upload file through /costs/upload.
3) Show preview using /costs/uploads/{upload_id}/preview.
4) Confirm using /costs/uploads/{upload_id}/confirm.
5) After confirm, refetch data-health and costs rows.

Important: Do not label template as XLSX if API returns text/csv.

Costs table columns:
- vendor_code
- barcode
- nm_id if available
- cost_price
- packaging_cost
- inbound_logistics_cost
- total_unit_cost
- supplier
- source/truth level
- valid_from
- valid_to
- comment
- linked SKU/card
- open issue status
```

---

# 9. ADS PAGE PROMPT — `/ads`

```text
Rebuild Ads page so it starts with advertising efficiency, not raw campaign table.

Use:
GET /api/v1/ads/efficiency?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
GET /api/v1/ads/stats?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
GET /api/v1/ads/campaigns?account_id={accountId}
GET /api/v1/money/actions?account_id={accountId}&action_type=AD_REVIEW

Top KPI cards:
- total ad spend
- ad-attributed revenue if available
- orders from ads
- DРР
- profit after ads
- cards with ads loss
- cards to scale
- ads allocation status

Main table: Ad efficiency by article/card
Columns:
- nm_id
- title
- ad spend
- views
- clicks
- orders
- CTR
- CPC
- DРР
- revenue
- profit after ads
- stock status
- recommendation: scale / review / pause / no data

Show warning if:
- ads source spend exists but card profitability has zero ad spend;
- ads allocation percent > 100;
- ad spend exists but no orders;
- ad spend exists but stock is zero/out-of-stock;
- DРР > business settings threshold.

Raw campaigns table must be a secondary tab named “Campaign raw data”.
Owner first needs answer: “Which ads eat money and which ads can be scaled?”
```

---

# 10. PRICING, PURCHASE, SETTINGS PROMPT

```text
Update Pricing, Purchase Plan and Settings pages.

A) Pricing page
Use:
GET /api/v1/pricing/safety?account_id={accountId}&date_from={dateFrom}&date_to={dateTo}
POST /api/v1/pricing/simulate

Show:
- current_price
- current_discounted_price
- average_sale_price
- break_even_price
- target_margin_price
- safe_price_gap
- estimated_margin_at_current_price
- confidence
- action_hint

If price is 0 or null:
- If null: show “Не рассчитано”
- If actual 0: show “0 ₽” only if API confirms actual zero
Do not show break-even as empty without explanation.

B) Purchase Plan page
Use:
GET /api/v1/inventory/purchase-plan

Show statuses:
- REORDER
- WAIT_DATA
- DO_NOT_BUY
- LIQUIDATE
- WATCH

Columns:
- card title / nm_id
- SKU/size if size-level
- sales velocity
- available stock
- days of stock
- lead time
- safety days
- recommended qty
- required cash
- expected profit
- risk
- reason

For WAIT_DATA, show exact missing data.
For LIQUIDATE, show affected stock value, not required cash.

C) Settings page
Use:
GET /api/v1/settings/business?account_id={accountId}
PATCH /api/v1/settings/business?account_id={accountId}

Important: use PATCH, not PUT.

Fields:
- target_margin_rate
- target_roi_percent
- lead_time_days
- safety_days
- overstock_threshold_days
- oos_threshold_days
- min_profit_threshold
- ad_drr_threshold_percent
- pack_multiple
- cost_trust_policy
- issue_aging.pending_days
- issue_aging.warning_days

Explain cost_trust_policy in UI:
- supplier_only: only supplier-confirmed cost is final
- operator_baseline: operator baseline accepted for operational decisions
- mixed: mixed mode with finality badge
```

---

# 11. PERFORMANCE / LOADING UX PROMPT

```text
Improve frontend performance and loading UX.

Rules:
1) Do not call all heavy endpoints at once on page load.
2) Use cached data and React Query / SWR staleTime where possible.
3) Use one global date range and account_id state; avoid duplicate refetches.
4) Initial table limit must be 20 or 50, not 1000.
5) Debounce search inputs by 400ms.
6) Use skeleton loaders for KPI cards.
7) Show partial page if one endpoint is slow; do not block the whole page.
8) Add retry button on endpoint error.
9) Use fallback endpoints only if preferred endpoint fails or is absent.
10) Exports must show progress/loading and should not freeze the UI.

Special notes:
- /money/summary and /ads/efficiency can be heavy. Do not repeatedly refetch them.
- /costs/template can be slow and returns CSV. Trigger only on user click.
- /sync/runs can be very slow. Do not load it on main money pages.
```

---

# 12. FINAL ACCEPTANCE PROMPT — Lovable tekshirish checklist

```text
After implementing the frontend changes, verify these acceptance checks:

Money page:
- It shows business accepted vs final finance vs supplier cost status separately.
- It shows owner profit after overhead/unallocated expenses.
- It never says “critical risks yo‘q” if finance mismatch, open issues or supplier cost warning exists.
- It has a money waterfall.

Cards page:
- Default list is article/nm_id level, not raw SKU/size.
- Economic profitable and final profitable counters are separated.
- Provisional and data-blocked cards are clearly marked.

Card detail:
- Shows one clear next step.
- Shows profit before ads, after ads, and after overhead if available.
- Shows finance mismatch and cost finality.
- Shows stock, ads, funnel, price safety and reconciliation in one page.
- Cancel rate is not conflicting.

Actions page:
- Shows Top-10 grouped article-level actions first.
- Does not show thousands of duplicate size-level actions as the first view.
- Liquidation actions show affected stock value, not required cash.

Data Fix page:
- Separates global blockers from open warnings/issues.
- Shows issue buckets and business meaning.
- Links issues to card/SKU pages.

Costs page:
- Shows business accepted cost coverage and supplier-confirmed coverage separately.
- Warns if supplier-confirmed coverage is low.
- Downloads cost template as CSV.

Ads page:
- Starts from ad efficiency and money impact, not raw campaign list.
- Shows DРР, profit after ads and ads risk.

Settings page:
- Uses PATCH /settings/business, not PUT.
- Shows cost_trust_policy explanation.

General:
- 0 and null are not confused.
- Date range and account_id are passed to every relevant endpoint.
- No misleading green statuses remain.
- Each main page answers: what is happening, where is money, what should be done next.
```

---

# Lovable uchun bitta katta universal prompt

Agar bittada yuborish kerak bo‘lsa, quyidagini yuboring:

```text
Refactor the entire frontend into a WB money-management control tower for a business owner.

Do not build a complex analytics dashboard. Every page must answer:
1) What is the current store situation and where is the money?
2) Which cards/articles bring money, where do they spend money, and are they profitable?
3) What exactly should we do next?

Use these endpoint rules:
- /money/summary for /money; fallback to /dashboard/owner + /dashboard/data-health + /balance.
- /money/articles for /cards; fallback to /skus grouped by nm_id.
- /money/articles/{nm_id} for /cards/:nmId; fallback to /dashboard/article-audit.
- /money/actions or /money/actions/today for /actions; fallback to /actions.
- /money/data-blockers for /data-fix; fallback to /dashboard/data-health + /dq/issues.
- /costs/* for /costs.
- /ads/efficiency first for /ads, raw campaigns only secondary.
- /pricing/safety and /pricing/simulate for pricing.
- /inventory/purchase-plan for purchase planning.
- /settings/business GET/PATCH for settings. Use PATCH, not PUT.

Mandatory UI rules:
- Separate “business accepted data”, “final finance”, and “supplier-confirmed cost”.
- Never show green healthy/trusted state if finance mismatch, supplier-confirmed cost 0%, unallocated expenses, open DQ issues, ads over-allocation or provisional profit exist.
- Show owner profit after overhead: profit_after_ads - unallocated_expenses.
- Show money waterfall: Revenue - COGS - WB direct expenses - Ads = card-level profit - unallocated expenses = owner-level profit.
- Cards page must default to WB article / nm_id level, not raw SKU/size.
- Actions page must show Top-10 grouped article-level actions first; full list secondary.
- Data Fix page must say “global blocker yo‘q, lekin open issues bor” if blockers are zero but open_issues_total > 0.
- Costs page must show business accepted cost coverage separately from supplier-confirmed coverage.
- Ads page must show ad efficiency, DРР, profit after ads, and recommendations before raw campaign table.
- 0 and null must not be confused: null = “not computed”, 0 = real zero only if computable.

Keep existing auth and navigation. Improve existing pages: /money, /cards, /cards/:nmId, /actions, /data-fix, /costs, /ads, /pricing, /purchase-plan, /settings. Add reusable components: StatusBanner, MoneyWaterfall, RiskCard, ActionCard, FinalityBadge, CostTrustBadge, FinanceStatusBadge, MetricWithConfidence.
```
