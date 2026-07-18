// Photo Studio — typed client for /portal/photo/*.
// Все запросы передают account_id, как и остальной portal-слой.
import { api, apiList, getBaseUrl } from "./api";
import { API_ENDPOINTS } from "./endpoints";

export type PhotoModuleState = "ok" | "empty" | "partial" | "failed" | string;
export type PhotoGenerationState = "ok" | "not_configured" | "disabled" | string;
export type PhotoJobState =
  | "queued" | "running" | "completed" | "partial" | "failed" | "cancelled" | "not_configured" | "disabled" | string;

export interface PhotoStatus {
  status: PhotoModuleState;
  generation?: PhotoGenerationState | { status?: PhotoGenerationState; provider?: string | null };
  message?: string | null;
  warnings?: any[];
  unavailable_sources?: any[];
  [k: string]: any;
}

export interface PhotoSettings {
  status?: PhotoModuleState;
  enabled?: boolean;
  allowed_formats?: string[];
  allowed_mime_types?: string[];
  max_upload_mb?: number;
  default_output_format?: string;
  external_apply?: boolean;
  external_apply_enabled?: boolean;
  generation_enabled?: boolean;
  editing_enabled?: boolean;
  default_provider?: string | null;
  generation?: { status?: PhotoGenerationState; provider?: string | null; operations?: string[] };
  supported_operations?: string[];
  [k: string]: any;
}

export interface PhotoProject {
  id: number | string;
  nm_id?: number | string | null;
  product_name?: string | null;
  vendor_code?: string | null;
  thumbnail?: string | null;
  preferred_thumbnail?: string | null;
  approved_thumbnail?: string | null;
  status?: string;
  source_issue?: string | null;
  source_module?: string | null;
  versions_count?: number;
  comments_count?: number;
  last_activity_at?: string | null;
  created_at?: string | null;
  [k: string]: any;
}

export interface PhotoAsset {
  id: number | string;
  kind?: "source_wb" | "upload" | "version" | string;
  asset_type?: string;
  source_type?: string;
  thumbnail?: string | null;
  url?: string | null;          // безопасный preview/cdn url (без подписи)
  filename?: string | null;
  original_file_name?: string | null;
  source_url?: string | null;
  width?: number;
  height?: number;
  size_bytes?: number;
  file_size?: number;
  created_at?: string | null;
  source?: string | null;       // "wb" | "user" | "generation"
  warnings?: string[];
  [k: string]: any;
}

export interface PhotoVersion {
  id: number | string;
  number?: number;
  version_number?: number;
  asset_id?: number | string;
  thumbnail?: string | null;
  url?: string | null;
  source?: "manual_upload" | "generation" | string;
  operation?: string | null;
  status?: "draft" | "preferred" | "approved" | "rejected" | string;
  is_preferred?: boolean;
  is_approved?: boolean;
  rejected_reason?: string | null;
  rejection_reason?: string | null;
  job_id?: number | string | null;
  created_at?: string | null;
  warnings?: string[];
  [k: string]: any;
}

export interface PhotoJob {
  id: number | string;
  state?: PhotoJobState;
  status?: PhotoJobState;
  operation?: string;
  job_type?: string;
  progress?: number;
  progress_percent?: number;
  message?: string | null;
  error?: string | null;
  error_message?: string | null;
  result_version_id?: number | string | null;
  can_cancel?: boolean;
  can_retry?: boolean;
  created_at?: string | null;
  [k: string]: any;
}

function withAcc(accountId: number | null | undefined, extra?: Record<string, any>) {
  if (accountId == null) throw new Error("photo: account_id is required");
  return { account_id: accountId, ...(extra ?? {}) };
}

// ─── Status / settings ─────────────────────────────────────────────────
export const fetchPhotoStatus = (accountId?: number | null) =>
  api<PhotoStatus>(API_ENDPOINTS.portal.photoStatus, { query: accountId != null ? { account_id: accountId } : {} });

export const fetchPhotoSettings = (accountId?: number | null) =>
  api<PhotoSettings>(API_ENDPOINTS.portal.photoSettings, { query: accountId != null ? { account_id: accountId } : {} });

// ─── Projects ──────────────────────────────────────────────────────────
export const fetchPhotoProjects = (
  accountId: number | null | undefined,
  extra?: Record<string, any>,
) =>
  apiList<PhotoProject>(API_ENDPOINTS.portal.photoProjects, { query: withAcc(accountId, extra) });

