export type LegacyDiagnosticDecision =
  | "migrate_to_dynamic_rule"
  | "admin_debug_only"
  | "fallback_only"
  | "remove_from_seller_navigation";

export type LegacyDiagnosticSurface = {
  id:
    | "legacy_profit_doctor_route"
    | "legacy_cards_route"
    | "legacy_card_detail_flags"
    | "money_risk_strips"
    | "legacy_finance_data_quality_action_cards"
    | "settings_doctor_module";
  route: string;
  title: string;
  decision: LegacyDiagnosticDecision;
  dynamicPrimary: string;
  sellerPolicy: string;
};

export const LEGACY_DIAGNOSTIC_SURFACES: LegacyDiagnosticSurface[] = [
  {
    id: "legacy_profit_doctor_route",
    route: "/doctor",
    title: "Диагностика прибыли legacy",
    decision: "admin_debug_only",
    dynamicPrimary: "/action-center",
    sellerPolicy: "Скрыта от продавцов. Динамические проблемы ведутся в Центре действий и на странице товара.",
  },
  {
    id: "legacy_cards_route",
    route: "/cards",
    title: "Старые карточки WB с денежными флагами",
    decision: "admin_debug_only",
    dynamicPrimary: "/products",
    sellerPolicy: "Скрыта от продавцов. Основная карточка товара открывается через Товары/Product360.",
  },
  {
    id: "legacy_card_detail_flags",
    route: "/cards/:nmId",
    title: "Старые флаги карточки, остатков, рекламы и данных",
    decision: "admin_debug_only",
    dynamicPrimary: "/products/:nmId",
    sellerPolicy: "Скрыта от продавцов как отдельная диагностика; Product360 использует SellerProblemUX.",
  },
  {
    id: "money_risk_strips",
    route: "/money",
    title: "Операционные финансовые риск-полосы",
    decision: "fallback_only",
    dynamicPrimary: "/action-center",
    sellerPolicy: "Остаются как финансовый контроль, но не заменяют карточки динамических проблем.",
  },
  {
    id: "legacy_finance_data_quality_action_cards",
    route: "/action-center",
    title: "Legacy finance/data_quality action cards",
    decision: "fallback_only",
    dynamicPrimary: "problem_engine",
    sellerPolicy: "Action Center предпочитает dynamic problem rows и показывает legacy только как fallback.",
  },
  {
    id: "settings_doctor_module",
    route: "/settings",
    title: "Модуль legacy-диагностики прибыли в настройках",
    decision: "remove_from_seller_navigation",
    dynamicPrimary: "/action-center",
    sellerPolicy: "Скрыт из seller settings; Центр действий является основной точкой входа.",
  },
];

export type LegacyDiagnosticSurfaceId = LegacyDiagnosticSurface["id"];

export function legacyDiagnosticsEnabled(): boolean {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env;
  return env?.VITE_ENABLE_LEGACY_DIAGNOSTICS === "true";
}

export function canAccessLegacyDiagnostics(isSuperuser?: boolean | null): boolean {
  return !!isSuperuser && legacyDiagnosticsEnabled();
}

export function legacyDiagnosticSurface(id: LegacyDiagnosticSurfaceId): LegacyDiagnosticSurface {
  return LEGACY_DIAGNOSTIC_SURFACES.find((surface) => surface.id === id) ?? LEGACY_DIAGNOSTIC_SURFACES[0];
}
