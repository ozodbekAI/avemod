// Prompt 1 (Etap 3): honest trust logic.
// Backend "trusted" state alone is not enough — downgrade to provisional
// if any business-level risk is open.

import type { MMoneySummary, DataTrustStateT } from "./api";

export type EffectiveTrustState = "trusted" | "provisional" | "blocked";

export type TriStatus = "ok" | "warn" | "bad" | "unknown";

export interface ThreeStatuses {
  business: { status: TriStatus; label: string; hint: string };
  finance: { status: TriStatus; label: string; hint: string };
  cost: { status: TriStatus; label: string; hint: string };
}

export interface EffectiveTrust {
  state: EffectiveTrustState;
  /** Backend's raw trust_state (for badges still reading the original). */
  rawState: DataTrustStateT;
  /** Honest business copy for the AnswerCard / banners. */
  shortLine: string;
  /** Reasons we downgraded (in addition to backend blocked_reasons). */
  downgradeReasons: string[];
  /** True if green badges/copy must not be shown. */
  forbidGreen: boolean;
  /** Three separate statuses for the top banner. */
  three: ThreeStatuses;
}

const SUPPLIER_COVERAGE_THRESHOLD = 95;
const UNALLOCATED_HIGH_ABS = 1000;

export function computeEffectiveTrust(s: MMoneySummary | null | undefined): EffectiveTrust {
  const raw: DataTrustStateT = (s?.meta.data_trust?.state ?? "test_only") as DataTrustStateT;
  const blockedReasons = s?.meta.data_trust?.blocked_reasons ?? [];
  const k = s?.kpis;

  const supplierPct = k?.supplier_cost_confirmed_revenue_percent ?? null;
  const unalloc = Number(k?.unallocated_expenses ?? 0);
  const adsAlloc = String(k?.ads_allocation_status ?? "");
  const financeMismatch = Number(k?.finance_mismatch_abs ?? 0) > 0
    || /mismatch|critical/i.test(String(k?.finance_reconciliation_status ?? ""));

  const downgradeReasons: string[] = [];

  if (supplierPct != null && supplierPct < SUPPLIER_COVERAGE_THRESHOLD) {
    downgradeReasons.push(`supplier_cost_coverage_${Math.round(supplierPct)}pct`);
  }
  if (unalloc > UNALLOCATED_HIGH_ABS) {
    downgradeReasons.push("unallocated_expenses_present");
  }
  if (adsAlloc && adsAlloc !== "linked" && adsAlloc !== "no_ads" && adsAlloc !== "article_level_only") {
    downgradeReasons.push(`ads_${adsAlloc}`);
  }
  if (blockedReasons.length > 0) {
    downgradeReasons.push(
      ...blockedReasons.filter((reason) => {
        const code = String(reason ?? "").toLowerCase();
        return !["finance_reconciliation_mismatch", "finance_without_sale", "sale_without_finance"].includes(code);
      }),
    );
  }

  let state: EffectiveTrustState;
  if (raw === "data_blocked") {
    state = "blocked";
  } else if (raw === "trusted" && downgradeReasons.length === 0) {
    state = "trusted";
  } else {
    state = "provisional";
  }

  // Business / Finance / Cost three statuses
  const businessAccepted = raw !== "data_blocked";
  const business: ThreeStatuses["business"] = businessAccepted
    ? { status: "ok", label: "Бизнес-данные приняты", hint: "Можно принимать операционные решения" }
    : { status: "bad", label: "Бизнес-данные не приняты", hint: "Сначала почините блокеры данных" };

  const finance: ThreeStatuses["finance"] = financeMismatch
    ? { status: "warn", label: "Финансы: автосверка WB", hint: "Система сверяет sales/orders с finance WB; ручных действий нет" }
    : raw === "trusted"
      ? { status: "ok", label: "Финансы закрыты", hint: "Сверка с финансовым отчётом сошлась" }
      : { status: "warn", label: "Финансы предварительные", hint: "Финансовый отчёт ещё не подтверждён" };

  const cost: ThreeStatuses["cost"] = supplierPct == null
    ? { status: "unknown", label: "Себестоимость: нет данных", hint: "Покрытие подтверждённой себестоимостью неизвестно" }
    : supplierPct >= SUPPLIER_COVERAGE_THRESHOLD
      ? { status: "ok", label: `Себестоимость подтверждена (${Math.round(supplierPct)}%)`, hint: "Покрытие подтверждённой себестоимостью ≥ 95%" }
      : supplierPct >= 50
        ? { status: "warn", label: `Себестоимость частично (${Math.round(supplierPct)}%)`, hint: "Подтвердите себестоимость по остальным карточкам" }
        : { status: "bad", label: `Себестоимость не подтверждена (${Math.round(supplierPct)}%)`, hint: "Загрузите реальную себестоимость поставщика" };

  const shortLine =
    state === "blocked"
      ? "Сначала исправьте данные — бизнес-рекомендации ограничены."
      : state === "trusted"
        ? "Данные готовы для управления и финальная прибыль подтверждена."
        : "Операционно управлять можно, но финальная прибыль предварительная.";

  return {
    state,
    rawState: raw,
    shortLine,
    downgradeReasons: Array.from(new Set(downgradeReasons)),
    forbidGreen: state !== "trusted",
    three: { business, finance, cost },
  };
}

