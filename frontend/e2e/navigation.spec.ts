import { expect, test } from "@playwright/test";

import { installMockApi } from "./mock-api";

const RESULTS_CORRELATION_COPY = "Корреляция, а не гарантия";
const RESULTS_ERROR_COPY = "Не удалось загрузить результаты";
const RESULTS_BEFORE_COPY = "До действия";
const RESULTS_AFTER_CHANGE_COPY = "После изменения";

test.beforeEach(async ({ page }) => {
  await installMockApi(page);
  await page.addInitScript(() => {
    localStorage.setItem("wb.access_token", "e2e-access-token");
    localStorage.setItem("wb.refresh_token", "e2e-refresh-token");
    localStorage.setItem("wb.active_account_id", "1");
  });
});

test("authenticated canonical navigation", async ({ page }) => {
  await page.goto("/dashboard");

  await expect(
    page.getByRole("heading", { name: "Панель владельца" }),
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Денежный тренд").first()).toBeVisible();

  await page.getByRole("button", { name: "AI оператор" }).click();
  await expect(page.getByText("Администратор портала")).toBeVisible();
});

test("AI operator handles JVO-like admin workflows", async ({ page }) => {
  const agentRequests: unknown[] = [];
  page.on("request", (request) => {
    if (!request.url().includes("/api/v1/portal/agent/message")) return;
    try {
      agentRequests.push(request.postDataJSON());
    } catch {
      agentRequests.push({});
    }
  });

  await page.goto("/dashboard");
  await page.getByRole("button", { name: "AI оператор" }).click();

  const input = page.getByPlaceholder("Введите вопрос или команду...");

  await input.fill("Открой отзывы и вопросы покупателей");
  await input.press("Enter");
  await expect(page.getByText("Открыл раздел репутации")).toBeVisible();
  await expect(page.getByRole("button", { name: "Репутация" })).toBeVisible();

  await input.fill("Настрой умные цены без риска потерять маржу");
  await input.press("Enter");
  await expect(page.getByText("Открыл контур цен")).toBeVisible();
  await expect(page.getByRole("button", { name: "Цены" })).toBeVisible();

  await input.fill("Открой рекламу");
  await input.press("Enter");
  await expect(page.getByText("Открыл раздел «Реклама»")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Реклама" }).first(),
  ).toBeVisible();

  await input.fill("Создай сценарий ответов на негативные отзывы");
  await input.press("Enter");
  const productDialog = page.getByRole("dialog", { name: "Выберите товар" });
  await expect(productDialog).toBeVisible();

  await page.getByRole("button", { name: "Product 360 deep link" }).click();
  await expect(productDialog).toBeHidden();
  await expect(page.getByText("Создал draft AI-сценария")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Тестовый запуск" }),
  ).toBeVisible();

  expect(
    agentRequests.some((item) => {
      const payload = item as Record<string, unknown>;
      return (
        payload.intent === "scenario_create" &&
        payload.selected_nm_id === 1001001 &&
        String(payload.message || "").includes("Создай сценарий")
      );
    }),
  ).toBeTruthy();
});

test("AI operator executes allow-listed API actions with confirmation", async ({
  page,
}) => {
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "AI оператор" }).click();

  const input = page.getByPlaceholder("Введите вопрос или команду...");
  await input.fill("Запусти проверку качества данных");
  await input.press("Enter");

  await expect(
    page.getByText("Готов запустить проверку качества данных"),
  ).toBeVisible();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("Выполнить действие?");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Запустить проверку данных" }).click();

  await expect(
    page.getByText("Проверка качества данных запущена.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("opened_count: 2")).toBeVisible();
  await expect(page.getByText("active_count: 2")).toBeVisible();
});

test("product 360 deep link", async ({ page }) => {
  await page.goto("/products/1001001");

  await expect(
    page.getByRole("heading", {
      name: "Product 360 deep link",
    }),
  ).toBeVisible();
});

test("empty beta page", async ({ page }) => {
  await page.goto("/photo-studio");

  await expect(page.getByRole("heading", { name: "Фотостудия" })).toBeVisible();
  await expect(page.getByText("Проектов пока нет")).toBeVisible();
});

test("API failures render a page error state", async ({ page }) => {
  await page.route("**/api/v1/portal/actions**", async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Не удалось загрузить задачи" }),
    });
  });

  await page.goto("/action-center");

  await expect(page.getByText("Серверная ошибка").first()).toBeVisible();
});

