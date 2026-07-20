import type { Page, Route } from "@playwright/test";

type JsonBody = Record<string, unknown> | unknown[];

const json = (body: JsonBody, status = 200) => ({
  status,
  contentType: "application/json",
  body: JSON.stringify(body),
});

const tokenPair = {
  access_token: "e2e-access-token",
  refresh_token: "e2e-refresh-token",
  token_type: "bearer",
};

const user = {
  id: 1,
  email: "owner@example.com",
  full_name: "E2E Owner",
  is_active: true,
  is_superuser: true,
  roles: ["superuser"],
  accounts: [{ id: 1, name: "E2E WB", role: "admin", is_default: true }],
};

const overview = {
  account_id: 1,
  period: {
    date_from: "2026-07-12",
    date_to: "2026-07-18",
    previous_date_from: "2026-07-05",
    previous_date_to: "2026-07-11",
  },
  hero: {
    title: "Магазин готов к управлению",
    subtitle: "Корреляция, а не гарантия: данные демонстрационные.",
    status: "operational",
  },
  money: { revenue: 125000, profit: 32000, expenses: 93000 },
  tasks: [
    {
      id: 1,
      title: "До действия",
      description: "После изменения проверьте результат.",
      priority: "P1",
      status: "open",
    },
  ],
  products: [],
  trust: { status: "provisional", message: "Корреляция, а не гарантия" },
};

const products = {
  items: [
    {
      nm_id: 1001001,
      vendor_code: "E2E-001",
      title: "Product 360 deep link",
      brand: "E2E",
      subject_name: "Брюки",
    },
  ],
  total: 1,
  limit: 10,
  offset: 0,
};

const assignableUsers = [
  {
    id: 1,
    email: "owner@example.com",
    full_name: "E2E Owner",
    display_name: "E2E Owner",
    role: "admin",
    is_active: true,
    is_superuser: true,
  },
];

const portalAction = {
  id: "42",
  action_id: 42,
  external_id: "problem:42",
  source: "problem_engine",
  source_module: "problem_engine",
  source_id: "problem:42",
  account_id: 1,
  action_type: "upload_cost",
  detector_code: "missing_cost_blocks_profit",
  problem_code: "missing_cost_blocks_profit",
  title: "Открыть задачу",
  reason: "По товару E2E-001 есть выручка, но не заполнена себестоимость.",
  next_step: "Загрузите себестоимость и перепроверьте товар.",
  priority: "P1",
  severity: "high",
  status: "new",
  confidence: "medium",
  nm_id: 1001001,
  sku_id: 7007001,
  created_at: "2026-07-18T09:00:00Z",
  assigned_to_user_id: 1,
  deadline_at: "2026-07-21T09:00:00Z",
  expected_impact_amount: 12000,
  impact_type: "data_blocker",
  trust_state: "blocked",
  evidence_state: "partial_evidence",
  can_update: true,
  can_update_status: true,
  can_execute: true,
  source_sync_state: "source_updated",
  allowed_actions: [
    "upload_cost",
    "open_data_fix",
    "open_results",
    "open_product",
    "recheck",
  ],
  data_freshness: {
    source_status: "fresh",
    required_sources: ["sales", "costs"],
    blocking_sources: ["costs"],
    freshness_notes: ["E2E mock data"],
  },
  money_trust: {
    state: "blocked",
    impact_kind: "data_blocker",
    display_label: "Не хватает данных",
    amount_label: "Не хватает данных",
    seller_visible_by_default: true,
    saved_money_claimed: false,
  },
  guided_fix: {
    route_key: "costs",
    label: "Загрузить себестоимость",
    href: "/costs?problem_instance_id=42&nm_id=1001001",
  },
  linked_entity: {
    entity_type: "product",
    nm_id: 1001001,
    sku_id: 7007001,
    vendor_code: "E2E-001",
  },
  payload: {
    problem_instance_id: 42,
    problem_code: "missing_cost_blocks_profit",
    nm_id: 1001001,
    sku_id: 7007001,
    vendor_code: "E2E-001",
    title: "Открыть задачу",
    reason: "Себестоимость отсутствует, прибыль нельзя подтвердить.",
    next_step: "Загрузите себестоимость и перепроверьте товар.",
    allowed_actions: [
      "upload_cost",
      "open_data_fix",
      "open_results",
      "open_product",
      "recheck",
    ],
  },
};

