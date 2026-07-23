# WB Action Center Capability Tracking

Last reviewed: 2026-07-22.

Action Center must not hide the difference between a detected problem, a local
fix, and a real WB write. Each capability exposed by
`GET /portal/action-center/capabilities` now carries WB API tracking fields:
connector IDs, endpoints, official docs, token categories, rate-limit notes,
implementation gaps, and write safety requirements.

## Official WB Sources

Official docs checked or referenced by the connector inventory:

- https://dev.wildberries.ru/en/docs/openapi/api-information
- https://dev.wildberries.ru/en/docs/openapi/work-with-products
- https://dev.wildberries.ru/en/docs/openapi/reports
- https://dev.wildberries.ru/en/docs/openapi/analytics
- https://dev.wildberries.ru/en/docs/openapi/financial-reports-and-accounting
- https://dev.wildberries.ru/en/docs/openapi/promotion
- https://dev.wildberries.ru/en/docs/openapi/wb-tariffs
- https://dev.wildberries.ru/en/docs/openapi/orders-fbw
- https://dev.wildberries.ru/en/docs/openapi/user-communication

Direct fetches to `dev.wildberries.ru` from this environment returned WB anti-bot
HTTP 498/WBAAS challenge on 2026-07-22. Search snippets from the same official
domain still confirmed key write/read endpoints, including:

- product card update:
  `https://content-api.wildberries.ru/content/v2/cards/update`
- price upload task:
  `https://discounts-prices-api.wildberries.ru/api/v2/upload/task`
- advertising budget read/deposit:
  `https://advert-api.wildberries.ru/adv/v1/budget`
  and `/adv/v1/budget/deposit`
- FBW supplies and acceptance options:
  `https://supplies-api.wildberries.ru/api/v1/supplies`
  and `/api/v1/acceptance/options`

The source of truth for implemented connectors remains
`app/core/wb_connector_inventory.py`.

## Write Safety Rules

No Action Center capability may perform a dangerous WB write unless all of these
are true:

- connector inventory has an active entry with official docs source
- token category matches `WBAPICategory`
- endpoint method, request shape, rate limit and no-data shape are documented
- raw WB request/response is stored
- user sees old/new diff and confirms the batch
- executor has idempotency or duplicate protection
- Action Center stores a result event and reruns the relevant recheck

## Current Gaps

- Price and discount writes are detected and planned, but there is no active
  price-upload write connector in inventory yet.
- Advertising campaign status, product membership, bid and budget writes are not
  inventoried; current ads connectors are read/statistics only.
- Supply planning uses WB supplies, stock and tariff context, but automatic WB
  supply creation/export is still preview-only.
- Reputation publishing uses the feedbacks/questions category and remains behind
  runtime permission, manager/admin access and explicit confirmation.
- Buyer returns, buyer chat and seller user management are explicit
  `not_implemented` connector categories and must not be collapsed into content
  or marketplace tokens.
