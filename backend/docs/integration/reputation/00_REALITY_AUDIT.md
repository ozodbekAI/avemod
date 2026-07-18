# Reputation Reality Audit

Date: 2026-06-21

## Current Finance Surface

- Public portal routes already exist under `app/modules/portal/router.py` for `/portal/reputation/*`.
- `PortalService` owns account-scoped routing and RBAC checks.
- `ReputationAdapter` normalized the old external service shape, but depended on `REPUTATION_BASE_URL`.
- Finance already owns reusable operator tables: `operator_drafts`, `unified_actions`, `result_events`, `portal_integrations`, and `portal_module_sync_runs`.
- WB token storage is Finance-owned through `wb_api_tokens`; there is no separate reputation auth boundary.

## Incoming Backend 7 Reference

Useful source concepts from `_incoming_projects/backend (7) .zip`:

- `Feedback`, `Question`, `ChatSession`, `ChatEvent`, `FeedbackDraft`, `QuestionDraft`, `ChatDraft`.
- WB feedback/question client endpoints under `feedbacks-api.wildberries.ru`.
- Shop settings fields for tone, signature, templates, automation, and auto publish.
- Draft/publish flow patterns.

Excluded from Finance runtime:

- Legacy `User`, `Shop`, `ShopMember`, JWT/auth, billing, credits, payments, team invites, and separate public API.

## Finance Decision

Reputation is now a local Finance module for item/settings persistence and portal contracts. Reviews/questions sync use the Finance WB content token. Chats remain per-source `not_configured` until a Finance-owned token/API category is available. Marketplace writes remain blocked unless manual confirm, manager/admin RBAC, approved draft, and `ENABLE_REPUTATION_PUBLISH=true` are all satisfied.

