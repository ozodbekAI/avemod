# Checker 1:1 Verification Report

Generated: 2026-07-01

Source of truth: `/home/ozodbek/Projects/wb-optimizer`

Finance target: `/home/ozodbek/AVEMOD_PROJECTS/Finance`

This report implements the requested read-only audit plan. Code was inspected with
line references, the latest existing Finance snapshot for `account_id=1`,
`nm_id=268593818` was read with SELECT-only queries, and targeted tests/build were
run. No Checker business code was changed while producing this report.

## 2026-07-01 Implementation Update

After the read-only audit, two high-impact parity gaps were fixed in Finance:

1. **Issue/UI order now follows source pipeline order.**
   - Backend issue APIs now sort by source checker order before severity.
   - Product360, Checker UI, queue/grouped issues, and Action Center use the same source-order helper.
   - Issue payloads expose `source_order`, and the Checker UI uses it before `severityRank`.

2. **Final filter chain is closer to source behavior.**
   - Compound fixes now collapse overlapping field issues.
   - Same-field competing issues now collapse into one human-check issue with merged candidates/evidence.
   - `description_refresh_needed` is dropped when a stronger description issue exists.

Verification after patch:

```text
backend/.venv/bin/pytest ...checker targeted suite... -q
81 passed, 2 warnings in 2.76s

cd frontend && npm run build
client build: passed
ssr build: passed
```

## Executive Verdict

Finance Checker is now closer to source than the previous audit described, but it
is still not honestly provable as byte-for-byte/pixel-for-pixel 1:1.

The current backend contains source-compatible adapters for the main lifecycle:
deterministic basic rules, WB catalog validation, fixed-file priority, Product
DNA, AI audit, AI fixes, dedicated title/description fixes, safety gates,
fingerprint-based reanalysis preservation, preview/fix/apply endpoints, Product
360 integration, and Action Center integration.

Remaining strict 1:1 risks:

1. Prompt behavior is source-like, but prompt parity is contract-level, not
   byte-for-byte across Gemini/GPT provider families.
2. Final filter chain now includes source compound/same-field/description-refresh
   collapse behavior, but the full source unverified catalog/AI strip helpers are
   still not byte-for-byte copied.
3. Apply-to-WB is safe by default and explicit, but Finance does not yet mirror
   the full source `WbApplyJob` verification/rollback model.
4. UI has the source essential workflow, but it is not a pixel/route 1:1 copy of
   source `CardDetailPage.tsx` and `IssueFixPage.tsx`.

## Source Pipeline Map

| Step | Source Evidence | Input | Output/Guard |
|---|---|---|---|
| Preserve user decisions before reanalysis | `app/services/card_service.py:2718`, skipped map around `:2750`, restore around `:4350` | Existing `CardIssue` rows | Restores skipped/postponed by `_issue_restore_key`; fixed rows stay available |
| Deterministic basic rules | `app/services/card_service.py:2776`, `app/services/analyzer.py:137` | Card title, description, photos, videos | Ordered source rules: title, photos, description, few photos, description length/policy, title length, video |
| WB catalog validation | `app/services/card_service.py:2835`, `app/services/wb_validator.py:864` | Raw WB card characteristics | Required/allowed/limits/wrong-category/fixed-field issues |
| Fixed file priority | `app/services/card_service.py:2886` | Store fixed-file rows + WB card | Fixed-file mismatch wins; AI issues for locked chars are dropped |
| Product DNA | `app/services/card_service.py:2921`, `app/services/gemini_service.py:930` | Product photos and category | Grounded/weak/failed/disabled visual audit state; photo is analyzed once and reused |
| AI whole-card audit | `app/services/card_service.py:3148`, `app/services/gemini_service.py:445` | Compact card, valid category chars, Product DNA/photos | Adds visual/text/category issues; must not decide allowed_values |
| AI fixes for characteristics | `app/services/card_service.py:3401`, retry around `:3710` | Current issue set, Product DNA/photos | Generates exact fixes/candidates/no-safe-fix, validates allowed values/limits, retries with `refix_value` |
| Dedicated title fixes | `app/services/card_service.py:3934`, retry around `:3951`, prompt at `app/services/gemini_service.py:975` | Title context, SEO keywords, Product DNA/photos | 40-60 char title, no brand/gender/marketing, business guard and fallback |
| Dedicated description fixes | `app/services/card_service.py:4162`, retry around `:4183`, prompt at `app/services/gemini_service.py:1092` | Description context, confirmed facts, Product DNA/photos | 1000-1800 chars, factual/material guard, forbidden words, no human-check leakage |
| Final safety/filter chain | `app/services/card_service.py:4322-4341` plus helpers at `:810`, `:934`, `:951`, `:1816`, `:1875`, `:1970`, `:4389`, `:4443`, `:4488` | Full issue set | Date drop, fixed-file AI exclusion, compound collapse, business safety, suggested values, unverified AI/catalog drops, no-op drop, dedupe |
| Super validator + persist | `app/services/card_service.py:4360` | Final source issues | Final score/counts/status and issue persistence |

