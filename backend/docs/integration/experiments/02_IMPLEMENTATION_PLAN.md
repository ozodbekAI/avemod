# Experiments Implementation Plan

Implemented phase 1:

1. Add local experiment, intervention, metric snapshot, evaluation, and settings tables.
2. Add portal schemas and endpoints for settings, CRUD, start, intervention recording, metrics, evaluation, and events.
3. Freeze baseline snapshots from real Finance marts before intervention.
4. Record exact intervention timestamp and scrub before/after references.
5. Collect post-window snapshots idempotently and evaluate before/after changes.
6. Write completed evaluations to `result_events` with `source_module="experiments"`.
7. Add Product 360 `experiments` block.
8. Register a daily scheduler job for due evaluations.

Deferred:

- Real controlled split assignment and statistical comparison.
- Rich Action Center task generation for every experiment state.
- Photo/Pricing/Ads prefill endpoints.
- Seasonality and promotion detection beyond explicit metric/confounder warnings.

