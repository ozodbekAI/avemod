# Checker Source vs Finance Audit

Date: 2026-07-01

Source of truth: `/home/ozodbek/Projects/wb-optimizer`

Finance target: `/home/ozodbek/AVEMOD_PROJECTS/Finance`

## 2026-07-01 Second Full Pass Update

Additional source UI/backend gaps found and ported in this pass:

- Source `IssueFixPage` is a queue/task workflow, while Finance was only a tabbed product detail. Finance now exposes source-compatible queue adapter endpoints:
  - `GET /portal/card-quality/issues/grouped`
  - `GET /portal/card-quality/issues/queue/next`
  - `GET /portal/card-quality/issues/queue/progress`
- Source fixed-file UI/API was missing from Finance even though fixed-file priority was added to the analyzer. Finance now exposes:
  - `GET /portal/card-quality/fixed-file/status`
  - `GET /portal/card-quality/fixed-file`
  - `POST /portal/card-quality/fixed-file/upload`
- Finance Checker UI now includes source-style fix editor behavior:
  - `swap`, `clear`, and `compound` fix previews from `error_details`
  - editable draft fixed value
  - clickable AI candidates and WB allowed values
  - media issues route to Photo Studio instead of pretending to apply as a field
  - explicit local fix vs explicit WB apply with preview/diff/confirm
  - assign action through Finance Action Center `actions/by-source`
  - visible fixed-file status and Product DNA/visual audit status
- Backend tests/static contracts were extended for:
  - source queue bucket semantics
  - source fixed-file Excel header parsing
  - UI source editor helper presence

## 2026-07-01 Third Pass Update

Additional parity fixes were implemented after the stricter verification report:

- Checker issue ordering now follows source pipeline order across Finance API/UI:
  - backend source-order helper sorts Product360 open issues, Checker issue pages, queue/grouped responses, and Action Center actions;
  - issue payloads expose `source_order`;
  - `checker.$nmId.tsx` uses `sourceOrder()` before severity sorting, so UI no longer overrides backend source order.
- Source final-filter behavior was tightened:
  - compound fixes collapse overlapping child field issues;
  - same-field competing suggestions collapse into one human-check issue with merged candidates/evidence;
  - `description_refresh_needed` is removed when a stronger description issue exists.
- Verification after this pass:
  - targeted backend checker suite: `81 passed, 2 warnings`;
  - frontend build: client and SSR builds passed.

## 1. Source Checker Full Analysis Sequence

Main entrypoint: `/home/ozodbek/Projects/wb-optimizer/app/services/card_service.py:2718`

`analyze_card(db, card, use_ai=True)` works in this order:

1. Preserve user decisions before re-analysis.
   - Reads existing `SKIPPED` / `POSTPONED` issues.
   - Deletes only unresolved `PENDING/SKIPPED/POSTPONED`.
   - Keeps `FIXED/AUTO_FIXED` rows for audit/team metrics.

2. Deterministic base checks.
   - Uses `app/services/analyzer.py` through `card_analyzer.analyze_card(card)`.
   - Keeps media and title/description structural codes only.
   - Adds KIZ issue from WB `needKiz/kizMarked`.

3. WB catalog characteristic validation.
   - Uses `app/services/wb_validator.py::validate_card_characteristics`.
   - Checks allowed values, limits, required chars, wrong category, fixed system fields.
   - Creates `wb_*` issues with `allowed_values`, `charc_id`, `error_details`.

4. Fixed-file priority.
   - Uses `app/services/fixed_file_service.py`.
   - Reads store fixed entries by `store_id + nmID`.
   - Fixed-file mismatch issues are added.
   - Fixed-file controlled characteristic names are excluded from later AI audit.

5. Product DNA generation/cache.
   - Uses `app/services/vision_service.py` or AI provider Product DNA method.
   - Source stores Product DNA on the card: `product_dna`, `product_dna_json`, `product_dna_audit`, status/error/generated_at.
   - Regenerates if missing or weak/not grounded.
   - Only grounded DNA is sent to later AI as trusted text.

6. AI audit of the whole card.
   - Provider: `get_ai_service()` from source, usually Gemini or GPT.
   - Source prompt functions:
     - `GeminiService.audit_card`: `/home/ozodbek/Projects/wb-optimizer/app/services/gemini_service.py:445`
     - `GPTService.audit_card`: `/home/ozodbek/Projects/wb-optimizer/app/services/gpt_service.py:365`
   - Audit receives card JSON, valid characteristic names, fixed-file locked fields, Product DNA or images.
   - AI audit can create visual/text/identification issues and `replace/clear/swap/compound` fix actions.
   - Guards remove date/certificate/vendorCode/allowed-values/color issues from AI audit because those are handled elsewhere.

