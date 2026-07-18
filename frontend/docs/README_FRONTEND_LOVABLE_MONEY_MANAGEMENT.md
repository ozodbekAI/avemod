# README Frontend Lovable — WB Money Management UI/UX

**Maqsad:** Lovable frontend murakkab analytics platforma emas, biznes egasi uchun **pul boshqaruvi pulti** bo‘lishi kerak.

Dastur har doim 3 ta savolga javob beradi:

1. **Magazinning hozirgi holati qanday? Pul qayerda va qayerga ketayapti?**
2. **Card qancha pul olib kelyapti, qayerga pul sarflayapti va qanchalik foydali?**
3. **Endi nima qilish kerak?**

UI’da xom `trust_state`, `blocked_reasons`, `DATA_BLOCKED`, `RECONCILIATION_REVIEW` kabi texnik so‘zlar asosiy matn bo‘lib chiqmasin. Ular ichki tafsilot sifatida qoladi. Foydalanuvchi birinchi navbatda oddiy biznes javob ko‘rishi kerak.

---

## 0. Lovable uchun eng qisqa prompt

Lovable’ga quyidagi yo‘nalishni berish kerak:

```text
Build a clean WB Money Management dashboard. The product must answer 3 business questions: store money status, card profitability, and what to do next. Keep UI simple. Do not show complex analytics first. Use cards, clear verdicts, money breakdown, and next actions. If data is blocked, show exactly what must be fixed; never say everything is normal while trust_state is data_blocked. Use the backend endpoints from this README. All screens must be in Uzbek Latin with key WB terms in Russian where useful: выручка, маржа, себестоимость, реклама, остаток.
```

---

## 1. Umumiy UI prinsiplari

### 1.1. Har bir sahifada bitta asosiy javob

Har bir sahifa yuqorisida katta **Answer Card** bo‘lsin.

Misollar:

```text
Magazin holati: Data ishonchsiz, avval 4 ta blocker yopilishi kerak.
```

```text
Bu card pul olib kelyapti, lekin finance mismatch sababli foyda final emas.
```

```text
Bugungi asosiy qadam: real себестоимостьni tasdiqlash va 96 ta unmatched SKU’ni map qilish.
```

### 1.2. Fake zero ko‘rsatmaslik

Agar backend `null` qaytarsa, frontend `0 ₽` deb ko‘rsatmasin.

| Backend value | UI text |
|---|---|
| `0` | `0 ₽` |
| `null` | `Ma’lumot yo‘q` |
| `null + reason=price_not_mapped` | `Narx ulanmagan` |
| `null + reason=ads_not_allocated` | `Reklama xarajati hali ulanmagan` |

### 1.3. Data blocked bo‘lsa

Data blocked bo‘lganda:

- barcha taxminiy foyda yonida `Taxminiy` badge;
- actionlar “business action” emas, “data fix action” bo‘lib ko‘rsatiladi;
- hech qachon `Srochniy action yo‘q`, `Hammasi yaxshi`, `Normal` deb yozilmasin;
- asosiy CTA: `Blockerlarni yopish`.

### 1.4. Rang va severity

| Status | UI rang | Ma’no |
|---|---|---|
| green / success | Ishonchli, foydali, scale | Rivojlantirish mumkin |
| yellow / warning | Tekshirish kerak | Narx/reklama/qoldiq xavfi |
| red / danger | Zarar / blocker | Avval tuzatish kerak |
| blue / info | Kuzatish | Hozircha action yo‘q |
| gray / muted | Data yo‘q | Hisoblab bo‘lmadi |

### 1.5. Matn stili

Murakkab texnik so‘zlar o‘rniga biznes tili:

| Texnik | UI’da ko‘rsatish |
|---|---|
| `DATA_BLOCKED` | `Avval data tuzatish kerak` |
| `supplier_cost_coverage_below_threshold` | `Real себестоимость yetarli emas` |
| `unmatched_sku_detected` | `SKU bog‘lanmagan` |
| `latest_stocks_not_completed` | `Qoldiq sync to‘liq emas` |
| `finance_reconciliation_mismatch` | `Finance report bilan farq bor` |
| `ad_spend=0 but ads exist` | `Reklama xarajati profitga ulanmagan` |

---

## 2. Sahifalar tuzilmasi

Minimal va kuchli struktura:

