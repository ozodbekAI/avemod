import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Download, Loader2 } from "lucide-react";
import { downloadExport, ExportError } from "@/lib/export";
import { toast } from "sonner";

// Endpoints that are known-flaky in production and may return 500.
// For those, show a soft user-facing message instead of leaking the raw error.
const FLAKY_ENDPOINTS = new Set<string>([
  "/export/data-quality.xlsx",
  "/export/missing-costs.xlsx",
]);

export function ExportButton({
  endpoint,
  filenamePrefix,
  query,
  label,
}: {
  endpoint: string;
  filenamePrefix: string;
  query: Record<string, string | number | boolean | null | undefined>;
  label: string;
}) {
  const [loading, setLoading] = useState(false);

  const handleClick = async () => {
    if (loading) return;
    setLoading(true);
    try {
      await downloadExport({ endpoint, filenamePrefix, query });
      toast.success("Файл скачивается");
    } catch (e: unknown) {
      const status = e instanceof ExportError ? e.status : 0;
      const isFlaky = FLAKY_ENDPOINTS.has(endpoint);
      if (isFlaky && status >= 500) {
        toast.error("Экспорт временно недоступен. Попробуйте позже.");
      } else {
        const msg = e instanceof Error ? e.message : "Не удалось скачать файл";
        toast.error(msg);
      }
      // Swallow — never crash the page or navigate away.
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button size="sm" variant="outline" onClick={handleClick} disabled={loading}>
      {loading ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <Download className="h-3.5 w-3.5 mr-1.5" />}
      {loading ? "Готовим…" : label}
    </Button>
  );
}
