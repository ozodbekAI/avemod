# WB Connector Compliance Report

Generated source of truth: `app/core/wb_connector_inventory.py`

Last verified against official WB documentation on 2026-07-03.

Official sources used:
- https://dev.wildberries.ru/en/docs/openapi/api-information
- https://dev.wildberries.ru/en/docs/openapi/work-with-products
- https://dev.wildberries.ru/en/docs/openapi/reports
- https://dev.wildberries.ru/en/docs/openapi/analytics
- https://dev.wildberries.ru/en/docs/openapi/financial-reports-and-accounting
- https://dev.wildberries.ru/en/docs/openapi/promotion
- https://dev.wildberries.ru/en/docs/openapi/wb-tariffs
- https://dev.wildberries.ru/en/docs/openapi/orders-fbw
- https://dev.wildberries.ru/en/docs/openapi/user-communication

## Summary

- Feedbacks/questions now require the `feedbacks_questions` token category. They must not use `content`.
- Buyer chat, buyer returns, and seller users are explicit token categories in the data model, but no production WB connector consumes them yet.
- Finance sync uses current `/api/finance/v1/sales-reports/*` endpoints. The old `/api/v5/supplier/reportDetailByPeriod` method is marked `legacy_not_used` and is guarded by tests.
- WB HTTP 204 no-data responses are normalized to `{"noData": true}` before raw snapshot storage and page-loop handling.
- Active connectors store raw WB responses in `raw_wb_api_responses` either through `DomainSyncBase._request_json` or `ReputationService._store_wb_raw_response`.

## Endpoint Inventory

