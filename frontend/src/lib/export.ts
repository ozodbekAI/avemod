// Excel export download helper.
// Uses api() with raw:true to stream the blob and trigger a browser download.
import { api } from "@/lib/api";
import { toast } from "sonner";

export interface ExportParams {
  endpoint: string;
  filenamePrefix: string;
  query: Record<string, string | number | boolean | null | undefined>;
}

function todaySuffix(): string {
  return new Date().toISOString().slice(0, 10);
}

export class ExportError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ExportError";
    this.status = status;
  }
}

export async function downloadExport({ endpoint, filenamePrefix, query }: ExportParams) {
  const res = await api<Response>(endpoint, { raw: true, query });
  if (!res.ok) {
    let msg = `Ошибка экспорта (${res.status})`;
    try {
      const body = await res.json();
      if (body && typeof body === "object" && "detail" in body && typeof (body as any).detail === "string") {
        msg = (body as any).detail;
      }
    } catch {
      try {
        const text = await res.text();
        if (text) msg = text;
      } catch {}
    }
    throw new ExportError(msg, res.status);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const filename = `${filenamePrefix}_${todaySuffix()}.xlsx`;

  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();

  // Delay revoke to let the browser finish the download
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

/** React-safe wrapper with loading state */
export function useExport() {
  return {
    download: async (params: ExportParams) => {
      try {
        await downloadExport(params);
        toast.success("Файл скачивается");
      } catch (e: any) {
        toast.error(e?.message ?? "Не удалось скачать файл");
        throw e;
      }
    },
  };
}
