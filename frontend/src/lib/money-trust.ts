export type MoneyTrustState =
  | "confirmed"
  | "provisional"
  | "estimated"
  | "opportunity"
  | "test_only"
  | "blocked"
  | string;

export type MoneyImpactKind =
  | "confirmed_loss"
  | "probable_loss"
  | "probable_risk"
  | "blocked_cash"
  | "lost_sales_risk"
  | "opportunity"
  | "estimated_opportunity"
  | "blocked_revenue"
  | "data_blocker"
  | "data_blocked"
  | "system_warning"
  | "test_only"
  | "informational"
  | string;

export interface MoneyTrustInfo {
  state: MoneyTrustState;
  impact_kind: MoneyImpactKind;
  display_label: string;
  amount_label: string;
  show_as_confirmed_money?: boolean;
  seller_visible_by_default?: boolean;
  reason?: string;
  evidence_trust_state?: MoneyTrustState | null;
  impact_trust_state?: MoneyTrustState | null;
  saved_money_claimed?: boolean;
  [key: string]: unknown;
}

const STATE_FALLBACK_LABEL: Record<string, { display_label: string; amount_label: string; impact_kind: string }> = {
  confirmed: { display_label: "Подтверждено", amount_label: "Подтверждённые деньги", impact_kind: "informational" },
  provisional: { display_label: "Предварительно", amount_label: "Вероятный риск", impact_kind: "probable_risk" },
  estimated: { display_label: "Оценка", amount_label: "Оценочная возможность", impact_kind: "estimated_opportunity" },
  opportunity: { display_label: "Возможность", amount_label: "Возможность роста", impact_kind: "opportunity" },
  test_only: { display_label: "Тестовое правило", amount_label: "Не деньги продавца", impact_kind: "test_only" },
  blocked: { display_label: "Не хватает данных", amount_label: "Не хватает данных", impact_kind: "data_blocker" },
};

const IMPACT_FALLBACK_LABEL: Record<string, { display_label: string; amount_label: string; impact_kind: string }> = {
  confirmed_loss: { display_label: "Подтверждённый убыток", amount_label: "Подтверждённый убыток", impact_kind: "confirmed_loss" },
  probable_loss: { display_label: "Вероятный убыток", amount_label: "Вероятный убыток", impact_kind: "probable_loss" },
  probable_risk: { display_label: "Вероятный риск", amount_label: "Вероятный риск", impact_kind: "probable_risk" },
  blocked_cash: { display_label: "Замороженные деньги", amount_label: "Замороженные деньги", impact_kind: "blocked_cash" },
  lost_sales_risk: { display_label: "Риск потери продаж", amount_label: "Риск потери продаж", impact_kind: "lost_sales_risk" },
  opportunity: { display_label: "Возможность роста", amount_label: "Возможность роста", impact_kind: "opportunity" },
  estimated_opportunity: { display_label: "Оценочная возможность", amount_label: "Оценочная возможность", impact_kind: "estimated_opportunity" },
  data_blocker: { display_label: "Не хватает данных", amount_label: "Не хватает данных", impact_kind: "data_blocker" },
  data_blocked: { display_label: "Данные заблокированы", amount_label: "Данные заблокированы", impact_kind: "data_blocked" },
  system_warning: { display_label: "Системное предупреждение", amount_label: "Системное предупреждение", impact_kind: "system_warning" },
  test_only: { display_label: "Тестовое правило", amount_label: "Не деньги продавца", impact_kind: "test_only" },
};

export function coerceMoneyTrust(value: unknown): MoneyTrustInfo | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const obj = value as Record<string, unknown>;
  if (obj.money_trust) return coerceMoneyTrust(obj.money_trust);
  const state = typeof obj.state === "string" ? obj.state : null;
  if (!state) return null;
  const impactKind = typeof obj.impact_kind === "string" ? obj.impact_kind : null;
  const fallback =
    (impactKind ? IMPACT_FALLBACK_LABEL[impactKind] : null) ??
    STATE_FALLBACK_LABEL[state] ??
    STATE_FALLBACK_LABEL.provisional;
  return {
    state,
    impact_kind: impactKind ?? fallback.impact_kind,
    display_label: typeof obj.display_label === "string" ? obj.display_label : fallback.display_label,
    amount_label: typeof obj.amount_label === "string" ? obj.amount_label : fallback.amount_label,
    show_as_confirmed_money: obj.show_as_confirmed_money === true,
    seller_visible_by_default: obj.seller_visible_by_default !== false,
    reason: typeof obj.reason === "string" ? obj.reason : undefined,
    evidence_trust_state: typeof obj.evidence_trust_state === "string" ? obj.evidence_trust_state : undefined,
    impact_trust_state: typeof obj.impact_trust_state === "string" ? obj.impact_trust_state : state,
    saved_money_claimed: obj.saved_money_claimed === true,
    ...obj,
  };
}

