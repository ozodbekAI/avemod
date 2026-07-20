import { expect, test } from "@playwright/test";

import { installMockApi } from "./mock-api";

test.beforeEach(async ({ page }) => {
  await installMockApi(page);
  await page.addInitScript(() => {
    localStorage.setItem("wb.access_token", "e2e-access-token");
    localStorage.setItem("wb.refresh_token", "e2e-refresh-token");
    localStorage.setItem("wb.active_account_id", "1");
  });
});

test("same dynamic problem is traceable through Action Center, Product360 and Results", async ({
  page,
}) => {
  await page.goto("/action-center?problem_instance_id=42");

  await expect(
    page.getByRole("heading", { name: "Центр действий" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Данные и себестоимость/i }),
  ).toBeVisible();

  await page.goto("/products/1001001?problem_instance_id=42");
  await expect(
    page.getByRole("heading", { name: "Главные проблемы" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Проблема.*Открыть задачу/i }).first(),
  ).toBeVisible();

  await page.goto("/results?problem_instance_id=42");
  await expect(page.getByRole("heading", { name: "Результаты" })).toBeVisible();
  await expect(page.getByText("Журнал событий")).toBeVisible();
});

test("action-center-task-drawer exposes professional navigation actions", async ({
  page,
}) => {
  await page.goto("/action-center?problem_instance_id=42");

  await page.getByRole("button", { name: /Данные и себестоимость/i }).click();
  await expect(
    page.getByRole("heading", { name: /Нет себестоимости/i }),
  ).toBeVisible();
  await expect(page.getByText("Заполнить себестоимость")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Перепроверить" }),
  ).toBeVisible();
  await expect(page.getByText("Открыть в результатах")).toBeVisible();
  await expect(page.getByText("Открыть исправление данных")).toBeVisible();
});

test("results-problem-timeline can be opened from Action Center", async ({
  page,
}) => {
  await page.goto("/results?problem_instance_id=42");

  await expect(page.getByRole("heading", { name: "Результаты" })).toBeVisible();
  await expect(page.getByText("Журнал событий")).toBeVisible();
});

test("product360-problem-preview can be opened from Action Center", async ({
  page,
}) => {
  await page.goto("/products/1001001?problem_instance_id=42");

  await expect(
    page.getByRole("heading", { name: "Главные проблемы" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Проблема.*Открыть задачу/i }).first(),
  ).toBeVisible();
  await expect(page.getByText("Открыть задачу").first()).toBeVisible();
});
