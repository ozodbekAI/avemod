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

  await expect(
    page.getByRole("heading", { name: "Панель владельца" }),
  ).toBeVisible();
  await expect(page.getByText("Денежный тренд").first()).toBeVisible();

  await page.getByRole("button", { name: "AI оператор" }).click();
  await expect(page.getByText("Администратор портала")).toBeVisible();
});

test("product 360 deep link", async ({ page }) => {
  await page.goto("/products/1001001");

  await expect(
    page.getByRole("heading", {
      name: /Product 360 deep link|Артикул 1001001/i,
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

  await expect(
    page.getByText(/Серверная ошибка|Не удалось загрузить страницу/i).first(),
  ).toBeVisible();
});

test("mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");

  await expect(page.getByRole("button", { name: "AI оператор" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Панель владельца" }),
  ).toBeVisible();
});
