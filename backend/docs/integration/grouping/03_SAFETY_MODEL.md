# Grouping Beta Safety Model

## Hard Rules

- Grouping Beta is recommendation-only.
- `auto_merge_enabled` is always false.
- Preview payloads include a blocked submit reason.
- Candidate review status is local to Finance.
- No WB write client is called by the local service.

## Default Blockers

- Different account.
- Different brand.
- Different subject/category.
- Conflicting article family.
- Missing identity evidence when required.

## Allowed Local Actions

- Run analysis from Finance product data.
- Store product snapshots for auditability.
- Store candidate groups.
- Accept, reject, postpone, or review a recommendation locally.
- Surface candidate actions in Action Center.

## Disallowed Actions

- `merge-wb`
- destructive card updates
- auto-apply
- hidden marketplace write calls
- claiming revenue/profit impact without measurement
