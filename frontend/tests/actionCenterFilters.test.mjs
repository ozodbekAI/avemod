import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "node:test";

const root = resolve(import.meta.dirname, "..");
const filters = readFileSync(
  resolve(root, "src/lib/action-center-filters.ts"),
  "utf8",
);

test("Action Center filters preserve saved views and deep links", () => {
  assert.match(filters, /ACTION_CENTER_DEFAULT_FILTERS/);
  assert.match(filters, /ACTION_CENTER_SAVED_VIEWS/);
  assert.match(filters, /actionCenterStateFromSearch/);
  assert.match(filters, /actionCenterSearchFromState/);
  assert.match(filters, /actionCenterMatchesProblemInstanceDeepLink/);
});

test("Action Center filters support urgency, blockers and result sorting", () => {
  assert.match(filters, /actionCenterIsUrgent/);
  assert.match(filters, /actionCenterIsDataBlocker/);
  assert.match(filters, /actionCenterMatchesFilters/);
  assert.match(filters, /sortActionCenterItems/);
  assert.match(filters, /buildActionCenterDailyDigest/);
  assert.match(filters, /buildActionCenterWeeklySummary/);
});