const portalActionsPage = {
  items: [portalAction],
  total: 1,
  limit: 50,
  offset: 0,
  summary: {
    open: 1,
    urgent: 1,
    data_blockers: 1,
  },
};

const resultEvent = {
  id: "result-42",
  account_id: 1,
  action_id: 42,
  problem_instance_id: 42,
  problem_code: "missing_cost_blocks_profit",
  source_module: "problem_engine",
  source_id: "problem:42",
  external_id: "problem:42",
  nm_id: 1001001,
  sku_id: 7007001,
  event_type: "result_evaluated",
  outcome: "not_enough_data",
  result_status: "not_enough_data",
  impact_type: "data_blocker",
  trust_state: "blocked",
  confidence: "medium",
  created_at: "2026-07-18T12:00:00Z",
  message: "Себестоимость ещё не заполнена, результат ждёт данных.",
  product_identity: {
    title: "Product 360 deep link",
    vendor_code: "E2E-001",
  },
  before_snapshot: {
    title: "Product 360 deep link",
    unit_profit: null,
    cost_price: null,
  },
  after_snapshot: {
    title: "Product 360 deep link",
    unit_profit: null,
    cost_price: null,
  },
  comparison: {
    metrics: [],
    status: "not_enough_data",
  },
  payload: {
    title: "Открыть задачу",
    problem_instance_id: 42,
    problem_code: "missing_cost_blocks_profit",
    nm_id: 1001001,
    vendor_code: "E2E-001",
  },
};

const actionCompletedEvent = {
  ...resultEvent,
  id: "result-42-action-completed",
  event_type: "action_completed",
  outcome: "pending_data",
  result_status: "pending_data",
  message: "Действие выполнено, ждём свежие данные после изменения.",
};

const recheckResultEvent = {
  ...resultEvent,
  id: "result-42-recheck",
  event_type: "recheck_result",
  outcome: "not_enough_data",
  result_status: "not_enough_data",
  message:
    "Повторная проверка выполнена, данных для финального результата пока мало.",
};

const resultEventsPage = {
  status: "ok",
  items: [resultEvent, actionCompletedEvent, recheckResultEvent],
  recent_events: [resultEvent, actionCompletedEvent, recheckResultEvent],
  total: 3,
  limit: 10,
  offset: 0,
  summary: {
    total: 3,
    improved: 0,
    worse: 0,
    neutral: 0,
    not_enough_data: 2,
    pending_data: 1,
  },
  by_module: { problem_engine: 3 },
  by_outcome: { not_enough_data: 2, pending_data: 1 },
  pending_followups: [],
  finance_windows: {},
};

const product360 = {
  nm_id: 1001001,
  identity: {
    status: "ok",
    data: {
      nm_id: 1001001,
      sku_id: 7007001,
      vendor_code: "E2E-001",
      title: "Product 360 deep link",
      brand: "E2E",
      subject_name: "Брюки",
    },
  },
  money: {
    status: "ok",
    data: {
      revenue: 125000,
      profit: null,
      margin_percent: null,
    },
  },
  costs: {
    status: "blocked",
    data: {
      cogs: { unit_cost: null },
    },
    message: "Себестоимость не заполнена.",
  },
  business_issues: {
    status: "blocked",
    data: {
      open: [portalAction],
      resolved: [],
      summary: {
        open_count: 1,
        resolved_count: 0,
      },
    },
  },
  actions: [portalAction],
  result_history: {
    status: "ok",
    data: resultEventsPage,
  },
  next_best_action: portalAction,
  module_health: {},
};

