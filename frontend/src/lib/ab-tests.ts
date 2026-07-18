import { api, apiList } from "@/lib/api";

export type ABTestStatus = "running" | "pending" | "finished" | "failed";

export interface ABTestPhoto {
  order: number;
  file_url: string;
  wb_url?: string | null;
  preview_url?: string | null;
  shows: number;
  clicks: number;
  ctr: number;
  is_winner: boolean;
  winner_score?: number | null;
  winner_score_confidence?: number | null;
  winner_score_conversion_source?: string | null;
  winner_score_reason?: string | null;
}

export interface ABTestCompany {
  id_company: number;
  company_id?: number | null;
  wb_advert_id?: number | null;
  account_id: number;
  nm_id: number;
  product_card_id?: number | null;
  card_id?: number | null;
  title: string;
  status: string;
  spend_rub: number;
  estimated_spend_rub: number;
  winner_decision?: string | null;
  views_per_photo: number;
  photos_count: number;
  current_photo_order: number;
  winner_photo_order?: number | null;
  last_error?: string | null;
  can_start?: boolean;
  can_stop?: boolean;
  started_at?: string | null;
  finished_at?: string | null;
  photos: ABTestPhoto[];
}

export interface ProductOption {
  id: number;
  nm_id: number;
  vendor_code?: string | null;
  title?: string | null;
  brand?: string | null;
  photos?: unknown;
}

export function fetchABTests(
  accountId: number,
  status: ABTestStatus,
  params?: { limit?: number; offset?: number },
) {
  return api<{ items: ABTestCompany[]; pagination: Record<string, number> }>(
    `/promotion/${status}`,
    {
      query: {
        account_id: accountId,
        page: Math.floor((params?.offset ?? 0) / (params?.limit ?? 50)) + 1,
        page_size: params?.limit ?? 50,
      },
    },
  );
}

export function fetchABTestBalance(accountId: number) {
  return api<{ balance: number; promo_bonus_rub: number; raw?: unknown }>(
    "/promotion/balance",
    {
      query: { account_id: accountId },
    },
  );
}

export function createABTestCompany(
  accountId: number,
  payload: Record<string, unknown>,
) {
  return api<Record<string, unknown>>("/promotion/create_company", {
    method: "POST",
    body: { ...payload, account_id: accountId },
  });
}

export function updateABTestCompany(
  accountId: number,
  payload: Record<string, unknown>,
) {
  return api<Record<string, unknown>>("/promotion/update", {
    method: "POST",
    body: { ...payload, account_id: accountId },
  });
}

export function startABTestCompany(
  accountId: number,
  companyId: number,
  options?: { confirm?: boolean },
) {
  return api<Record<string, unknown>>(`/promotion/company/${companyId}/start`, {
    method: "POST",
    query: { account_id: accountId, confirm: options?.confirm || undefined },
  });
}

export function stopABTestCompany(
  accountId: number,
  companyId: number,
  options?: { confirm?: boolean },
) {
  return api<Record<string, unknown>>(`/promotion/company/${companyId}/stop`, {
    method: "POST",
    query: { account_id: accountId, confirm: options?.confirm || undefined },
  });
}

export function fetchABTestStats(accountId: number, companyId: number) {
  return api<ABTestCompany>(`/promotion/company/${companyId}/stats`, {
    query: { account_id: accountId },
  });
}

export function fetchProductsForABTest(accountId: number, search: string) {
  return apiList<ProductOption>("/products", {
    query: {
      account_id: accountId,
      search: search || undefined,
      limit: 80,
      sort_by: "updated_at_wb",
      sort_dir: "desc",
    },
  });
}

export function uploadABTestPhoto(file: File, accountId: number) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("asset_type", "custom");
  formData.append("name", file.name || "A/B variant");
  return api<{
    id: number;
    file_url?: string;
    url?: string;
    image_url?: string;
    file_name?: string;
  }>("/photo/assets/upload", {
    method: "POST",
    query: { account_id: accountId },
    formData,
  });
}

export function extractProductPhotos(product: ProductOption): string[] {
  const raw = product.photos;
  const out: string[] = [];
  const push = (value: unknown) => {
    if (typeof value === "string" && value.trim()) out.push(value.trim());
    else if (value && typeof value === "object") {
      const obj = value as Record<string, unknown>;
      for (const key of [
        "big",
        "url",
        "full",
        "c516x688",
        "c246x328",
        "square",
      ]) {
        if (typeof obj[key] === "string" && String(obj[key]).trim()) {
          out.push(String(obj[key]).trim());
          break;
        }
      }
    }
  };
  if (Array.isArray(raw)) raw.forEach(push);
  else push(raw);
  return Array.from(new Set(out));
}
