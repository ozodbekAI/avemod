# Experiments Evaluation Model

Phase 1 evaluates `before_after` experiments only.

For each metric:

- baseline window snapshots are frozen before intervention;
- post window snapshots are collected after `intervention_at + evaluation_delay_days`;
- absolute and relative changes are calculated;
- lower-is-better metrics invert outcome direction.

Outcome rules:

- `not_enough_data`: post orders or revenue below account settings, or no usable primary metric.
- `inconclusive`: high-severity confounder such as excessive stockout days.
- `improved`: primary metric moves by at least 5% in the good direction and guardrails do not invalidate the result.
- `worse`: primary metric moves by at least 5% in the bad direction.
- `neutral`: movement is inside the 5% practical band.

Controlled split:

- Returns `not_supported`/`inconclusive` until real split assignment and variant-level metric data exist.
- No simulated split or fake statistical significance is allowed.

All before/after seller summaries include:

```text
Это наблюдаемая связь, а не доказанная причинность.
```

