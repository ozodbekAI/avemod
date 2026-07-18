// @ts-nocheck
import type { ProblemResultEvent } from "@/lib/portal";
import {
  problemResultCanClaimSavedMoney,
  problemResultHasAfterData,
} from "@/lib/problem-results";

export type ResultOutcomeKey =
  | "pending_data"
  | "improved"
  | "worse"
  | "neutral"
  | "not_enough_data";

export type ResultTrustKey = "confirmed" | "estimated" | "unknown";

const OUTCOME_ALIASES: Record<string, ResultOutcomeKey> = {
  improved: "improved",
  better: "improved",
  positive: "improved",
  success: "improved",
  worse: "worse",
  degraded: "worse",
  negative: "worse",
  regressed: "worse",
  neutral: "neutral",
  no_change: "neutral",
  unchanged: "neutral",
  same: "neutral",
  pending: "pending_data",
  pending_data: "pending_data",
  waiting_data: "pending_data",
  awaiting_data: "pending_data",
  not_enough_data: "not_enough_data",
  no_data: "not_enough_data",
  insufficient_data: "not_enough_data",
  missing_data: "not_enough_data",
  blocked: "not_enough_data",
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === "object" && !Array.isArray(v);
}

export function classifyOutcome(event: unknown): ResultOutcomeKey {
  const e = isRecord(event) ? event : {};
  const raw = String(
    e.outcome ?? e.result_status ?? e.status ?? "",
  ).toLowerCase();
  const mapped = OUTCOME_ALIASES[raw];
  if (mapped) {
    if (
      (mapped === "improved" || mapped === "worse" || mapped === "neutral") &&
      !problemResultHasAfterData(e)
    ) {
      return "pending_data";
    }
    return mapped;
  }
  if (problemResultHasAfterData(e)) return "neutral";
  return "pending_data";
}

export function classifyTrust(event: unknown): ResultTrustKey {
  const e = isRecord(event) ? event : {};
  const c = String(e.confidence ?? e.confidence_label ?? "").toLowerCase();
  if (["high", "confirmed", "высокая", "высокий"].includes(c))
    return "confirmed";
  if (typeof e.confidence === "number") {
    const n = Number(e.confidence);
    if (Number.isFinite(n)) {
      const pct = Math.abs(n) <= 1 ? n * 100 : n;
      if (pct >= 75) return "confirmed";
      if (pct > 0) return "estimated";
    }
  }
  if (
    ["medium", "mid", "low", "средняя", "средний", "низкая", "низкий"].includes(
      c,
    )
  )
    return "estimated";
  return "unknown";
}

export function needsRecheck(event: unknown): boolean {
  const e = isRecord(event) ? event : {};
  const type = String(e.event_type ?? "").toLowerCase();
  if (type.includes("recheck")) return true;
  const outcome = classifyOutcome(event);
  return outcome === "pending_data";
}

export function isMeasuredEffect(event: unknown): boolean {
  return problemResultCanClaimSavedMoney(event);
}

export function measuredAmount(event: unknown): number | null {
  if (!isMeasuredEffect(event)) return null;
  const e = isRecord(event) ? event : {};
  const raw = e.delta_amount ?? e.effect_amount ?? e.amount;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

export type ResultSummaryCounts = {
  pending_data: number;
  improved: number;
  worse: number;
  neutral: number;
  not_enough_data: number;
  measured_amount: number;
  measured_count: number;
};

export function computeSummaryCounts(items: unknown[]): ResultSummaryCounts {
  const counts: ResultSummaryCounts = {
    pending_data: 0,
    improved: 0,
    worse: 0,
    neutral: 0,
    not_enough_data: 0,
    measured_amount: 0,
    measured_count: 0,
  };
  for (const item of items) {
    const key = classifyOutcome(item);
    counts[key] += 1;
    const amount = measuredAmount(item);
    if (amount != null) {
      counts.measured_count += 1;
      counts.measured_amount += amount;
    }
  }
  return counts;
}