const agentResponse = {
  status: "ok",
  mode: "ai",
  intent: "product_search",
  message: "Товары найдены. Выберите нужный товар.",
  actions: [
    {
      type: "open_product_picker",
      title: "Выбрать товар",
      payload: { intent: "product_details", search_query: "брюки" },
    },
  ],
  products: products.items,
  suggestions: [],
  warnings: [],
  audit: { planner: "ai" },
};

function agentResponseFor(body: Record<string, unknown>) {
  const message = String(body.message || "").toLowerCase();
  if (
    (message.includes("отзывы") || message.includes("репутац")) &&
    !message.includes("сценар")
  ) {
    return {
      status: "ok",
      mode: "ai",
      intent: "reputation_agent",
      message:
        "Открыл раздел репутации: там можно работать с отзывами, вопросами и задачами по ответам покупателям.",
      actions: [
        { type: "navigate", title: "Репутация", href: "/reputation" },
        { type: "navigate", title: "История задач", href: "/action-center" },
      ],
      products: [],
      suggestions: ["Создай сценарий ответов"],
      warnings: [],
      audit: { planner: "ai", direct_marketplace_writes: false },
    };
  }
  if (message.includes("умные цены") || message.includes("марж")) {
    return {
      status: "ok",
      mode: "ai",
      intent: "pricing_agent",
      message:
        "Открыл контур цен. Изменения цен готовятся только через безопасную проверку маржи и ручное подтверждение.",
      actions: [
        { type: "navigate", title: "Цены", href: "/pricing" },
        { type: "navigate", title: "Центр действий", href: "/action-center" },
      ],
      products: [],
      suggestions: ["Создай сценарий умных цен"],
      warnings: [],
      audit: { planner: "ai", direct_marketplace_writes: false },
    };
  }
  if (message.includes("реклам")) {
    return {
      status: "ok",
      mode: "ai",
      intent: "module_navigate",
      message:
        "Открыл раздел «Реклама»: там можно смотреть кампании, статистику и эффективность.",
      actions: [{ type: "navigate", title: "Реклама", href: "/ads" }],
      products: [],
      suggestions: ["Открой аналитику"],
      warnings: [],
      audit: {
        planner: "ai",
        direct_marketplace_writes: false,
        module_key: "ads",
      },
    };
  }
  if (message.includes("качеств") || message.includes("dq")) {
    return {
      status: "ok",
      mode: "ai",
      intent: "api_action",
      message:
        "Готов запустить проверку качества данных. Перед выполнением потребуется подтверждение.",
      actions: [
        {
          type: "api_request",
          title: "Запустить проверку данных",
          description:
            "Запустить проверку качества данных по выбранному аккаунту.",
          href: "/dq/run",
          method: "POST",
          confirm_required: true,
          payload: {
            api_action_key: "data_quality.run",
            body: { account_id: 1 },
            success_message: "Проверка качества данных запущена.",
          },
        },
        { type: "navigate", title: "Качество данных", href: "/data-fix" },
      ],
      products: [],
      suggestions: ["Открой качество данных"],
      warnings: [
        "Прямые записи в Wildberries не выполняются без отдельного подтверждения, аудита и прав пользователя.",
      ],
      audit: {
        planner: "ai",
        direct_marketplace_writes: false,
        api_action_key: "data_quality.run",
      },
    };
  }
  if (message.includes("сценар")) {
    if (body.selected_nm_id) {
      return {
        status: "ok",
        mode: "ai",
        intent: "scenario_create",
        message:
          "Сценарий подготовлен как безопасная задача. Я не публикую ответы и не меняю WB автоматически.",
        actions: [
          {
            type: "create_manual_task",
            title: "Создать задачу",
            payload: {
              account_id: 1,
              title: "AI-сценарий для проверки",
              products: products.items,
            },
          },
          { type: "navigate", title: "Центр действий", href: "/action-center" },
        ],
        products: products.items,
        suggestions: ["Создать задачу"],
        warnings: [],
        audit: { planner: "ai", direct_marketplace_writes: false },
      };
    }
    return {
      status: "needs_input",
      mode: "ai",
      intent: "scenario_create",
      message:
        "С каким товаром работаем? Выберите товар из списка или уточните поисковый запрос.",
      actions: [
        {
          type: "open_product_picker",
          title: "Выбрать товар",
          payload: {
            intent: "scenario_create",
            search_query: "",
            draft_message: body.message,
          },
        },
      ],
      products: products.items,
      suggestions: [],
      warnings: [],
      audit: { planner: "ai", direct_marketplace_writes: false },
    };
  }
  return agentResponse;
}