## Finance Pipeline Map

| Step | Finance Evidence | Match | Impact |
|---|---|---|---|
| Entrypoint | `backend/app/services/card_quality.py:1134` | equivalent adapter | Uses Finance auth/account/WB card tables and snapshots |
| Skip unchanged unless forced | `backend/app/services/card_quality.py:1145-1155` | Finance-specific intentional | Source analyzes a `Card`; Finance preserves portal cache conventions |
| Basic deterministic rules | `backend/app/services/card_quality.py:522`, `_source_basic_rules` at `:544` | partial/exact core | Rule order is source-like inside engine, but persisted UI order can drift |
| WB catalog rules | `_wb_catalog_rules` at `backend/app/services/card_quality.py:884`, resolver at `backend/app/services/checker_core/wb_validator.py:851`, validator at `:875` | equivalent adapter | Source WB validator behavior is ported through Finance data-path adapter |
| Fixed-file priority | `_load_fixed_field_values` at `:1386`, `_apply_fixed_file_priority` at `:1626`, upload/status APIs at `:3011`, `:3055` | equivalent adapter | Finance DB model replaces source store fixed-file service |
| Product DNA | `_attach_product_dna` at `:1347`, vision service under `backend/app/services/checker_core/vision_service.py` | equivalent adapter | Disabled/no-photo/failure reasons are visible through summary JSON |
| AI audit | `_apply_ai_audit` at `:1400`, `CheckerAIFixer.audit_card` at `backend/app/services/checker_core/ai_fixer.py:141` | partial | Stage exists, but provider/telemetry is Finance OpenAI adapter, not full source Gemini/GPT service family |
| AI fixes | `_apply_ai_fixes` at `:1687`, `_merge_ai_fix` at `:2218`, prompt at `ai_fixer.py:596` | partial | Contract is close; full source retry/provider behavior needs broader snapshot tests |
| Title/description fixes | `_apply_text_ai_fixes` at `:1789`, title at `:1849`, description at `:1899`, prompts at `ai_fixer.py:333`, `:419`, refix at `:491`, `:533` | equivalent adapter | Dedicated prompts exist; source business/factual guards are present through validators |
| Super validator | `_score_with_super_validator` at `backend/app/services/card_quality.py:1996` | equivalent adapter | Finance returns source-style category/ready/potential scores inside portal schema |
| Final gates/dedupe | `_finalize_rule_issues`, `_collapse_compound_overlaps`, `_collapse_same_field_competitors`, `_collapse_description_refresh_overlaps`, `_apply_safety_gates`, `_dedupe_rule_issues` | partial/equivalent adapter | Source collapse helpers are now ported; unverified catalog/AI strip helpers remain contract-level |
| Persist/reanalysis | `_sync_issues` at `:3524`, restore statuses at `:3542`, reopen at `:3633`, resolve at `:3650` | equivalent adapter | Preserves Finance status model; not identical to source delete/recreate ordering |
| Status API | router at `backend/app/modules/portal/router.py:813`, service at `card_quality.py:3423`, canonical statuses at `:3497` | equivalent adapter | Uses Finance statuses: new/in_progress/done/postponed/ignored/blocked/resolved |
| Preview/fix/apply | router at `:844`, `:872`; service at `card_quality.py:3105`, `:3139` | partial | Default local-only is correct; full source WB job verification is not mirrored |
| Action Center | `quality_actions` at `card_quality.py:2789`, `_action_from_issue` at `:3811`, portal tests | equivalent adapter | Checker issues are exposed as Finance portal actions |

