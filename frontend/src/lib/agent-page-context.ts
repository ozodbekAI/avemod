import { getRecentApiSnapshots, type AgentApiSnapshot } from "./api";

type PageMetricSnippet = {
  text: string;
  tag: string;
};

type PageMetricProvenance = {
  key: string;
  label: string;
  value: string;
  source?: string;
  formula?: string;
  api_path?: string;
  updated_at?: string;
};

type ApiField = {
  path: string;
  value: string | number | boolean | null;
};

const PRIORITY_API_FIELD_PATHS = [
  "revenue",
  "net_profit",
  "margin_percent",
  "kpis.revenue",
  "kpis.revenue_final",
  "kpis.net_profit",
  "kpis.net_profit_after_ads",
  "kpis.net_profit_after_overhead",
  "kpis.net_profit_after_all_expenses",
  "kpis.margin_percent",
  "kpis.margin_after_overhead_percent",
  "expense_breakdown.revenue_final",
  "expense_breakdown.net_profit_after_all_expenses",
  "expense_breakdown.total_expenses",
  "expense_breakdown.total_wb_expenses",
  "expense_breakdown.total_seller_expenses",
  "expense_breakdown.seller_cogs",
  "expense_breakdown.seller_other_expense",
  "expense_breakdown.total_ad_expenses",
  "expense_breakdown.ad_spend_final",
  "profit_cascade.totals.net_profit_after_all_expenses",
  "profit_cascade.totals.net_profit_after_overhead",
  "profit_cascade.totals.total_expenses",
  "profit_cascade.revenue.amount",
  "finance_reconciliation.status",
  "trust.financial_final",
  "trust.trust_state",
  "meta.data_trust.financial_final",
  "meta.data_trust.trust_state",
];

function compactText(value: string, limit = 600) {
  const text = collapseWhitespace(value);
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
}

function collapseWhitespace(value: string) {
  let output = "";
  let pendingSpace = false;
  for (const char of value) {
    const isSpace =
      char === " " ||
      char === "\n" ||
      char === "\r" ||
      char === "\t" ||
      char === "\f" ||
      char === "\v";
    if (isSpace) {
      pendingSpace = output.length > 0;
      continue;
    }
    if (pendingSpace) {
      output += " ";
      pendingSpace = false;
    }
    output += char;
  }
  return output;
}

function hasDigit(value: string) {
  for (const char of value) {
    if (char >= "0" && char <= "9") return true;
  }
  return false;
}

function isElementVisible(element: Element) {
  const rect = element.getBoundingClientRect();
  const style = window.getComputedStyle(element);
  return (
    rect.width > 0 &&
    rect.height > 0 &&
    style.display !== "none" &&
    style.visibility !== "hidden" &&
    style.opacity !== "0"
  );
}

function shouldSkip(element: Element) {
  return Boolean(
    element.closest(
      [
        "script",
        "style",
        "noscript",
        "[role='dialog']",
        "[data-agent-ignore='true']",
        ".fixed.bottom-3.right-3",
      ].join(","),
    ),
  );
}

function collectTextChunks(root: Element, limit = 160) {
  const chunks: string[] = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (walker.nextNode() && chunks.length < limit) {
    const node = walker.currentNode;
    const parent = node.parentElement;
    if (!parent || shouldSkip(parent) || !isElementVisible(parent)) continue;
    const text = compactText(node.textContent || "", 260);
    if (text.length < 2) continue;
    chunks.push(text);
  }
  return chunks;
}

function collectHeadings(root: Element) {
  return Array.from(root.querySelectorAll("h1,h2,h3"))
    .filter((element) => !shouldSkip(element) && isElementVisible(element))
    .map((element) => compactText(element.textContent || "", 180))
    .filter(Boolean)
    .slice(0, 24);
}

function collectMetricSnippets(root: Element) {
  const seen = new Set<string>();
  const snippets: PageMetricSnippet[] = [];
  const candidates = Array.from(
    root.querySelectorAll("div,section,article,li,tr,td,button"),
  );
  for (const element of candidates) {
    if (snippets.length >= 60) break;
    if (shouldSkip(element) || !isElementVisible(element)) continue;
    const text = compactText(
      (element as HTMLElement).innerText || element.textContent || "",
      420,
    );
    if (!text || text.length > 280 || !hasDigit(text) || seen.has(text))
      continue;
    if (element.childElementCount > 8) continue;
    seen.add(text);
    snippets.push({ text, tag: element.tagName.toLowerCase() });
  }
  return snippets;
}

