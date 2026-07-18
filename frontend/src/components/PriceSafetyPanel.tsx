import { AlertTriangle, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { formatMoney } from "@/lib/format";
export {
  priceSafetyFrom,
  priceSafetyNeededForProblem,
  priceSafetyNeededFromText,
} from "@/lib/price-safety";
export type { PriceSafetyPayload } from "@/lib/price-safety";
import type { PriceSafetyPayload } from "@/lib/price-safety";

function asNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function asList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item).trim()).filter(Boolean);
}

function money(value: unknown): string {
  const parsed = asNumber(value);
  return parsed == null ? "-" : formatMoney(parsed);
}

function hasCyrillic(value: string): boolean {
  return /[А-Яа-яЁё]/.test(value);
}

function metricLabel(code: unknown): string {
  const labels: Record<string, string> = {
    price_current: "текущая цена",
    price_after_discount: "эффективная цена после скидки",
    price_after_discount_or_price_current: "эффективная или текущая цена",
    cost_price: "себестоимость",
    commission_per_unit: "комиссия",
    logistics_per_unit: "логистика",
    acquiring_per_unit: "эквайринг",
    storage_fee_per_unit: "хранение",
    unit_profit: "прибыль на единицу",
    margin_pct: "маржа",
  };
  const key = String(code ?? "").trim();
  if (!key) return "показатель";
  return labels[key] ?? (hasCyrillic(key) ? key : "показатель");
}

function componentLabel(item: Record<string, unknown>): string {
  const raw = String(item?.label ?? "").trim();
  if (raw && hasCyrillic(raw)) return raw;
  return metricLabel(item?.metric_code);
}

function warningLabel(value: string): string {
  if (hasCyrillic(value)) return value;
  if (value === "price_recommendation_blocked_missing_unit_economics") {
    return "Рекомендация по цене заблокирована: не хватает экономики единицы товара.";
  }
  if (value.startsWith("missing_required_metric:")) {
    return `Не хватает данных: ${metricLabel(value.split(":")[1])}.`;
  }
  if (value === "price_decrease_blocked_by_min_safe_price") {
    return "Снижение цены заблокировано минимальной безопасной ценой.";
  }
  if (value === "price_increase_target_calculated_from_unit_economics") {
    return "Целевая цена рассчитана по экономике единицы товара.";
  }
  if (value === "promo_discount_blocked_by_min_safe_price") {
    return "Увеличение скидки заблокировано безопасной ценой.";
  }
  if (value === "price_safety_checked") {
    return "Проверка безопасной цены выполнена.";
  }
  return "Проверка безопасной цены требует внимания.";
}

function reasonLabel(priceSafety: PriceSafetyPayload, status: string): string {
  const raw = String(priceSafety.reason ?? "").trim();
  if (raw && hasCyrillic(raw)) return raw;
  if (status === "data_incomplete") {
    return "Рекомендация по цене заблокирована, пока не заполнена экономика единицы товара.";
  }
  if (status === "increase_recommended") {
    return `Текущая цена ниже цены для целевой маржи: ${money(priceSafety.target_price)}.`;
  }
  if (status === "safe") {
    return `Скидка остаётся безопасной, пока цена не ниже ${money(priceSafety.min_safe_price)}.`;
  }
  if (status === "unsafe") {
    return `Текущая цена уже на уровне безопасного минимума или ниже: ${money(priceSafety.min_safe_price)}.`;
  }
  return "Проверка экономики товара оценила рекомендацию.";
}

function pct(value: unknown): string {
  const parsed = asNumber(value);
  return parsed == null ? "-" : `${parsed.toFixed(2).replace(/\.00$/, "")}%`;
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    safe: "безопасно",
    unsafe: "опасно",
    data_incomplete: "не хватает данных",
    increase_recommended: "можно повысить цену",
    price_ok: "цена в норме",
    checked: "проверено",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

export function PriceSafetyMissingNotice({ compact = false }: { compact?: boolean }) {
  return (
    <div
      data-price-safety-missing="1"
      className="rounded-md border border-amber-500/45 bg-amber-500/10 p-3 text-xs text-amber-900 dark:text-amber-200"
    >
      <div className="flex items-center gap-2 font-semibold">
        <AlertTriangle className="h-4 w-4" />
        Нет проверки безопасной маржи
      </div>
      <div className={compact ? "mt-1" : "mt-2"}>
        Рекомендацию по цене, скидке или промо нельзя показывать как безопасное действие, пока нет доказательств безопасной цены: себестоимости, маржи или безопасной цены.
      </div>
    </div>
  );
}

export function PriceSafetyPanel({ priceSafety, compact = false }: { priceSafety?: PriceSafetyPayload | null; compact?: boolean }) {
  if (!priceSafety) return null;
  const status = String(priceSafety.status ?? "").trim().toLowerCase();
  const unsafe = status === "unsafe" || status === "data_incomplete";
  const missing = asList(priceSafety.missing_required_metrics);
  const warnings = asList(priceSafety.warnings);
  const components = Array.isArray(priceSafety.component_breakdown) ? priceSafety.component_breakdown.slice(0, 4) : [];

  return (
    <div className={`rounded-md border ${unsafe ? "border-warning/40 bg-warning/10" : "border-emerald-500/30 bg-emerald-500/10"} p-3`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
          {unsafe ? <AlertTriangle className="h-4 w-4 text-warning" /> : <ShieldCheck className="h-4 w-4 text-emerald-600" />}
          Проверка безопасной цены
        </div>
        <Badge variant="outline" className={unsafe ? "border-warning/40 text-warning" : "border-emerald-500/30 text-emerald-700"}>
          {statusLabel(status || "checked")}
        </Badge>
      </div>

      <div className={`mt-2 grid gap-2 text-xs ${compact ? "sm:grid-cols-2" : "sm:grid-cols-3"}`}>
        <div>
          <div className="text-muted-foreground">Минимальная безопасная цена</div>
          <div className="font-medium">{money(priceSafety.min_safe_price)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Текущая эффективная цена</div>
          <div className="font-medium">{money(priceSafety.reference_price ?? priceSafety.price_after_discount ?? priceSafety.current_price)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Максимальная безопасная скидка</div>
          <div className="font-medium">{pct(priceSafety.max_safe_discount_pct)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Целевая маржа</div>
          <div className="font-medium">{pct(priceSafety.target_margin_pct)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Маржа после скидки</div>
          <div className="font-medium">{pct(priceSafety.margin_after_discount)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Целевая цена</div>
          <div className="font-medium">{money(priceSafety.target_price)}</div>
        </div>
      </div>

      <div className="mt-2 text-xs">
        <span className="font-medium">Почему безопасно или нет: </span>
        <span className="text-muted-foreground">{reasonLabel(priceSafety, status)}</span>
      </div>

      {missing.length > 0 ? (
        <div className="mt-2 text-xs text-warning">
          Не хватает данных: {missing.map(metricLabel).join(", ")}
        </div>
      ) : null}

      {!compact && components.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {components.map((item, index) => {
            const component = item as Record<string, unknown>;
            return (
            <Badge key={`${component.metric_code ?? "component"}-${index}`} variant="outline" className="text-[10px]">
              {componentLabel(component)}: {money(component.value)}
            </Badge>
            );
          })}
        </div>
      ) : null}

      {!compact && warnings.length > 0 ? (
        <div className="mt-2 text-[11px] text-muted-foreground">
          {warnings.map(warningLabel).join(" ")}
        </div>
      ) : null}
    </div>
  );
}
