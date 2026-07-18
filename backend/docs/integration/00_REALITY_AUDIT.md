# Reality Audit: Finance Seller Portal Integration

Generated from local Finance source and temporary extraction of `_incoming_projects/*` into `/tmp/finance_incoming_projects_audit`. External projects remain reference material only and are not copied into the deploy context.

## Current Finance Backend

Finance is already the authoritative FastAPI backend, PostgreSQL schema owner, auth/account boundary, token boundary, and money source.

- Runtime entry: `app/main.py`
- API wiring: `app/api/router.py`
- Portal routes: `app/modules/portal/router.py`
- Portal orchestration: `app/services/portal.py`
- Optional module health: `app/services/module_registry.py`
- Finance-owned operator tables: `app/models/operator.py`
- Auth/account models: `app/models/auth.py`, `app/models/accounts.py`
- WB data sources: `wb_product_cards`, `wb_product_card_characteristics`, `wb_product_card_sizes`, finance/orders/sales/stocks/ads/marts tables.

Existing `/portal/*` contracts are stable and must stay frontend-facing. Optional adapters currently report `disabled`, `not_configured`, `degraded`, or `unavailable` depending on env and adapter probes.

## Incoming Archives

| Archive | Temporary audit folder | Role | Keep | Do not carry over |
|---|---|---|---|---|
| `checker.zip` | `/tmp/finance_incoming_projects_audit/checker` | Card quality/checker logic | Card snapshot normalization, issue rules, score calculation, title/description/characteristic/media checks, analysis orchestration patterns, safe issue schemas | Checker auth/users/stores/team/billing, SQLite/runtime DB, WB apply jobs, auto-apply |
| `backend (7) .zip` | `/tmp/finance_incoming_projects_audit/backend__7__` | Reputation/reviews/questions/chats backend | WB feedback/question/chat sync patterns, normalized item models, classification, drafts, tone/signature/templates, manual attention flow, safe publish workflow | Separate user/shop/team/billing, credits, public frontend, direct auth boundary |
| `backenddefect.zip` | `/tmp/finance_incoming_projects_audit/backenddefect` | Defect/claims/support backend | Case lifecycle, response classifier, compensation matching, finance trace/evidence concepts, draft/proof-check patterns | Separate auth, telegram runtime, direct submit defaults, separate case DB as runtime dependency |
| `groupingbackend.zip` | `/tmp/finance_incoming_projects_audit/groupingbackend` | Grouping recommendation engine | Article normalization, constraints, pipeline, scoring, candidate/recommendation/risk payload generation | Product DB as source of truth, merge-wb endpoint, destructive product sync, separate auth |
| `all.zip` | `/tmp/finance_incoming_projects_audit/all` | Stock/TZostatka logic | Excess/shortage/redistribution/ship-from-hand/store-balance calculators, reference data mapping patterns | Separate auth, SQLite/runtime DB, Excel-only state as source of truth, direct WB modifications |

## Legacy Structure Map

### Checker

- Models: `app/models/card.py`, `issue.py`, `task.py`, `store.py`, `approval.py`, `photo_asset.py`, `promotion.py`, `wb_apply_job.py`.
- Routers: `cards`, `issues`, `sync`, `dashboard`, `photo_chat`, `promotion`, `stores`, `team`, `auth`.
- Services: `card_service.py`, `issue_service.py`, `wb_cards.py`, `wb_repository.py`, `wb_validator.py`, `super_validator.py`, `title_policy.py`, `text_policy.py`, `vision_service.py`, `task_service.py`.
- Jobs/workers: `app/worker/tasks.py`, `card_scheduler.py`, ad analysis bootstrap scheduler.
- Algorithms of interest: issue de-duplication/collapse, visible issue counts, score breakdown, media/title/description/characteristic validation, WB validation issue formatting.
- Incompatibilities: store/user/team auth is separate; store IDs must become finance `account_id`; WB apply jobs are unsafe for MVP.

