import { useState } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EvidenceButton, EvidenceDrawer } from "@/components/EvidenceDrawer";
import {
  SeverityBadge,
  TrustBadge,
  ImpactBadge,
  ResultBadge,
} from "@/components/badges/StatusBadges";
import { formatMoney } from "@/lib/format";
import type { MDataBlocker } from "@/lib/api";

export interface FinanceProblemDrawerProps {
  problem: MDataBlocker | null;
  onClose: () => void;
  accountId?: number | null;
}

function fmt(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  return formatMoney(v);
}

function factOrEstimate(code: string, trust?: string | null): string {
  const c = code.toLowerCase();
  if (/reconc|mismatch|finance_without_sale|sale_without_finance/.test(c))
    return "Данные подтверждены (расхождение между источниками)";
  if (/missing_cost|missing_data|unclassified|unmatched|expense_unclassified/.test(c))
    return "Не хватает данных";
  if (/negative_unit_profit|unprofitable|loss/.test(c))
    return "Оценка на основе доступной себестоимости и комиссий";
  const t = String(trust ?? "").toLowerCase();
  if (["final", "financial_final", "confirmed"].includes(t)) return "Данные подтверждены";
  if (["provisional", "preliminary"].includes(t)) return "Предварительные данные";
  if (["test", "sandbox", "test_only"].includes(t)) return "Тестовый сигнал";
  return "Оценка";
}

function recommendedAction(code: string): string {
  const c = code.toLowerCase();
  if (/missing_cost/.test(c)) return "Загрузить себестоимость";
  if (/unmatched_sku|missing_sku/.test(c)) return "Сопоставить SKU";
  if (/expense_unclassified/.test(c)) return "Классифицировать расход";
  if (/ad_spend_without_sku/.test(c)) return "Привязать рекламу к SKU";
  if (/reconc|mismatch/.test(c)) return "Открыть исправление данных";
  if (/negative_unit_profit|unprofitable/.test(c)) return "Проверить цену и себестоимость";
  if (/document|unpaid|duplicate/.test(c)) return "Открыть документ";
  return "Открыть исправление данных";
}