| Route | Sahifa | Savol |
|---|---|---|
| `/money` | Pul boshqaruvi / Owner Dashboard | Magazin holati qanday? |
| `/cards` | Card Control Center | Qaysi card foydali, qaysi biri xavfli? |
| `/cards/:skuId` | Card Detail | Shu card bilan nima qilish kerak? |
| `/actions` | Bugungi qadamlar / Action Center | Endi nima qilish kerak? |
| `/data-fix` | Data Fix Center | Actionlar nega bloklangan va nima tuzatish kerak? |
| `/settings` | Settings | Target margin, lead time, safety days |
| `/costs` | Себестоимость | Cost import/coverage |

Qo‘shimcha eski pages bo‘lishi mumkin, lekin asosiy navigation yuqoridagi 7 sahifadan oshmasin.

---

## 3. Global layout

### 3.1. Sidebar

Sidebar tartibi:

1. **Pul boshqaruvi** `/money`
2. **Cardlar** `/cards`
3. **Bugungi qadamlar** `/actions`
4. **Data tuzatish** `/data-fix`
5. **Sebestoimost** `/costs`
6. **Sozlamalar** `/settings`

Pastda kichik admin bo‘lim:

- Sync status
- Exportlar
- Raw reports

### 3.2. Header

Header’da:

- account selector;
- date range selector: `7 kun`, `30 kun`, `90 kun`, custom;
- data trust badge;
- refresh button;
- last updated time.

Data trust badge misollari:

```text
Ishonchli
Taxminiy
Data tuzatish kerak
```

### 3.3. Global warning banner

Agar `data_trust.state = data_blocked`:

```text
⚠ Ma’lumotlar hali biznes qaror uchun to‘liq ishonchli emas.
Avval 4 ta blocker yopilishi kerak: real себестоимость, SKU mapping, stock sync, DQ issues.
[Data tuzatish sahifasiga o‘tish]
```

---

## 4. Page 1 — `/money` Pul boshqaruvi

### 4.1. Maqsad

Sahifa bitta savolga javob beradi:

```text
Magazin holati qanday? Pul qayerda va qayerga ketayapti?
```

### 4.2. API

Asosiy endpoint:

```text
GET /api/v1/money/summary?account_id=1&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
```

Vaqtincha backend yangi endpointni bermaguncha fallback:

```text
GET /api/v1/dashboard/owner
GET /api/v1/dashboard/data-health
GET /api/v1/marts/account-expense-daily
GET /api/v1/balance
GET /api/v1/actions
```

Lekin Lovable final dizayni yangi `/money/summary` response’ga mos bo‘lsin.

### 4.3. Layout

#### Block A — Answer Card

Yuqorida katta card:

```text
Magazin holati: Data ishonchsiz, foyda taxminiy.
Выручка bor, lekin reklama, stock value va real cost to‘liq ulanmagan.
Bugungi asosiy qadam: real себестоимость va SKU mapping’ni yopish.
```

Elementlar:

- status badge;
- title;
- short_text;
- main_next_step;
- CTA: `Bugungi qadamlarni ko‘rish`;
- CTA: `Data blockerlarni yopish`.

#### Block B — KPI cards

Grid 2x4 yoki 4x2:

1. **Выручка**
2. **Sof foyda** / `Taxminiy foyda`
3. **Marja**
4. **WB balans**
5. **Tovarda muzlagan pul**
6. **Reklama xarajati**
7. **WB xarajatlari**
8. **Data blockerlar**

Har bir KPI’da:

- amount;
- confidence badge;
- tooltip: qayerdan hisoblangan;
- agar null: `Hisoblanmadi` + reason.

#### Block C — Pul oqimi

Oddiy flow cards:

```text
Sotuvdan kirdi -> WB ushlab qoldi -> Reklama -> Tannarx -> Tovarda qoldi -> Foyda
```

Grafika murakkab bo‘lishi shart emas. Cards yetarli:

- **Kirdi:** revenue, additional payments;
- **WB ushlab qoldi:** commission, logistics, storage, penalties, deductions;
- **Biznes xarajat:** COGS, ads;
- **Pul qayerda turibdi:** WB balance, stock value, in-transit;
- **Unallocated:** SKU’ga ulanmagan xarajatlar.

#### Block D — Eng katta 5 risk

`risk_summary.risks`dan:

- Real себестоимость yo‘q;
- SKU bog‘lanmagan;
- Stock sync to‘liq emas;
- Finance mismatch;
- Reklama profitga ulanmagan.

Har bir risk card:

- title;
- business impact;
- affected amount/count;
- CTA.

