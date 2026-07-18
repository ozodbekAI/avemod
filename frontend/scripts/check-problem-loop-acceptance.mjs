import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const fixture = readFileSync(
  resolve(root, "src/product-acceptance/problem-loop.acceptance.fixtures.ts"),
  "utf8",
);

const scenarios = [
  "actionCenterDynamicProblemDrawer",
  "productDoctorGroupedIssue",
  "dataFixLinkedIssue",
  "evidenceDrawerSellerMode",
  "estimatedVsConfirmedMoneyStyling",
  "adminRuleBuilderNoCode",
];

for (const scenario of scenarios) {
  assert.match(
    fixture,
    new RegExp(`\\b${scenario}\\b`),
    `${scenario} fixture is required`,
  );
}

for (const step of [
  "Проблема",
  "доказательства",
  "действие",
  "статус",
  "повторная проверка",
  "результат",
]) {
  assert.match(fixture, new RegExp(step), `${step} loop label is required`);
}

console.log("Problem loop acceptance fixtures passed");
