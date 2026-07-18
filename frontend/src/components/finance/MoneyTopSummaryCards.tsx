// 6 верхних карточек денежного статуса для /money.
// Используем shared TrustBadge/ImpactBadge — единая таксономия для всего продукта.
// Никаких выдуманных значений: только бэкенд-числа или «—».
import { Card, CardContent } from "@/components/ui/card";
import { TrustBadge, ImpactBadge } from "@/components/badges/StatusBadges";
import { Button } from "@/components/ui/button";
import { EvidenceButton, EvidenceDrawer } from "@/components/EvidenceDrawer";
import type { EvidenceLedger } from "@/lib/evidence";
import { formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useState } from "react";

type Kind = "confirmed" | "provisional" | "risk" | "frozen" | "blocker" | "opportunity";

const FRAME: Record<Kind, string> = {
  confirmed:   "border-emerald-500/30 bg-emerald-500/5",
  provisional: "border-amber-500/30 bg-amber-500/5",
  risk:        "border-orange-500/30 bg-orange-500/5",
  frozen:      "border-sky-500/30 bg-sky-500/5",
  blocker:     "border-destructive/30 bg-destructive/5",
  opportunity: "border-primary/30 bg-primary/5",
};

const TRUST_VALUE: Record<Kind, string> = {
  confirmed:   "confirmed",
  provisional: "provisional",
  risk:        "estimated",
  frozen:      "estimated",
  blocker:     "blocked",
  opportunity: "opportunity",
};

const IMPACT_VALUE: Partial<Record<Kind, string>> = {
  risk: "probable_loss",
  frozen: "blocked_cash",
  opportunity: "opportunity",
  blocker: "data_blocker",
};

function Cell({
  kind, title, hint, value, format, subtitle, missingReason, evidence, linkHref, linkLabel,
}: {
  kind: Kind;
  title: string;
  hint: string;
  value: number | null | undefined;
  format: "money" | "count";
  subtitle?: string | null;
  missingReason?: string | null;
  evidence?: EvidenceLedger | null;
  linkHref?: string | null;
  linkLabel?: string;
}) {
  const [ledger, setLedger] = useState<EvidenceLedger | null>(null);
  const isMissing = value === null || value === undefined;
  const impactKey = IMPACT_VALUE[kind];
  return (
    <Card className={cn("border", FRAME[kind])}>
      <CardContent className="p-4 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {title}
          </div>
          <TrustBadge value={TRUST_VALUE[kind]} />
        </div>
        <div className="text-2xl font-semibold tabular-nums">
          {isMissing ? (
            <span className="text-muted-foreground text-base font-normal">
              — {missingReason ? <span className="text-xs">· {missingReason}</span> : null}
            </span>
          ) : format === "money" ? (
            formatMoney(value as number)
          ) : (
            String(value)
          )}
        </div>
        <div className="text-[11px] text-muted-foreground leading-snug">{hint}</div>
        {subtitle ? <div className="text-[11px] text-muted-foreground">{subtitle}</div> : null}
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          {impactKey ? <ImpactBadge value={impactKey} /> : null}
          {evidence ? <EvidenceButton ledger={evidence} onClick={() => setLedger(evidence)} /> : null}
          {linkHref ? (
            <Button asChild size="sm" variant="ghost" className="h-6 px-2 text-[11px]">
              <a href={linkHref}>{linkLabel ?? "Открыть"}</a>
            </Button>
          ) : null}
        </div>
      </CardContent>
      <EvidenceDrawer
        open={!!ledger}
        onOpenChange={(v) => !v && setLedger(null)}
        ledger={ledger ?? undefined}
        title="Как посчитано"
      />
    </Card>
  );
}