#### Block E — Bugungi 5 action

`next_actions`dan top 5:

- title;
- what_to_do;
- expected effect;
- priority;
- status button.

### 4.4. Empty/error states

| Holat | UI text |
|---|---|
| Revenue yo‘q | `Bu davrda sotuv ma’lumoti topilmadi` |
| Stock value null | `Qoldiq qiymati hisoblanmadi: stock yoki cost ulanmagan` |
| Ad spend null | `Reklama xarajati hali SKU profitga ulanmagan` |
| Data blocked | `Raqamlar taxminiy. Avval data blockerlarni yoping.` |

---

## 5. Page 2 — `/cards` Card Control Center

### 5.1. Maqsad

Bitta sahifada barcha cardlarni ko‘rish:

```text
Qaysi card pul olib kelyapti?
Qaysi card pul yeyayapti?
Qaysi cardni dозаказать qilish mumkin?
Qaysi cardni sotmaslik yoki rasprodaja qilish kerak?
Qaysi cardda data xato?
```

### 5.2. API

```text
GET /api/v1/money/cards?account_id=1&date_from=...&date_to=...&limit=50&offset=0
```

Fallback:

```text
GET /api/v1/skus
GET /api/v1/dashboard/sku-profitability
GET /api/v1/pricing/safety
GET /api/v1/inventory/purchase-plan
```

### 5.3. Top presets

Sahifa yuqorisida quick filter tabs:

1. **Hammasi**
2. **Pul olib kelayotgan**
3. **Pul yeyayotgan**
4. **Tugab qoladigan**
5. **Qoldiq muzlagan**
6. **Narx xavfi**
7. **Reklama xavfi**
8. **Data tuzatish kerak**

### 5.4. Table columns

| Column | Nima ko‘rsatiladi |
|---|---|
| Card | rasm placeholder, title, vendor_code, nm_id, barcode |
| Status | `Foydali`, `Zararli`, `Data tuzatish kerak`, `Qoldiq xavfi` |
| Revenue | Выручка |
| Profit | Sof foyda / taxminiy foyda |
| Margin / ROI | foizlar |
| Stock | qty + days_of_stock |
| Ads | spend + DRR |
| Price | current price + safe price gap |
| Next action | eng muhim qadam |
| Trust | Ishonchli / Taxminiy / Blocked |

### 5.5. Row click

Row bosilganda `/cards/:skuId` ochiladi.

### 5.6. Row visual rules

- `data_blocked`: qizil chap border, `Avval data` badge;
- `loss_making`: qizil profit;
- `protect_stock`: sariq stock badge;
- `profitable_scale`: yashil status;
- null price/ad/stock: gray `Ma’lumot yo‘q`.

### 5.7. Filters

O‘ng tomonda yoki top drawer:

- search;
- status;
- trust state;
- next action;
- subject/category;
- brand;
- margin min/max;
- stock days min/max;
- ad spend min/max;
- only data blocked;
- only negative profit.

Ko‘p filter UI’ni murakkab qilmasin. Defaultda faqat search + presetlar ko‘rinsin, qolganlari `Advanced filters` ichida.

---

## 6. Page 3 — `/cards/:skuId` Card Detail

### 6.1. Maqsad

Bitta card bo‘yicha aniq javob:

```text
Bu card foydalimi?
Pul qayerga ketayapti?
Muammo nimada?
Endi nima qilish kerak?
```

### 6.2. API

```text
GET /api/v1/money/cards/{sku_id}?account_id=1&date_from=...&date_to=...
```

Fallback:

```text
GET /api/v1/skus/{sku_id}
GET /api/v1/core-sku/{sku_id}
GET /api/v1/dashboard/article-audit?nm_id=...
GET /api/v1/marts/sku-daily?sku_id=...
GET /api/v1/marts/stock-daily?sku_id=...
GET /api/v1/dq/issues?sku_id=...
```

### 6.3. Layout

#### Block A — Card Answer Header

```text
СС 1074 черный
Status: Data tuzatish kerak
Xulosa: Card pul olib kelyapti, lekin finance mismatch va reklama allocation muammosi bor.
Decision: Hozircha dозаказать qilma. Avval reconciliation va ads allocation’ni yop.
```

Headerda:

- title;
- vendor_code;
- nm_id;
- subject;
- status badge;
- data trust badge;
- main_next_step.

#### Block B — Money Breakdown

Cards:

