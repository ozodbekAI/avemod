import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "node:test";

const root = resolve(import.meta.dirname, "..");
const backendRoot = resolve(root, "..", "backend");
const portalService = readFileSync(
  resolve(backendRoot, "app/services/portal.py"),
  "utf8",
);
const portalRouter = readFileSync(
  resolve(backendRoot, "app/modules/portal/router.py"),
  "utf8",
);
const resultTracking = readFileSync(
  resolve(backendRoot, "app/services/result_tracking.py"),
  "utf8",
);

test("backend exposes source-based Action Center updates", () => {
  assert.match(portalRouter, /portal_update_action_by_source/);
  assert.match(portalService, /async def update_action_by_source/);
  assert.match(portalService, /source_sync_state/);
  assert.match(portalService, /shadow_only/);
  assert.match(portalService, /source_updated/);
});

test("backend links dynamic problems to recheck and result ledger", () => {
  assert.match(portalRouter, /portal_recheck_problem_instance/);
  assert.match(portalService, /_problem_instance_actions/);
  assert.match(portalService, /create_problem_completed_event/);
  assert.match(resultTracking, /problem_instance_id/);
  assert.match(resultTracking, /payload=self\._safe_snapshot\(payload\)/);
});
