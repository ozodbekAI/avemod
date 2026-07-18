import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const src = resolve(root, "src");

const read = (path) => readFileSync(path, "utf8");

function files(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    const stat = statSync(path);
    if (stat.isDirectory()) {
      if (["node_modules", "dist", ".screenshots"].includes(entry)) continue;
      files(path, out);
    } else if (/\.(ts|tsx|js|jsx|mjs)$/.test(entry)) {
      out.push(path);
    }
  }
  return out;
}

const endpoints = read(resolve(src, "lib/endpoints.ts"));
const portal = read(resolve(src, "lib/portal.ts"));

const requiredEndpointTokens = [
  "cardQualityProducts",
  "cardQualityProductRecheck",
  "cardQualityIssueAcceptLocal",
  "cardQualityIssueMarkFixed",
  "cardQualityIssueDraft",
  "cardQualityIssueApplyWb",
  "cardQualityIssueRecheck",
];

for (const token of requiredEndpointTokens) {
  assert.match(
    endpoints,
    new RegExp(`\\b${token}\\b`),
    `API_ENDPOINTS.portal.${token} is required`,
  );
  assert.match(
    portal,
    new RegExp(`API_ENDPOINTS\\.portal\\.${token}\\b`),
    `portal.ts must call API_ENDPOINTS.portal.${token}`,
  );
}

const invalidBareApiPaths = [
  "/cards",
  "/sku",
  "/data-fix",
  "/finance",
  "/operations",
  "/pricing",
  "/purchase-plan",
  "/ads/summary",
  "/analytics/overview",
  "/catalog/cards",
  "/costs/coverage",
  "/dq/summary",
  "/sync/status",
];

const offenders = [];
for (const file of files(src)) {
  const text = read(file);
  const rel = relative(root, file);
  if (
    ["src/lib/api.ts", "src/lib/endpoints.ts", "src/routeTree.gen.ts"].includes(
      rel,
    )
  ) {
    continue;
  }
  for (const path of invalidBareApiPaths) {
    const literal = path.replaceAll("/", "\\/");
    const hardcodedApiCall = new RegExp(
      `\\bapi(?:List)?(?:<[^>]+>)?\\s*\\(\\s*["'\`]${literal}["'\`]`,
      "m",
    );
    if (hardcodedApiCall.test(text)) {
      offenders.push(`${rel} calls backend with bare API path ${path}`);
    }
  }
}

assert.deepEqual(offenders, [], offenders.join("\n"));
console.log("MVP API contract check passed");
