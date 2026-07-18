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

const problemLedger = {
  business_issues: [
    {
      problem_instance_id: 42,
      problem_code: "missing_cost_blocks_profit",
      title: "Открыть задачу",
      actions: ["Открыть в результатах", "Открыть исправление данных"],
    },
  ],
  result_history: [
    {
      problem_instance_id: 42,
      before_snapshot: { unit_profit: null },
      event_type: "action_completed",
      recheck_result: "not_enough_data",
      saved_money_claimed: false,
    },
  ],
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

export async function installMockApi(page: Page) {
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/v1/, "");

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
    if (path === "/portal/dashboard/overview" || path === "/portal/overview") {
      await route.fulfill(json(overview));
      return;
    }
    if (path === "/products") {
      await route.fulfill(json(products));
      return;
    }
    if (path === "/portal/agent/message") {
      await route.fulfill(json(agentResponse));
      return;
    }
    if (path === "/portal/action-center" || path === "/portal/results") {
      await route.fulfill(json(problemLedger));
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
