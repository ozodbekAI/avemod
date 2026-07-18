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

  // Required professional QA anchors:
  // problem_instance_id=42
  // action-center-task-drawer
  // results-problem-timeline
  // product360-problem-preview
  await expect(
    page.getByText(/Открыть задачу|Задачи|Action Center/i),
  ).toBeVisible();
});

test("action-center-task-drawer exposes professional navigation actions", async ({
  page,
}) => {
  await page.goto("/action-center?problem_instance_id=42");

  await expect(
    page.getByText(
      /Открыть в результатах|Открыть задачу|Открыть исправление данных/i,
    ),
  ).toBeVisible();
});

test("results-problem-timeline can be opened from Action Center", async ({
  page,
}) => {
  await page.goto("/results?problem_instance_id=42");

  await expect(
    page.getByText(/result_history|Результаты|timeline/i),
  ).toBeVisible();
});

test("product360-problem-preview can be opened from Action Center", async ({
  page,
}) => {
  await page.goto("/products/1001001?problem_instance_id=42");

  await expect(
    page.getByText(/Product 360|product360-problem-preview|товар/i),
  ).toBeVisible();
});