## Evidence Matrix

| Area | Source | Finance | Match | Impact | Fix Required | Test |
|---|---|---|---|---|---|---|
| Full lifecycle | `analyze_card` order at `card_service.py:2718` | `analyze_product` order at `card_quality.py:1134` | partial/equivalent adapter | Main stages exist; source-order sorting and source collapse filters are now patched | Add pipeline-order trace test comparing source step names to Finance step names | New `test_checker_pipeline_order_contract.py` |
| Deterministic validation order | `card_service.py:2776`, `analyzer.py:137` | `_source_basic_rules` and source-order API/UI sorting | equivalent adapter | UI/API now use source pipeline order before severity | Keep source-order static/unit tests | Added unit/static tests |
| WB validator | `wb_validator.py:864` | `checker_core/wb_validator.py:875` | equivalent adapter | Finance path resolver changed, behavior ported | Keep contract tests against required/allowed/limits/wrong-category | Existing `test_checker_parity_wbchecker_contract.py` |
| Fixed-file correction priority | `card_service.py:2886` | `_load_fixed_field_values` `:1386`, `_apply_fixed_file_priority` `:1626` | equivalent adapter | Finance uses its own DB model | Add end-to-end fixed-file priority test with AI issue on locked char | New integration test |
| Product DNA generation | `card_service.py:2921`, `gemini_service.py:930` | `_attach_product_dna` `:1347` | equivalent adapter | Disabled/no-photo/failure surfaced; provider differs | Contract-test grounded/weak/disabled states in API and UI | Existing product DNA tests + UI static test |
| Product DNA prompt usage | Source passes Product DNA to audit/fix/title/description | Finance passes `normalized.product_dna_text` to AI audit/fix/text fix | equivalent adapter | Correct when grounded; if disabled, Finance returns disabled reason | Add prompt-call-order test with fake AI recorder | New test |
| AI audit | `card_service.py:3148`, `gemini_service.py:445` | `_apply_ai_audit` `:1400`, `ai_fixer.audit_card` `:141` | partial | Audit exists, but not full source provider implementation | Snapshot source prompt contract and exact field/category mapping | New prompt snapshot tests |
| AI prompt contracts | `gemini_service.py` and `gpt_service.py` prompt family | `ai_fixer.py` prompt family | partial | Finance has source clauses but no byte-for-byte parity proof | Snapshot prompts for all seven prompt methods | Expand `test_checker_parity_prompt_contract.py` |
| AI fix validation/retry | `generate_fixes`, `refix_value`, retry at `card_service.py:3710` | `_apply_ai_fixes`, `_validated_ai_candidate`, `refix_value` in `ai_fixer.py:263` | partial | Validation exists; retry loop needs explicit source-count parity proof | Add fake AI sequence test: invalid fix then refix | New regression test |
| Human-check safety | Source forces candidate/draft/no_safe_fix to manual | `_merge_ai_fix` `:2218`, `_validated_ai_candidate` and schema `suggestion_kind` | equivalent adapter | Human-check issues are not auto-applied by default | Keep default no-WB/human-check tests | Existing visual/default tests |
| Visual risky gates | Source helpers around `card_service.py:951` | `_apply_safety_gates` `:2384`, visual tests | equivalent adapter | Product DNA/visual evidence is required before safe autofix | Add API evidence for disabled Product DNA reason | Existing visual tests + new API assertion |
| Title business guard | Source around `card_service.py:3934` and policy helpers | `_generate_title_fix` `:1849`, guard in `_validated_ai_candidate` | equivalent adapter | Unsafe/regressive titles become human-check/no safe fix | Existing title guard tests |
| Description factual guard | Source around `card_service.py:4162` and text policy | `_generate_description_fix` `:1899`, guard in `_validated_ai_candidate` | equivalent adapter | Unsupported factual claims should not auto-apply | Existing description guard tests |
| Characteristic validation | Source WB validator + AI category map `card_service.py:4771` | `_map_ai_issue_category` `:1554`, WB rules `:884` | partial | Qualification now maps to characteristics, but color shade expansion is not full source | Add color/qualification/wrong-category parity tests | New characteristic integration tests |
| Duplicate/no-op unsafe filtering | Source helpers `:4319-4341`, `:4443`, `:4488` | Finance final filters now collapse compound overlaps, same-field competitors, description refresh overlaps, then safety/dedupe | partial/equivalent adapter | Biggest duplicate/competitor UI noise is patched; unverified catalog/AI strip remains not byte-for-byte | Port remaining source strip/drop helpers or snapshot known edge cards | Added edge tests; more fixtures still needed |
| Issue fingerprint/dedup/reopen | Source restore key at `card_service.py:434`/`:4350` | fingerprint at `card_quality.py:763`, sync at `:3524` | equivalent adapter | Finance preserves status better for portal, but exact issue IDs/order differ | Add reanalysis status preservation integration test | Existing status tests + new DB integration |
| Status behavior | Source statuses include pending/fixed/skipped/postponed/applied_to_wb | Finance statuses new/in_progress/done/postponed/ignored/blocked/resolved | Finance-specific intentional | Finance common status model is preserved | Keep bidirectional status mapping docs/tests | Portal Action Center contract tests |
| Re-analysis preservation | Source restores skipped/postponed only | Finance preserves postponed/ignored/done/blocked | equivalent adapter | Matches product rule of not losing user decisions; extends source safely | Add forced reanalysis test for skipped/postponed/done/ignored | New integration test |
| Default fix behavior | Source `test_issue_fix_default_no_wb_apply.py` | Finance schema default `apply_to_wb=False` in `card_quality.py`/schema | exact | Default does not write to WB | Keep default-no-WB test | Existing visual/default tests |
| Apply-to-WB | Source `wb_apply_service.py` with `WbApplyJob`, verification, rollback | Finance preview/fix endpoints `:3105`, `:3139` | partial | User is not misled, but no full source verification job model | Implement Finance-compatible apply job audit or mark as intentional adapter | New apply confirm/verification tests |
| Product360 sync | Source card detail embeds issues | Finance Product360 card section at `frontend/src/routes/_authenticated/products.$nmId.tsx:545` | equivalent adapter | Product360 can show and mutate Checker status | Add Product360/Checker status drift test | New frontend/API test |
| Action Center sync | Source issue task flow | Finance `quality_actions` and portal action patch tests | equivalent adapter | Checker issues appear and update through Action Center | Keep `test_portal_action_center_contract.py` | Passing |
| UI audit flow | Source `CardDetailPage.tsx:291`, `IssueFixPage.tsx:216` | Finance `checker.$nmId.tsx:504`, toolbar `:973`, workspace `:1054`, source-order UI sort | partial/equivalent adapter | Essential workflow exists and issue order now follows source; visual/route 1:1 is not proven | Add Playwright screenshots and DOM contract states | Static source-order test added; Playwright still needed |