- Выручка;
- WB for_pay;
- WB xarajatlari;
- Reklama;
- Себестоимость;
- Profit before ads;
- Profit after ads;
- Margin;
- ROI.

Agar confidence low:

```text
Taxminiy: real supplier cost yoki finance allocation to‘liq tasdiqlanmagan.
```

#### Block C — “Pul qayerga ketdi?” mini breakdown

Progress/stacked cards:

```text
Выручка 727 028 ₽
- Себестоимость 293 477 ₽
- Реклама 29 388 ₽
- WB xarajatlari ?
= Taxminiy foyda 404 162 ₽
```

Agar WB xarajatlari 0 bo‘lib, data suspicious bo‘lsa:

```text
WB xarajatlari 0 ko‘rinmoqda, bu ehtimol mapping muammosi. Tekshirish kerak.
```

#### Block D — Operations / Funnel

Ko‘rsatish:

- Orders;
- Cancelled orders;
- Cancel rate;
- Sales;
- Returns;
- Return rate;
- Open count;
- Cart conversion;
- Order conversion;
- Buyout rate.

Interpretatsiya card:

```text
Cancel rate yuqori: 63.5%. Sababini tekshirish kerak.
```

#### Block E — Stock / Zakupka

Ko‘rsatish:

- current stock;
- in way to client;
- in way from client;
- stock value;
- days of stock;
- purchase recommendation.

Agar data blocked:

```text
Zakupka tavsiyasi bloklangan. Sabab: data trust yetarli emas.
```

#### Block F — Price Safety

Ko‘rsatish:

- current price;
- discounted price;
- break-even;
- target margin price;
- safe price gap;
- action hint.

Agar price null:

```text
Narx xavfsizligi hisoblanmadi: price mapping yo‘q.
```

#### Block G — Ads

Ko‘rsatish:

- spend;
- views;
- clicks;
- orders;
- CTR;
- CPC;
- DRR;
- profit after ads;
- action hint.

Agar ads spend article auditda bor, daily economics’da yo‘q:

```text
Reklama xarajati topildi, lekin profit hisobiga ulanmagan. Avval ads allocation’ni tuzatish kerak.
```

#### Block H — Problems and Next Actions

Bu eng muhim block. Issuesni raw list qilib bermasdan, biznes muammo sifatida ko‘rsatish:

```text
1. Finance report bilan 34.12% farq bor
   Nega muhim: foyda noto‘g‘ri chiqishi mumkin
   Nima qilish kerak: finance reconciliation source rowsni tekshirish

2. Reklama profitga ulanmagan
   Nega muhim: DRR 0 bo‘lib ko‘rinyapti, aslida spend bor
   Nima qilish kerak: ads allocation fix
```

### 6.4. Card detail tabs

Tabs bo‘lishi mumkin:

1. **Xulosa**
2. **Pul**
3. **Qoldiq**
4. **Narx**
5. **Reklama**
6. **Muammolar**
7. **Raw data**

Default: **Xulosa**.

---

## 7. Page 4 — `/actions` Bugungi qadamlar

### 7.1. Maqsad

Foydalanuvchi kunni shu sahifadan boshlaydi:

```text
Bugun nima qilish kerak?
Qaysi qadam ko‘proq pulga ta’sir qiladi?
Qaysi qadam data blocker?
Qaysi qadam real biznes action?
```

### 7.2. API

```text
GET /api/v1/money/actions/today?account_id=1&date_from=...&date_to=...
PATCH /api/v1/actions/{action_id}
```

### 7.3. Layout

#### Block A — Action Summary

Cards:

- Critical;
- High;
- Business actions;
- Data fix actions;
- Done today.

#### Block B — Action list

Har bir action card:

- priority badge;
- title;
- what_to_do;
- why;
- expected effect;
- linked SKU/card;
- confidence;
- buttons: `Bajarildi`, `Keyinga qoldir`, `Kommentariya`, `Cardni ochish`.

#### Block C — Action groups

Group by type:

1. **Avval data tuzatish**
2. **Pulni himoya qilish**
3. **Zakupka**
4. **Narx**
5. **Reklama**
6. **Qoldiq**

### 7.4. Action card example

```text
Critical · Real себестоимость tasdiqlanmagan
Nima qilish kerak: supplier cost faylini yuklang yoki mavjud baseline costlarni tasdiqlang.
Nega: profit, ROI, закупка va price safety final emas.
Ta’sir: barcha cardlar bo‘yicha biznes actionlar ochiladi.
[Cost sahifasiga o‘tish] [Bajarildi] [Kommentariya]
```

