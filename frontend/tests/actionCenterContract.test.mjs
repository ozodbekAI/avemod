import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "node:test";

const root = resolve(import.meta.dirname, "..");
const contract = readFileSync(
  resolve(root, "src/lib/action-center-contract.ts"),
  "utf8",
);
const actions = readFileSync(
  resolve(root, "src/lib/action-center-actions.ts"),
  "utf8",
);
const page = readFileSync(
  resolve(root, "src/components/action-center/ActionCenterPageContainer.tsx"),
  "utf8",
);

test("Action Center contract keeps evidence, source sync and result links", () => {
  assert.match(contract, /export interface ActionCenterItem/);
  assert.match(contract, /source_sync_state/);
  assert.match(contract, /evidence_ledger/);
  assert.match(contract, /allowed_actions/);
  assert.match(contract, /money_trust/);
  assert.match(actions, /export function resultsHrefForAction/);
  assert.match(actions, /export function guidedFixHref/);
  assert.match(actions, /problem_instance_id/);
});

test("Action Center page wires source updates and evidence controls", () => {
  assert.match(page, /useActionCenterMutations/);
  assert.match(page, /updateActionBySource/);
  assert.match(page, /EvidenceDrawer/);
  assert.match(page, /EvidenceButton/);
  assert.match(page, /ActionCenterHistoryTimeline/);
  assert.match(page, /Перепроверить/);
});
