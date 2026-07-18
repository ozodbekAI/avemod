import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5173";
const webServerURL = new URL(baseURL);
const webServerHost = webServerURL.hostname || "127.0.0.1";
const webServerPort =
  webServerURL.port || (webServerURL.protocol === "https:" ? "443" : "80");

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  webServer: {
    command: `npm run dev -- --host ${webServerHost} --port ${webServerPort} --strictPort`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: "Desktop Chrome",
      use: {
        ...devices["Desktop Chrome"],
        channel: "chrome",
      },
    },
    {
      name: "Pixel 5",
      use: {
        ...devices["Pixel 5"],
      },
    },
  ],
});
