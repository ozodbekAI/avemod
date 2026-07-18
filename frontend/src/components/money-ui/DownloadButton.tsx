import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Download, Loader2 } from "lucide-react";
import { toast } from "sonner";

export interface DownloadButtonProps {
  /** Эндпоинт-источник (с авторизацией) или прямой URL. Если возвращает Blob — скачается. */
  fetchBlob: () => Promise<{ blob: Blob; filename?: string }>;
  filename?: string;
  label?: string;
  size?: "sm" | "default";
  variant?: "default" | "outline" | "secondary";
  endpoint?: string; // для сообщения об ошибке
}

/**
 * Кнопка экспорта с состояниями: idle / loading / progress.
 * Не превращает ошибку в тишину — показывает endpoint и HTTP-код.
 */
export function DownloadButton({
  fetchBlob,
  filename = "export.csv",
  label = "Скачать",
  size = "sm",
  variant = "outline",
  endpoint,
}: DownloadButtonProps) {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      size={size}
      variant={variant}
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          const { blob, filename: fn } = await fetchBlob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = fn ?? filename;
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);
        } catch (e: any) {
          const status = e?.status ? ` (HTTP ${e.status})` : "";
          toast.error(`Не удалось скачать${status}`, {
            description: endpoint ? `endpoint: ${endpoint}` : e?.message,
          });
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <Download className="h-3.5 w-3.5 mr-1.5" />}
      {busy ? "Готовим файл…" : label}
    </Button>
  );
}