7. Characteristic AI fix generation first.
   - Source explicitly avoids title/description in batch fixes.
   - Source prompt functions:
     - `GeminiService.generate_fixes`: `/home/ozodbek/Projects/wb-optimizer/app/services/gemini_service.py:642`
     - `GPTService.generate_fixes`: `/home/ozodbek/Projects/wb-optimizer/app/services/gpt_service.py:502`
   - Sends non-text, non-media, non-fixed-file, non-auto-fixed issues.
   - If a visual issue needs photos, source passes image URLs unless trusted Product DNA text is used.

8. AI fix validation and retry.
   - Validates allowed values and min/max limits.
   - Handles `clear/swap/compound` only where destructive fix is allowed.
   - Uses `refix_value` for failed characteristic candidates:
     - Gemini: `/home/ozodbek/Projects/wb-optimizer/app/services/gemini_service.py:777`
     - GPT: `/home/ozodbek/Projects/wb-optimizer/app/services/gpt_service.py:640`
   - Has special color flow:
     - parent color chosen first,
     - children shades selected,
     - final WB palette built.
   - Has salvage/fallback for subset fixes and confirmed values.

9. Description refresh after characteristics.
   - If non-text characteristics need changes and description has no issue, source creates `description_refresh_needed`.

10. Title/description generation after characteristics.
    - Dedicated prompts, not the batch `generate_fixes` prompt.
    - Title:
      - `generate_title`: Gemini `:975`, GPT `:838`
      - `refix_title`: Gemini `:1213`, GPT `:1034`
    - Description:
      - `generate_description`: Gemini `:1092`, GPT `:943`
      - `refix_description`: Gemini `:1285`, GPT `:1085`
    - Validation uses title policy, description policy, factual guards, business regression guards, safe current-title preservation, draft/human-check fallback.

11. Final safety gates and filtering.
    - Drops date issues unless fixed-file.
    - Drops AI issues for fixed-file fields.
    - Collapses compound overlaps and same-field competitors.
    - Applies visual/human-check safety gates.
    - Ensures suggested values only where safe.
    - Strips unverified catalog suggestions.
    - Drops unverified AI issues.
    - Drops no-op issues.
    - Dedupes identical issues.
    - Keeps manual-actionable issues.

12. Super validator and score.
    - Uses `app/services/super_validator.py`.
    - Calculates final score, ready/potential score, Product DNA trust, category scores.
    - Updates card issue counts and `last_analysis_at`.

13. Persist issues.
    - Restores skipped/postponed status from saved map.
    - Commits final issues.

## 2. Source Issue/UI/Apply Sequence

Source issue router: `/home/ozodbek/Projects/wb-optimizer/app/routers/issues.py`

Key endpoints:

- `POST /stores/{store_id}/issues/{issue_id}/fix`: validates manual fixed value, optionally submits WB apply job, then marks fixed.
- `POST /skip`, `POST /unskip`, `POST /postpone`, `POST /assign`.
- Queue endpoints: `/queue/next`, `/queue/progress`.
- Grouped issues split by `actionable`, `human_check`, `media`, `all`.

Source card apply:

- `/home/ozodbek/Projects/wb-optimizer/app/routers/cards.py:781`
- Requires all workflow sections confirmed.
- Builds fresh WB payload, submits WB apply job, does not silently update WB without permission/confirm flow.

Source WB apply:

- `/home/ozodbek/Projects/wb-optimizer/app/services/wb_apply_service.py:271`
- Writes to WB, stores `WbApplyJob`, verifies protected fields and target fields, can roll failed issue apply back to pending.

## 3. Finance Current Checker Sequence

Main entrypoint: `/home/ozodbek/AVEMOD_PROJECTS/Finance/backend/app/services/card_quality.py:855`

`CardQualityAnalysisService.analyze_product()` works in this order:

1. Normalize Finance WB card from Finance tables.
2. If unchanged and not forced, return latest snapshot.
3. Attach Product DNA.
4. Run `CardQualityRuleEngine.analyze()`:
   - title rules,
   - description rules,
   - characteristic rules,
   - WB catalog rules,
   - media rules,
   - identity rules.
5. Load fixed-field values through `_load_fixed_field_values()`.
   - Current implementation returns `{}`.
6. Apply fixed-file priority only if adapter returns values.
7. Run `_apply_ai_fixes()`.
   - Uses only `/home/ozodbek/AVEMOD_PROJECTS/Finance/backend/app/services/checker_core/ai_fixer.py`.
   - One prompt family: `CheckerAIFixer.generate_fixes()`.
8. Validate AI candidate against allowed values/title/description guards.
9. Apply simplified safety gates.
10. Deduplicate.
11. Save snapshot.
12. Sync issues by fingerprint.
13. Create Action Center actions through Finance adapter.

Finance issue endpoints:

- Status patch: `/portal/card-quality/issues/{issue_id}/status`
- Preview: `/portal/card-quality/issues/{issue_id}/preview`
- Fix/apply: `/portal/card-quality/issues/{issue_id}/fix`

## 4. Prompt Comparison

