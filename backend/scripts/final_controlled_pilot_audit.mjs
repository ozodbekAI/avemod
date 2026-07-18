#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";

const REQUIRED_ENV = [
  "AUDIT_APP_URL",
  "AUDIT_BASE_URL",
  "AUDIT_EMAIL",
  "AUDIT_PASSWORD",
  "AUDIT_ACCOUNT_ID",
  "AUDIT_EXPECT_PATCH",
];

const REQUIRED_ENDPOINTS = [
  ["POST", "/auth/login"],
  ["GET", "/auth/me"],
  ["GET", "/accounts"],
  ["GET", "/portal/modules/health"],
  ["GET", "/portal/doctor"],
  ["GET", "/portal/actions"],
  ["PATCH", "/portal/actions/by-source"],
  ["GET", "/portal/products"],
  ["GET", "/portal/products/{nm_id}"],
  ["GET", "/portal/results"],
  ["GET", "/portal/cases"],
  ["GET", "/portal/reputation/summary"],
  ["GET", "/portal/reputation/inbox"],
];

const SCREENSHOTS = [
  ["dashboard", "/dashboard"],
  ["ai_profit_doctor", "/dashboard"],
  ["action_center_before", "/actions"],
  ["products", "/cards"],
  ["results", "/results"],
  ["claims", "/claims"],
  ["reputation", "/reputation"],
  ["settings", "/settings"],
];

const STATUS_CANDIDATES = ["in_progress", "done", "postponed", "ignored", "new"];
const TOKEN_KEY_RE =
  /(token|jwt|secret|password|passwd|authorization|api[_-]?key|access[_-]?key|refresh[_-]?token|encrypted[_-]?wb)/i;
const SECRET_VALUE_RE =
  /(eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|Bearer\s+[A-Za-z0-9._-]{16,}|[A-Za-z0-9_=-]{32,})/;