| Domain | Connector | Endpoint | Token | Method | Pagination / Cursor | Date / Scope | Rate / Backoff | Success / No Data | Status | DB Targets | DQ Checks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| product_cards | `product_cards.list_cards` | `https://content-api.wildberries.ru/content/v2/get/cards/list` | `content` | POST | `cursor.updatedAt` + `cursor.nmID` until total < limit | Full card list by update order | Content limits plus 429 headers | `cards[]` / empty cards | active | `wb_product_cards`, sizes, characteristics, `core_sku`, raw snapshots | `unmatched_sku`, `missing_chrt_id`, manual-cost SKU checks |
| product_cards | `product_cards.list_tags` | `https://content-api.wildberries.ru/content/v2/tags` | `content` | GET | none | current tags | Content limits plus 429 headers | `data[]` or `tags[]` / empty list | active | `wb_product_card_tags`, raw snapshots | none |
| prices | `prices.list_goods` | `https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter` | `prices` | GET | offset while rows == limit | current prices | WB limits plus 429 headers | `data.listGoods[]` / empty list | active | `wb_prices`, `wb_price_snapshots`, `core_sku`, raw snapshots | price jump/zero, `unmatched_sku` |
| prices | `prices.list_sizes` | `https://discounts-prices-api.wildberries.ru/api/v2/list/goods/size/nm` | `prices` | GET | offset available; one page per nmID in current sync | current size prices | WB limits plus 429 headers | `data.listGoods[]` / empty list | active | `wb_price_sizes`, raw snapshots | `missing_chrt_id`, price zero |
| prices | `prices.upload_state` | `/api/v2/history/tasks`, `/api/v2/history/goods/task`, `/api/v2/buffer/tasks`, `/api/v2/buffer/goods/task` | `prices` | GET | offset for task rows | upload history scope | WB limits plus 429 headers | task rows / empty goods | active | upload task tables, raw snapshots | upload history unavailable |
| prices | `prices.quarantine_goods` | `https://discounts-prices-api.wildberries.ru/api/v2/quarantine/goods` | `prices` | GET | offset while rows == limit | current quarantine state | WB limits plus 429 headers | quarantine goods / empty list | active | `wb_price_quarantine`, raw snapshots | price jump/too low |
| orders | `orders.fetch_orders` | `https://statistics-api.wildberries.ru/api/v1/supplier/orders` | `statistics` | GET | no cursor; incremental `dateFrom` | preliminary operational data, WB retention window | Statistics limits plus 429 headers | array / empty array | active | `wb_orders`, raw snapshots | order/sale/finance reconciliation, `unmatched_sku` |
| sales | `sales.fetch_sales` | `https://statistics-api.wildberries.ru/api/v1/supplier/sales` | `statistics` | GET | no cursor; incremental `dateFrom` | preliminary operational data, WB retention window | Statistics limits plus 429 headers | array / empty array | active | `wb_sales`, raw snapshots | sale/finance/stock reconciliation, `unmatched_sku` |
| stocks | `stocks.warehouse_remains` | `https://seller-analytics-api.wildberries.ru/api/v1/warehouse_remains` | `analytics` | GET/task | async task id, poll, download | current stock snapshot | local stock spacing plus 429 headers | task/download rows / empty report | active | stock snapshot tables, `mart_stock_daily`, raw snapshots | stock/sales checks, `unmatched_sku` |
| finance | `finance.sales_reports_list` | `https://finance-api.wildberries.ru/api/finance/v1/sales-reports/list` | `finance` | POST | offset/list body per WB contract | report list since current WB finance coverage | 1 request/min local spacing plus 429 headers | report list / empty list or 204 noData | active | `wb_realization_reports`, raw snapshots | finance reconciliation |
| finance | `finance.sales_reports_detailed` | `https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed` | `finance` | POST | `rrdId`; stop on 204/noData or short page | report rows for requested period | 1 request/min local spacing plus 429 headers | rows / 204 `noData` | active | realization rows, finance marts, raw snapshots | finance mismatch, sale/finance gaps, unclassified expense |
| finance | `finance.legacy_report_detail_by_period` | `https://statistics-api.wildberries.ru/api/v5/supplier/reportDetailByPeriod` | `statistics` | GET | legacy `rrdid` | legacy realization report | deprecated | array / 204 | legacy_not_used | none | none |
| finance | `finance.acquiring` | `https://finance-api.wildberries.ru/api/finance/v1/acquiring/list`, `/detailed` | `finance` | POST | `rrdId` for detail rows | Russia-only acquiring report scope | finance spacing plus 429 headers | reports/rows / empty or 204 noData | active | acquiring tables, raw snapshots | acquiring unsupported/failed |
| analytics | `analytics.funnel_history` | `https://seller-analytics-api.wildberries.ru/api/analytics/v3/sales-funnel/products/history` | `analytics` | POST | local nmID batches | product analytics history window | 3/min style spacing plus 429 headers | history rows / empty array | active | `wb_card_funnel_daily`, raw snapshots | Checker opportunity estimates |
| analytics | `analytics.region_sales` | `https://seller-analytics-api.wildberries.ru/api/v1/analytics/region-sale` | `analytics` | GET | none | requested sync window | WB limits plus 429 headers | `report[]` / empty report | active | `wb_region_sales_daily`, raw snapshots | none |
| analytics | `analytics.hidden_products` | blocked/shadowed analytics endpoints | `analytics` | GET | none | current hidden/blocked state | WB limits plus 429 headers | `report[]` / empty report | active | `wb_hidden_products`, raw snapshots | Checker visibility warning |
| ads | `ads.campaigns` | `https://advert-api.wildberries.ru/api/advert/v2/adverts` | `promotion` | GET | none | current campaigns | Promotion limits plus 429 headers | campaigns / empty list | active | ad campaign tables, raw snapshots | ad allocation issues |
| ads | `ads.full_stats` | `https://advert-api.wildberries.ru/adv/v3/fullstats` | `promotion` | GET | local campaign batches | default 7-day sync window unless backfilled | local 20s spacing plus 429 headers | stats rows / empty array | active | `wb_ad_stats_daily`, raw snapshots | ad spend allocation |
| ads | `ads.cluster_stats` | `https://advert-api.wildberries.ru/adv/v1/normquery/stats` | `promotion` | POST | local item batches | default 7-day sync window unless backfilled | local 20s spacing plus 429 headers | stats/data/items / empty | active | `wb_ad_cluster_stats`, raw snapshots | ad spend without SKU |
| tariffs | `tariffs.common` | commission, box, pallet, return, acceptance coefficients | `tariffs` | GET | none | current/requested tariff date; acceptance next 14 days | method-specific limits plus 429 headers | reports/warehouse lists/arrays / empty | active | tariff tables, raw snapshots | none |
| documents | `documents.documents` | `https://documents-api.wildberries.ru/api/v1/documents/categories`, `/list` | `documents` | GET | none | default 30-day sync unless backfilled | local 10s spacing plus 429 headers | documents/categories / empty list | active | document tables, raw snapshots | none |
| supplies | `supplies.fbw` | `https://supplies-api.wildberries.ru/api/v1/warehouses`, `/acceptance/options`, `/supplies`, details | `supplies` | GET/POST | offset for supplies/goods | current plus recent/changed supplies | local enrichment pause plus 429 headers | lists/data / empty list | active | supply tables, raw snapshots | supply discrepancy, `unmatched_sku` |
| reputation | `feedbacks_questions.reputation` | `https://feedbacks-api.wildberries.ru/api/v1/feedbacks`, `/questions`, answer endpoints | `feedbacks_questions` | GET/POST/PATCH | `take`/`skip` per source | feedback/question history exposed by WB | feedbacks/questions limits plus 429 headers | WB envelope / empty adapter rows | active | `reputation_items`, drafts/events, raw snapshots | reputation sync failed |
| buyer_chat | `buyer_chat` | buyer chat API | `buyer_chat` | GET/POST | not implemented | not implemented | must be checked before implementation | not implemented | not_implemented | none | none |
| buyer_returns | `buyer_returns` | `https://returns-api.wildberries.ru/api/v1/claims`, `/claim` | `buyer_returns` | GET/PATCH | not implemented | not implemented | must be checked before implementation | not implemented | not_implemented | none | none |
| users | `users.access` | seller user management API | `users` | GET/POST/PUT | not implemented | not implemented | must be checked before implementation | not implemented | not_implemented | none | none |

## Test Coverage

`tests/unit/test_wb_connector_compliance.py` verifies:

- all required token categories exist in `WBAPICategory`
- all required domains are represented in the inventory
- registered sync services use the token category declared in the inventory
- active connector client methods exist
- feedbacks/questions, buyer chat, buyer returns, and users do not collapse into `content`
- production code does not call `reportDetailByPeriod`
- each active connector has documented rate/backoff and raw snapshot storage
- HTTP 204 no-data responses are preserved as `{"noData": true}` without network access
- WB finance raw fields map into internal DB/UI fields

