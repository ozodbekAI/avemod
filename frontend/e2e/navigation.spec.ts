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

test("authenticated canonical navigation", async ({ page }) => {
  await page.goto("/dashboard");

  await expect(page.getByText("Панель владельца")).toBeVisible();
  await expect(page.getByText("Корреляция, а не гарантия")).toBeVisible();

  await page.getByRole("button", { name: "AI оператор" }).click();
  await expect(page.getByText("Администратор портала")).toBeVisible();
});

test("product 360 deep link", async ({ page }) => {
  await page.goto("/products/1001001");

  await expect(
    page.getByText(/Product 360 deep link|Product 360|товар/i),
  ).toBeVisible();
});

test("empty beta page", async ({ page }) => {
  await page.goto("/photo-studio");

  await expect(
    page.getByText(/Проектов пока нет|Photo Studio|Фотостудия/i),
  ).toBeVisible();
});

test("API failures render a page error state", async ({ page }) => {
  await page.route("**/api/v1/portal/dashboard/overview**", async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Не удалось загрузить результаты" }),
    });
  });

  await page.goto("/dashboard");

  await expect(
    page.getByText(/Не удалось загрузить результаты|ошибка|Ошибка/i),
  ).toBeVisible();
});

test("mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");

  await expect(page.getByRole("button", { name: "AI оператор" })).toBeVisible();
  await expect(page.getByText("До действия")).toBeVisible();
  await expect(page.getByText("После изменения")).toBeVisible();
});
