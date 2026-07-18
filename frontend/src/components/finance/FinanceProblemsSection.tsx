import { useMemo, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ProblemCard } from "@/components/shell/ProblemCard";
import { EmptyState } from "@/components/shell/EmptyState";
import { EvidenceButton, EvidenceDrawer } from "@/components/EvidenceDrawer";
import { ResultBadge } from "@/components/badges/StatusBadges";
import {
  FINANCE_CATEGORY_LABEL,
  FINANCE_CATEGORY_ORDER,
  categorizeFinanceCode,
  isFinanceBlocker,
  type FinanceCategory,
} from "./financeCategorize";
import { FinanceProblemDrawer } from "./FinanceProblemDrawer";
import type { MDataBlocker } from "@/lib/api";
import type { EvidenceLedger } from "@/lib/evidence";

export interface FinanceProblemsSectionProps {
  blockers: MDataBlocker[] | undefined | null;
  warnings?: MDataBlocker[] | undefined | null;
  accountId?: number | null;
  isLoading?: boolean;
}

export function FinanceProblemsSection({
  blockers,
  warnings,
  accountId,
  isLoading,
}: FinanceProblemsSectionProps) {
  const [selected, setSelected] = useState<MDataBlocker | null>(null);
  const [evidenceLedger, setEvidenceLedger] = useState<EvidenceLedger | null>(null);

  const grouped = useMemo(() => {
    const all: MDataBlocker[] = [
      ...(Array.isArray(blockers) ? blockers : []),
      ...(Array.isArray(warnings) ? warnings : []),
    ].filter((b) => isFinanceBlocker(b?.code));
    const map = new Map<FinanceCategory, MDataBlocker[]>();
    for (const b of all) {
      const cat = categorizeFinanceCode(b?.code);
      const arr = map.get(cat) ?? [];
      arr.push(b);
      map.set(cat, arr);
    }
    return map;
  }, [blockers, warnings]);

  const totalCount = Array.from(grouped.values()).reduce((s, a) => s + a.length, 0);

  return (
    <section className="space-y-3">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">Финансовые проблемы</h2>
          <p className="text-xs text-muted-foreground">
            Всё, что мешает подтвердить деньги и прибыль. Откройте карточку, чтобы увидеть,
            как посчитано, и что сделать.
          </p>
        </div>
        {totalCount > 0 ? (
          <Button asChild size="sm" variant="outline">
            <a href="/results?source_module=finance" title="Открывает страницу результатов с фильтром по финансам">
              Открыть все результаты по деньгам
            </a>
          </Button>
        ) : (
          <Button
            size="sm"
            variant="outline"
            disabled
            title="Пока нет финансовых проблем, поэтому и результатов по деньгам нет"
          >
            Результатов по деньгам пока нет
          </Button>
        )}
      </header>

      {isLoading ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">Загружаем финансовые проблемы…</CardContent>
        </Card>
      ) : totalCount === 0 ? (
        <EmptyState
          variant="no_problems"
          title="Финансовых проблем не найдено"
          hint="По текущим данным активных финансовых проблем нет."
        />
      ) : (
        <div className="space-y-4">
          {FINANCE_CATEGORY_ORDER.map((cat) => {
            const items = grouped.get(cat);
            if (!items || items.length === 0) return null;
            return (
              <div key={cat} className="space-y-2">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold">{FINANCE_CATEGORY_LABEL[cat]}</h3>
                  <Badge variant="secondary" className="text-[10px]">открыто: {items.length}</Badge>
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  {items.map((p, i) => {
                    const problemInstanceId = (p as any)?.problem_instance_id ?? null;
                    const actionId = (p as any)?.action_id ?? null;
                    const nmId = (p as any)?.nm_id ?? null;
                    const dataFixHref = problemInstanceId
                      ? `/data-fix?problem_instance_id=${encodeURIComponent(String(problemInstanceId))}${nmId ? `&nm_id=${nmId}` : ""}`
                      : `/data-fix`;
                    const actionHref = actionId
                      ? `/action-center?action_id=${encodeURIComponent(String(actionId))}`
                      : problemInstanceId
                        ? `/action-center?problem_instance_id=${encodeURIComponent(String(problemInstanceId))}`
                        : null;
                    const resultHref = problemInstanceId
                      ? `/results?problem_instance_id=${encodeURIComponent(String(problemInstanceId))}`
                      : null;
                    const trustLabel =
                      p.money_trust?.display_label ?? p.money_trust?.trust_state ?? undefined;
                    const amount = (p as any)?.affected_amount ?? p.affected_revenue ?? null;
                    const isRisk = String(p.money_trust?.impact_kind ?? "").toLowerCase().includes("risk")
                      || String(p.money_trust?.trust_state ?? "").toLowerCase().includes("risk");
                    const amountLabel = amount == null
                      ? null
                      : `${isRisk ? "Риск" : "Затронуто"}: ${amount.toLocaleString("ru-RU")} ₽`;
                    return (
                      <ProblemCard
                        key={`${p.code}-${i}`}
                        title={p.title || p.code}
                        explanation={
                          <>
                            {p.simple_reason || p.business_impact}
                            {amountLabel ? (
                              <div className="mt-1 text-xs font-medium text-foreground">{amountLabel}</div>
                            ) : null}
                          </>
                        }
                        severity={p.priority ? String(p.priority) : undefined}
                        trust={trustLabel ? String(trustLabel) : undefined}
                        impact={p.business_impact ? String(p.business_impact) : undefined}
                        onClick={() => setSelected(p)}
                        status={
                          (p as any)?.result_state ? (
                            <ResultBadge value={String((p as any).result_state)} />
                          ) : undefined
                        }
                        primaryAction={
                          <div className="flex flex-wrap gap-1.5" onClick={(e) => e.stopPropagation()}>
                            <Button asChild size="sm">
                              <a href={dataFixHref}>Открыть исправление данных</a>
                            </Button>
                            {actionHref ? (
                              <Button asChild size="sm" variant="outline">
                                <a href={actionHref}>Открыть задачу</a>
                              </Button>
                            ) : (
                              <Button size="sm" variant="outline" disabled title="Задача ещё не создана">
                                Открыть задачу
                              </Button>
                            )}
                            {resultHref ? (
                              <Button asChild size="sm" variant="outline">
                                <a href={resultHref}>Открыть результат</a>
                              </Button>
                            ) : (
                              <Button size="sm" variant="outline" disabled title="Результата пока нет — ждём повторную проверку">
                                Открыть результат
                              </Button>
                            )}
                          </div>
                        }
                        evidence={
                          p.evidence_ledger ? (
                            <span
                              onClick={(e) => {
                                e.stopPropagation();
                                setEvidenceLedger(p.evidence_ledger ?? null);
                              }}
                            >
                              <EvidenceButton ledger={p.evidence_ledger} onClick={() => setEvidenceLedger(p.evidence_ledger ?? null)} />
                            </span>
                          ) : undefined
                        }
                      />
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <FinanceProblemDrawer
        problem={selected}
        onClose={() => setSelected(null)}
        accountId={accountId}
      />

      <EvidenceDrawer
        open={!!evidenceLedger}
        onOpenChange={(v) => !v && setEvidenceLedger(null)}
        ledger={evidenceLedger ?? undefined}
        title="Как посчитано"
      />
    </section>
  );
}