export async function installMockApi(page: Page) {
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const apiPrefix = "/api/v1";
    const path = url.pathname.startsWith(apiPrefix)
      ? url.pathname.slice(apiPrefix.length)
      : url.pathname;

    if (path === "/auth/login" || path === "/auth/refresh") {
      await route.fulfill(json(tokenPair));
      return;
    }
    if (path === "/auth/me") {
      await route.fulfill(json(user));
      return;
    }
    if (path === "/accounts") {
      await route.fulfill(json(user.accounts));
      return;
    }
    if (path === "/dashboard/owner") {
      await route.fulfill(
        json({
          account_id: 1,
          account_name: "E2E WB",
          date_from: "2026-07-13",
          date_to: "2026-07-19",
          revenue: 125000,
          profit: 32000,
          owner_message: {
            title: "Магазин готов к управлению",
            reason: "Корреляция, а не гарантия: данные демонстрационные.",
            today_focus: "Проверьте блокеры данных и прибыльность.",
          },
          next_actions_preview: [portalAction],
          trust: {
            trust_state: "provisional",
            financial_final: false,
            blocking_open_issues_total: 1,
          },
        }),
      );
      return;
    }
    if (path === "/dashboard/data-health") {
      await route.fulfill(
        json({
          account_id: 1,
          financial_final: false,
          open_issues_total: 1,
          revenue_cost_coverage_percent: 75,
          sync_status: {},
          domains: {},
        }),
      );
      return;
    }
    if (path === "/dashboard/owner-ai-summary") {
      await route.fulfill(
        json({
          title: "Сводка",
          summary: "Проверьте себестоимость по тестовому товару.",
          bullets: [],
        }),
      );
      return;
    }
    if (path === "/portal/dashboard/overview" || path === "/portal/overview") {
      await route.fulfill(json(overview));
      return;
    }
    if (path === "/products" || path === "/portal/products") {
      await route.fulfill(json(products));
      return;
    }
    if (path === "/portal/products/1001001") {
      await route.fulfill(json(product360));
      return;
    }
    if (path === "/portal/agent/message") {
      let body: Record<string, unknown> = {};
      try {
        const parsed = request.postDataJSON();
        body = parsed && typeof parsed === "object" ? parsed : {};
      } catch {
        body = {};
      }
      await route.fulfill(json(agentResponseFor(body)));
      return;
    }
    if (path === "/dq/run") {
      await route.fulfill(
        json({
          checked_accounts: 1,
          opened_count: 2,
          updated_count: 1,
          resolved_count: 0,
          active_count: 2,
        }),
      );
      return;
    }
    if (path === "/portal/assignable-users") {
      await route.fulfill(json(assignableUsers));
      return;
    }
    if (path === "/portal/actions" || path === "/portal/action-center") {
      await route.fulfill(json(portalActionsPage));
      return;
    }
    if (path === "/portal/results" || path === "/portal/problems/42/results") {
      await route.fulfill(json(resultEventsPage));
      return;
    }
    if (path === "/analytics/overview") {
      await route.fulfill(
        json({
          ...overview,
          summary: {},
          products: [],
          regions: [],
          trend: [],
        }),
      );
      return;
    }

    await route.fulfill(json({ items: [], total: 0, limit: 10, offset: 0 }));
  });
}