Prompt block that is identical:

- `wb_logic_prompt.py` is effectively identical except import/config path.

Prompt family missing or different in Finance:

1. Source `audit_card` prompt is missing from Finance.
   - Finance does not run AI whole-card audit before fix generation.
   - This means visual/text mismatch issues that source AI audit creates may never be created.

2. Source `generate_fixes` is only partially represented.
   - Finance `CheckerAIFixer._build_prompt()` resembles source `GPTService.generate_fixes`, not the full provider family.
   - Finance uses it for title/description too, while source explicitly generates title/description later with dedicated prompts.

3. Source `refix_value` prompt is missing from Finance.
   - Finance retries by re-calling the same `generate_fixes` prompt with `validation_error`.
   - Source uses a dedicated retry prompt with allowed-values/limits/failure reason.

4. Source `generate_title` and `refix_title` prompts are missing from Finance.
   - Source title prompt has strict 40-60 char, no brand, no gender, no marketing, preserve commercial tokens, business regression fallback.
   - Finance title fixes go through the generic fix prompt.

5. Source `generate_description` and `refix_description` prompts are missing from Finance.
   - Source description prompt has 1000-1800 chars, 3-6 paragraphs, forbidden words, composition guardrail, material factual guards.
   - Finance description fixes go through the generic fix prompt.

6. Source image usage differs.
   - Source prompt calls may pass image URLs when no grounded Product DNA is available.
   - Finance `CheckerAIFixer` is text-only OpenAI chat prompt; it never attaches product photos.

## 5. Characteristic Detection Differences

Mostly copied/compatible:

- `wb_validator.py` is effectively source-compatible except config path.
- `title_policy.py` and `text_policy.py` are effectively source-compatible except config path.

Important missing/different behavior:

1. Source AI audit can create new characteristic issues from visual mismatch.
   - Finance mostly creates characteristic issues from deterministic and WB catalog rules.

2. Source passes valid characteristic names for subject into AI audit.
   - Finance does not have the same AI audit stage.

3. Source handles `swap`, `clear`, `compound` from AI audit/fix.
   - Finance direct AI merge does not port the full compound/swap lifecycle.

4. Source has fixed-file DB service and excludes locked fields before AI audit.
   - Finance has `_load_fixed_field_values()` placeholder returning `{}`.

5. Source color logic has parent color plus child shade selection via AI.
   - Finance `_validate_allowed_value()` only validates/similarity-corrects allowed values; it does not port full color palette expansion.

6. Source has many post-filters:
   - `_strip_unverified_catalog_suggestions`,
   - `_drop_unverified_ai_issues`,
   - `_drop_noop_issues`,
   - `_collapse_compound_overlaps`,
   - `_collapse_same_field_competitors`,
   - `_ensure_all_suggested_values`.
   Finance has a smaller `_finalize_rule_issues()` and `_dedupe_rule_issues()`.

## 6. Status/Reanalysis Differences

Source:

- Saves skipped/postponed before deleting unresolved rows.
- Recreates current issues and restores skipped/postponed by restore key.
- Keeps fixed/auto-fixed rows.
- Issue statuses are source-specific: `pending`, `fixed`, `auto_fixed`, `skipped`, `postponed`, `applied_to_wb`, etc.

Finance:

- Uses issue fingerprint upsert/reopen/resolve.
- Preserves `postponed`, `ignored`, `done`, `blocked`.
- This matches Finance architecture better, but the exact source delete/recreate/restore behavior is not the same.

## 7. Apply Behavior Differences

Source:

- `fix` can optionally create a WB apply job.
- Card-level apply requires workflow sections confirmed.
- WB job is verified after submit.
- Failed apply can roll local fixed issue back to pending.
- Media apply has its own verification and re-analysis path.

Finance:

- Local fix and explicit WB apply are now separated.
- Preview/confirm exists.
- But full source card workflow section confirmation and WB apply job verification model are not fully ported.

## 8. Highest-Priority Port Gaps

1. Port source AI audit stage into Finance before generic AI fixes.
2. Port source prompt family, not only `generate_fixes`:
   - `audit_card`,
   - `refix_value`,
   - `generate_title`,
   - `generate_description`,
   - `refix_title`,
   - `refix_description`,
   - color shade picker if color issues are in scope.
3. Change Finance analysis order to source order:
   deterministic base → WB catalog → fixed file → Product DNA → AI audit → characteristic fixes → title/description generation → final gates/filters → score.
4. Implement Finance fixed-file adapter instead of returning `{}`.
5. Port source characteristic post-processing:
   swap/clear/compound, no-op filtering, visual risky gates, unverified catalog strip, unverified AI drop.
6. Integrate source super-validator into Finance scoring.
7. Expand Finance status endpoints/UI to include skip/unskip/postpone/assign queue semantics, mapped to Finance Action Center without drift.
8. Port source contract/regression tests around prompts and analysis order.
