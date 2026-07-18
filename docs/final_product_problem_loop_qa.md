# Final Product Problem Loop QA

Date: 2026-07-08

This checklist verifies that one dynamic product problem keeps the same identity
and story across Action Center, Product360, Results and Data Fix.

Core story:

`Проблема -> доказательства -> действие -> статус/история -> повторная проверка -> результат`

## Automated Checks

Run from `frontend/`:

```bash
npx playwright test e2e/action-center-professional.spec.ts --project=desktop -g "same dynamic problem"
npm run test:action-center-contract
npm run test:problem-loop
```

Run from `backend/`:

```bash
../.venv/bin/python -m pytest -q tests/unit/test_product_problem_loop_acceptance_static.py
```

The Playwright cross-surface test attaches these screenshots to the test report:

- `action-center-task-drawer`
- `results-problem-timeline`
- `product360-problem-preview`

Fixture used by the cross-surface test:

- product: `nmID 245405620`, vendor code `SKU-DEMO`;
- dynamic problem: `problem_instance_id=42`, `problem_code=low_stock_risk`;
- data blocker: `problem_instance_id=43`, `problem_code=missing_cost_blocks_profit`;
- all result events use `saved_money_claimed=false`.

## Manual QA Prerequisites

Use a seller or manager account with:

- dynamic problem rules enabled;
- at least one product with a fresh dynamic problem;
- evidence ledger populated for the problem;
- Action Center, Product360, Results and Data Fix enabled;
- cost data missing only when testing the Data Fix blocker path.

Keep the same product and the same `problem_instance_id` for the whole check.

## Manual Checklist

1. Evaluate a dynamic problem for one product.
   Expected: the backend creates or refreshes one `problem_instance` with a
   stable `problem_instance_id`, `problem_code`, `nm_id`, status and evidence.

2. Open Action Center.
   Expected: the problem appears as one task. The seller should not see a
   duplicate legacy doctor/card for the same problem.

3. Check the Action Center row.
   Expected: row shows severity, source, trust badge, impact badge, evidence
   state, status, assignee/deadline state and result badge.

4. Open evidence with `Как посчитано?`.
   Expected: evidence shows formula, input facts, source table or endpoint, date
   range, row count when available, missing data, trust notes and warnings.
   Seller mode must not show raw JSON.

5. Open the task drawer with `Открыть задачу`.
   Expected: the drawer title and product identity match the row.

6. Assign an owner.
   Expected: assignee is saved and remains visible after refresh.

7. Set a deadline.
   Expected: deadline is saved and row SLA state updates.

8. Change status to `В работе` and add a comment.
   Expected: status changes to `in_progress`, comment is saved and history gets
   a status/comment event.

9. Refresh the page and reopen the task.
   Expected: status, assignee, deadline, comment and history still match the
   saved values.

10. Click `Перепроверить`.
    Expected: re-check event appears in history/result timeline. Status may move
    to resolved or reopened according to rule logic.

11. Mark the task `Выполнено`.
    Expected: an `action_completed` result event appears.

12. Check result wording.
    Expected: the result section can show before/action/re-check/after
    comparison, but it must not call expected impact `сэкономлено` unless
    measured after-data and confidence are shown.

13. Open Product360 for the same product.
    Expected: `Проблемы товара` shows the same problem title, status, last status
    change, re-check state, result badge, evidence button and `Открыть задачу`
    link.

14. Follow Product360 -> Action Center.
    Expected: the link opens Action Center filtered to the same
    `problem_instance_id`.

15. Open Results from Action Center.
    Expected: Results opens with `problem_instance_id`, `problem_code`, `nm_id`
    and `source_module=problem_engine`; the title is the problem title, not
    `Result #N`, and the timeline reads as before/action/re-check/after.

16. Open Data Fix when the same product has a data blocker.
    Expected: Data Fix shows the blocker in seller-readable language and links
    back to the exact Action Center task/result ledger. Raw IDs are secondary
    or admin-only.

QA passes when the product owner can start from any page and still understand
that it is the same problem, with the same status, evidence and result story.
