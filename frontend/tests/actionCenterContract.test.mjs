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
const status = readFileSync(
  resolve(root, "src/lib/action-center-status.ts"),
  "utf8",
);

test("Action Center contract keeps evidence, source sync and result links", () => {
  assert.match(contract, /export interface ActionCenterItem/);
  assert.match(contract, /source_sync_state/);
  assert.match(contract, /evidence_ledger/);
  assert.match(contract, /allowed_actions/);
  assert.match(contract, /can_execute: boolean/);
  assert.match(contract, /can_execute: canExecute/);
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
  assert.match(page, /Что сделать: рекламная утечка денег/);
  assert.match(page, /ActionCenterDataHealthBanner/);
  assert.match(page, /ScenarioCoveragePanel/);
  assert.match(page, /Покрытие сценариев V1/);
  assert.match(page, /Эффект\/риск/);
  assert.doesNotMatch(page, /Потенциальный эффект/);
  assert.match(page, /dataFreshnessBlocksAction/);
  assert.match(page, /if \(dataFreshnessBlocksAction\(item\.data_freshness\)\) return "blocked"/);
  assert.match(page, /item\.can_execute === true/);
  assert.doesNotMatch(page, /Действие пока открывается в отдельном разделе/);
  assert.doesNotMatch(page, /можно сделать здесь/);
  assert.match(page, /Перепроверить/);
});

test("Action Center keeps 48 audited V1 scenarios visible", () => {
  const start = page.indexOf("const ACTION_CENTER_V1_SCENARIO_CATALOG");
  const end = page.indexOf("function problemGroupKey");
  const catalog = page.slice(start, end);
  const ids = [...catalog.matchAll(/\bid:\s*"([^"]+)"/g)].map(
    (match) => match[1],
  );
  assert.ok(start > -1 && end > start, "V1 scenario catalog is present");
  assert.equal(new Set(ids).size, 48);
  assert.match(catalog, /profit_dropped_wow/);
  assert.match(catalog, /regional_distribution/);
  assert.match(catalog, /profitable_campaign_underfunded/);
  assert.match(catalog, /repeated_defect_batch_size/);
});

test("Action Center does not mark checker content opportunities urgent", () => {
  assert.match(status, /export function isContentQualityOpportunityAction/);
  assert.match(
    status,
    /if \(isContentQualityOpportunityAction\(a\)\) return false/,
  );
});

test("Action Center top money metric deduplicates repeated product signals", () => {
  assert.match(page, /function dedupedImpactSummary/);
  assert.match(page, /businessCaseKey\(item\) \?\? `action:\$\{item\.id\}`/);
  assert.match(page, /Math\.max\(byObject\.get\(key\) \?\? 0, amount\)/);
  assert.match(page, /label="Оценка без дублей"/);
  assert.match(page, /Без повторных сигналов, до сверки WB/);
  assert.doesNotMatch(
    page,
    /const overviewMoneyAtStake = problemGroups\.reduce/,
  );
});

test("Action Center overview shows business cases instead of raw signal storage", () => {
  assert.match(page, /function buildBusinessCases/);
  assert.match(page, /const workCases = useMemo/);
  assert.match(page, /label="В фокусе сегодня"/);
  assert.match(page, /Топ кейсов на сегодня/);
  assert.match(page, /buildBusinessCaseGroups\(workCases\)/);
  assert.match(page, /Кейсы по категориям/);
  assert.match(page, /readyCaseCount/);
  assert.match(page, /signalCountLabel\(caseItem\.count\)/);
});

test("Action Center keeps deep-linked problem groups while data is loading", () => {
  assert.match(
    page,
    /selectedGroupKey &&\s*!isLoading &&\s*problemGroups\.length > 0 &&\s*!problemGroups\.some/,
  );
  assert.match(page, /navigateActionCenter\(filters, key, false\)/);
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
  assert.match(groupKey, /code === "ad_pause_review"[\s\S]*return "ads_promo"/);
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