### 7.5. Action details drawer

Action bosilganda drawer ochilsin:

- linked card;
- calculation basis;
- source period;
- blocker reasons;
- how_to_fix steps;
- raw issue/source link;
- history/comments.

---

## 8. Page 5 — `/data-fix` Data Fix Center

### 8.1. Maqsad

Data blocked sababli real business actions chiqmayotganini oddiy ko‘rsatish.

```text
Nima bloklayapti?
Qancha pul/SKU ta’sirda?
Qanday yopamiz?
```

### 8.2. API

```text
GET /api/v1/money/data-blockers
GET /api/v1/dq/issues/summary
GET /api/v1/dq/issues
PATCH /api/v1/dq/issues/{issue_id}/classify
POST /api/v1/dq/issues/{issue_id}/resolve
POST /api/v1/dq/run
```

### 8.3. Layout

#### Block A — Data Trust status

```text
Holat: Data tuzatish kerak
Business actions: bloklangan
Sabab: 4 blocker
```

#### Block B — Blocker cards

Cards:

1. Real себестоимость;
2. Unmatched SKU;
3. Stock sync;
4. Finance mismatch;
5. Ads allocation;
6. Price mapping;
7. Open DQ issues.

Har bir card:

- current value;
- required value;
- affected SKU/revenue;
- business impact;
- how to fix;
- CTA.

#### Block C — Issues table

Columns:

- priority;
- code label;
- affected card/SKU;
- business impact;
- status/classification;
- age;
- action buttons.

### 8.4. Data fix UX

Data fix sahifasi developer panelga o‘xshamasin. Foydalanuvchiga shunday ko‘rsatilsin:

```text
Muammo: 96 ta SKU bog‘lanmagan
Ta’sir: bu SKU’larda foyda va reklama noto‘g‘ri ulanadi
Qanday yopish: SKU mapping qiling yoki eski/arxiv deb belgilab ignore qiling
```

---

## 9. Page 6 — `/costs` Себестоимость

### 9.1. Maqsad

Real profit uchun eng muhim joy — cost.

### 9.2. API

```text
GET /api/v1/costs/template
POST /api/v1/costs/upload
GET /api/v1/costs/uploads/{upload_id}/preview
POST /api/v1/costs/uploads/{upload_id}/confirm
GET /api/v1/costs/rows
GET /api/v1/costs/unresolved
POST /api/v1/costs/relink
```

### 9.3. Layout

- Coverage cards:
  - SKU cost coverage;
  - revenue cost coverage;
  - supplier-confirmed coverage;
  - operator baseline count;
  - missing/unresolved cost.

- Import flow:
  1. Template yuklab olish;
  2. File upload;
  3. Preview;
  4. Errors/mapping;
  5. Confirm;
  6. Refresh marts.

### 9.4. UI copy

Agar `OPERATOR_TRUSTED_COST` bo‘lsa:

```text
Bu cost operator baseline. Profit taxminiy. Supplier-confirmed cost yuklansa, business actionlar ochiladi.
```

---

## 10. Page 7 — `/settings`

### 10.1. API

```text
GET /api/v1/settings/business?account_id=1
PATCH /api/v1/settings/business?account_id=1
```

### 10.2. Ko‘rsatish kerak bo‘lgan sozlamalar

| Setting | UI label | Default |
|---|---|---:|
| `target_margin_rate` | Maqsad marja | 20% |
| `target_roi_percent` | Maqsad ROI | 30% |
| `lead_time_days` | Yetkazib berish vaqti | 14 kun |
| `safety_days` | Safety stock | 7 kun |
| `overstock_threshold_days` | Qoldiq muzlash threshold | 90 kun |
| `oos_threshold_days` | Tugab qolish xavfi | 7 kun |
| `ad_drr_threshold_percent` | Reklama DRR limiti | 25% |
| `pack_multiple` | Zakupka qadoq koeffitsienti | 1 |
| `cost_trust_policy` | Cost ishonch siyosati | supplier_only |

---

## 11. Components ro‘yxati

Lovable’da reusable components qilib qurish kerak.

### 11.1. `DataTrustBadge`

Props:

```ts
{
  state: 'trusted' | 'test_only' | 'data_blocked';
  confidence?: 'high' | 'medium' | 'low';
  blockedReasons?: string[];
}
```

### 11.2. `AnswerCard`

Props:

