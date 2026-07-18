import type { PortalAction } from "@/lib/portal";
import type { JsonRecord } from "@/lib/problem-contracts";
import { formatMoney } from "@/lib/format";
import type { ActionCenterItem } from "@/lib/action-center-contract";

export function normalizeText(value: unknown): string {
  return String(value ?? "")
    .trim()
    .toLowerCase();
}

export function firstText(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value;
    if (typeof value === "number" && Number.isFinite(value)) {
      return String(value);
    }
  }
  return null;
}

export function isJsonRecord(value: unknown): value is JsonRecord {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

export function asJsonRecord(value: unknown): JsonRecord {
  return isJsonRecord(value) ? value : {};
}

export function hasRecordKeys(value: unknown): boolean {
  return isJsonRecord(value) && Object.keys(value).length > 0;
}

export function extractActions(data: unknown): PortalAction[] {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  const record = asJsonRecord(data);
  if (Array.isArray(record.items)) return record.items as PortalAction[];
  if (Array.isArray(record.actions)) return record.actions as PortalAction[];
  return [];
}

export function renderValue(value: unknown): string {
  if (value == null || value === "") return "—";
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return String(value);
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function moneyValue(a: ActionCenterItem): number | string | null {
  return a.money_impact_amount;
}

export function formatMoneyField(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return formatMoney(value);
  }
  if (typeof value === "string" && value.trim()) return value;
  return "—";
}