export const fetchPhotoProject = (id: number | string, accountId: number | null | undefined) =>
  api<any>(API_ENDPOINTS.portal.photoProjectDetail(id), { query: withAcc(accountId) });

export async function fetchPhotoCardImages(
  accountId: number | null | undefined,
  nmId: number | string | null | undefined,
): Promise<string[]> {
  if (accountId == null || nmId == null) return [];
  const res = await api<any>(API_ENDPOINTS.photoStudioCards.wbLive(accountId), {
    query: { limit: 20, with_photo: 1, q: String(nmId) },
  });
  const cards = Array.isArray(res?.cards) ? res.cards : Array.isArray(res?.items) ? res.items : [];
  const matched = cards.find((card: any) => String(card?.nm_id) === String(nmId)) ?? cards[0];
  const photos = matched?.photos;
  if (Array.isArray(photos)) {
    return photos
      .map((item: unknown) => photoUrl(item))
      .filter((url: string | null): url is string => !!url);
  }
  const main = matched?.main_photo_url ?? matched?.photo_url ?? matched?.image_url;
  return typeof main === "string" && main.trim() ? [main] : [];
}

function photoUrl(item: unknown): string | null {
  if (typeof item === "string" && item.trim()) return item;
  if (!item || typeof item !== "object") return null;
  const value = item as Record<string, unknown>;
  for (const key of ["big", "canonical_url", "url", "full", "photo", "src", "c516x688", "square", "c246x328", "tm"]) {
    const raw = value[key];
    if (typeof raw === "string" && raw.trim()) return raw;
  }
  return null;
}

export function photoDisplayUrl(src: string | null | undefined): string | undefined {
  const raw = typeof src === "string" ? src.trim() : "";
  if (!raw) return undefined;
  return raw;
}

export const createPhotoProject = (payload: {
  account_id: number;
  nm_id: number | string;
  sku_id?: number | string | null;
  source_issue_id?: number | string | null;
  source_action_key?: string | null;
  title?: string | null;
}) =>
  api<PhotoProject>(API_ENDPOINTS.portal.photoProjects, { method: "POST", body: payload });

/** Find-or-create an active project for nm_id; uses GET with nm_id then POST. */
export async function ensureProjectForNm(args: {
  accountId: number;
  nmId: number | string;
  source?: string | null;
  sourceIssue?: string | null;
  source_action_key?: string | null;
}): Promise<PhotoProject> {
  const list = await fetchPhotoProjects(args.accountId, {
    nm_id: args.nmId,
    active: true,
    limit: 1,
  });
  const existing = list.find(
    (p) => String(p.nm_id) === String(args.nmId) && !["approved", "closed", "rejected"].includes(String(p.status ?? "")),
  ) ?? list[0];
  if (existing) return existing;
  const issueId = args.sourceIssue && /^\d+$/.test(args.sourceIssue) ? Number(args.sourceIssue) : null;
  return createPhotoProject({
    account_id: args.accountId,
    nm_id: args.nmId,
    source_issue_id: issueId,
    source_action_key: args.source_action_key ?? (issueId ? (args.source ?? null) : (args.sourceIssue ?? args.source ?? null)),
    title: `Фотостудия ${args.nmId}`,
  });
}

// ─── Assets / WB import / upload ───────────────────────────────────────
export const importWbAssets = (projectId: number | string, accountId: number) =>
  api<{ imported?: number; assets?: PhotoAsset[] }>(API_ENDPOINTS.portal.photoProjectImportWb(projectId), {
    method: "POST",
    query: withAcc(accountId),
  });

export const uploadProjectAsset = (
  projectId: number | string,
  accountId: number,
  file: File,
  onProgress?: (pct: number) => void,
) => {
  // Use XHR so we can report upload progress; api() uses fetch which lacks it.
  return new Promise<PhotoAsset>((resolve, reject) => {
    const fd = new FormData();
    fd.append("file", file);
    const xhr = new XMLHttpRequest();
    const url = `${getBaseUrl()}${API_ENDPOINTS.portal.photoProjectAssetUpload(projectId)}?account_id=${encodeURIComponent(String(accountId))}`;
    xhr.open("POST", url);
    const tok = typeof localStorage !== "undefined" ? localStorage.getItem("wb.access_token") : null;
    if (tok) xhr.setRequestHeader("Authorization", `Bearer ${tok}`);
    xhr.setRequestHeader("ngrok-skip-browser-warning", "true");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText) as PhotoAsset); }
        catch { resolve({ id: -1 } as PhotoAsset); }
      } else {
        let msg = `Загрузка не удалась (${xhr.status})`;
        try { const b = JSON.parse(xhr.responseText); if (b?.detail) msg = b.detail; } catch {}
        reject(new Error(msg));
      }
    };
    xhr.onerror = () => reject(new Error("Сеть недоступна — попробуйте снова"));
    xhr.send(fd);
  });
};

