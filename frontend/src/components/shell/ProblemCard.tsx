import type { ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  SeverityBadge,
  TrustBadge,
  ImpactBadge,
} from "@/components/badges/StatusBadges";

export interface ProblemCardProduct {
  nmId?: string | number;
  name?: string | null;
  vendorCode?: string | null;
  imageUrl?: string | null;
}

export interface ProblemCardProps {
  title: string;
  explanation?: ReactNode;
  severity?: string | null;
  trust?: string | null;
  impact?: string | null;
  product?: ProblemCardProduct;
  primaryAction?: ReactNode;
  evidence?: ReactNode; // ожидается <EvidenceButton />
  status?: ReactNode; // <StatusBadge /> или <ResultBadge />
  className?: string;
  onClick?: () => void;
}

/**
 * Единая карточка проблемы для операционного цикла:
 *   Проблема → доказательства → действие → статус → результат.
 * Не подключается к API — просто структура и стили.
 */
export function ProblemCard({
  title,
  explanation,
  severity,
  trust,
  impact,
  product,
  primaryAction,
  evidence,
  status,
  className,
  onClick,
}: ProblemCardProps) {
  const interactive = !!onClick;
  return (
    <Card
      className={cn(
        "border-border/60 transition-colors",
        interactive && "cursor-pointer hover:border-primary/40 hover:bg-accent/30",
        className,
      )}
      onClick={onClick}
    >
      <CardContent className="p-4 space-y-3">
        {/* Ряд бейджей */}
        <div className="flex flex-wrap items-center gap-1.5">
          {severity ? <SeverityBadge value={severity} /> : null}
          {trust ? <TrustBadge value={trust} /> : null}
          {impact ? <ImpactBadge value={impact} /> : null}
          {status ? <span className="ml-auto">{status}</span> : null}
        </div>

        {/* Идентичность товара */}
        {product ? <ProductIdentityRow product={product} /> : null}

        {/* Заголовок и объяснение */}
        <div className="space-y-1">
          <div className="text-sm font-semibold leading-snug">{title}</div>
          {explanation ? (
            <div className="text-sm text-muted-foreground leading-relaxed">
              {explanation}
            </div>
          ) : null}
        </div>

        {/* Действия */}
        {(primaryAction || evidence) && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            {primaryAction}
            {evidence}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ProductIdentityRow({ product }: { product: ProblemCardProduct }) {
  const { nmId, name, vendorCode, imageUrl } = product;
  return (
    <div className="flex items-center gap-2 rounded-md bg-muted/40 p-2">
      {imageUrl ? (
        <img
          src={imageUrl}
          alt=""
          className="h-8 w-8 shrink-0 rounded-sm object-cover"
          loading="lazy"
        />
      ) : (
        <div className="h-8 w-8 shrink-0 rounded-sm bg-muted" />
      )}
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-medium">
          {name || `Товар ${nmId ?? ""}`.trim()}
        </div>
        <div className="truncate text-[11px] text-muted-foreground">
          {nmId ? `nmId ${nmId}` : null}
          {nmId && vendorCode ? " · " : null}
          {vendorCode ? `арт. ${vendorCode}` : null}
        </div>
      </div>
    </div>
  );
}
