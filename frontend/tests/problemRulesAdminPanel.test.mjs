import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "node:test";

const root = resolve(import.meta.dirname, "..");
const panel = readFileSync(
  resolve(root, "src/components/problem-rules/ProblemRulesAdminPanel.tsx"),
  "utf8",
);

test("Problem Rules admin keeps no-code seller-safe controls", () => {
  assert.match(panel, /VisualFormulaBuilder/);
  assert.match(panel, /ProblemRuleCreateWizard/);
  assert.match(panel, /Расширенный режим/);
  assert.match(panel, /JSON только для технических администраторов/);
  assert.match(panel, /Оценка влияния по типу и доверию/);
  assert.match(panel, /Карточки продавца/);
  assert.match(panel, /data-admin-rule-seller-card-preview/);
});

test("Problem Rules admin exposes validation blockers", () => {
  assert.match(panel, /no_backtest/);
  assert.match(panel, /no_evidence/);
  assert.match(panel, /price_safety/);
  assert.match(panel, /too_many_matches/);
  assert.match(panel, /test_only/);
});