## Prompt-by-Prompt Audit

| Prompt | Source Evidence | Finance Evidence | Match | Notes |
|---|---|---|---|---|
| `audit_card` | `gemini_service.py:445`, source call `card_service.py:3148` | `ai_fixer.py:141`, Finance call `card_quality.py:1400` | partial | Same role/output style and Product DNA/photo split, but Finance provider is OpenAI adapter |
| `generate_fixes` | `gemini_service.py:642`, `gpt_service.py` equivalent | `ai_fixer.py:250`, `_build_prompt` `:596` | partial | Required clauses for allowed values, free fields, human-check, no-safe-fix are present |
| `refix_value` | `gemini_service.py:783`, `gpt_service.py:646` | `ai_fixer.py:263` | partial | Exists; needs fake-AI retry sequence test to prove order/count |
| `generate_title` | `gemini_service.py:975`, `gpt_service.py` equivalent | `ai_fixer.py:333`, service call `card_quality.py:1856` | equivalent adapter | Dedicated title prompt exists with source guardrails |
| `refix_title` | `gemini_service.py:1213` | `ai_fixer.py:491`, service call `card_quality.py:1871` | partial | Exists, but Finance prompt is shorter than source main title prompt |
| `generate_description` | `gemini_service.py:1092`, source call `card_service.py:4162` | `ai_fixer.py:419`, service call `card_quality.py:1906` | equivalent adapter | Dedicated description prompt exists with factual/forbidden-word guardrails |
| `refix_description` | `gemini_service.py:1285` | `ai_fixer.py:533`, service call `card_quality.py:1922` | partial | Exists, but exact source provider retry behavior needs contract snapshots |

