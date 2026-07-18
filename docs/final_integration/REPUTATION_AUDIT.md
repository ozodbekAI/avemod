# Reputation Audit

Section 07 scope: local Finance module for reviews, questions, chats, sync runs, inbox, summary, classification, draft, edit, regenerate, approve, reject, no-reply, safe publish, settings, Product 360, Actions, Doctor, and Results.

## Static Evidence

- Local persistence lives in `reputation_items` and `reputation_settings`.
- Local service lives in `backend/app/services/reputation.py`.
- Legacy/read-only compatibility adapter lives in `backend/app/services/reputation_adapter.py`.
- Portal endpoints live in `backend/app/modules/portal/router.py` under `/portal/reputation/*`.
- Frontend route is `/reputation` and now calls local sync, inbox, draft lifecycle, no-reply, and guarded publish endpoints.
- Result events are written for publish attempts and no-reply decisions, then surfaced by the Results module.

## Flow Coverage

| Flow | Local Status | Evidence |
| --- | --- | --- |
| reviews | Implemented | WB content sync fetches feedbacks; inbox filters `item_type=review`; actions for negative unanswered reviews |
| questions | Implemented | WB content sync fetches questions; inbox filters `item_type=question`; question drafts use local draft type |
| chats | Degraded but isolated | chats report `not_configured`; missing chat token/config does not disable reviews/questions |
| sync runs | Implemented | `PortalModuleSyncRun(module="reputation")`, per-source status in sync response |
| inbox | Implemented | `/portal/reputation/inbox` with type/status/rating/sentiment/priority/nm/date filters |
| summary | Implemented | `/portal/reputation/summary` counts unanswered reviews/questions/chats, negative unanswered, drafts, rating |
| classification | Implemented | adapter normalizes sentiment, priority, status, needs_reply |
| draft | Implemented | `/items/{item_id}/draft`, local `OperatorDraft`, manual text override supported |
| edit | Implemented through manual draft text payload and regenerate | local draft body is persisted in Finance |
| regenerate | Implemented | `/drafts/{draft_id}/regenerate` |
| approve | Implemented | `/drafts/{draft_id}/approve`, local approval only |
| reject | Implemented | `/drafts/{draft_id}/reject` |
| no-reply | Implemented | `/items/{item_id}/no-reply-needed`, writes local result event |
| safe publish | Guarded | requires manager role, `confirm=true`, approved draft, WB content token, and `ENABLE_REPUTATION_PUBLISH=true` |
| settings | Implemented | `/portal/reputation/settings`; automation and auto-publish forced off |
| Product 360 | Implemented | local `ReputationService.product_360()` populates item list and next action |
| Actions | Implemented | local `reputation_actions()` emits actionable reply tasks |
| Legacy profit diagnostics | Implemented | Legacy profit diagnostics receive local reputation signals |
| Results | Implemented | publish/no-reply decisions create `ResultEvent(source_module="reputation")` |

## Safety

- Safe publish is disabled by default via `ENABLE_REPUTATION_PUBLISH=false`.
- Frontend can request publish only for an approved draft, but backend remains authoritative and blocks unsafe states.
- Local settings force `automation_enabled=false`, `auto_publish_enabled=false`, and `chat_auto_reply_enabled=false`.
- Adapter and local schemas scrub private fields and WB tokens from responses.
- Reviews/questions can be operational while chats are unavailable; chat absence is represented as a per-source degraded state, not a module-wide disable.

## Runtime Proof Still Needed

Runtime verification requires a real account with a WB content token and reputation source rows.

Run:

```bash
cd backend
python -m compileall -q app tests scripts alembic
pytest -q tests/unit/test_reputation_service.py tests/unit/test_reputation_adapter.py tests/unit/test_reputation_section07_static.py tests/unit/test_result_tracking_service.py
```

Then with a real account:

1. Call `POST /api/v1/portal/reputation/sync` and record `per_source_status` for reviews, questions, and chats.
2. Call `GET /api/v1/portal/reputation/inbox?item_type=review`, `question`, and `chat`.
3. Call `GET /api/v1/portal/reputation/summary`.
4. Generate, regenerate, approve, reject, and no-reply a safe test item.
5. Attempt publish without confirm and with publish flag disabled; both must be blocked.
6. Verify Product 360 reputation block, Action Center reputation actions, Doctor reputation signals, and Results reputation events.

## Legacy Parity Notes

The old Reputation ZIP parity is covered at contract level through `ReputationAdapter.SAFE_REFERENCE_ENDPOINTS`: reviews/feedbacks, questions, chats, sync, draft, publish, no-reply, settings, and draft management. Exact payload parity still needs a sanitized legacy fixture/output comparison.