export function FinanceProblemDrawer({ problem, onClose }: FinanceProblemDrawerProps) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const open = !!problem;
  const p = problem;
  const code = String(p?.code ?? "");
  const trust = String(p?.money_trust?.display_label ?? p?.money_trust?.trust_state ?? "");
  const evidence = p?.evidence_ledger ?? null;
  const affected = p?.affected_amount ?? p?.affected_revenue ?? null;
  const problemInstanceId = (p as any)?.problem_instance_id ?? null;
  const nmId = (p as any)?.nm_id ?? null;

  const dataFixHref = problemInstanceId
    ? `/data-fix?problem_instance_id=${encodeURIComponent(String(problemInstanceId))}${nmId ? `&nm_id=${nmId}` : ""}`
    : `/data-fix`;
  const actionCenterHref = problemInstanceId
    ? `/action-center?problem_instance_id=${encodeURIComponent(String(problemInstanceId))}`
    : `/action-center`;
  const resultsHref = problemInstanceId
    ? `/results?problem_instance_id=${encodeURIComponent(String(problemInstanceId))}`
    : null;

  return (
    <>
      <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
        <SheetContent side="right" className="w-full sm:max-w-xl overflow-y-auto">
          {p ? (
            <>
              <SheetHeader className="space-y-2">
                <SheetTitle className="text-base leading-snug">{p.title || code || "Финансовая проблема"}</SheetTitle>
                <div className="flex flex-wrap gap-1.5">
                  {p.priority ? <SeverityBadge value={String(p.priority)} /> : null}
                  {trust ? <TrustBadge value={trust} /> : null}
                  {p.business_impact ? <ImpactBadge value={String(p.business_impact)} /> : null}
                  {(p as any)?.result_state ? <ResultBadge value={String((p as any).result_state)} /> : null}
                </div>
              </SheetHeader>

              <div className="mt-4 space-y-5 text-sm">
                <Section title="Что произошло?">
                  <p className="text-muted-foreground">
                    {p.simple_reason || p.business_impact || p.title}
                  </p>
                </Section>

                <Section title="Почему платформа так решила?">
                  <div className="text-muted-foreground">
                    {p.calculation_title || "Расчёт на основе доступных источников."}
                  </div>
                  {p.calculation_formula ? (
                    <div className="mt-1 rounded-md border bg-muted/40 p-2 text-xs font-mono">
                      {p.calculation_formula}
                    </div>
                  ) : null}
                  <div className="mt-2">
                    {evidence ? (
                      <EvidenceButton ledger={evidence} onClick={() => setEvidenceOpen(true)} />
                    ) : (
                      <span className="text-xs text-muted-foreground">
                        Как посчитано? (доказательств пока нет)
                      </span>
                    )}
                  </div>
                </Section>

                <Section title="Какие деньги затронуты?">
                  <ul className="grid grid-cols-2 gap-2 text-xs">
                    <MoneyRow label="Подтверждено" value={null} />
                    <MoneyRow label="Предварительно" value={affected} />
                    <MoneyRow label="Оценка риска" value={p.current_value ?? null} />
                    <MoneyRow label="Заблокировано" value={null} />
                    <MoneyRow label="Не хватает данных" value={p.affected_sku_count ? `${p.affected_sku_count} SKU` : null} />
                  </ul>
                </Section>

                <Section title="Это факт или оценка?">
                  <Badge variant="outline" className="text-xs">{factOrEstimate(code, trust)}</Badge>
                </Section>

                <Section title="Что сделать сейчас?">
                  <div className="flex flex-wrap gap-2">
                    <Button asChild size="sm">
                      <a href={dataFixHref}>{recommendedAction(code)}</a>
                    </Button>
                    <Button asChild size="sm" variant="outline">
                      <a href={actionCenterHref}>Открыть задачу</a>
                    </Button>
                    {resultsHref ? (
                      <Button asChild size="sm" variant="outline">
                        <a href={resultsHref}>Открыть результат</a>
                      </Button>
                    ) : (
                      <Button size="sm" variant="outline" disabled title="Результат появится после действия и перепроверки">
                        Открыть результат
                      </Button>
                    )}
                  </div>
                </Section>

                <Section title="Связь с задачей">
                  <div className="text-xs text-muted-foreground">
                    {problemInstanceId ? (
                      <>Связано с задачей #{String(problemInstanceId)}</>
                    ) : (
                      <>Задача ещё не создана. Откройте Action Center, чтобы поставить в работу.</>
                    )}
                  </div>
                </Section>

                <Section title="Повторная проверка">
                  <div className="text-xs text-muted-foreground">
                    Перепроверка запускается автоматически после действия. Если действие не поддерживается — кнопка отключена.
                  </div>
                </Section>

                <Section title="Результат">
                  <div className="text-xs text-muted-foreground">
                    {resultsHref
                      ? "Смотрите вкладку «Результаты» — там измеренный эффект после перепроверки."
                      : "Ждём данных для измерения эффекта."}
                  </div>
                  <div className="mt-1 text-[11px] text-muted-foreground/80">
                    Это ожидаемый эффект, а не измеренная экономия.
                  </div>
                </Section>
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>

      {evidence ? (
        <EvidenceDrawer
          open={evidenceOpen}
          onOpenChange={setEvidenceOpen}
          ledger={evidence}
          title="Как посчитано"
        />
      ) : null}
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </div>
      <div>{children}</div>
    </div>
  );
}

function MoneyRow({ label, value }: { label: string; value: number | string | null }) {
  return (
    <li className="rounded-md border bg-card/40 px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-sm font-medium">
        {value == null ? "—" : typeof value === "number" ? fmt(value) : value}
      </div>
    </li>
  );
}
