import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "node:test";

const root = resolve(import.meta.dirname, "..");
const checkerDetail = readFileSync(
  resolve(root, "src/routes/_authenticated/checker.$nmId.tsx"),
  "utf8",
);
const portalApi = readFileSync(resolve(root, "src/lib/portal.ts"), "utf8");

test("checker hides unconfirmed AI suggestions from local apply flow", () => {
  assert.match(
    checkerDetail,
    /issue\?\.requires_human_check !== true[\s\S]*issue\?\.can_accept_local !== false[\s\S]*issue\?\.has_confirmed_suggestion === true/,
  );
  assert.match(
    checkerDetail,
    /\.\.\.\(canShowAiSuggestion \? \[issue\?\.ai_suggested_value\] : \[\]\)/,
  );
  assert.match(
    checkerDetail,
    /\.\.\.\(canShowAiSuggestion \? \[issue\?\.expected_value_json\] : \[\]\)/,
  );
  assert.match(checkerDetail, /issue\?\.ai_alternatives/);
  assert.match(checkerDetail, /issue\?\.alternatives/);
  assert.match(
    checkerDetail,
    /\["candidate", "draft_text"\]\.includes\(suggestionKind\)/,
  );
  assert.match(checkerDetail, /function issueCanApply/);
});

test("checker only renders apply for confirmed locally acceptable fixes", () => {
  assert.match(
    checkerDetail,
    /function issueCanApplyValue\(issue: any, value: string\)/,
  );
  assert.match(
    checkerDetail,
    /issueCanApply\(issue\)[\s\S]*\["human_check_requires_manual_review", "fixed_value_required"\]/,
  );
  assert.match(
    checkerDetail,
    /Boolean\(effectiveSuggested\) && issueCanApplyValue\(issue, effectiveSuggested\)/,
  );
  assert.match(checkerDetail, /issue\?\.requires_human_check === true/);
  assert.match(checkerDetail, /\{suggested && canApply \? \(/);
  assert.doesNotMatch(checkerDetail, /Исправить вручную/);
});

test("checker issue recheck is wired to backend endpoint", () => {
  assert.match(checkerDetail, /const recheckIssueMutation = useMutation/);
  assert.match(
    checkerDetail,
    /return recheckCardQualityIssue\(id, activeId\);/,
  );
  assert.match(
    portalApi,
    /API_ENDPOINTS\.portal\.cardQualityIssueRecheck\(issueId\)/,
  );
});

test("checker product detail has card-level recheck progress", () => {
  assert.match(checkerDetail, /Перепроверить карточку/);
  assert.match(checkerDetail, /CheckerAnalysisProgress/);
  assert.match(checkerDetail, /Идет проверка карточки/);
  assert.match(
    checkerDetail,
    /analyzeProductCardQuality\(nmId, activeId, \{ force \}\)/,
  );
});

test("checker list keeps rows clickable without an extra open-checker button", () => {
  const checkerList = readFileSync(
    resolve(root, "src/routes/_authenticated/checker.index.tsx"),
    "utf8",
  );
  assert.match(checkerList, /<Link\s+to="\/checker\/\$nmId"/);
  assert.doesNotMatch(
    checkerList,
    /Открыть checker|Открыть чекер|Open checker|Открыть карточку/,
  );
});

test("checker fixed-file upload is wired to backend endpoint", () => {
  const fixedFilePage = readFileSync(
    resolve(root, "src/routes/_authenticated/checker.fixed-file.tsx"),
    "utf8",
  );
  assert.match(portalApi, /export const uploadCardQualityFixedFile/);
  assert.match(portalApi, /export const fetchCardQualityFixedFileEntries/);
  assert.match(portalApi, /export const updateCardQualityFixedFileEntry/);
  assert.match(portalApi, /export const downloadCardQualityFixedFile/);
  assert.match(portalApi, /API_ENDPOINTS\.portal\.cardQualityFixedFileUpload/);
  assert.match(
    fixedFilePage,
    /uploadCardQualityFixedFile\(activeId, file, replaceAll\)/,
  );
  assert.match(fixedFilePage, /type="file"[\s\S]*accept="\.xlsx,\.xls,\.xlsm"/);
  assert.match(fixedFilePage, /<Table[\s\S]*<TableHeader[\s\S]*sticky top-0/);
});

test("checker detail does not render empty AI suggestion boxes", () => {
  assert.match(
    checkerDetail,
    /effectiveSuggested[\s\S]*\? "md:grid-cols-\[1fr_28px_1fr\]"[\s\S]*: "md:grid-cols-1"/,
  );
  assert.match(
    checkerDetail,
    /\{effectiveSuggested \? \([\s\S]*<SuggestionValueBox[\s\S]*\) : null\}/,
  );
  assert.doesNotMatch(checkerDetail, /value=\{effectiveSuggested \|\| "—"\}/);
});