function today() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tashkent",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const year = parts.find((part) => part.type === "year")?.value ?? "1970";
  const month = parts.find((part) => part.type === "month")?.value ?? "01";
  const day = parts.find((part) => part.type === "day")?.value ?? "01";
  return `${year}-${month}-${day}`;
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function writeJson(file, value) {
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

function appendJsonl(file, value) {
  fs.appendFileSync(file, `${JSON.stringify(value)}\n`);
}

function trimBase(value) {
  return String(value || "").replace(/\/+$/, "");
}

function scrub(value, redactions = []) {
  if (Array.isArray(value)) {
    return value.map((item) => scrub(item, redactions));
  }
  if (!value || typeof value !== "object") {
    if (typeof value === "string" && SECRET_VALUE_RE.test(value)) {
      redactions.push("secret_like_value");
      return "[REDACTED]";
    }
    return value;
  }
  const out = {};
  for (const [key, item] of Object.entries(value)) {
    if (TOKEN_KEY_RE.test(key)) {
      redactions.push(key);
      out[key] = "[REDACTED]";
    } else {
      out[key] = scrub(item, redactions);
    }
  }
  return out;
}

function query(accountId, extra = {}) {
  const params = new URLSearchParams();
  if (accountId !== undefined && accountId !== null && accountId !== "") {
    params.set("account_id", String(accountId));
  }
  for (const [key, value] of Object.entries(extra)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

function getItems(payload) {
  if (Array.isArray(payload)) return payload;
  if (payload && Array.isArray(payload.items)) return payload.items;
  if (payload && payload.data && Array.isArray(payload.data.items)) return payload.data.items;
  return [];
}

function firstString(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function firstNumber(...values) {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  }
  return null;
}

function findDeep(value, names) {
  if (!value || typeof value !== "object") return undefined;
  for (const name of names) {
    if (Object.prototype.hasOwnProperty.call(value, name)) return value[name];
  }
  for (const child of Object.values(value)) {
    const found = findDeep(child, names);
    if (found !== undefined) return found;
  }
  return undefined;
}

async function requestJson({ method, baseUrl, pathName, token, body, networkJsonl, endpointKey }) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  const url = `${baseUrl}${pathName}`;
  const started = Date.now();
  let status = 0;
  let payload = null;
  let text = "";
  let error = null;
  try {
    const response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    status = response.status;
    text = await response.text();
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      payload = { text: text.slice(0, 500) };
    }
  } catch (err) {
    error = err instanceof Error ? err.message : String(err);
  }
  const redactions = [];
  const cleanPayload = scrub(payload, redactions);
  const entry = {
    ts: new Date().toISOString(),
    endpoint_key: endpointKey ?? `${method} ${pathName.replace(/\?.*/, "")}`,
    method,
    path: pathName.replace(/\?.*/, ""),
    query: pathName.includes("?") ? pathName.slice(pathName.indexOf("?") + 1) : "",
    status,
    duration_ms: Date.now() - started,
    ok_200: status === 200,
    error,
    body_keys: cleanPayload && typeof cleanPayload === "object" && !Array.isArray(cleanPayload) ? Object.keys(cleanPayload) : [],
    redactions,
    sample: cleanPayload,
  };
  appendJsonl(networkJsonl, entry);
  return { status, payload: cleanPayload, entry };
}

function classifyUser(mePayload) {
  const role = firstString(
    mePayload?.role,
    mePayload?.user?.role,
    mePayload?.data?.role,
    mePayload?.permissions?.role,
  );
  const isSuperuser =
    mePayload?.is_superuser === true ||
    mePayload?.is_admin === true ||
    mePayload?.user?.is_superuser === true ||
    mePayload?.user?.is_admin === true ||
    role === "superuser" ||
    role === "admin";
  return {
    role: role ?? null,
    is_superuser: Boolean(isSuperuser),
    seller_rbac_proof: isSuperuser ? "NOT_RUN" : "PASS",
  };
}

function findProductId(productsPayload) {
  const first = getItems(productsPayload)[0];
  return firstNumber(
    first?.nm_id,
    first?.identity?.nm_id,
    first?.data?.nm_id,
    findDeep(first, ["nm_id"]),
  );
}

function findSkuId(productsPayload, productDetail) {
  const first = getItems(productsPayload)[0];
  return firstNumber(
    first?.sku_id,
    first?.id,
    first?.linked_entity?.sku_id,
    productDetail?.identity?.sku_id,
    productDetail?.sku_id,
    productDetail?.id,
    findDeep(productDetail, ["sku_id"]),
  );
}

function findPatchableAction(actionsPayload) {
  return getItems(actionsPayload).find((item) => {
    const sourceModule = firstString(item?.source_module, item?.source?.module, item?.sourceModule);
    const sourceId = firstString(item?.source_id, item?.source?.id, item?.external_id, item?.sourceId);
    return sourceModule && sourceId;
  });
}

function product360Acceptance(product) {
  const title = firstString(product?.title, product?.identity?.title, product?.data?.title, findDeep(product, ["title"]));
  const revenue = firstNumber(
    product?.revenue,
    product?.for_pay,
    product?.money?.revenue,
    product?.money?.for_pay,
    findDeep(product, ["revenue", "for_pay"]),
  );
  const profit = firstNumber(product?.profit, product?.money?.profit, product?.money?.profit?.after_ads, findDeep(product, ["profit"]));
  const margin = firstNumber(product?.margin, product?.margin_percent, product?.money?.margin, product?.money?.margin_percent, findDeep(product, ["margin", "margin_percent"]));
  const cost = firstNumber(product?.cost, product?.unit_cost, product?.money?.cogs?.unit_cost, findDeep(product, ["cost", "unit_cost"]));
  const stock = firstNumber(product?.stock, product?.stock_quantity, product?.stock?.quantity, findDeep(product, ["stock", "stock_quantity", "quantity"]));
  const quality = firstString(product?.quality?.status, product?.data_quality?.status, product?.status, findDeep(product, ["quality_status", "data_status", "status"]));
  const actions = getItems(product?.actions ?? { items: product?.actions }).length || (Array.isArray(product?.actions) ? product.actions.length : 0);
  return {
    product_title: title ? "PASS" : "FAIL",
    revenue_or_for_pay: revenue !== null ? "PASS" : "FAIL",
    profit: profit !== null ? "PASS" : "FAIL",
    margin: margin !== null ? "PASS" : "FAIL",
    cost: cost !== null ? "PASS" : "FAIL",
    stock_or_unavailable_state: stock !== null || JSON.stringify(product).includes("unavailable") ? "PASS" : "FAIL",
    quality_data_status: quality ? "PASS" : "FAIL",
    product_actions: actions > 0 ? "PASS" : "FAIL",
  };
}

function moduleStatusAcceptance(health, cases, repSummary, repInbox) {
  const text = JSON.stringify({ health, cases, repSummary, repInbox }).toLowerCase();
  return {
    core_modules_connected: /finance|money|dashboard|products/.test(text) && /ok|connected|healthy/.test(text) ? "PASS" : "FAIL",
    checker_explicit_state: /checker/.test(text) && /(not_configured|connected|disabled|unavailable|ok)/.test(text) ? "PASS" : "FAIL",
    claims_disabled_or_connected: /claim|case/.test(text) && /(disabled|not_configured|connected|ok|empty|unavailable)/.test(text) ? "PASS" : "FAIL",
    reputation_disabled_or_connected: /reputation/.test(text) && /(disabled|not_configured|connected|ok|empty|unavailable)/.test(text) ? "PASS" : "FAIL",
    stockops_explicit_state: /stockops/.test(text) && /(not_configured|connected|disabled|unavailable|ok)/.test(text) ? "PASS" : "FAIL",
  };
}

function scoreFromChecks(checks) {
  const values = Object.values(checks);
  if (!values.length) return 0;
  return Math.round((values.filter((value) => value === "PASS").length / values.length) * 100);
}

async function runBrowserAudit({ appUrl, email, password, accountId, skuId, outDir, networkJsonl, summary }) {
  let puppeteer;
  try {
    puppeteer = await import("puppeteer-core");
  } catch {
    try {
      const requireFromFrontend = createRequire(path.resolve("frontend/package.json"));
      puppeteer = requireFromFrontend("puppeteer-core");
    } catch {
      summary.browser_error = "puppeteer-core is not installed. Run from frontend/: npm install --no-save --package-lock=false puppeteer-core";
      return;
    }
  }
  const chromePath = process.env.AUDIT_CHROME_PATH || "/usr/bin/google-chrome";
  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: "new",
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--window-size=1440,1100"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 1100, deviceScaleFactor: 1 });
  page.on("response", async (response) => {
    const url = response.url();
    if (!url.includes("/api/")) return;
    appendJsonl(networkJsonl, {
      ts: new Date().toISOString(),
      source: "browser",
      method: response.request().method(),
      url: url.replace(/([?&](password|token|authorization)=)[^&]+/gi, "$1[REDACTED]"),
      status: response.status(),
      ok_200: response.status() === 200,
    });
  });

  try {
    await page.goto(`${appUrl}/login`, { waitUntil: "networkidle2", timeout: 45000 });
    await page.$eval('input[type="email"]', (el, value) => {
      el.value = value;
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }, email);
    await page.$eval('input[type="password"]', (el, value) => {
      el.value = value;
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }, password);
    await Promise.all([
      page.waitForNavigation({ waitUntil: "networkidle2", timeout: 45000 }).catch(() => null),
      page.click('button[type="submit"]'),
    ]);
    summary.login_page_after_submit_url = page.url();
    await page.evaluate((value) => {
      window.localStorage.setItem("wb-account-id", String(value));
    }, accountId);

    const screenshotDir = path.join(outDir, "screenshots");
    ensureDir(screenshotDir);
    const pageResults = {};
    for (const [name, route] of SCREENSHOTS) {
      const url = `${appUrl}${route}`;
      await page.goto(url, { waitUntil: "networkidle2", timeout: 45000 }).catch(() => null);
      await page.evaluate((value) => {
        window.localStorage.setItem("wb-account-id", String(value));
      }, accountId);
      await new Promise((resolve) => setTimeout(resolve, 1200));
      const screenshotPath = path.join(screenshotDir, `${name}.png`);
      await page.screenshot({ path: screenshotPath, fullPage: true });
      const text = await page.evaluate(() => document.body.innerText.slice(0, 5000));
      pageResults[name] = {
        route,
        final_url: page.url(),
        screenshot: `screenshots/${name}.png`,
        login_page_detected: /Авторизуйтесь|Вход администратора|Email\s*Пароль|login/i.test(text) || page.url().includes("/login"),
        not_found_detected: /404|not found/i.test(text),
      };
    }
    if (skuId) {
      await page.goto(`${appUrl}/cards/${skuId}`, { waitUntil: "networkidle2", timeout: 45000 }).catch(() => null);
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await page.screenshot({ path: path.join(screenshotDir, "product_360.png"), fullPage: true });
      const text = await page.evaluate(() => document.body.innerText.slice(0, 8000));
      pageResults.product_360 = {
        route: `/cards/${skuId}`,
        final_url: page.url(),
        screenshot: "screenshots/product_360.png",
        login_page_detected: /Авторизуйтесь|Вход администратора|Email\s*Пароль|login/i.test(text) || page.url().includes("/login"),
        not_found_detected: /404|not found/i.test(text),
      };
    }
    await page.goto(`${appUrl}/actions`, { waitUntil: "networkidle2", timeout: 45000 }).catch(() => null);
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await page.screenshot({ path: path.join(screenshotDir, "action_center_after.png"), fullPage: true });
    pageResults.action_center_after = {
      route: "/actions",
      final_url: page.url(),
      screenshot: "screenshots/action_center_after.png",
      login_page_detected: page.url().includes("/login"),
    };
    summary.screenshots = pageResults;
  } finally {
    await browser.close();
  }
}

function scanArtifacts(outDir, zipName) {
  const findings = [];
  const skip = new Set([zipName]);
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (!skip.has(entry.name) && !/\.(png|jpg|jpeg)$/i.test(entry.name)) {
        const text = fs.readFileSync(full, "utf8");
        const lines = text.split(/\r?\n/);
        lines.forEach((line, index) => {
          if (TOKEN_KEY_RE.test(line) && SECRET_VALUE_RE.test(line)) {
            findings.push({ file: path.relative(outDir, full), line: index + 1 });
          }
        });
      }
    }
  }
  walk(outDir);
  return findings;
}

