import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "node:test";

const root = resolve(import.meta.dirname, "..");

const read = (path) => readFileSync(resolve(root, path), "utf8");

test("legacy diagnostics stay behind the explicit env flag", () => {
  const legacy = read("src/lib/legacy-diagnostics.ts");

  assert.match(legacy, /VITE_ENABLE_LEGACY_DIAGNOSTICS/);
  assert.match(legacy, /export function legacyDiagnosticsEnabled/);
  assert.match(legacy, /export function canAccessLegacyDiagnostics/);
  assert.match(legacy, /!!isSuperuser && legacyDiagnosticsEnabled\(\)/);
});

test("legacy diagnostics are not shown in seller navigation by default", () => {
  const sidebar = read("src/components/SidebarNavContent.tsx");
  const modules = read("src/components/settings/ModulesHealthSection.tsx");

  assert.match(sidebar, /legacyDiagnosticsNav/);
  assert.match(
    sidebar,
    /legacyDiagnosticsEnabled\(\) \? legacyDiagnosticsNav : \[\]/,
  );
  assert.match(
    modules,
    /def\.key !== "doctor" \|\| legacyDiagnosticsEnabled\(\)/,
  );
});

test("legacy routes require superuser access and the legacy flag", () => {
  for (const path of [
    "src/routes/_authenticated/doctor.tsx",
    "src/routes/_authenticated/cards.index.tsx",
    "src/routes/_authenticated/cards.$nmId.tsx",
  ]) {
    const source = read(path);

    assert.match(source, /canAccessLegacyDiagnostics/);
  }
});