```ts
{
  status: string;
  title: string;
  shortText: string;
  mainProblem?: string;
  mainNextStep?: string;
  primaryAction?: { label: string; href: string };
}
```

### 11.3. `MoneyKpiCard`

Props:

```ts
{
  label: string;
  value: number | null;
  format: 'money' | 'percent' | 'number';
  confidence?: 'high' | 'medium' | 'low';
  reason?: string;
  badge?: string;
}
```

### 11.4. `NextActionCard`

Props:

```ts
{
  priority: 'critical' | 'high' | 'medium' | 'low';
  title: string;
  whatToDo: string;
  why: string;
  expectedEffectAmount?: number | null;
  confidence: string;
  status: string;
  linkedEntity?: object;
}
```

### 11.5. `CardStatusBadge`

Statuses:

```ts
type CardStatus =
  | 'data_blocked'
  | 'profitable_scale'
  | 'protect_stock'
  | 'loss_making'
  | 'overstock'
  | 'price_risk'
  | 'ad_risk'
  | 'watch'
  | 'new_card';
```

### 11.6. `NullValue`

Agar value null bo‘lsa:

```text
Ma’lumot yo‘q
```

Tooltip’da reason:

```text
Sabab: reklama xarajati profitga ulanmagan
```

---

## 12. Formatting rules

### 12.1. Money

```ts
formatMoney(9902644.09) => "9 902 644 ₽"
formatMoney(null) => "Ma’lumot yo‘q"
```

### 12.2. Percent

```ts
formatPercent(54.829) => "54.8%"
formatPercent(null) => "—"
```

### 12.3. Large numbers

```ts
formatNumber(16639) => "16 639"
```

### 12.4. Confidence label

```ts
high => "Ishonch yuqori"
medium => "Taxminiy"
low => "Ishonch past"
```

---

## 13. API client qoidalari

### 13.1. Auth

Login:

```text
POST /api/v1/auth/login
```