// ─── Shared normalizer ────────────────────────────────────────────────────
// Pages read trust signals from three different shapes depending on the
// endpoint:
//   • data.trust           — e.g. /money/articles[*], /money/cards[*]
//   • data.meta.data_trust — e.g. /money/summary, /money/cards/{id}
//   • top-level data       — e.g. /dashboard/data-health, /dashboard/owner
// This helper unifies them so every page reads the SAME field names.
//
// Important: businessTrusted/operationalTrusted means "operational decisions
// are allowed". It does NOT imply financialFinal — final profit confirmation
// is a strictly stronger signal and must be read from financialFinal alone.

export interface NormalizedTrust {
  operationalTrusted: boolean;
  businessTrusted: boolean;
  financialFinal: boolean;
  trustState: string | null;
  costTrustPolicy: string | null;
  supplierConfirmedCoverage: number | null;
  operatorBaselineCoverage: number | null;
  finalBlockers: number | null;
}

function firstDefined<T>(...vals: (T | null | undefined)[]): T | null {
  for (const v of vals) if (v !== undefined && v !== null) return v;
  return null;
}

function toNum(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

const BLOCKED_STATES = new Set(["data_blocked", "blocked", "test_only"]);
const FINAL_STATES = new Set(["final", "financial_final"]);

export function normalizeTrust(data: any): NormalizedTrust {
  const empty: NormalizedTrust = {
    operationalTrusted: false,
    businessTrusted: false,
    financialFinal: false,
    trustState: null,
    costTrustPolicy: null,
    supplierConfirmedCoverage: null,
    operatorBaselineCoverage: null,
    finalBlockers: null,
  };
  if (!data || typeof data !== "object") return empty;

  const trust = (data.trust ?? {}) as any;
  const metaTrust = (data.meta?.data_trust ?? {}) as any;
  const k = (data.kpis ?? {}) as any;

  const trustStateRaw = firstDefined<string>(
    trust.trust_state, trust.state,
    metaTrust.state, metaTrust.trust_state,
    data.trust_state,
  );
  const trustState = trustStateRaw ? String(trustStateRaw) : null;

  const bt = firstDefined<boolean>(
    trust.business_trusted, metaTrust.business_trusted, data.business_trusted,
  );
  const businessTrusted = bt === true
    ? true
    : bt === false
      ? false
      : trustState
        ? !BLOCKED_STATES.has(trustState)
        : false;

  const ff = firstDefined<boolean>(
    trust.financial_final, metaTrust.financial_final,
    data.financial_final, k.financial_final,
  );
  const financialFinal = ff === true
    ? true
    : ff === false
      ? false
      : trustState
        ? FINAL_STATES.has(trustState)
        : false;

  const costTrustPolicy = firstDefined<string>(
    trust.cost_trust_policy, metaTrust.cost_trust_policy,
    data.cost_trust_policy, data.cost_truth_level, k.cost_truth_level,
  );

  const supplierConfirmedCoverage = toNum(firstDefined(
    trust.supplier_confirmed_coverage, metaTrust.supplier_confirmed_coverage,
    data.supplier_confirmed_coverage,
    data.supplier_confirmed_revenue_coverage_percent,
    data.supplier_cost_confirmed_revenue_percent,
    k.supplier_confirmed_revenue_coverage_percent,
    k.supplier_cost_confirmed_revenue_percent,
    k.supplier_cost_coverage_percent,
  ));

  const operatorBaselineCoverage = toNum(firstDefined(
    trust.operator_baseline_coverage, metaTrust.operator_baseline_coverage,
    data.operator_baseline_coverage,
    data.operator_baseline_cost_coverage_percent,
    k.operator_baseline_coverage,
  ));

  const finalBlockers = toNum(firstDefined(
    trust.final_blockers, trust.financial_final_blockers_total,
    metaTrust.final_blockers, metaTrust.financial_final_blockers_total,
    data.final_blockers, data.financial_final_blockers_total,
    k.financial_final_blockers_total,
  ));

  return {
    operationalTrusted: businessTrusted,
    businessTrusted,
    financialFinal,
    trustState,
    costTrustPolicy: costTrustPolicy ? String(costTrustPolicy) : null,
    supplierConfirmedCoverage,
    operatorBaselineCoverage,
    finalBlockers,
  };
}
