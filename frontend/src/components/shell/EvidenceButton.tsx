import { Calculator } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface EvidenceButtonProps {
  onClick?: () => void;
  disabled?: boolean;
  /**
   * Данные недоступны/частичные — кнопка активна, но с пояснением
   * «Данные неполные». Используется, когда бэкенд признаёт отсутствие
   * части фактов, но всё ещё готов открыть панель.
   */
  missing?: boolean;
  className?: string;
  label?: string;
}

/**
 * Единая кнопка «Как посчитано?» для открытия панели доказательств.
 * Никаких смешанных подписей вроде «How calculated?» — только русский.
 */
export function EvidenceButton({
  onClick,
  disabled,
  missing,
  className,
  label = "Как посчитано?",
}: EvidenceButtonProps) {
  const finalLabel = missing ? "Как посчитано? (данные неполные)" : label;
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      className={cn(
        "h-auto min-h-8 gap-1.5 whitespace-normal px-2.5 py-1 text-left text-xs leading-tight sm:min-h-7",
        missing && "border-warning/40 text-[oklch(0.42_0.12_60)]",
        className,
      )}
      disabled={disabled}
      onClick={onClick}
      title={
        missing
          ? "Часть входных данных отсутствует. Расчёт может быть неполным."
          : "Показать источник расчёта, формулу и входные данные"
      }
    >
      <Calculator className="h-3.5 w-3.5" />
      <span>{finalLabel}</span>
    </Button>
  );
}
