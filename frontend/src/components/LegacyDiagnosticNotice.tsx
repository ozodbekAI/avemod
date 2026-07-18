import { AlertTriangle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  legacyDiagnosticSurface,
  type LegacyDiagnosticSurfaceId,
} from "@/lib/legacy-diagnostics";

export function LegacyFallbackBadge() {
  return (
    <Badge variant="outline" className="border-amber-500/45 bg-amber-500/10 text-amber-800 dark:text-amber-200">
      Legacy fallback
    </Badge>
  );
}

export function LegacyDiagnosticNotice({
  surfaceId,
}: {
  surfaceId: LegacyDiagnosticSurfaceId;
}) {
  const surface = legacyDiagnosticSurface(surfaceId);
  return (
    <Alert className="mb-4 border-amber-500/40 bg-amber-500/5" data-testid="legacy-diagnostic-notice">
      <AlertTriangle className="h-4 w-4 text-amber-600" />
      <AlertTitle className="flex flex-wrap items-center gap-2">
        <LegacyFallbackBadge />
        Админская legacy-диагностика
      </AlertTitle>
      <AlertDescription>
        {surface.title}. Основной источник проблем для продавца: {surface.dynamicPrimary}.
        {surface.sellerPolicy ? ` ${surface.sellerPolicy}` : ""}
      </AlertDescription>
    </Alert>
  );
}
