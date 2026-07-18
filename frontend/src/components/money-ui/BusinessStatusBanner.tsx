import { Card, CardContent } from "@/components/ui/card";
import { AlertTriangle, CheckCircle2, ShieldAlert, XCircle } from "lucide-react";

export interface BusinessStatusBannerProps {
  businessStatus?: string | null;
  financeStatus?: string | null;
  financeDifferencePercent?: number | null;
  supplierConfirmedCostPercent?: number | null;
  openIssuesTotal?: number | null;
  adsOverallocatedSpend?: number | null;
  adsAllocationStatus?: string | null;
  financialFinal?: boolean | null;
  message?: string | null;
}

type Tone = "success" | "warning" | "danger";

const TONE: Record<Tone, { card: string; icon: string; Icon: typeof CheckCircle2 }> = {
  success: { card: "border-emerald-500/40 bg-emerald-500/5",       icon: "text-emerald-600",  Icon: CheckCircle2 },
  warning: { card: "border-amber-500/40 bg-amber-500/5",           icon: "text-amber-600",    Icon: ShieldAlert },
  danger:  { card: "border-red-500/40 bg-red-500/5",               icon: "text-red-600",      Icon: XCircle },
};

export function BusinessStatusBanner(p: BusinessStatusBannerProps) {
  const lines: { tone: Tone; text: string }[] = [];

  if (typeof p.supplierConfirmedCostPercent === "number" && p.supplierConfirmedCostPercent < 95) {
    lines.push({
      tone: p.supplierConfirmedCostPercent < 50 ? "danger" : "warning",
      text: `Себестоимость операционная, не supplier-confirmed (${p.supplierConfirmedCostPercent.toFixed(0)}%)`,
    });
  }

  if ((p.openIssuesTotal ?? 0) > 0) {
    lines.push({ tone: "warning", text: `Есть открытые data issues (${p.openIssuesTotal})` });
  }

  const adsOverallocated =
    (p.adsAllocationStatus && /overallocat/i.test(p.adsAllocationStatus)) ||
    (p.adsOverallocatedSpend ?? 0) > 0;
  if (adsOverallocated) {
    lines.push({ tone: "warning", text: "Реклама распределена с предупреждением (overallocated)" });
  }

  if (p.businessStatus === "data_blocked") {
    lines.push({ tone: "danger", text: "Данные заблокированы — сначала исправить" });
  } else if (
    p.financialFinal === false ||
    p.businessStatus === "provisional" ||
    p.businessStatus === "operational_provisional"
  ) {
    if (!lines.length) {
      lines.push({ tone: "warning", text: "Данные предварительные" });
    }
  }

  if (!lines.length) {
    lines.push({ tone: "success", text: p.message || "Финансово подтверждено" });
  }

  const worst: Tone = lines.some(l => l.tone === "danger") ? "danger"
    : lines.some(l => l.tone === "warning") ? "warning" : "success";
  const cfg = TONE[worst];
  const Icon = cfg.Icon;

  return (
    <Card className={`border ${cfg.card}`}>
      <CardContent className="p-4 flex items-start gap-3">
        <Icon className={`h-5 w-5 mt-0.5 shrink-0 ${cfg.icon}`} />
        <div className="space-y-1">
          {lines.map((l, i) => (
            <div key={i} className="text-sm font-medium leading-snug">
              {l.tone === "danger" ? <AlertTriangle className="inline h-3.5 w-3.5 mr-1 text-red-600" /> : null}
              {l.text}
            </div>
          ))}
          {p.message && worst !== "success" ? (
            <div className="text-xs text-muted-foreground">{p.message}</div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
