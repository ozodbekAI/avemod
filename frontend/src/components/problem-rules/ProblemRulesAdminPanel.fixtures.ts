import type {
  ProblemDefinitionCreatePayload,
  RuleBacktestResponse,
  RuleValidationResponse,
} from "@/lib/problem-rules";

type AdminRuleBuilderFixture = {
  templateTitle: string;
  metricAreas: string[];
  humanPreview: string;
  definition: ProblemDefinitionCreatePayload;
};

type UnsafePublishFixture = {
  validation: RuleValidationResponse;
  backtest: RuleBacktestResponse;
  selectedMetrics: string[];
  expectedBlockers: string[];
};

export const adminProblemRulesFixtures = {
  createRuleFromTemplate: {
    templateTitle: "Нет себестоимости, прибыль не считается",
    metricAreas: [
      "Остатки",
      "Продажи",
      "Цена",
      "Себестоимость",
      "Комиссии и логистика",
      "Реклама",
      "Промо",
      "Возвраты",
      "Контент",
    ],
    humanPreview:
      "IF cost_price отсутствует AND revenue_30d больше 0; влияние берём из revenue_30d; доказательства показываются в «Как посчитано?»",
    definition: {
      problem_code: "missing_cost_blocks_profit",
      source_module: "problem_engine",
      category: "data_quality",
      entity_type: "product",
      title_template: "Нет себестоимости для {nm_id}",
      description_template:
        "По товару есть выручка, но cost_price отсутствует. Прибыльность нельзя считать финальной.",
      recommendation_template:
        "Загрузите себестоимость или сопоставьте SKU, затем запустите перепроверку.",
      impact_type_default: "data_blocker",
      trust_state_default: "blocked",
      severity_default: "high",
      allowed_actions_json: ["upload_cost", "map_sku", "recheck", "dismiss"],
    },
  } satisfies AdminRuleBuilderFixture,
  blockedUnsafePublish: {
    validation: {
      valid: true,
      formula_results: {},
      required_metrics: ["promo_discount_pct", "unit_profit"],
      warnings: [],
    },
    backtest: {
      rule_version_id: 501,
      account_id: 1,
      date_from: "2026-06-08",
      date_to: "2026-07-07",
      matched_count: 80,
      evaluated_count: 100,
      sample_issues: [
        {
          nm_id: 1001,
          problem_code: "promo_without_profit",
          trust_state: "estimated",
          money_impact_amount: 12000,
        },
      ],
      total_impact_amount: 12000,
      warnings: ["too_many_matches"],
      missing_metric_stats: { margin_pct: 72 },
      test_run_id: 9001,
    },
    selectedMetrics: ["promo_discount_pct", "unit_profit"],
    expectedBlockers: [
      "Правило срабатывает слишком широко",
      "Метрика margin_pct отсутствует больше чем у половины проверенных товаров",
      "Для цены или промо нужны метрики безопасной маржи",
    ],
  } satisfies UnsafePublishFixture,
};
