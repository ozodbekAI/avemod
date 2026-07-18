/**
 * Канонический вид «затронутой строки» для Data Fix Workbench.
 *
 * Задача: показать продавцу одни и те же понятные колонки независимо
 * от того, какие ключи прислал backend. Отсутствующие поля рендерятся как «—».
 */

export type AffectedRowView = {
  nm_id: string | number | null;
  vendor_code: string | null;
  barcode: string | null;
  source: string | null;
  current_value: string | number | null;
  missing_or_invalid_value: string | null;
  suggested_fix: string | null;
  confidence: number | string | null;
  row_status: string | null;
  raw?: unknown;
};

const NM_ID_KEYS = ["nm_id", "nmId", "nmID", "product_nm_id", "wb_nm_id"];
const VENDOR_KEYS = [
  "vendor_code",
  "vendorCode",
  "supplier_article",
  "supplierArticle",
  "article",
  "sku",
  "seller_sku",
  "sku_id",
];
const BARCODE_KEYS = ["barcode", "wb_barcode", "ean"];
const SOURCE_KEYS = [
  "source",
  "source_name",
  "source_table",
  "source_endpoint",
  "service",
  "import_name",
  "file_name",
  "_source",
];
const CURRENT_KEYS = [
  "current_value",
  "current",
  "value",
  "existing_value",
  "old_value",
  "actual_value",
  "amount",
  "current_price",
];
const MISSING_KEYS = [
  "missing_or_invalid_value",
  "missing_value",
  "missing_field",
  "invalid_value",
  "error",
  "issue",
  "problem",
  "reason",
];
const SUGGESTED_KEYS = [
  "suggested_fix",
  "suggestion",
  "recommended_value",
  "candidate",
  "candidate_value",
  "expected_value",
  "target_value",
];
const CONFIDENCE_KEYS = [
  "confidence",
  "confidence_score",
  "score",
  "match_score",
  "probability",
];
const STATUS_KEYS = [
  "row_status",
  "status",
  "state",
  "resolution_status",
  "fix_status",
];

function pick(row: Record<string, unknown>, keys: string[]): unknown {
  for (const k of keys) {
    if (row[k] !== undefined && row[k] !== null && row[k] !== "") return row[k];
  }
  return null;
}

function toPrimitiveString(value: unknown): string | null {
  if (value == null) return null;
  if (typeof value === "string") return value.trim() || null;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "да" : "нет";
  if (Array.isArray(value)) {
    const first = value.find((v) => v != null && v !== "");
    return first != null ? toPrimitiveString(first) : null;
  }
  if (typeof value === "object") {
    // Компактно, без raw JSON
    const parts: string[] = [];
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (v == null || v === "") continue;
      parts.push(`${k}: ${toPrimitiveString(v) ?? "—"}`);
      if (parts.length >= 3) break;
    }
    return parts.length ? parts.join("; ") : null;
  }
  return String(value);
}

function toNumberOrString(value: unknown): number | string | null {
  if (value == null) return null;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const num = Number(trimmed.replace(",", "."));
    if (Number.isFinite(num)) return num;
    return trimmed;
  }
  return toPrimitiveString(value);
}

function pickNmId(row: Record<string, unknown>): string | number | null {
  const direct = pick(row, NM_ID_KEYS);
  if (direct != null) {
    if (typeof direct === "number") return direct;
    const s = toPrimitiveString(direct);
    return s ?? null;
  }
  // entity_id when entity_type is product
  const entType = row.entity_type ?? row.entityType;
  if (typeof entType === "string" && entType.toLowerCase().includes("product")) {
    const eid = row.entity_id ?? row.entityId;
    if (typeof eid === "number") return eid;
    const s = toPrimitiveString(eid);
    if (s) return s;
  }
  return null;
}

function pickBarcode(row: Record<string, unknown>): string | null {
  const direct = pick(row, BARCODE_KEYS);
  if (direct != null) return toPrimitiveString(direct);
  const arr = row.barcodes ?? row.barcode_list;
  if (Array.isArray(arr) && arr.length) return toPrimitiveString(arr[0]);
  return null;
}

export function normalizeAffectedRow(raw: unknown): AffectedRowView {
  const row = (raw && typeof raw === "object" ? raw : {}) as Record<
    string,
    unknown
  >;
  return {
    nm_id: pickNmId(row),
    vendor_code: toPrimitiveString(pick(row, VENDOR_KEYS)),
    barcode: pickBarcode(row),
    source: toPrimitiveString(pick(row, SOURCE_KEYS)),
    current_value: toNumberOrString(pick(row, CURRENT_KEYS)),
    missing_or_invalid_value: toPrimitiveString(pick(row, MISSING_KEYS)),
    suggested_fix: toPrimitiveString(pick(row, SUGGESTED_KEYS)),
    confidence: toNumberOrString(pick(row, CONFIDENCE_KEYS)),
    row_status: toPrimitiveString(pick(row, STATUS_KEYS)),
    raw,
  };
}

export function normalizeAffectedRows(
  rows: unknown[] | null | undefined,
): AffectedRowView[] {
  if (!Array.isArray(rows)) return [];
  return rows.map(normalizeAffectedRow);
}

const ROW_STATUS_LABELS: Record<string, string> = {
  open: "Открыто",
  pending: "Ожидает",
  pending_data: "Ждём данные",
  pending_recheck: "Ждёт перепроверки",
  in_progress: "В работе",
  resolved: "Исправлено",
  fixed: "Исправлено",
  applied: "Применено",
  ignored: "Пропущено",
  error: "Ошибка",
  needs_review: "Нужна проверка",
  ok: "OK",
};

export function formatRowStatus(status: string | null): string {
  if (!status) return "—";
  const key = String(status).toLowerCase();
  return ROW_STATUS_LABELS[key] ?? status;
}

export function formatConfidenceValue(
  value: number | string | null,
): string {
  if (value == null) return "—";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "—";
    const pct = value <= 1 ? value * 100 : value;
    return `${Math.round(pct)}%`;
  }
  return value;
}

export function formatCellText(
  value: string | number | null | undefined,
): string {
  if (value == null || value === "") return "—";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "—";
    // тысячи с неразрывным пробелом
    return Math.round(value * 100) / 100 + "";
  }
  return String(value);
}

/** true, если хотя бы одна каноническая колонка (кроме идентификаторов) пустая. */
export function rowHasMissingFields(row: AffectedRowView): boolean {
  return (
    row.source == null ||
    row.current_value == null ||
    row.missing_or_invalid_value == null ||
    row.suggested_fix == null ||
    row.confidence == null ||
    row.row_status == null
  );
}

export function anyRowHasMissingFields(rows: AffectedRowView[]): boolean {
  return rows.some(rowHasMissingFields);
}

export function searchAffectedRows(
  rows: AffectedRowView[],
  term: string,
): AffectedRowView[] {
  const t = term.trim().toLowerCase();
  if (!t) return rows;
  return rows.filter((r) => {
    const hay = [
      r.nm_id,
      r.vendor_code,
      r.barcode,
      r.source,
      r.current_value,
      r.missing_or_invalid_value,
      r.suggested_fix,
      r.row_status,
    ]
      .map((v) => (v == null ? "" : String(v).toLowerCase()))
      .join(" ");
    return hay.includes(t);
  });
}
