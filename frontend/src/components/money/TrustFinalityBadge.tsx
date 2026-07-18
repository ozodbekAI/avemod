// Two-tier trust badge: operational vs financial-final.
// - businessTrusted=true AND financialFinal=false → yellow provisional badge
// - financialFinal=true → green "Финансово подтверждено"
// - supplierConfirmedCoverage === 0 → extra notice about operator baseline
// Never shows the green final badge unless financialFinal is true.

import { Badge } from "@/components/ui/badge";
import { CheckCircle2, AlertTriangle, Info } from "lucide-react";
import type { NormalizedTrust } from "@/lib/trust";

interface Props {
  trust: NormalizedTrust;
  className?: string;
}

export function TrustFinalityBadge({ trust, className }: Props) {
  const { businessTrusted, operationalTrusted, financialFinal, supplierConfirmedCoverage } = trust;
  const showProvisional = (operationalTrusted || businessTrusted) && !financialFinal;
  const showFinal = financialFinal === true;
  const showSupplierMissing = supplierConfirmedCoverage === 0;

  if (!showProvisional && !showFinal && !showSupplierMissing) return null;

  return (
    <div className={`flex flex-wrap items-center gap-2 ${className ?? ""}`}>
      {showFinal && (
        <Badge variant="outline" className="border-success/40 bg-success/10 text-success gap-1.5">
          <CheckCircle2 className="h-3.5 w-3.5" />
          Финансово подтверждено
        </Badge>
      )}
      {showProvisional && (
        <Badge variant="outline" className="border-warning/40 bg-warning/10 text-warning gap-1.5">
          <AlertTriangle className="h-3.5 w-3.5" />
          Данные предварительные
        </Badge>
      )}
      {showSupplierMissing && (
        <Badge variant="outline" className="border-orange-500/40 bg-orange-500/10 text-orange-600 gap-1.5">
          <Info className="h-3.5 w-3.5" />
          Supplier-confirmed себестоимость не загружена. Используется операторская себестоимость.
        </Badge>
      )}
    </div>
  );
}

/** Profit label that follows financialFinal strictly. */
export function profitLabel(financialFinal: boolean): string {
  return financialFinal ? "Финальная прибыль" : "Операционная прибыль";
}