// ─── Jobs ──────────────────────────────────────────────────────────────
export const createPhotoJob = (
  projectId: number | string,
  payload: {
    account_id: number;
    asset_id: number | string;
    operation: string;
    brief?: string | null;
    params?: Record<string, any>;
  },
) =>
  api<PhotoJob>(API_ENDPOINTS.portal.photoProjectJobs(projectId), {
    method: "POST",
    query: withAcc(payload.account_id),
    body: {
      job_type: normalizeJobType(payload.operation),
      input_asset_ids: payload.asset_id ? [Number(payload.asset_id)] : [],
      prompt: payload.brief ?? "",
      ...(payload.params?.provider ? { provider: payload.params.provider } : {}),
      ...(payload.params?.model ? { model: payload.params.model } : {}),
      ...(payload.params?.idempotency_key ? { idempotency_key: payload.params.idempotency_key } : {}),
    },
  });

export const cancelPhotoJob = (jobId: number | string, accountId: number) =>
  api<PhotoJob>(API_ENDPOINTS.portal.photoJobCancel(jobId), { method: "POST", query: withAcc(accountId) });

export const retryPhotoJob = (jobId: number | string, accountId: number) =>
  api<PhotoJob>(API_ENDPOINTS.portal.photoJobRetry(jobId), { method: "POST", query: withAcc(accountId) });

// ─── Versions ──────────────────────────────────────────────────────────
export const createPhotoVersion = (
  projectId: number | string,
  accountId: number,
  payload: {
    asset_id: number | string;
    parent_version_id?: number | string | null;
    label?: string | null;
    brief_text?: string | null;
    change_summary?: string | null;
  },
) =>
  api<PhotoVersion>(API_ENDPOINTS.portal.photoProjectVersions(projectId), {
    method: "POST",
    query: withAcc(accountId),
    body: {
      asset_id: Number(payload.asset_id),
      parent_version_id: payload.parent_version_id == null ? null : Number(payload.parent_version_id),
      label: payload.label ?? null,
      brief_text: payload.brief_text ?? null,
      change_summary: payload.change_summary ?? null,
    },
  });

const reviewVersion = (
  projectId: number | string,
  versionId: number | string,
  accountId: number,
  status: "preferred" | "approved" | "rejected",
  reason?: string | null,
) =>
  api<PhotoVersion>(API_ENDPOINTS.portal.photoVersionReview(projectId, versionId), {
    method: "POST",
    query: withAcc(accountId),
    body: { status, reason: reason ?? null },
  });

export const preferVersion = (projectId: number | string, versionId: number | string, accountId: number) =>
  reviewVersion(projectId, versionId, accountId, "preferred");

export const approveVersion = (projectId: number | string, versionId: number | string, accountId: number) =>
  reviewVersion(projectId, versionId, accountId, "approved");

export const rejectVersion = (
  projectId: number | string, versionId: number | string,
  accountId: number, reason: string,
) =>
  reviewVersion(projectId, versionId, accountId, "rejected", reason);

export const applyVersionToWb = (
  projectId: number | string,
  versionId: number | string,
  accountId: number,
  photoNumber = 1,
) =>
  api<any>(API_ENDPOINTS.portal.photoVersionApplyWb(projectId, versionId), {
    method: "POST",
    query: withAcc(accountId),
    body: { photo_number: photoNumber },
  });

export const saveProjectCardPhotosToWb = (
  projectId: number | string,
  accountId: number,
  photos: string[],
) =>
  api<any>(API_ENDPOINTS.portal.photoProjectCardPhotosSaveWb(projectId), {
    method: "POST",
    query: withAcc(accountId),
    body: { photos },
  });

