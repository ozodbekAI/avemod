import type { PriceSafetyContract } from "@/lib/problem-contracts";

export type PriceSafetyPayload = PriceSafetyContract;

export function priceSafetyFrom(...sources: unknown[]): PriceSafetyPayload | null {
  for (const source of sources) {
    if (!source || typeof source !== "object") continue;
    const candidate = source as Record<string, unknown>;
    const direct = candidate.price_safety;
    if (direct && typeof direct === "object") return direct as PriceSafetyPayload;
    const snapshot = candidate.calculation_snapshot;
    if (snapshot && typeof snapshot === "object" && (snapshot as Record<string, unknown>).price_safety) {
      return (snapshot as Record<string, unknown>).price_safety as PriceSafetyPayload;
    }
  }
  return null;
}

const PRICE_OR_PROMO_ACTIONS = new Set([
  "open_price_review",
  "review_price",
  "pricing_review",
  "open_promo_planner",
  "promo_planner",
  "review_promo",
  "safe_promo",
  "reduce_promo",
  "bundle",
]);

const PRICE_SAFETY_PROBLEM_CODES = new Set([
  "overstock_slow_moving",
  "dead_stock",
  "promo_not_profitable",
  "price_below_safe_margin",
  "negative_unit_profit",
]);

export function priceSafetyNeededFromText(...values: unknown[]): boolean {
  const text = values
    .map((value) => String(value ?? ""))
    .join(" ")
    .toLowerCase();
  return /price|pricing|promo|promotion|discount|liquidat|safe_margin|margin|цена|скид|промо|марж/.test(text);
}

export function priceSafetyNeededForProblem(problem: Record<string, unknown> | null | undefined): boolean {
  if (!problem) return false;
  const payload = problem.payload && typeof problem.payload === "object" ? problem.payload as Record<string, unknown> : {};
  const raw = problem.raw && typeof problem.raw === "object" ? problem.raw as Record<string, unknown> : {};
  const actionList =
    Array.isArray(problem.allowed_actions) ? problem.allowed_actions :
    Array.isArray(payload.allowed_actions) ? payload.allowed_actions :
    Array.isArray(raw.allowed_actions) ? raw.allowed_actions :
    [];
  if (actionList.some((action) => PRICE_OR_PROMO_ACTIONS.has(String(action).toLowerCase()))) return true;
  const problemCodes = [
    problem.problem_code,
    problem.action_type,
    problem.code,
    payload.problem_code,
    payload.action_type,
    raw.problem_code,
    raw.action_type,
  ].map((value) => String(value ?? "").trim().toLowerCase());
  if (problemCodes.some((code) => PRICE_SAFETY_PROBLEM_CODES.has(code))) return true;
  return priceSafetyNeededFromText(
    problem.action_type,
    problem.problem_code,
    problem.code,
    problem.title,
    problem.recommendation,
    problem.next_step,
    problem.what_to_do,
    payload.problem_code,
    payload.recommendation,
    payload.next_step,
    raw.problem_code,
    raw.recommendation,
    raw.next_step,
  );
}
