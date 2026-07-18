// Компактная линейка уровней доверия для шапки /money.
// Единая таксономия: Подтверждено / Предварительно / Оценка / Не хватает данных / Возможность / Тестовое правило.
// Используем shared TrustBadge, чтобы не расходиться с /results и /action-center.
import { TrustBadge } from "@/components/badges/StatusBadges";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export interface MoneyTrustChipStripProps {
  hasConfirmedFinance: boolean;
  hasProvisional: boolean;
  hasEstimate: boolean;
  hasMissing: boolean;
  hasOpportunity?: boolean;
  hasTestOnly?: boolean;
}

const CHIPS: Array<{ key: keyof MoneyTrustChipStripProps; value: string; hint: string }> = [
  { key: "hasConfirmedFinance", value: "confirmed",   hint: "Финансовые отчёты WB закрыли период по этим цифрам." },
  { key: "hasProvisional",      value: "provisional", hint: "Операционные цифры до закрытия фин. отчёта. Могут уточниться." },
  { key: "hasEstimate",         value: "estimated",   hint: "Расчёт от себестоимости, остатков или моделей. Не факт." },
  { key: "hasMissing",          value: "blocked",     hint: "Источник не подтвердил цифру. Показываем «—», а не ноль." },
  { key: "hasOpportunity",      value: "opportunity", hint: "Ожидаемый эффект от закрытия финансовой проблемы." },
  { key: "hasTestOnly",         value: "test_only",   hint: "Тестовое правило — на решения владельца не влияет." },
];

export function MoneyTrustChipStrip(p: MoneyTrustChipStripProps) {
  return (
    <TooltipProvider>
      <div className="flex flex-wrap items-center gap-1.5">
        {CHIPS.map(({ key, value, hint }) => {
          const active = !!p[key];
          return (
            <Tooltip key={key as string}>
              <TooltipTrigger asChild>
                <span className={active ? "" : "opacity-40"}>
                  <TrustBadge value={value} />
                </span>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs text-xs">{hint}</TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </TooltipProvider>
  );
}
