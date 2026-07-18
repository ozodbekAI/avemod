// @ts-nocheck
import type {
  PortalAction,
  PortalResultEventsPage,
  ProblemResultEvent,
  ProblemResultStatus,
  ProblemResultSummary,
} from "@/lib/portal";
import { problemCodeLabel } from "@/lib/problem-ux-copy";
import { humanizeMessage } from "@/lib/results-i18n";

type JsonRecord = Record<string, unknown>;

type PortalActionResultAdapterFields = PortalAction & {
  problem_instance_id?: unknown;
  problem_code?: unknown;
  payload?: JsonRecord & {
    problem_instance_id?: unknown;
    problem_code?: unknown;
  };
  raw?: JsonRecord & {
    problem_instance_id?: unknown;
    problem_code?: unknown;
  };
};

export const PROBLEM_RESULT_CORRELATION_DISCLAIMER =
  "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе.";

function isRecord(value: unknown): value is JsonRecord {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function compactRecord(value: unknown): JsonRecord {
  return isRecord(value) ? value : {};
}

function hasKeys(value: unknown): boolean {
  return isRecord(value) && Object.keys(value).length > 0;
}

function resultRecords(value: unknown): JsonRecord[] {
  const raw = compactRecord(value);
  const records: JsonRecord[] = [raw];
  const summary = compactRecord(raw.summary);
  if (hasKeys(summary)) records.push(summary);
  const payload = compactRecord(raw.payload);
  if (hasKeys(payload)) records.push(payload);
  const items = Array.isArray(raw.items)
    ? raw.items
    : Array.isArray(raw.recent_events)
      ? raw.recent_events
      : [];
  for (const item of items) {
    const event = compactRecord(item);
    records.push(event);
    const eventPayload = compactRecord(event.payload);
    if (hasKeys(eventPayload)) records.push(eventPayload);
  }
  return records;
}

export function problemResultHasAfterData(value: unknown): boolean {
  return resultRecords(value).some((record) => {
    if (hasKeys(record.after_snapshot)) return true;
    const comparison = compactRecord(record.comparison);
    const windows = compactRecord(record.finance_windows ?? record.windows);
    return Object.values(windows).some((window) => {
      const windowRecord = compactRecord(window);
      return hasKeys(windowRecord.after_snapshot);
    });
  });
}

export function problemResultHasConfidence(value: unknown): boolean {
  return resultRecords(value).some((record) => {
    const confidence =
      record.confidence ?? record.confidence_label ?? record.trust_state;
    return confidence != null && String(confidence).trim() !== "";
  });
}

export function problemResultCanClaimSavedMoney(value: unknown): boolean {
  return (
    problemResultHasAfterData(value) &&
    problemResultHasConfidence(value) &&
    problemResultSavedMoneyClaimed(value)
  );
}

export function problemResultSavedMoneyClaimed(value: unknown): boolean {
  return resultRecords(value).some(
    (record) => record.saved_money_claimed === true,
  );
}

function normalized(value: unknown): string {
  return String(value ?? "")
    .trim()
    .toLowerCase();
}

function textValue(value: unknown): string | null {
  const text = String(value ?? "").trim();
  return text ? text : null;
}

function recordText(record: JsonRecord, keys: string[]): string | null {
  for (const key of keys) {
    const value = textValue(record[key]);
    if (value) return value;
  }
  return null;
}

function productTitleFromEvent(
  event?: ProblemResultEvent | null,
): string | null {
  const productIdentity = compactRecord(event?.product_identity);
  return (
    recordText(productIdentity, ["title", "name", "product_title"]) ??
    textValue(event?.payload?.product_title)
  );
}

function nmIdFromEvent(event?: ProblemResultEvent | null): string | null {
  const productIdentity = compactRecord(event?.product_identity);
  return textValue(productIdentity.nm_id) ?? textValue(event?.nm_id);
}

function problemTitleFromRecord(record: JsonRecord): string | null {
  return recordText(record, [
    "title",
    "problem_title",
    "dynamic_problem_title",
    "action_title",
  ]);
}

function problemTitleFromEvent(
  event?: ProblemResultEvent | null,
): string | null {
  if (!event) return null;
  const payload = compactRecord(event.payload);
  return (
    problemTitleFromRecord(payload) ??
    problemTitleFromRecord(compactRecord(event.before_snapshot)) ??
    problemTitleFromRecord(compactRecord(event.after_snapshot)) ??
    problemTitleFromRecord(compactRecord(payload.current_snapshot)) ??
    problemTitleFromRecord(compactRecord(payload.before_snapshot))
  );
}

export function problemResultTimelineTitleFromEvents(
  events: ProblemResultEvent[],
): string {
  const eventWithTitle = events.find((event) => problemTitleFromEvent(event));
  const latest = events[0];
  const title = problemTitleFromEvent(eventWithTitle ?? latest);
  if (title) return title;

  const code = latest?.problem_code ?? latest?.payload?.problem_code;
  const label = problemCodeLabel(code);
  const productTitle = productTitleFromEvent(latest);
  if (productTitle) return `${label} — ${productTitle}`;

  const nmId = nmIdFromEvent(latest);
  if (nmId) return `${label} · nmID ${nmId}`;

  return label;
}

export function problemResultTimelineStoryFromEvents(
  events: ProblemResultEvent[],
): {
  before: boolean;
  action: boolean;
  recheck: boolean;
  after: boolean;
  comparison: boolean;
  confidence: boolean;
} {
  const pageLike = { items: events, recent_events: events };
  const after = problemResultHasAfterData(pageLike);
  return {
    before: events.some(
      (event) =>
        event.event_type === "before_snapshot" ||
        hasKeys(event.before_snapshot),
    ),
    action: events.some((event) =>
      ["action_started", "action_completed"].includes(event.event_type),
    ),
    recheck: events.some((event) =>
      String(event.event_type ?? "").includes("recheck"),
    ),
    after,
    comparison:
      after &&
      events.some((event) => {
        if (
          event.event_type === "measured_comparison" ||
          event.event_type === "result_evaluated"
        )
          return true;
        if (hasKeys(event.comparison?.metrics)) return true;
        return hasKeys(event.payload?.comparison?.metrics);
      }),
    confidence: events.some((event) => {
      const confidence = event.confidence ?? event.payload?.confidence;
      return confidence != null && String(confidence).trim() !== "";
    }),
  };
}

export function problemResultEvents(
  page?: PortalResultEventsPage | null,
): ProblemResultEvent[] {
  if (!page) return [];
  if (Array.isArray(page.items) && page.items.length > 0) return page.items;
  if (Array.isArray(page.recent_events)) return page.recent_events;
  return [];
}

export function problemInstanceIdFromAction(
  action?: PortalAction | null,
): number | null {
  const adapted = action as PortalActionResultAdapterFields | null | undefined;
  const raw =
    adapted?.problem_instance_id ??
    adapted?.payload?.problem_instance_id ??
    adapted?.raw?.problem_instance_id ??
    String(action?.source_id ?? "")
      .split(":")
      .pop();
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function problemCodeFromAction(
  action?: PortalAction | null,
): string | null {
  const adapted = action as PortalActionResultAdapterFields | null | undefined;
  const code = String(
    adapted?.problem_code ??
      adapted?.payload?.problem_code ??
      adapted?.raw?.problem_code ??
      action?.detector_code ??
      action?.action_type ??
      "",
  )
    .trim()
    .toLowerCase();
  return code || null;
}

export function isProblemEngineResult(
  event: ProblemResultEvent | null | undefined,
): boolean {
  return (
    event?.source_module === "problem_engine" ||
    !!event?.problem_instance_id ||
    !!event?.problem_code
  );
}

function statusFromOutcome(value: unknown): ProblemResultStatus | null {
  const key = normalized(value);
  if (
    [
      "pending_data",
      "pending",
      "waiting_data",
      "waiting_for_data",
      "awaiting_data",
    ].includes(key)
  )
    return "pending_data";
  if (["improved", "better", "success", "positive"].includes(key))
    return "improved";
  if (["worse", "degraded", "negative", "regressed"].includes(key))
    return "worse";
  if (["neutral", "no_change", "unchanged", "same"].includes(key))
    return "neutral";
  if (
    [
      "not_enough_data",
      "no_data",
      "insufficient_data",
      "missing_data",
      "blocked",
    ].includes(key)
  )
    return "not_enough_data";
  return null;
}

export function problemResultStatusFromSummary(
  summary?: Partial<ProblemResultSummary> | JsonRecord | null,
): ProblemResultStatus {
  const raw = compactRecord(summary);
  const hasAfterData = problemResultHasAfterData(raw);
  const direct = statusFromOutcome(
    raw.status ?? raw.result_status ?? raw.outcome,
  );
  if (direct) {
    if (["improved", "worse", "neutral"].includes(direct) && !hasAfterData)
      return "pending_data";
    if (
      direct === "not_enough_data" &&
      !hasAfterData &&
      (hasKeys(raw.before_snapshot) || Array.isArray(raw.events))
    )
      return "pending_data";
    return direct;
  }
  const comparison = raw.comparison;
  if (typeof comparison === "string") {
    const fromComparison = statusFromOutcome(comparison);
    if (fromComparison) {
      if (
        ["improved", "worse", "neutral"].includes(fromComparison) &&
        !hasAfterData
      )
        return "pending_data";
      return fromComparison;
    }
  }
  if (isRecord(comparison)) {
    const fromComparison = statusFromOutcome(
      comparison.outcome ?? comparison.status ?? comparison.direction,
    );
    if (fromComparison) {
      if (
        ["improved", "worse", "neutral"].includes(fromComparison) &&
        !hasAfterData
      )
        return "pending_data";
      return fromComparison;
    }
  }
  if (!hasAfterData)
    return hasKeys(raw.before_snapshot) || raw.events?.length
      ? "pending_data"
      : "pending_data";
  const metrics = compactRecord(raw.metrics);
  const directions = Object.values(metrics)
    .map((metric) => normalized((metric as JsonRecord)?.direction))
    .filter(Boolean);
  if (directions.includes("improved")) return "improved";
  if (directions.includes("worse")) return "worse";
  if (directions.length > 0) return "neutral";
  if (hasAfterData) return "neutral";
  return hasKeys(raw.before_snapshot) || raw.events?.length
    ? "not_enough_data"
    : "pending_data";
}

function latestRecord(
  events: ProblemResultEvent[],
  key: "before_snapshot" | "after_snapshot",
): JsonRecord {
  const event = events.find((item) => hasKeys(item[key]));
  return compactRecord(event?.[key]);
}

function latestPayloadRecord(
  events: ProblemResultEvent[],
  key: string,
): JsonRecord {
  const event = events.find((item) => hasKeys(item.payload?.[key]));
  return compactRecord(event?.payload?.[key]);
}

function latestComparison(
  events: ProblemResultEvent[],
): JsonRecord | string | null {
  const event = events.find(
    (item) => hasKeys(item.comparison) || hasKeys(item.payload?.comparison),
  );
  return hasKeys(event?.comparison)
    ? compactRecord(event?.comparison)
    : hasKeys(event?.payload?.comparison)
      ? compactRecord(event?.payload?.comparison)
      : null;
}

function latestMetrics(
  events: ProblemResultEvent[],
  pageSummary: JsonRecord,
): JsonRecord {
  if (hasKeys(pageSummary.metrics)) return compactRecord(pageSummary.metrics);
  const comparison = latestComparison(events);
  if (isRecord(comparison) && hasKeys(comparison.metrics))
    return compactRecord(comparison.metrics);
  return {};
}

export function problemResultSummaryFromPage(
  page?: PortalResultEventsPage | null,
): ProblemResultSummary {
  const events = problemResultEvents(page);
  const pageSummary = compactRecord(page?.summary);
  const before = hasKeys(pageSummary.before_snapshot)
    ? compactRecord(pageSummary.before_snapshot)
    : latestRecord(events, "before_snapshot");
  const after = hasKeys(pageSummary.after_snapshot)
    ? compactRecord(pageSummary.after_snapshot)
    : latestRecord(events, "after_snapshot");
  const current = hasKeys(pageSummary.current_snapshot)
    ? compactRecord(pageSummary.current_snapshot)
    : latestPayloadRecord(events, "current_snapshot");
  const comparison = pageSummary.comparison ?? latestComparison(events);
  const hasAfterData = problemResultHasAfterData({
    ...pageSummary,
    items: events,
    recent_events: events,
  });
  const metrics = hasAfterData ? latestMetrics(events, pageSummary) : {};
  const financeWindows = hasKeys(page?.finance_windows)
    ? compactRecord(page?.finance_windows)
    : compactRecord(pageSummary.windows ?? pageSummary.finance_windows);
  const statusHistory = events
    .slice()
    .reverse()
    .map((event) => ({
      event_type: event.event_type,
      status: event.payload?.new_status
        ? String(event.payload.new_status)
        : (event.outcome ?? null),
      old_status: event.payload?.old_status
        ? String(event.payload.old_status)
        : null,
      new_status: event.payload?.new_status
        ? String(event.payload.new_status)
        : event.payload?.current_snapshot &&
            isRecord(event.payload.current_snapshot)
          ? String(event.payload.current_snapshot.status ?? "")
          : null,
      comment: event.message ?? null,
      created_at: event.created_at ?? null,
      created_by: event.created_by ?? null,
    }));
  const latestEvent = events[0];
  const status = problemResultStatusFromSummary({
    status: pageSummary.status ?? latestEvent?.outcome,
    outcome: latestEvent?.outcome,
    comparison,
    metrics,
    before_snapshot: before,
    after_snapshot: after,
    events,
  });
  return {
    status,
    before_snapshot: before,
    current_snapshot: current,
    after_snapshot: after,
    comparison,
    metrics,
    finance_windows: financeWindows,
    status_history: statusHistory,
    calculation_note: String(
      pageSummary.calculation_note ?? latestEvent?.calculation_note ?? "",
    ),
    disclaimer: PROBLEM_RESULT_CORRELATION_DISCLAIMER,
    confidence: String(pageSummary.confidence ?? latestEvent?.confidence ?? ""),
    events,
  };
}

export function problemResultForAction(
  action: PortalAction,
  page?: PortalResultEventsPage | null,
): PortalResultEventsPage | null {
  const events = problemResultEvents(page);
  if (!events.length) return null;
  const instanceId = problemInstanceIdFromAction(action);
  const code = problemCodeFromAction(action);
  const nmId = action.nm_id == null ? null : Number(action.nm_id);
  const matched = events.filter((event) => {
    if (instanceId != null && event.problem_instance_id === instanceId)
      return true;
    if (
      code &&
      event.problem_code === code &&
      (nmId == null || event.nm_id === nmId)
    )
      return true;
    return false;
  });
  if (!matched.length) return null;
  return {
    ...(page ?? {
      total: matched.length,
      limit: matched.length,
      offset: 0,
      items: [],
    }),
    total: matched.length,
    items: matched,
    recent_events: matched,
    summary: {},
  };
}

export function problemResultBadgeStatus(
  page?: PortalResultEventsPage | null,
): ProblemResultStatus {
  return problemResultSummaryFromPage(page).status;
}

export function problemResultContractValue(
  page?: PortalResultEventsPage | null,
) {
  const summary = problemResultSummaryFromPage(page);
  return {
    status: summary.status,
    detail: summary.disclaimer || PROBLEM_RESULT_CORRELATION_DISCLAIMER,
    amount: null,
  };
}

export function problemResultTimelineMessageFromEvent(
  event: ProblemResultEvent,
): string | null {
  const comment = String(event.payload?.comment ?? "").trim();
  if (comment) return comment;
  const message = humanizeMessage(event.message);
  if (!message) return null;
  if (/^dynamic problem/i.test(String(event.message ?? ""))) return null;
  if (/^before snapshot/i.test(String(event.message ?? ""))) return null;
  return message;
}