test("results page shows causality warning with До and После markers", async ({
  page,
}) => {
  await page.goto("/results");

  await expect(page.getByRole("heading", { name: "Результаты" })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("Сравнение показывает связь")).toBeVisible();
  await expect(page.getByText(RESULTS_CORRELATION_COPY).first()).toBeVisible();
  await expect(page.getByText(RESULTS_BEFORE_COPY).first()).toBeVisible();
  await expect(
    page.getByText(new RegExp(RESULTS_AFTER_CHANGE_COPY, "i")).first(),
  ).toBeVisible();
  expect(RESULTS_ERROR_COPY).toBe("Не удалось загрузить результаты");
});

test("logistics workspace uses Russian decision-first UI with sortable shipment columns", async ({
  page,
}) => {
  await page.goto("/logistics");

  await expect(page.getByRole("heading", { name: "Логистика WB" })).toBeVisible(
    { timeout: 30_000 },
  );
  await expect(page.getByText("1. Главное")).toBeVisible();
  await expect(
    page.getByText("Где теряются деньги", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Как читать страницу")).toBeVisible();
  await expect(page.getByText("2. Задачи и потерянный спрос")).toHaveCount(0);
  await expect(page.getByText("3. Подробный разбор")).toHaveCount(0);

  await page.getByRole("button", { name: /Потерянный спрос/ }).click();
  await expect(page.getByText("2. Задачи и потерянный спрос")).toBeVisible();
  await expect(page.getByText("1. Главное")).toHaveCount(0);
  await expect(
    page.getByText("Где теряются деньги", { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText("3. Подробный разбор")).toHaveCount(0);
  await page.getByRole("button", { name: /Коледино: дефицит/ }).click();
  await expect(page.getByText("3. Подробный разбор")).toBeVisible();
  await expect(page.getByText("2. Задачи и потерянный спрос")).toHaveCount(0);
  await expect(page.getByText("Очередь задач")).toBeVisible();
  await expect(page.getByText("Контроль маршрута")).toBeVisible();
  await expect(page.getByText("Лучшие направления")).toBeVisible();

  await page.getByRole("button", { name: "Главное" }).click();
  await expect(page.getByText("1. Главное")).toBeVisible();
  await page.getByRole("button", { name: /Запас и отгрузка/ }).click();
  await expect(page.getByText("2. Куда и сколько везти")).toBeVisible();
  await expect(page.getByText("1. Главное")).toHaveCount(0);
  await expect(page.getByText("3. Подробный разбор")).toHaveCount(0);
  await page.getByRole("button", { name: /Коледино.*отгрузка/ }).click();
  await expect(page.getByText("3. Подробный разбор")).toBeVisible();
  await expect(page.getByText("Подсортировка по выгоде")).toBeVisible();
  await expect(page.getByText("Направления")).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Расчёт поставки" }),
  ).toBeVisible();
  await expect(page.getByText("Формула контроля остатков")).toBeVisible();
  await expect(page.getByRole("button", { name: "Рекоменд." })).toBeVisible();
  await page.getByRole("button", { name: "Регион" }).click();
  await expect(
    page.getByRole("button", { name: /Центральный.*дефицит/ }),
  ).toBeVisible();
  if ((page.viewportSize()?.width ?? 1280) < 768) {
    await expect(page.getByText("Остаток").first()).toBeVisible();
    await expect(page.getByText("Скорость").first()).toBeVisible();
    await expect(page.getByText("Цель").first()).toBeVisible();
    await expect(page.getByText("Отгрузка").first()).toBeVisible();
    await expect(page.getByText("Чистый эффект").first()).toBeVisible();
  } else {
    await expect(page.getByRole("button", { name: /Остаток/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /Скорость/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /Цель/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /Отгрузка/ })).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Чистый эффект/ }),
    ).toBeVisible();
  }
  await expect(page.getByText("Net")).toHaveCount(0);
});

test("mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");

  await expect(page.getByRole("button", { name: "AI оператор" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Панель владельца" }),
  ).toBeVisible();
});