Required prompt proof still missing: generated prompt snapshots for all seven
methods compared against source fixtures. Current tests assert critical clauses,
not full prompt text or call sequence.

## UI Audit

| Flow | Source UI | Finance UI | Match | Gap |
|---|---|---|---|---|
| Card audit entry | `CardDetailPage.tsx:291` | `checker.$nmId.tsx:504`, analyze mutation `:542` | equivalent adapter | Finance route is `/checker/$nmId`, not source route |
| Queue/progress | `IssueFixPage.tsx:601`, progress badges around `:1002` | toolbar `checker.$nmId.tsx:973`, queue progress `:1020` | equivalent adapter | Needs screenshot parity states |
| Issue list/detail | `IssueFixPage.tsx:296`, sidebar/status sections | `SourceTabWorkspace` `checker.$nmId.tsx:1054`, detail/action panes around `:1684` | partial | Layout is source-inspired, not identical |
| Fix editor | Source draft/editor flow around `IssueFixPage.tsx:365-450` and card inline fixes | Finance draft panel around `checker.$nmId.tsx:1710-1871` | equivalent adapter | Human-check and allowed-values chips present |
| Skip/unskip/postpone/assign | Source skip/unskip/assign around `IssueFixPage.tsx:545`, `:725`, `:770` | Finance status/assign mutations `checker.$nmId.tsx:550`, `:618`, handlers `:936-940` | equivalent adapter | Finance status names differ by architecture |
| Local fix | Source default no WB apply test | Finance local fix mutation sets `apply_to_wb:false` at `checker.$nmId.tsx:576-579` | exact | Button/title now communicates local-only |
| Apply-to-WB confirm | Source `WbApplyJob` flow and apply UI | Finance preview before fix at `checker.$nmId.tsx:590-602`, apply button `:1928` | partial | Explicit preview/confirm exists; source verification job missing |
| Product DNA/disabled/error states | Source visual audit state | Finance product DNA panel around `checker.$nmId.tsx:493-499`, `:1629` | equivalent adapter | Needs browser assertions for disabled reason |
| Product360 link/status | Source card detail issue integration | Finance Product360 section `products.$nmId.tsx:545` | equivalent adapter | Needs drift test after Action Center mutation |

## Real Card Evidence

Card read: `account_id=1`, `nm_id=268593818`.

Read mode: SELECT-only from latest existing Finance snapshot. No new analysis was
triggered for this report.

Latest Finance snapshot:

| Field | Value |
|---|---|
| Snapshot id | `4348` |
| Analyzed at | `2026-07-01T12:43:46.582237+00:00` |
| Source revision | `3f89677f808ccb21de376f3b2ff19ac2e4c4bbb6313e846cd4f1b565b479c5a8` |
| Score/status | `26` / `critical` |
| Product DNA | `enabled=true`, `status=grounded` |
| Issue count | `47` |
| Human-check count | `40` |
| Statuses present | `done`, `new`, `resolved` |
| Sources present | `ai`, `code` |

Observed first issue codes in persisted UI/DB order:

