import { clearTokens, getAccessToken, getBaseUrl, getRefreshToken, setTokens } from "@/lib/api";

function resolvePhotoApiRoot(): string {
  const configured = getBaseUrl().replace(/\/+$/, "");
  try {
    const parsed = new URL(configured, typeof window === "undefined" ? "http://localhost" : window.location.origin);
    const looksLikeImportedCheckerBackend =
      parsed.port === "8002" || parsed.hostname.includes("wb-optimizer") || configured.includes("wb-optimizer");
    if (!looksLikeImportedCheckerBackend) return configured;
  } catch {
    return configured;
  }

  const rawEnvBase =
    (typeof import.meta !== "undefined" && (import.meta as any).env?.VITE_API_BASE_URL) ||
    "http://127.0.0.1:8000/api/v1";
  const envBase = String(rawEnvBase).replace(/\/+$/, "").replace(/(\/api(\/v\d+)?)+$/i, "/api/v1");
  return /\/api\/v\d+$/i.test(envBase) ? envBase : `${envBase}/api/v1`;
}

const API_ROOT = resolvePhotoApiRoot();
const URL_BASE = typeof window === "undefined" ? "http://localhost" : window.location.origin;
export const API_ORIGIN = new URL(API_ROOT, URL_BASE).origin;

let refreshPromise: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  refreshPromise = (async () => {
    try {
      const res = await fetch(buildUrl("/auth/refresh"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "ngrok-skip-browser-warning": "1",
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      if (!data?.access_token || !data?.refresh_token) return false;
      setTokens(String(data.access_token), String(data.refresh_token));
      return true;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

function buildUrl(path: string, params?: Record<string, any>): string {
  const url = new URL(path.replace(/^\//, ""), `${API_ROOT}/`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === "") continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

function withQuery(path: string, params?: Record<string, any>): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value === undefined || value === null || value === "") continue;
    qs.set(key, String(value));
  }
  const query = qs.toString();
  return query ? `${path}?${query}` : path;
}

async function parseError(res: Response): Promise<Error> {
  const text = await res.text().catch(() => "");
  try {
    const data = JSON.parse(text);
    const detail = data?.detail;
    if (typeof detail === "string") return new Error(detail);
    if (detail?.message) return new Error(String(detail.message));
  } catch {
    // Fall through to raw text.
  }
  return new Error(text || `HTTP ${res.status}`);
}

class PhotoStudioChatApi {
  private headers(contentType?: string | null): Headers {
    const headers = new Headers();
    headers.set("ngrok-skip-browser-warning", "1");
    if (contentType) headers.set("Content-Type", contentType);
    const token = getAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return headers;
  }

  async requestRaw(path: string, init: RequestInit = {}, contentType?: string | null, retried = false): Promise<Response> {
    const res = await fetch(buildUrl(path), {
      ...init,
      headers: this.headers(contentType),
    });
    if (res.status === 401 && !retried) {
      const refreshed = await refreshAccessToken();
      if (refreshed) return this.requestRaw(path, init, contentType, true);
      clearTokens();
    }
    if (!res.ok) throw await parseError(res);
    return res;
  }

  async requestJson<T>(path: string, init: RequestInit = {}, contentType?: string | null): Promise<T> {
    const res = await this.requestRaw(path, init, contentType);
    if (res.status === 204) return null as T;
    return (await res.json()) as T;
  }

  getStores() {
    return this.requestJson<any[]>("/stores");
  }

  getCards(storeId: number, page = 1, limit = 50, filters?: Record<string, any>) {
    return this.requestJson<any>(withQuery(`/stores/${storeId}/cards`, { page, limit, ...(filters || {}) }));
  }

  getCard(storeId: number, cardId: number) {
    return this.requestJson<any>(`/stores/${storeId}/cards/${cardId}`);
  }

  getWbCardsLive(storeId: number, params?: Record<string, any>) {
    return this.requestJson<any>(withQuery(`/stores/${storeId}/cards/wb/live`, params));
  }

  syncCardPhotos(storeId: number, cardId: number, photos: string[]) {
    return this.requestJson<any>(
      `/stores/${storeId}/cards/${cardId}/photos/sync`,
      { method: "POST", body: JSON.stringify({ photos }) },
      "application/json",
    );
  }

  uploadUserPhotoAsset(file: File, options?: { assetType?: string; name?: string }) {
    const form = new FormData();
    form.append("file", file);
    if (options?.assetType) form.append("asset_type", options.assetType);
    if (options?.name) form.append("name", options.name);
    return this.requestRaw("/photo-assets/user/upload", { method: "POST", body: form }, null).then((r) => r.json());
  }

  importUserPhotoAssetFromUrl(data: Record<string, any>) {
    return this.requestJson<any>(
      "/photo-assets/user/import",
      { method: "POST", body: JSON.stringify(data) },
      "application/json",
    );
  }

  getPhotoCatalogAll() {
    return this.requestJson<any>("/photo/catalog/all");
  }

  getPhotoGalleryAssets(assetType: "scene" | "model") {
    return this.requestJson<any>(`/photo-assets/catalog?asset_type=${encodeURIComponent(assetType)}`);
  }

  getPhotoChatModels() {
    return this.requestJson<any>("/photo/chat/models");
  }

  getPhotoChatHistory(threadId?: number | null, accountId?: number | null) {
    return this.requestJson<any>(withQuery("/photo/chat/history", { thread_id: threadId, account_id: accountId }));
  }

  createNewPhotoThread(payload?: Record<string, any>) {
    return this.requestJson<any>(
      "/photo/threads/new",
      { method: "POST", body: JSON.stringify(payload || {}) },
      "application/json",
    );
  }

  listPhotoThreads(accountId?: number | null) {
    return this.requestJson<any>(withQuery("/photo/threads", { account_id: accountId }));
  }

  deletePhotoThread(threadId: number) {
    return this.requestJson<any>(`/photo/threads/${threadId}`, { method: "DELETE" });
  }

  uploadPhotoChatAsset(file: File, params?: { threadId?: number | null; accountId?: number | null }) {
    const form = new FormData();
    form.append("file", file);
    return this.requestRaw(
      withQuery("/photo/assets/upload", { thread_id: params?.threadId, account_id: params?.accountId }),
      { method: "POST", body: form },
      null,
    ).then((r) => r.json());
  }

  importPhotoChatAsset(sourceUrl: string, params?: { threadId?: number | null; accountId?: number | null; nmId?: number | null }) {
    return this.requestJson<any>(
      "/photo/assets/import",
      {
        method: "POST",
        body: JSON.stringify({
          source_url: sourceUrl,
          thread_id: params?.threadId || undefined,
          account_id: params?.accountId || undefined,
          nm_id: params?.nmId || undefined,
        }),
      },
      "application/json",
    );
  }

  streamPhotoChat(payload: Record<string, any>) {
    return this.requestRaw(
      "/photo/chat/stream",
      { method: "POST", body: JSON.stringify(payload) },
      "application/json",
    );
  }

  runPhotoGenerator(payload: Record<string, any>) {
    return this.requestJson<any>(
      "/photo/generator/run",
      { method: "POST", body: JSON.stringify(payload) },
      "application/json",
    );
  }

  clearPhotoChat(threadId?: number, clearMode: "messages" | "context" | "all" = "all") {
    return this.requestJson<any>(
      "/photo/chat/clear",
      { method: "POST", body: JSON.stringify({ thread_id: threadId, clear_mode: clearMode }) },
      "application/json",
    );
  }

  deletePhotoChatMessages(messageIds: number[], threadId?: number) {
    return this.requestJson<any>(
      "/photo/chat/messages/delete",
      { method: "POST", body: JSON.stringify({ message_ids: messageIds, thread_id: threadId }) },
      "application/json",
    );
  }

  deletePhotoChatAssets(assetIds: number[], threadId?: number) {
    return this.requestJson<any>(
      "/photo/chat/assets/delete",
      { method: "POST", body: JSON.stringify({ asset_ids: assetIds, thread_id: threadId }) },
      "application/json",
    );
  }
}

const api = new PhotoStudioChatApi();
export default api;
