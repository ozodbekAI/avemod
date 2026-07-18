# Experiments And Results Audit

Generated during Section 11 on 2026-06-25.

## Static Status

Experiments and Results are implemented as a Finance-owned before/after observation system.

- Supported experiment mode is `before_after` / observational. `controlled_split` is explicitly marked unsupported until real assignment and variant data exist.
- Default settings use a 7-day baseline and 7-day post window; the Photo Studio bridge creates photo experiments with a 7-day baseline and 14-day post window.
- Interventions record exact applied time, application mode, before/after references, change summary, and optional sync confirmation.
- Metric snapshots are collected from Finance-owned marts: SKU daily finance, card funnel daily, and stock daily.
- Evaluation writes a `ResultEvent(source_module="experiments", event_type="experiment_evaluated")`.
- Result payloads now preserve sanitized experiment evidence: baseline window, post window, primary result, data sufficiency, confounders, confidence, outcome, evaluation version, and causality note.
- Results UI renders experiment evidence without claiming causality.

## Safety Wording

The canonical wording is:

`Это наблюдаемая связь, а не доказанная причинность.`

Results must stay framed as observed correlation. It is acceptable to say "observed improvement" or "observed worsening"; it is not acceptable to say the intervention caused the outcome.

## Product And Photo Bridge

- Product 360 already receives the product experiment block via `/portal/products/{nm_id}` aggregation.
- Product event history is available through `/portal/products/{nm_id}/events`.
- Approved Photo Studio versions can create an experiment through `/portal/photo/projects/{project_id}/versions/{version_id}/experiment`.
- The frontend approved-version panel exposes "Отслеживать эффект 14 дней" using the Photo bridge.

## Remaining Runtime Proof

- Create a real photo experiment from an approved version and verify the Product 360 experiment block updates.
- Start the experiment and confirm baseline snapshots contain 7 complete days where data exists.
- Record the manual intervention after the WB photo update.
- Wait or backfill the 14-day post window, then evaluate.
- Confirm Results shows the experiment payload, confounders, data sufficiency, and safe causality note.
- Verify stockout and ads-spend confounders trigger low confidence or inconclusive outcomes when appropriate.