```text
title_policy_violation
description_policy_violation
wb_qualification
wb_qualification
wb_qualification
wb_qualification
wb_qualification
wb_qualification
wb_qualification
wb_qualification
wb_qualification
wb_qualification
wb_qualification
wb_allowed_values
wb_limit
wb_wrong_category
wb_allowed_values
wb_allowed_values
media_too_few_images
media_no_video_info
ai_text
ai_photo
ai_photo
ai_text
title_too_short
few_photos
description_too_short
description_policy_violation
no_video
ai_text
```

Original interpretation from the read-only snapshot:

- Product DNA is active and grounded.
- AI issues and WB characteristic issues are being created.
- Human-check safety is heavily used, which matches the source safety posture.
- The persisted DB order was not source pipeline order. This has now been fixed
  at API/UI presentation level with `source_order` sorting, so old row IDs no
  longer force WB/AI issues ahead of source basic issues in Checker/Product360.

## Verification Results

Backend targeted parity/contract run:

```text
backend/.venv/bin/pytest \
  backend/tests/unit/test_card_quality_service.py \
  backend/tests/unit/test_checker_status_only_ui_static.py \
  backend/tests/unit/test_checker_parity_prompt_contract.py \
  backend/tests/unit/test_checker_parity_visual_review_semantics.py \
  backend/tests/unit/test_checker_parity_text_title_guards.py \
  backend/tests/unit/test_checker_parity_product_dna_contract.py \
  backend/tests/unit/test_checker_parity_wbchecker_contract.py \
  backend/tests/api/test_portal_action_center_contract.py -q

81 passed, 2 warnings in 2.76s
```

Frontend build:

```text
npm run build

client build: passed
ssr build: passed
warning: some chunks are larger than 500 kB
```

## Required Fixes To Reach Strict 1:1

| Priority | Required Fix | Why | Lock Test |
|---|---|---|---|
| P0 | Add pipeline trace recorder in Finance tests for one fake card | Proves exact source step order instead of inferring from code | `test_checker_pipeline_order_contract.py` |
| Done | Deterministic source-order sorting for Checker issue API/UI | Latest real card showed persisted order mismatch | Added source-order unit/static tests |
| P0 | Snapshot all seven prompt methods against source fixtures | Current prompt tests check clauses, not full contracts | `test_checker_prompt_snapshots.py` |
| P1 | Port/align remaining final filter helpers: unverified catalog strip, unverified AI drop, stricter no-op drop | Compound overlap, same-field competitors, and description refresh overlap are now ported | More edge-card regression tests |
| P1 | Add fake-AI retry tests for invalid `generate_fixes` output followed by `refix_value/title/description` | Confirms retry order and validation behavior | `test_checker_ai_retry_sequence.py` |
| P1 | Implement Finance-compatible WB apply job verification or explicitly document intentional adapter | Source has `WbApplyJob` verification/rollback; Finance only previews and explicit-applies | Apply confirm/verification/rollback tests |
| P1 | Add reanalysis preservation DB test for postponed/ignored/done/blocked | Finance extends source skipped/postponed model | `test_checker_reanalysis_preserves_user_decisions.py` |
| P2 | Add Playwright screenshot/DOM parity tests for Checker UI states | UI is source-inspired but not visually proven 1:1 | `checker-ui.spec.ts` |
| P2 | Add Product360 <-> Checker <-> Action Center drift integration test | Ensures Finance product rule status never drifts | API integration test |

## Acceptance Status

| Acceptance Criteria | Status |
|---|---|
| Same type of issues/fixes/explanations/safety decisions | partial pass |
| Source prompt behavior preserved | partial pass |
| Finance Checker no longer simplified copy | pass |
| Prompt sequence matches source | partial, needs call-order test |
| Apply/draft behavior not misleading | pass for UI/API labels and defaults |
| No fake apply-to-WB remains | pass for default local-only; partial for full source verification |
| UI shows essential Checker workflow | pass for essential flow; partial for visual 1:1 |
| Action Center receives Checker issues | pass |
| Backend targeted tests pass | pass: 75 passed |
| Frontend build passes | pass |

Bottom line: Finance now has a source-compatible Checker adapter, but the audit
does not support claiming "100% 1:1" yet. The main blockers are persisted
issue/UI order, prompt snapshot proof, exact final filter chain parity, and full
source-compatible WB apply verification.