function collectMetricProvenance(root: Element) {
  return Array.from(root.querySelectorAll("[data-agent-metric]"))
    .filter((element) => !shouldSkip(element) && isElementVisible(element))
    .map((element) => {
      const item = element as HTMLElement;
      const value = compactText(item.innerText || item.textContent || "", 420);
      const metric: PageMetricProvenance = {
        key: item.dataset.agentMetric || "",
        label:
          item.dataset.agentLabel || item.getAttribute("aria-label") || value,
        value,
      };
      if (item.dataset.agentSource) metric.source = item.dataset.agentSource;
      if (item.dataset.agentFormula) metric.formula = item.dataset.agentFormula;
      if (item.dataset.agentApiPath) {
        metric.api_path = item.dataset.agentApiPath;
      }
      if (item.dataset.agentUpdatedAt) {
        metric.updated_at = item.dataset.agentUpdatedAt;
      }
      return metric;
    })
    .filter((item) => item.key && item.value)
    .slice(0, 80);
}

function flattenApiFields(
  value: unknown,
  prefix = "",
  out: ApiField[] = [],
  depth = 0,
) {
  if (out.length >= 70 || depth > 5) return out;
  if (
    value === null ||
    ["string", "number", "boolean"].includes(typeof value)
  ) {
    if (prefix) {
      out.push({
        path: prefix,
        value: value as string | number | boolean | null,
      });
    }
    return out;
  }
  if (Array.isArray(value)) {
    if (prefix) out.push({ path: `${prefix}.__length`, value: value.length });
    for (const item of value.slice(0, 2)) {
      flattenApiFields(item, `${prefix}[]`, out, depth + 1);
      if (out.length >= 70) break;
    }
    return out;
  }
  if (!value || typeof value !== "object") return out;
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    if (key === "__omitted_keys" || key === "sample" || key === "keys")
      continue;
    const nextPrefix = prefix ? `${prefix}.${key}` : key;
    flattenApiFields(item, nextPrefix, out, depth + 1);
    if (out.length >= 70) break;
  }
  return out;
}

function readPath(value: unknown, path: string): unknown {
  let current = value;
  for (const part of path.split(".")) {
    if (!current || typeof current !== "object" || Array.isArray(current)) {
      return undefined;
    }
    current = (current as Record<string, unknown>)[part];
  }
  return current;
}

function priorityApiFields(summary: unknown) {
  return PRIORITY_API_FIELD_PATHS.map((path) => {
    const value = readPath(summary, path);
    if (
      value === null ||
      ["string", "number", "boolean"].includes(typeof value)
    ) {
      return { path, value: value as string | number | boolean | null };
    }
    return null;
  }).filter((field): field is ApiField => Boolean(field));
}

function compactApiSnapshot(snapshot: AgentApiSnapshot) {
  return {
    method: snapshot.method,
    path: snapshot.path,
    query: snapshot.query,
    status: snapshot.status,
    received_at: snapshot.received_at,
    priority_fields: priorityApiFields(snapshot.summary),
    fields: flattenApiFields(snapshot.summary),
  };
}

export function buildAgentPageContext() {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return {};
  }
  const root =
    document.querySelector("[data-agent-page-root]") ||
    document.querySelector("main") ||
    document.querySelector("[data-sidebar='inset']") ||
    document.body;
  const textChunks = collectTextChunks(root);
  const pageText = compactText(textChunks.join("\n"), 12000);

  return {
    path: window.location.pathname,
    search: window.location.search,
    hash: window.location.hash,
    title: document.title,
    selected_text: compactText(window.getSelection()?.toString() || "", 600),
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight,
    },
    headings: collectHeadings(root),
    visible_text: pageText,
    visible_number_context: collectMetricSnippets(root),
    metric_provenance: collectMetricProvenance(root),
    recent_api: getRecentApiSnapshots().slice(0, 12).map(compactApiSnapshot),
  };
}