export interface MoneyTopSummaryCardsProps {
  financeConfirmedRevenue: number | null | undefined;
  operationalRevenue: number | null | undefined;
  operationalReconciliationRevenue?: number | null | undefined;
  financeDiffAmount: number | null | undefined;
  financeDiffSubtitle?: string | null | undefined;
  overstockValue: number | null | undefined;
  stockValue: number | null | undefined;
  blockersCount: number | null | undefined;
  opportunityValue: number | null | undefined;
  opportunityCount?: number | null | undefined;
  evidence?: {
    confirmed?: EvidenceLedger | null;
    provisional?: EvidenceLedger | null;
    risk?: EvidenceLedger | null;
    frozen?: EvidenceLedger | null;
  };
}

export function MoneyTopSummaryCards(p: MoneyTopSummaryCardsProps) {
  const reconciliationSubtitle =
    p.operationalReconciliationRevenue != null &&
    p.operationalRevenue != null &&
    Math.abs(p.operationalReconciliationRevenue - p.operationalRevenue) > 0.01
      ? `Для фин. сверки: ${formatMoney(p.operationalReconciliationRevenue)}`
      : null;
  return (
    <section className="space-y-2">
      <div className="space-y-0.5">
        <h2 className="text-base font-semibold">Деньги за период</h2>
        <div className="text-xs text-muted-foreground">
          Подтверждённые, предварительные, оценочные и заблокированные суммы разнесены отдельно.
          Ожидаемый эффект — это оценка, а не измеренная экономия.
        </div>
      </div>
      <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
        <Cell
          kind="confirmed"
          title="Подтверждённые деньги"
          hint="Выручка из финансового отчёта WB за закрытый период."
          value={p.financeConfirmedRevenue ?? null}
          format="money"
          missingReason="фин. отчёт ещё не пришёл"
          evidence={p.evidence?.confirmed ?? null}
        />
        <Cell
          kind="provisional"
          title="Предварительные продажи"
          hint="Операционная выручка. Может уточниться после закрытия финансового отчёта."
          value={p.operationalRevenue ?? null}
          format="money"
          subtitle={reconciliationSubtitle}
          missingReason="нет операционных данных"
          evidence={p.evidence?.provisional ?? null}
        />
        <Cell
          kind="risk"
          title="Вероятные риски"
          hint="Расхождения фин. отчёта и операций, отрицательная маржа, риск потерь по рекламе. Оценка, не факт."
          value={p.financeDiffAmount != null ? Math.abs(p.financeDiffAmount) : null}
          format="money"
          subtitle={p.financeDiffAmount != null ? (p.financeDiffSubtitle ?? "По закрытому периоду WB: finance − operations") : null}
          missingReason="нет сверки"
          evidence={p.evidence?.risk ?? null}
        />
        <Cell
          kind="frozen"
          title="Замороженные деньги"
          hint="Сверхзапас и медленные остатки — деньги, которые лежат на складе."
          value={p.overstockValue ?? null}
          format="money"
          subtitle={p.stockValue != null ? `Всего в товаре: ${formatMoney(p.stockValue as number)}` : null}
          missingReason="нет себестоимости или остатков"
          evidence={p.evidence?.frozen ?? null}
        />
        <Cell
          kind="blocker"
          title="Блокеры расчёта"
          hint="Нет себестоимости, несопоставленный SKU, нераспределённые расходы. Пока открыты — часть цифр остаётся предварительной."
          value={p.blockersCount != null ? p.blockersCount : null}
          format="count"
          subtitle="открытых финансовых проблем"
          missingReason="нет данных о блокерах"
          linkHref="/data-fix"
          linkLabel="Открыть исправление данных"
        />
        <Cell
          kind="opportunity"
          title="Возможности роста"
          hint="Ожидаемый эффект от закрытия финансовых проблем. Это оценка, а не сэкономленные деньги."
          value={p.opportunityValue ?? null}
          format="money"
          subtitle={
            p.opportunityCount != null && p.opportunityCount > 0
              ? `по ${p.opportunityCount} проблемам`
              : "ожидаемый эффект, не факт"
          }
          missingReason="эффект пока не оценён"
          linkHref="/action-center"
          linkLabel="Открыть задачи"
        />
      </div>
    </section>
  );
}
