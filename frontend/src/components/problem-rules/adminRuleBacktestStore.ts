/**
 * Lightweight external store used to share the last admin rule
 * backtest between ProblemRulesAdminPanel and sibling preview
 * surfaces in the admin route. Read-only for consumers.
 */
import { useSyncExternalStore } from "react";
import type { RuleBacktestResponse } from "@/lib/problem-rules";

type Snapshot = {
  backtest: RuleBacktestResponse | null;
  ruleVersionId: number | null;
};

let snapshot: Snapshot = { backtest: null, ruleVersionId: null };
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

export function setAdminRuleBacktest(
  backtest: RuleBacktestResponse | null,
  ruleVersionId: number | null,
) {
  snapshot = { backtest, ruleVersionId };
  emit();
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

function getSnapshot(): Snapshot {
  return snapshot;
}

export function useAdminRuleBacktest(): Snapshot {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
