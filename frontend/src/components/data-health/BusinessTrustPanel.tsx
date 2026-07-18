// Business-trust summary built strictly from GET /dashboard/data-health.
// Only fields actually present in the payload are shown — no invented values,
// no mocks. Operational trust and financial-final trust are kept on separate
// cards so they cannot be confused.
import type { DashboardDataHealth } from "@/lib/api";
import { normalizeTrust } from "@/lib/trust";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";
import { formatNumber } from "@/lib/format";
import { humanizeBusinessStatus } from "@/lib/copy";
import {
  ShieldCheck, ShieldAlert, ShieldX, AlertTriangle, CheckCircle2,
  Database, Wallet, Activity, ListChecks, Lock,
} from "lucide-react";

interface Props {
  data: DashboardDataHealth | null | undefined;
  isLoading?: boolean;
  isError?: boolean;
}

const dash = "—";

function pct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return dash;
  return `${Number(v).toFixed(0)}%`;
}
function num(v: number | null | undefined): string {
  if (v == null) return dash;
  return formatNumber(Number(v));
}

export function BusinessTrustPanel({ data, isLoading, isError }: Props) {
  if (isLoading) {
    return (
      <Card className="mb-4">
        <CardContent className="p-4 text-sm text-muted-foreground">Загрузка состояния доверия…</CardContent>
      </Card>
    );
  }
  if (isError || !data) {
    return (
      <Alert variant="destructive" className="mb-4">
        <AlertTitle>Не удалось получить /dashboard/data-health</AlertTitle>
        <AlertDescription>Состояние доверия временно недоступно.</AlertDescription>
      </Alert>
    );
  }

  const t = normalizeTrust(data);
  const businessTrusted = t.businessTrusted;
  const financialFinal = t.financialFinal;
  const trustState = t.trustState;
  const supplierCov = t.supplierConfirmedCoverage;
  const realCov = data.real_revenue_cost_coverage_percent ?? null;
  const placeholderCnt = data.placeholder_manual_cost_count ?? null;
  const realCnt = data.real_manual_cost_count ?? null;
  const trustedCnt = data.trusted_manual_cost_count ?? null;
  const costPolicy = t.costTrustPolicy;
  const openIssues = data.open_issues_total ?? 0;
  const finalBlockers = t.finalBlockers;
  const failed = data.failed_domains ?? [];
  const skipped = data.skipped_domains ?? [];
  const missedDays = data.missed_days_count ?? 0;
  const adRows = data.ad_cluster_rows ?? 0;
  const adState = data.ad_cluster_state ?? null;
  const adReason = data.ad_cluster_reason ?? null;

  return (
    <div className="mb-4 space-y-3">
      {/* ─── Warnings (strict order per spec) ─────────────────────────────── */}
      {businessTrusted === false && (
        <Alert variant="destructive">
          <ShieldX className="h-4 w-4" />
          <AlertTitle>Прибыльность нельзя считать достоверной.</AlertTitle>
          <AlertDescription>
            Бизнес-данные не приняты системой. Сначала закройте блокеры данных,
            прежде чем принимать операционные или финансовые решения.
          </AlertDescription>
        </Alert>
      )}

      {businessTrusted === true && financialFinal === false && (
        <Alert className="border-l-4 border-l-warning bg-warning/5">
          <AlertTriangle className="h-4 w-4 text-warning" />
          <AlertTitle>Операционные решения разрешены, но финальная прибыль ещё не закрыта.</AlertTitle>
          <AlertDescription>
            Можно работать с ассортиментом, ценой и рекламой. Финальную маржу
            и P&L используйте только после того, как данные станут финансово подтверждёнными.
          </AlertDescription>
        </Alert>
      )}

      {supplierCov === 0 && (
        <Alert className="border-l-4 border-l-warning bg-warning/5">
          <AlertTriangle className="h-4 w-4 text-warning" />
          <AlertTitle>Подтверждённая себестоимость не загружена. Используется операторская себестоимость.</AlertTitle>
          <AlertDescription>
            Маржа рассчитана по операторской себестоимости. Загрузите файл поставщика, чтобы
            подтвердить себестоимость и закрыть финальную прибыль.
          </AlertDescription>
        </Alert>
      )}

      {financialFinal === true && (
        <Alert className="border-l-4 border-l-success bg-success/5">
          <CheckCircle2 className="h-4 w-4 text-success" />
          <AlertTitle>Финансово подтверждено.</AlertTitle>
          <AlertDescription>
            Сверка с финансовым отчётом WB прошла, подтверждённая
            себестоимость загружена. Прибыль можно использовать как финальную.
          </AlertDescription>
        </Alert>
      )}

      {/* ─── Six trust cards ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {/* 1. Operational trust */}
        <Card className={
          businessTrusted === true ? "border-l-4 border-l-success" :
          businessTrusted === false ? "border-l-4 border-l-destructive" :
          "border-l-4 border-l-muted"
        }>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              {businessTrusted === true
                ? <ShieldCheck className="h-4 w-4 text-success" />
                : businessTrusted === false
                  ? <ShieldX className="h-4 w-4 text-destructive" />
                  : <ShieldAlert className="h-4 w-4 text-muted-foreground" />}
              Операционная пригодность данных
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs space-y-1.5">
            <Row label="Данные пригодны для операционных решений" value={
              businessTrusted == null ? dash : businessTrusted ? "да" : "нет"
            } tone={businessTrusted === true ? "success" : businessTrusted === false ? "danger" : "muted"} />
            <Row label="Состояние доверия" value={trustState ? humanizeBusinessStatus(trustState).label : dash} />
            <div className="text-muted-foreground pt-1">
              Можно ли принимать операционные решения (ассортимент, цена, реклама).
            </div>
          </CardContent>
        </Card>

        {/* 2. Financial final */}
        <Card className={
          financialFinal === true ? "border-l-4 border-l-success" :
          financialFinal === false ? "border-l-4 border-l-warning" :
          "border-l-4 border-l-muted"
        }>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Lock className={`h-4 w-4 ${financialFinal === true ? "text-success" : "text-warning"}`} />
              Финансово подтверждено
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs space-y-1.5">
            <Row label="Финансово подтверждено" value={
              financialFinal == null ? dash : financialFinal ? "да" : "нет"
            } tone={financialFinal === true ? "success" : financialFinal === false ? "warning" : "muted"} />
            <Row label="Блокеров финальной прибыли" value={num(finalBlockers)}
                 tone={(finalBlockers ?? 0) > 0 ? "danger" : "default"} />
            <div className="text-muted-foreground pt-1">
              Финальная прибыль доверяется только когда данные финансово
              подтверждены и блокеров нет.
            </div>
          </CardContent>
        </Card>

        {/* 3. Cost coverage — supplier vs operator baseline strictly separated */}
        <Card className="border-l-4 border-l-primary">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Wallet className="h-4 w-4 text-primary" /> Покрытие себестоимости
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs space-y-2">
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-muted-foreground">Покрытие выручки подтверждённой себестоимостью</span>
                <span className="font-mono">{pct(supplierCov)}</span>
              </div>
              <Progress value={supplierCov ?? 0} className="h-1.5" />
            </div>
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-muted-foreground">Покрытие выручки реальной себестоимостью</span>
                <span className="font-mono">{pct(realCov)}</span>
              </div>
              <Progress value={realCov ?? 0} className="h-1.5" />
            </div>
            <div className="grid grid-cols-3 gap-2 pt-1">
              <Mini label="Подтверждено" value={num(trustedCnt)} />
              <Mini label="Реальная" value={num(realCnt)} />
              <Mini label="Тестовая" value={num(placeholderCnt)} tone={(placeholderCnt ?? 0) > 0 ? "warning" : "default"} />
            </div>
            <Row label="Политика доверия к себестоимости" value={costPolicy ?? dash} />
            {supplierCov === 0 && (
              <div className="text-warning pt-1">
                Используется операторская себестоимость: подтверждённой = 0%.
              </div>
            )}
          </CardContent>
        </Card>

        {/* 4. Sync health */}
        <Card className={
          (failed.length > 0)
            ? "border-l-4 border-l-destructive"
            : (skipped.length > 0 || missedDays > 0)
              ? "border-l-4 border-l-warning"
              : "border-l-4 border-l-success"
        }>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Activity className="h-4 w-4" /> Состояние синхронизаций
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs space-y-1.5">
            <Row label="Источники с ошибкой" value={failed.length === 0 ? "—" : failed.join(", ")}
                 tone={failed.length > 0 ? "danger" : "default"} />
            <Row label="Пропущенные источники" value={skipped.length === 0 ? "—" : skipped.join(", ")}
                 tone={skipped.length > 0 ? "warning" : "default"} />
            <Row label="Пропущено дней" value={num(missedDays)}
                 tone={missedDays > 0 ? "warning" : "default"} />
            <div className="pt-1 border-t mt-1.5">
              <Row label="Строк кластерной статистики" value={num(adRows)} />
              <Row label="Состояние кластерной статистики" value={adState ?? dash}
                   tone={adState && adState !== "ok" && adState !== "linked" ? "warning" : "default"} />
              {adReason && <div className="text-muted-foreground text-[11px] mt-1">{adReason}</div>}
            </div>
          </CardContent>
        </Card>

        {/* 5. Open issues */}
        <Card className={openIssues > 0 ? "border-l-4 border-l-warning" : "border-l-4 border-l-success"}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <ListChecks className="h-4 w-4" /> Открытые проблемы данных
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs space-y-1.5">
            <Row label="Открытых проблем" value={num(openIssues)}
                 tone={openIssues > 0 ? "warning" : "success"} />
            <div className="text-muted-foreground pt-1">
              Открытые проблемы качества данных. Закрытие снижает риск и приближает финансово подтверждённое состояние.
            </div>
          </CardContent>
        </Card>

        {/* 6. Final profit blockers */}
        <Card className={
          (finalBlockers ?? 0) > 0
            ? "border-l-4 border-l-destructive"
            : finalBlockers === 0
              ? "border-l-4 border-l-success"
              : "border-l-4 border-l-muted"
        }>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Database className="h-4 w-4" /> Блокеры финальной прибыли
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs space-y-1.5">
            <Row label="Блокеров финальной прибыли" value={num(finalBlockers)}
                 tone={(finalBlockers ?? 0) > 0 ? "danger" : finalBlockers === 0 ? "success" : "muted"} />
            <div className="text-muted-foreground pt-1">
              Что именно блокирует переход к финальной прибыли (детали — в блоке «Блокеры данных» ниже).
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Row({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "success" | "warning" | "danger" | "muted" }) {
  const cls =
    tone === "success" ? "text-success" :
    tone === "warning" ? "text-warning" :
    tone === "danger"  ? "text-destructive" :
    tone === "muted"   ? "text-muted-foreground" : "";
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground font-mono text-[11px]">{label}</span>
      <span className={`font-mono tabular-nums ${cls}`}>{value}</span>
    </div>
  );
}

function Mini({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "warning" }) {
  return (
    <div className={`rounded border p-1.5 text-center ${tone === "warning" ? "border-warning/40 bg-warning/5" : ""}`}>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="font-mono tabular-nums text-sm">{value}</div>
    </div>
  );
}

// Re-export Badge so the panel surface stays self-contained if consumers
// want to render extra chips inline.
export { Badge as TrustChip };