### Reputation

- Models: feedback/question/chat/draft/signature/tone/shop/job/audit/generation trace.
- Routes: feedbacks, questions, chats, drafts, settings, jobs, analytics, admin integrations.
- Services: `sync.py`, `wb_client.py`, `wb_content_client.py`, `wb_chat_client.py`, `review_classifier.py`, `drafting.py`, `question_drafting.py`, `publish_service.py`, `review_backlog_orchestrator.py`.
- Algorithms of interest: item sync, category/sentiment classification, draft generation, templates/tone/signature, safe publish lifecycle.
- Incompatibilities: shop membership/auth/billing/credits are separate; publish must remain preview/confirm and disabled by default.

### Claims

- Models: centralized in `app/models/entities.py`.
- Routes: cases, media, support, templates, WB, auth.
- Services: cases, claim actions/lifecycle, compensation matcher, finance sync/trace, legal documents, media, support gateway/tracker, WB sync.
- Algorithms of interest: compensation matching, defect/return case lifecycle, evidence/media handling, proof-check, draft creation.
- Incompatibilities: own auth and telegram workflow; submit/appeal must remain disabled until finance confirm/audit flow is complete.

### Grouping

- Models: product, article, group, scenario, recommendation, pipeline.
- Routers: products, articles, groups, recommendations, scenarios, pipeline, config.
- Engine: `engine/core.py`, `constraints.py`, `scoring.py`, `pipeline.py`, `recommendations.py`, `recommendations_v2.py`, `segment.py`, `rebalance.py`.
- Algorithms of interest: grouping candidates, scenario scoring, risk/constraints, preview payloads.
- Incompatibilities: `merge-wb` and transfer endpoints are unsafe; product DB must be replaced by Finance product snapshots.

### Stock/TZostatka

- Models: analysis run, calculation snapshot, article snapshot, warehouse/region mapping, uploaded artifacts.
- Services/calculators: `calculator.py`, `ship_demand.py`, `ship_distribution.py`, `dispatch_from_hand.py`, `store_balance.py`, `analysis_service.py`.
- Algorithms of interest: deficit/excess/region imbalance/store balance/action candidate calculations.
- Incompatibilities: local SQLite/Excel state is not source of truth; Finance stock tables must feed local module runs.

## Current Finance Adapter Gap

The current system has adapters for checker/grouping/stockops/reputation/claims, but most module health is env-driven. A `200` response with `disabled` or `not_configured` means the route contract exists, not that the module is integrated.

The first implemented bridge in this branch is a DB-backed integration registry:

- `portal_integrations`
- `portal_module_sync_runs`

This lets Finance record account-level module state before each module is fully localized.

## Contract And Auth Incompatibilities

- Legacy projects use separate users, shops, stores, teams, roles, billing, and sometimes SQLite/local DBs.
- Finance must map all imported module data to `account_id` and product identifiers such as `nm_id`, `sku_id`, `vendor_code`, and `external_id`.
- Frontend must keep calling Finance `/portal/*`; no direct browser calls to legacy checker/reputation/grouping/claims/stock services.
- Dangerous operations remain draft/preview/confirm only. No auto-publish, submit, merge-wb, card auto-apply, or WB write operation is enabled by module import.
- Legacy payloads containing tokens, headers, encrypted credentials, emails, phones, buyer details, or raw support data must be scrubbed before seller-facing responses.

## Baseline Acceptance State

Not complete yet:

- Checker/Card Quality is not local persisted analysis.
- Reputation is not local Reviews Lite.
- Grouping is not local Beta run/recommendation storage.
- Claims Factory still needs real-data hardening and synthetic audit hiding.
- Stock/TZostatka calculators are not yet fed by Finance stock snapshots.

Complete in this first increment:

- Reality audit of source projects.
- DB-backed account-level module registry foundation.
- Forward-only migration for integration state and module sync runs.
- Registry reads DB state first and falls back to env config.
