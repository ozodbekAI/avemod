import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const copy = readFileSync(resolve(root, "src/lib/problem-ux-copy.ts"), "utf8");
const resultCopy = readFileSync(
  resolve(root, "src/lib/problem-results.ts"),
  "utf8",
);

assert.match(copy, /PROBLEM_SEVERITY_LABELS/);
assert.match(copy, /PROBLEM_STATUS_LABELS/);
assert.match(copy, /PROBLEM_TRUST_LABELS/);
assert.match(copy, /SEEDED_PROBLEM_SELLER_COPY/);
assert.match(copy, /EVIDENCE_BUTTON_LABEL = "Как посчитано\?"/);
assert.doesNotMatch(copy, /Customer|Revenue loss|Fix now/);
assert.match(resultCopy, /PROBLEM_RESULT_CORRELATION_DISCLAIMER/);
assert.match(resultCopy, /не доказывает причинность/);

console.log("Problem UX copy contract passed");
