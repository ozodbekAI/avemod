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
  assert.match(page, /ActionDecisionResolutionPanel/);
  assert.match(page, /Решить здесь: рекламная утечка денег/);
  assert.doesNotMatch(page, /Действие пока открывается в отдельном разделе/);
  assert.match(page, /Перепроверить/);
});

test("Action Center grouping keeps JVO-style review tasks in their business domains", () => {
  const start = page.indexOf("function problemGroupKey");
  const end = page.indexOf("function isMissingCostProblem");
  const groupKey = page.slice(start, end);
  assert.ok(start > -1 && end > start, "problemGroupKey source is present");
  assert.equal(
    groupKey.includes('text.includes("review")'),
    false,
    "generic review must not route price/ads/card review tasks to reputation",
  );
  assert.equal(
    groupKey.includes('text.includes("ad_")'),
    false,
    "generic ad_ substring must not route dead_stock to ads",
  );
  assert.match(
    groupKey,
    /code === "price_increase_review"[\s\S]*return "price"/,
  );
  assert.match(
    groupKey,
    /code === "ad_pause_review"[\s\S]*return "ads_promo"/,
  );
  assert.match(
    groupKey,
    /code === "card_content_review"[\s\S]*return "card_quality"/,
  );
  assert.ok(
    groupKey.indexOf('code === "ad_spend_without_sku"') <
      groupKey.indexOf('code === "ad_pause_review"'),
    "SKU/data blockers are classified before ad optimization tasks",
  );
  assert.match(
    groupKey,
    /code === "fix_cost_trust"[\s\S]*return "data_blockers"/,
  );
});