async function main() {
  const date = today();
  const outDir = path.resolve(`FINAL_CONTROLLED_PILOT_ACCEPTANCE_AUDIT_${date}`);
  const zipPath = path.resolve(`FINAL_CONTROLLED_PILOT_ACCEPTANCE_AUDIT_${date}.zip`);
  fs.rmSync(outDir, { recursive: true, force: true });
  fs.rmSync(zipPath, { force: true });
  ensureDir(path.join(outDir, "screenshots"));
  const networkJsonl = path.join(outDir, "network.jsonl");
  fs.writeFileSync(networkJsonl, "");

  const env = Object.fromEntries(REQUIRED_ENV.map((key) => [key, process.env[key] || ""]));
  const missingEnv = REQUIRED_ENV.filter((key) => !env[key]);
  const summary = {
    audit_date: date,
    audit_app_url_present: Boolean(env.AUDIT_APP_URL),
    audit_base_url_present: Boolean(env.AUDIT_BASE_URL),
    audit_account_id: env.AUDIT_ACCOUNT_ID || null,
    missing_env: missingEnv,
    seller_rbac_proof: "NOT_RUN",
    endpoint_proof: {},
    product360_acceptance: {},
    action_center_acceptance: {},
    module_ux_acceptance: {},
    screenshots: {},
    secret_scan: { status: "NOT_RUN", findings: [] },
    scores: {},
    controlled_pilot_readiness: "NO_GO",
    public_mvp_readiness: "NO_GO",
  };

  const baseUrl = trimBase(env.AUDIT_BASE_URL);
  const appUrl = trimBase(env.AUDIT_APP_URL);
  const accountId = env.AUDIT_ACCOUNT_ID;
  let token = null;
  let endpoints = {};
  let productsPayload = null;
  let productPayload = null;
  let actionsPayload = null;
  let skuId = null;

  if (missingEnv.length === 0) {
    const login = await requestJson({
      method: "POST",
      baseUrl,
      pathName: "/auth/login",
      body: { email: env.AUDIT_EMAIL, password: env.AUDIT_PASSWORD },
      networkJsonl,
      endpointKey: "POST /auth/login",
    });
    token = firstString(login.payload?.access_token, login.payload?.token, login.payload?.data?.access_token);
    endpoints["POST /auth/login"] = login.status;

    const me = await requestJson({ method: "GET", baseUrl, pathName: "/auth/me", token, networkJsonl, endpointKey: "GET /auth/me" });
    endpoints["GET /auth/me"] = me.status;
    Object.assign(summary, classifyUser(me.payload));

    const accounts = await requestJson({ method: "GET", baseUrl, pathName: "/accounts", token, networkJsonl, endpointKey: "GET /accounts" });
    endpoints["GET /accounts"] = accounts.status;

    const health = await requestJson({ method: "GET", baseUrl, pathName: `/portal/modules/health${query(accountId)}`, token, networkJsonl, endpointKey: "GET /portal/modules/health" });
    endpoints["GET /portal/modules/health"] = health.status;

    const doctor = await requestJson({ method: "GET", baseUrl, pathName: `/portal/doctor${query(accountId, { period: "30d" })}`, token, networkJsonl, endpointKey: "GET /portal/doctor" });
    endpoints["GET /portal/doctor"] = doctor.status;

    const actions = await requestJson({ method: "GET", baseUrl, pathName: `/portal/actions${query(accountId, { limit: 20, offset: 0 })}`, token, networkJsonl, endpointKey: "GET /portal/actions" });
    actionsPayload = actions.payload;
    endpoints["GET /portal/actions"] = actions.status;

    const patchable = findPatchableAction(actionsPayload);
    let patchStatus = 0;
    let persisted = false;
    let readonlyReason = "No action with source_module/source_id was available for by-source PATCH.";
    if (patchable && env.AUDIT_EXPECT_PATCH === "1") {
      const sourceModule = firstString(patchable.source_module, patchable.source?.module, patchable.sourceModule);
      const sourceId = firstString(patchable.source_id, patchable.source?.id, patchable.external_id, patchable.sourceId);
      const currentStatus = firstString(patchable.status) || "new";
      const nextStatus = STATUS_CANDIDATES.find((item) => item !== currentStatus) || "in_progress";
      const patch = await requestJson({
        method: "PATCH",
        baseUrl,
        pathName: "/portal/actions/by-source",
        token,
        body: {
          account_id: Number(accountId),
          source_module: sourceModule,
          source_id: sourceId,
          status: nextStatus,
          comment: "controlled pilot acceptance audit status persistence proof",
        },
        networkJsonl,
        endpointKey: "PATCH /portal/actions/by-source",
      });
      patchStatus = patch.status;
      const reload = await requestJson({ method: "GET", baseUrl, pathName: `/portal/actions${query(accountId, { limit: 50, offset: 0 })}`, token, networkJsonl, endpointKey: "GET /portal/actions reload after PATCH" });
      persisted = getItems(reload.payload).some((item) => {
        const sameSource =
          firstString(item.source_module, item.source?.module, item.sourceModule) === sourceModule &&
          firstString(item.source_id, item.source?.id, item.external_id, item.sourceId) === sourceId;
        return sameSource && firstString(item.status) === nextStatus;
      });
      readonlyReason = null;
    } else {
      appendJsonl(networkJsonl, {
        ts: new Date().toISOString(),
        endpoint_key: "PATCH /portal/actions/by-source",
        method: "PATCH",
        path: "/portal/actions/by-source",
        status: patchStatus,
        ok_200: false,
        skipped: true,
        reason: readonlyReason,
      });
    }
    endpoints["PATCH /portal/actions/by-source"] = patchStatus;
    summary.action_center_acceptance = {
      at_least_one_action: getItems(actionsPayload).length > 0 ? "PASS" : "FAIL",
      priority_label: JSON.stringify(actionsPayload).includes("priority") ? "PASS" : "FAIL",
      reason_next_step: /(reason|why|next|what_to_do|next_step)/i.test(JSON.stringify(actionsPayload)) ? "PASS" : "FAIL",
      status_controls_for_updateable_action: patchable ? "PASS" : "FAIL",
      readonly_reason_for_non_updateable_action: patchable ? "PASS" : "FAIL",
      patch_200: patchStatus === 200 ? "PASS" : "FAIL",
      status_persisted_after_reload: persisted ? "PASS" : "FAIL",
      readonly_reason: readonlyReason,
    };

    const products = await requestJson({ method: "GET", baseUrl, pathName: `/portal/products${query(accountId, { limit: 20, offset: 0 })}`, token, networkJsonl, endpointKey: "GET /portal/products" });
    productsPayload = products.payload;
    endpoints["GET /portal/products"] = products.status;
    const nmId = findProductId(productsPayload);
    if (nmId) {
      const product = await requestJson({ method: "GET", baseUrl, pathName: `/portal/products/${nmId}${query(accountId)}`, token, networkJsonl, endpointKey: "GET /portal/products/{nm_id}" });
      productPayload = product.payload;
      endpoints["GET /portal/products/{nm_id}"] = product.status;
      summary.product360_acceptance = product360Acceptance(productPayload);
      skuId = findSkuId(productsPayload, productPayload) || nmId;
    } else {
      endpoints["GET /portal/products/{nm_id}"] = 0;
      appendJsonl(networkJsonl, {
        ts: new Date().toISOString(),
        endpoint_key: "GET /portal/products/{nm_id}",
        method: "GET",
        path: "/portal/products/{nm_id}",
        status: 0,
        ok_200: false,
        skipped: true,
        reason: "No nm_id found in products list.",
      });
      summary.product360_acceptance = product360Acceptance(null);
    }

    const results = await requestJson({ method: "GET", baseUrl, pathName: `/portal/results${query(accountId, { limit: 20, offset: 0 })}`, token, networkJsonl, endpointKey: "GET /portal/results" });
    endpoints["GET /portal/results"] = results.status;
    const cases = await requestJson({ method: "GET", baseUrl, pathName: `/portal/cases${query(accountId, { limit: 20, offset: 0 })}`, token, networkJsonl, endpointKey: "GET /portal/cases" });
    endpoints["GET /portal/cases"] = cases.status;
    const repSummary = await requestJson({ method: "GET", baseUrl, pathName: `/portal/reputation/summary${query(accountId)}`, token, networkJsonl, endpointKey: "GET /portal/reputation/summary" });
    endpoints["GET /portal/reputation/summary"] = repSummary.status;
    const repInbox = await requestJson({ method: "GET", baseUrl, pathName: `/portal/reputation/inbox${query(accountId, { limit: 20, offset: 0 })}`, token, networkJsonl, endpointKey: "GET /portal/reputation/inbox" });
    endpoints["GET /portal/reputation/inbox"] = repInbox.status;
    summary.module_ux_acceptance = moduleStatusAcceptance(health.payload, cases.payload, repSummary.payload, repInbox.payload);

    await runBrowserAudit({
      appUrl,
      email: env.AUDIT_EMAIL,
      password: env.AUDIT_PASSWORD,
      accountId,
      skuId,
      outDir,
      networkJsonl,
      summary,
    });
  }

  for (const [method, endpoint] of REQUIRED_ENDPOINTS) {
    const key = `${method} ${endpoint}`;
    summary.endpoint_proof[key] = endpoints[key] === 200 ? "PASS" : "FAIL";
  }

  const loginPageScreenshots = Object.values(summary.screenshots || {}).filter((item) => item.login_page_detected);
  const missingScreenshots = [
    "dashboard",
    "ai_profit_doctor",
    "action_center_before",
    "action_center_after",
    "products",
    "product_360",
    "results",
    "claims",
    "reputation",
    "settings",
  ].filter((name) => !summary.screenshots?.[name]);
  summary.screenshot_acceptance = {
    all_required_screenshots_present: missingScreenshots.length === 0 ? "PASS" : "FAIL",
    no_login_page_screenshots_for_protected_pages: loginPageScreenshots.length === 0 ? "PASS" : "FAIL",
    missing_screenshots: missingScreenshots,
    login_page_screenshots: loginPageScreenshots.map((item) => item.route),
  };

  const networkSummary = {
    required_endpoints: summary.endpoint_proof,
    all_required_200: Object.values(summary.endpoint_proof).every((value) => value === "PASS"),
  };
  writeJson(path.join(outDir, "network_summary.json"), networkSummary);

  const securityFindings = scanArtifacts(outDir, path.basename(zipPath));
  summary.secret_scan = {
    status: securityFindings.length === 0 ? "PASS" : "FAIL",
    findings: securityFindings,
  };

  summary.scores = {
    backend_runtime_score: scoreFromChecks(summary.endpoint_proof),
    frontend_integration_score: scoreFromChecks(summary.screenshot_acceptance),
    product360_score: scoreFromChecks(summary.product360_acceptance),
    action_center_score: scoreFromChecks(summary.action_center_acceptance),
    module_status_score: scoreFromChecks(summary.module_ux_acceptance),
    security_audit_score: summary.secret_scan.status === "PASS" ? 100 : 0,
  };
  const controlledPilotGo =
    Object.values(summary.product360_acceptance).every((value) => value === "PASS") &&
    summary.action_center_acceptance.patch_200 === "PASS" &&
    summary.action_center_acceptance.status_persisted_after_reload === "PASS" &&
    summary.screenshot_acceptance.no_login_page_screenshots_for_protected_pages === "PASS" &&
    summary.secret_scan.status === "PASS" &&
    networkSummary.all_required_200 &&
    Object.values(summary.module_ux_acceptance).every((value) => value === "PASS");
  summary.controlled_pilot_readiness = controlledPilotGo ? "GO" : "NO_GO";
  summary.public_mvp_readiness = controlledPilotGo && summary.seller_rbac_proof === "PASS" ? "GO" : "NO_GO";

  writeJson(path.join(outDir, "summary.json"), summary);
  fs.writeFileSync(
    path.join(outDir, "README.md"),
    [
      `# Final Controlled Pilot Acceptance Audit ${date}`,
      "",
      `Controlled pilot readiness: ${summary.controlled_pilot_readiness}`,
      `Public MVP readiness: ${summary.public_mvp_readiness}`,
      `Seller RBAC proof: ${summary.seller_rbac_proof}`,
      "",
      "Artifacts:",
      "- `summary.json` contains scoring and pass/fail decisions.",
      "- `network.jsonl` contains sanitized request/response proof.",
      "- `network_summary.json` rolls up required endpoint 200 proof.",
      "- `screenshots/` contains browser evidence when the required env and browser tooling are available.",
      "",
      missingEnv.length ? `Missing required environment: ${missingEnv.join(", ")}` : "Required environment was present.",
      summary.browser_error ? `Browser audit error: ${summary.browser_error}` : "",
      "",
    ].filter(Boolean).join("\n"),
  );

  const zip = spawnSync("zip", ["-qr", zipPath, path.basename(outDir)], {
    cwd: path.dirname(outDir),
    encoding: "utf8",
  });
  if (zip.status !== 0) {
    throw new Error(zip.stderr || "zip failed");
  }
  console.log(zipPath);
  console.log(JSON.stringify({
    controlled_pilot_readiness: summary.controlled_pilot_readiness,
    public_mvp_readiness: summary.public_mvp_readiness,
    missing_env: missingEnv,
    browser_error: summary.browser_error || null,
  }, null, 2));
  process.exit(summary.controlled_pilot_readiness === "GO" ? 0 : 2);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