// ─── Comments ─────────────────────────────────────────────────────────
export const addProjectComment = (
  projectId: number | string,
  accountId: number, text: string, versionId?: number | string | null,
) =>
  api<any>(API_ENDPOINTS.portal.photoProjectMessages(projectId), {
    method: "POST",
    query: withAcc(accountId),
    body: {
      message_type: "comment",
      text,
      linked_asset_ids: versionId == null ? [] : [Number(versionId)],
    },
  });

// ─── Manual WB update marker (без авто-апплая) ────────────────────────
export const recordManualWbUpdate = (
  projectId: number | string,
  accountId: number, payload: { applied_at?: string; comment?: string; version_id?: number | string | null } = {},
) =>
  addProjectComment(
    projectId,
    accountId,
    [
      `Ручное обновление WB отмечено${payload.applied_at ? `: ${payload.applied_at}` : ""}.`,
      payload.comment?.trim() ? payload.comment.trim() : "",
    ].filter(Boolean).join(" "),
    payload.version_id,
  );

export const fetchPhotoAssetDownloadUrl = (assetId: number | string, accountId: number) =>
  api<{ asset_id: number | string; url: string; expires_at?: string }>(
    API_ENDPOINTS.portal.photoAssetDownloadUrl(assetId),
    { query: withAcc(accountId) },
  );

export const createPhotoVersionExperiment = (
  projectId: number | string,
  versionId: number | string,
  accountId: number,
  payload: {
    hypothesis?: string | null;
    primary_metric?: string;
    secondary_metrics?: string[];
    guardrail_metrics?: string[];
    baseline_days?: number | null;
    post_days?: number | null;
    evaluation_delay_days?: number | null;
    is_test?: boolean;
  } = {},
) =>
  api<any>(API_ENDPOINTS.portal.photoVersionExperiment(projectId, versionId), {
    method: "POST",
    query: withAcc(accountId),
    body: {
      hypothesis: payload.hypothesis ?? "Approved photo update may improve conversion without harming revenue.",
      primary_metric: payload.primary_metric ?? "conversion_rate",
      secondary_metrics: payload.secondary_metrics ?? ["revenue", "orders_count"],
      guardrail_metrics: payload.guardrail_metrics ?? ["stockout_days", "ads_spend"],
      baseline_days: payload.baseline_days ?? 7,
      post_days: payload.post_days ?? 14,
      evaluation_delay_days: payload.evaluation_delay_days ?? 0,
      is_test: payload.is_test ?? false,
    },
  });

// ─── Helpers / labels ─────────────────────────────────────────────────
export const PROJECT_STATUS_LABEL: Record<string, string> = {
  active: "Активный",
  draft: "Черновик",
  in_progress: "В работе",
  ready_for_review: "Готово к проверке",
  review: "На проверке",
  approved: "Одобрено",
  rejected: "Отклонено",
  closed: "Закрыто",
};

export const JOB_STATE_LABEL: Record<string, string> = {
  queued: "В очереди",
  running: "Обрабатывается",
  processing: "Обрабатывается",
  completed: "Готово",
  done: "Готово",
  partial: "Частично готово",
  failed: "Ошибка",
  cancelled: "Отменено",
  not_configured: "Провайдер не настроен",
  disabled: "Выключено",
};

export const OPERATION_LABEL: Record<string, string> = {
  remove_background: "Удалить фон",
  background_replace: "Заменить фон",
  replace_background: "Заменить фон",
  enhance:            "Улучшить качество",
  crop_resize:        "Обрезать",
  crop:               "Обрезать",
  variant:            "Создать вариант",
  generate:           "Сгенерировать",
  edit:               "Редактировать",
};

export const humanizeProjectStatus = (s?: string | null) =>
  (s && PROJECT_STATUS_LABEL[s]) || s || "—";
export const humanizeJobState = (s?: string | null) =>
  (s && JOB_STATE_LABEL[s]) || s || "—";
export const humanizeOperation = (s?: string | null) =>
  (s && OPERATION_LABEL[s]) || s || "—";

export const isTerminalJob = (s?: string | null) =>
  s === "done" || s === "completed" || s === "partial" || s === "failed" || s === "cancelled" || s === "not_configured" || s === "disabled";

export const generationStateOf = (st?: PhotoStatus | null): PhotoGenerationState => {
  if (!st) return "not_configured";
  const g = st.generation;
  if (!g) return "ok";
  if (typeof g === "string") return g;
  return g.status ?? "ok";
};

function normalizeJobType(operation: string): string {
  if (operation === "replace_background") return "background_replace";
  if (operation === "crop") return "crop_resize";
  return operation;
}
