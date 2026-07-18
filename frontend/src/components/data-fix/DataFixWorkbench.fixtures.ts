import type { DataQualityResolutionContext } from "@/lib/api";

type Issue = DataQualityResolutionContext["issue"];
type Definition = DataQualityResolutionContext["definition"];
type DynamicProblemInstance = NonNullable<DataQualityResolutionContext["dynamic_problem_instance"]>;

const baseIssue = (overrides: Partial<Issue>): Issue => ({
  id: 1,
  account_id: 1,
  domain: "data_quality",
  severity: "high",
  code: "missing_manual_cost",
  entity_key: null,
  entity_type: "nm_id",
  entity_id: 1001,
  sku_id: 2001,
  nm_id: 1001,
  source_table: "sku_costs",
  message: "Не хватает себестоимости",
  payload: {},
  detected_at: "2026-07-07T08:00:00Z",
  first_seen_at: "2026-07-07T08:00:00Z",
  last_seen_at: "2026-07-07T08:00:00Z",
  resolved_at: null,
  effective_financial_final_blocker: true,
  business_impact: "Без себестоимости нельзя подтвердить прибыль.",
  simple_reason: "Платформа не нашла реальную себестоимость по товару.",
  first_action: "Заполните себестоимость и запустите повторную проверку.",
  status: "new",
  ...overrides,
});

const definition = (overrides: Partial<Definition>): Definition => ({
  owner_type: "user",
  can_user_fix_inside_platform: true,
  fix_component_type: "cost_inline_editor",
  required_inputs: [],
  affected_rows_query: {},
  preview_before_change: { description: "Заполните недостающие данные." },
  apply_action: {},
  recheck_query: {},
  success_state: {},
  failure_state: {},
  safety_notes: [],
  ...overrides,
});

const dynamicProblem = (overrides: Partial<DynamicProblemInstance>): DynamicProblemInstance => ({
  id: 101,
  problem_code: "missing_manual_cost",
  status: "new",
  source_module: "problem_engine",
  source_id: "101",
  action_center_source_module: "problem_engine",
  action_center_source_id: "101",
  title: "Не хватает себестоимости",
  explanation: "Проверка нашла товар без подтверждённой себестоимости.",
  recommendation: "Заполните себестоимость и перепроверьте проблему.",
  impact_type: "data_blocker",
  trust_state: "blocked",
  ...overrides,
});

const context = (overrides: Partial<DataQualityResolutionContext>): DataQualityResolutionContext => ({
  issue: baseIssue({}),
  definition: definition({}),
  resolver: null,
  affected_rows: [],
  affected_rows_total: 0,
  affected_rows_limit: 50,
  affected_rows_offset: 0,
  source_facts: [],
  suggested_fix_action: {},
  recheck_rule: "После исправления платформа повторно проверит условие проблемы.",
  audit_history: [],
  safe_to_apply: true,
  dynamic_problem_instance: dynamicProblem({}),
  ...overrides,
});

export const dataFixWorkbenchFixtures = {
  missingCostDataFixFixture: context({
    issue: baseIssue({
      id: 11,
      code: "missing_manual_cost",
      message: "Не хватает себестоимости",
      simple_reason: "По товару нет подтверждённой себестоимости.",
    }),
    definition: definition({
      fix_component_type: "cost_inline_editor",
      required_inputs: ["cost_price"],
      preview_before_change: { description: "Заполните себестоимость в таблице." },
    }),
    affected_rows: [{ nm_id: 1001, sku_id: 2001, vendor_code: "A-1001", cost_price: null }],
    affected_rows_total: 1,
    dynamic_problem_instance: dynamicProblem({
      id: 111,
      problem_code: "missing_manual_cost",
      title: "Не хватает себестоимости",
      impact_type: "data_blocker",
      trust_state: "blocked",
    }),
  }),
  unmatchedSkuDataFixFixture: context({
    issue: baseIssue({
      id: 12,
      code: "unmatched_sku",
      message: "SKU не сопоставлен",
      simple_reason: "Строка продаж или себестоимости не привязалась к карточке.",
    }),
    definition: definition({
      fix_component_type: "sku_mapping",
      required_inputs: ["mapped_sku_id"],
      preview_before_change: { description: "Сопоставьте строку с правильным SKU." },
    }),
    affected_rows: [{ nm_id: 1002, sku_id: null, vendor_code: "A-1002", barcode: "4600000000002" }],
    affected_rows_total: 1,
    dynamic_problem_instance: dynamicProblem({
      id: 112,
      problem_code: "unmatched_sku",
      title: "SKU не сопоставлен",
      impact_type: "data_blocker",
      trust_state: "blocked",
    }),
  }),
  unclassifiedExpenseDataFixFixture: context({
    issue: baseIssue({
      id: 13,
      code: "expense_unclassified",
      message: "Расход без категории",
      simple_reason: "Финансовая строка WB пришла без понятной категории расхода.",
    }),
    definition: definition({
      fix_component_type: "expense_classification",
      required_inputs: ["expense_category"],
      preview_before_change: { description: "Выберите категорию расхода." },
    }),
    affected_rows: [{ amount: 1240, expense_category: null, source_table: "finance_report_rows" }],
    affected_rows_total: 1,
    dynamic_problem_instance: dynamicProblem({
      id: 113,
      problem_code: "expense_unclassified",
      title: "Расход без категории",
      impact_type: "data_blocker",
      trust_state: "blocked",
    }),
  }),
  financeReconciliationMismatchDataFixFixture: context({
    issue: baseIssue({
      id: 14,
      code: "finance_reconciliation_mismatch",
      message: "Расхождение финансовой сверки",
      simple_reason: "Операционная выручка и финансовый отчёт WB не совпали.",
      effective_financial_final_blocker: true,
    }),
    definition: definition({
      owner_type: "admin",
      can_user_fix_inside_platform: false,
      fix_component_type: "open_finance_reconciliation",
      preview_before_change: { description: "Проверьте период, отчёт WB и повторную синхронизацию." },
      safety_notes: ["Финансовые суммы WB нельзя менять вручную."],
    }),
    safe_to_apply: false,
    affected_rows: [{ stat_date: "2026-07-07", final_revenue: 125000, status: "mismatch" }],
    affected_rows_total: 1,
    dynamic_problem_instance: dynamicProblem({
      id: 114,
      problem_code: "finance_reconciliation_mismatch",
      status: "in_progress",
      title: "Расхождение финансовой сверки",
      impact_type: "system_warning",
      trust_state: "provisional",
    }),
  }),
} satisfies Record<string, DataQualityResolutionContext>;