export function moneyTrustFrom(...values: unknown[]): MoneyTrustInfo {
  for (const value of values) {
    const trust = coerceMoneyTrust(value);
    if (trust) return trust;
  }
  return {
    state: "provisional",
    impact_kind: "probable_risk",
    display_label: "Предварительно",
    amount_label: "Вероятный риск",
    show_as_confirmed_money: false,
    seller_visible_by_default: true,
    reason: "Классификатор доверия к деньгам не передан.",
    evidence_trust_state: "provisional",
    impact_trust_state: "provisional",
    saved_money_claimed: false,
  };
}

export function moneyTrustTone(trust: MoneyTrustInfo | null | undefined): string {
  const kind = String(trust?.impact_kind ?? trust?.state ?? "").toLowerCase();
  if (kind === "confirmed_loss") return "border-destructive/35 bg-destructive/10 text-destructive";
  if (kind === "probable_loss" || kind === "probable_risk" || kind === "lost_sales_risk") return "border-amber-500/35 bg-amber-500/10 text-amber-800 dark:text-amber-300";
  if (kind === "blocked_cash") return "border-orange-500/35 bg-orange-500/10 text-orange-800 dark:text-orange-300";
  if (kind === "test_only" || trust?.state === "test_only") return "border-slate-500/30 bg-slate-500/10 text-slate-700 dark:text-slate-300";
  if (kind === "blocked_revenue" || kind === "data_blocked" || kind === "data_blocker" || trust?.state === "blocked") return "border-amber-500/35 bg-amber-500/10 text-amber-800 dark:text-amber-300";
  if (kind === "estimated_opportunity" || kind === "opportunity" || trust?.state === "opportunity") return "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300";
  if (trust?.state === "confirmed") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  return "border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-300";
}

export function isSellerVisibleMoneyTrust(...values: unknown[]): boolean {
  return moneyTrustFrom(...values).seller_visible_by_default !== false;
}

export function evidenceTrustStateFrom(...values: unknown[]): MoneyTrustState | null {
  for (const value of values) {
    if (!value || typeof value !== "object" || Array.isArray(value)) continue;
    const obj = value as Record<string, unknown>;
    const nested = evidenceTrustStateFrom(obj.money_trust);
    if (nested) return nested;
    if (typeof obj.evidence_trust_state === "string" && obj.evidence_trust_state.trim()) {
      return obj.evidence_trust_state;
    }
    if (Array.isArray(obj.input_facts) && obj.input_facts.length > 0) {
      const factStates = obj.input_facts
        .map((fact) =>
          fact && typeof fact === "object" && !Array.isArray(fact)
            ? String((fact as Record<string, unknown>).trust_state ?? "").trim()
            : "",
        )
        .filter(Boolean);
      if (factStates.length > 0 && factStates.every((state) => state === "confirmed")) {
        return "confirmed";
      }
    }
    if (typeof obj.confidence === "string" && obj.confidence.trim()) {
      return obj.confidence;
    }
  }
  return null;
}

export function evidenceTrustLabel(value: unknown): string | null {
  const state = String(value ?? "").trim().toLowerCase();
  if (!state) return null;
  if (state === "confirmed" || state === "trusted" || state === "final") return "Данные подтверждены";
  if (state === "estimated" || state === "estimate") return "Данные оценочные";
  if (state === "provisional") return "Данные предварительные";
  if (state === "blocked" || state === "data_blocked" || state === "data_blocker") return "Данных не хватает";
  if (state === "test_only" || state === "test") return "Тестовые данные";
  return null;
}