Response:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer"
}
```

Har bir protected request:

```text
Authorization: Bearer <access_token>
```

### 13.2. Base URL

Environment variable:

```text
VITE_API_BASE_URL=https://.../api/v1
```

### 13.3. Common fetch wrapper

- auth token qo‘shadi;
- 401 bo‘lsa refresh qiladi;
- `ngrok-skip-browser-warning` header qo‘shishi mumkin;
- errorni `ApiError` sifatida qaytaradi;
- money endpointsda nullni 0ga aylantirmaydi.

### 13.4. Page response type

```ts
export interface Page<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}
```

---

## 14. TypeScript interface draft

### 14.1. DataTrust

```ts
export interface DataTrustInfo {
  state: 'trusted' | 'test_only' | 'data_blocked';
  business_trusted: boolean;
  can_generate_business_actions: boolean;
  confidence: 'high' | 'medium' | 'low';
  blocked_reasons: string[];
  human_message: string;
}
```

### 14.2. Money Summary

```ts
export interface MoneySummary {
  meta: {
    account_id: number;
    date_from: string;
    date_to: string;
    currency: string;
    generated_at: string;
    data_trust: DataTrustInfo;
  };
  answer: {
    business_status: string;
    title: string;
    short_text: string;
    main_problem?: string | null;
    main_next_step?: string | null;
  };
  kpis: Record<string, number | null>;
  money_flow: {
    incoming: MoneyFlowItem[];
    outgoing: MoneyFlowItem[];
    cash_and_stock: MoneyFlowItem[];
  };
  risk_summary: {
    critical_count: number;
    risks: RiskItem[];
  };
  top_cards: Record<string, MoneyCardRow[]>;
  next_actions: NextAction[];
}
```

### 14.3. Card row

```ts
export interface MoneyCardRow {
  sku_id: number | null;
  nm_id: number | null;
  vendor_code: string | null;
  barcode: string | null;
  title: string | null;
  brand: string | null;
  subject_name: string | null;
  business_verdict: {
    status: string;
    label: string;
    short_text: string;
    confidence: 'high' | 'medium' | 'low';
  };
  money: {
    revenue: number | null;
    profit_after_ads: number | null;
    profit_before_ads: number | null;
    margin_percent: number | null;
    roi_percent: number | null;
    cogs: number | null;
    wb_expenses: number | null;
    ad_spend: number | null;
    stock_value: number | null;
  };
  stock: {
    stock_qty: number | null;
    days_of_stock: number | null;
    status: string;
    in_transit_qty: number | null;
  };
  price: {
    current_price: number | null;
    current_discounted_price: number | null;
    break_even_price: number | null;
    target_margin_price: number | null;
    safe_price_gap: number | null;
    status: string;
  };
  ads: {
    ad_spend: number | null;
    drr_percent: number | null;
    status: string;
  };
  data_trust: DataTrustInfo;
  next_action: NextAction | null;
  priority_score: number;
}
```

---

## 15. UX copy dictionary

### 15.1. Status copy

| Backend | UI title | UI subtitle |
|---|---|---|
| `data_blocked` | Avval data tuzatish kerak | Bu card bo‘yicha biznes tavsiya hozircha bloklangan |
| `profitable_scale` | Rivojlantirish mumkin | Card foydali va ko‘rsatkichlari yaxshi |
| `protect_stock` | Tugab qolish xavfi | Card foydali, lekin qoldiq yetmaydi |
| `loss_making` | Zararli | Card foyda bermayapti, sababini tekshiring |
| `overstock` | Qoldiq muzlagan | Tovar sekin aylanmoqda, pul qoldiqda turibdi |
| `price_risk` | Narx xavfi | Narx foydani xavfga qo‘yayapti |
| `ad_risk` | Reklama xavfi | Reklama foydani yeyayotgan bo‘lishi mumkin |
| `watch` | Kuzatish | Hozircha keskin harakat kerak emas |

### 15.2. Action copy

| Action | UI title |
|---|---|
| `FIX_COST_TRUST` | Real себестоимостьni tasdiqlash |
| `MAP_UNMATCHED_SKU` | SKU mapping qilish |
| `FIX_STOCK_SYNC` | Qoldiq sync’ni tuzatish |
| `RECONCILE_FINANCE` | Finance farqini tekshirish |
| `FIX_AD_ALLOCATION` | Reklama xarajatini card profitga ulash |
| `FIX_PRICE_MAPPING` | Narx mapping’ni tuzatish |
| `REORDER` | Dозаказать qilish |
| `DO_NOT_REORDER` | Qayta sotib olmaslik |
| `LIQUIDATE_STOCK` | Qoldiqni sotish |
| `PRICE_INCREASE_REVIEW` | Narxni ko‘tarishni tekshirish |
| `AD_PAUSE_REVIEW` | Reklamani to‘xtatishni tekshirish |

---

## 16. Fallback logic — backend yangi endpointlarni bermasa

Frontend vaqtincha eski endpointlardan foydalanishi mumkin, lekin UI bir xil qoladi.

### 16.1. Money page fallback

```text
/dashboard/owner -> revenue, net_profit, margin, risks
/dashboard/data-health -> trust_state, blocked_reasons, issue buckets
/balance -> cash_on_wb
/marts/account-expense-daily -> WB expenses
/actions -> next_actions
```

### 16.2. Cards page fallback

```text
/skus -> control rows
/dashboard/sku-profitability -> profit breakdown
/pricing/safety -> price risk
/inventory/purchase-plan -> purchase status
```

### 16.3. Card detail fallback

```text
/skus/{sku_id}
/core-sku/{sku_id}
/dashboard/article-audit?nm_id=...
/dq/issues?sku_id=...
```

### 16.4. Fallback warning

Agar fallback ishlatilsa, UI ichki development badge ko‘rsatsin:

```text
Backend money endpoint hali tayyor emas. Raqamlar bir nechta endpointdan yig‘ildi.
```

---

## 17. Responsive design

### Desktop

- Sidebar + content;
- KPI grid 4 columns;
- Card table full width;
- Detail page 2-column layout.

### Tablet

- Sidebar collapsed;
- KPI grid 2 columns;
- Tables horizontal scroll.

### Mobile

- Bottom navigation;
- KPI cards single column;
- Card table card-listga aylanadi;
- Action cards full width.

---

## 18. Loading states

### 18.1. Money page loading

Skeleton:

- answer card skeleton;
- KPI cards skeleton;
- flow cards skeleton;
- top actions skeleton.

### 18.2. Error state

```text
Ma’lumot yuklanmadi.
Sabab: API javob bermadi yoki token eskirgan.
[Qayta urinish]
```

### 18.3. Partial data state

```text
Ma’lumot qisman yuklandi. Quyidagi bloklar to‘liq emas: reklama, stock, finance.
```

---

## 19. Acceptance criteria

### 19.1. Money page

Qabul qilinadi, agar foydalanuvchi 30 soniyada tushunsa:

- magazin holati qanday;
- pul qayerda;
- pul qayerga ketdi;
- eng katta 3 muammo nima;
- bugun nima qilish kerak.

### 19.2. Cards page

Qabul qilinadi, agar:

- har bir cardda status bor;
- card foydali/zararli/data blocked ko‘rinadi;
- profit, stock, ads, price qisqa ko‘rinadi;
- next action table’da ko‘rinadi;
- data yo‘q joyda 0 emas, `Ma’lumot yo‘q` chiqadi.

### 19.3. Card detail

Qabul qilinadi, agar:

- sahifa yuqorisida aniq xulosa bor;
- pul breakdown tushunarli;
- reklama, stock, price, funnel alohida ko‘rinadi;
- muammolar business impact bilan chiqadi;
- keyingi qadamlar aniq.

### 19.4. Actions page

Qabul qilinadi, agar:

- actions texnik emas, biznes tili bilan;
- `what_to_do`, `why`, `how_to_fix` ko‘rinadi;
- action status update ishlaydi;
- data blocker actionlar va business actionlar alohida.

### 19.5. Data Fix page

Qabul qilinadi, agar:

- nimani tuzatish kerakligi aniq;
- ta’sir miqdori/SKU count ko‘rinadi;
- har bir blocker uchun CTA bor;
- data blocked bo‘lsa Money page va Actions page shu sahifaga yo‘naltiradi.

---

## 20. Lovable uchun aniq build tartibi

### Step 1 — UI shell

- Auth login;
- Sidebar;
- Header account/date filters;
- DataTrustBadge;
- formatting helpers.

### Step 2 — Money page

- `/money/summary` integration;
- fallback endpointlar;
- AnswerCard;
- KPI cards;
- money flow;
- top risks;
- top actions.

### Step 3 — Cards page

- `/money/cards` integration;
- presets;
- table;
- filters;
- detail navigation.

### Step 4 — Card detail

- `/money/cards/:skuId` integration;
- tabs;
- money breakdown;
- stock/price/ads/funnel;
- problems and actions.

### Step 5 — Actions page

- `/money/actions/today` integration;
- status update via `PATCH /actions/{id}`;
- action drawer.

### Step 6 — Data Fix and Costs

- `/money/data-blockers`;
- DQ issue list;
- costs upload flow.

### Step 7 — Polish

- null states;
- error states;
- responsive;
- copy dictionary;
- performance.

---

## 21. Muhim “do not” ro‘yxati

Lovable frontend quyidagilarni qilmasin:

1. `null`ni `0` qilib ko‘rsatmasin.
2. Data blocked holatda “hammasi normal” demasin.
3. Raw issue code’larni asosiy UI text qilmasin.
4. Birinchi ekranda juda ko‘p chart bermasin.
5. Profit raqamlarini `final` deb ko‘rsatmasin, agar confidence low bo‘lsa.
6. Business action va data fix actionni aralashtirmasin.
7. Ads spend yo‘q bo‘lsa, lekin article auditda bor bo‘lsa, `0` demasin — `ulanmagan` desin.
8. Price safety `current_price=0`ni real narx deb ko‘rsatmasin.
9. 1948 ta issue’ni xom ro‘yxat qilib foydalanuvchiga tashlamasin — summary va priority berilsin.
10. Dashboardni bezak uchun murakkablashtirmasin.

---

## 22. Yakuniy frontend maqsadi

Dastur ochilganda foydalanuvchi quyidagini ko‘rishi kerak:

```text
Magazin holati: Data tuzatish kerak.
Pul: 9.9M ₽ выручка, foyda taxminiy, WB balans 914k ₽, stock value hisoblanmagan.
Asosiy muammo: real себестоимость 0%, SKU mapping, stock sync, reklama allocation.
Bugungi qadam: real costni tasdiqlash, 96 SKU’ni map qilish, ads allocationni tuzatish.
```

Card ochilganda:

```text
Bu card sotilyapti va pul olib kelyapti, lekin finance farqi 34% va reklama profitga ulanmagan.
Hozircha dозаказать qilma. Avval reconciliation + ads allocation tuzat.
```

Actions sahifasida:

```text
Bugun qilish kerak bo‘lgan 5 qadam: cost trust, SKU mapping, stock sync, finance mismatch, ads allocation.
```

Shu natijaga erishilsa, frontend haqiqiy **pul boshqaruvi pulti** bo‘ladi.
