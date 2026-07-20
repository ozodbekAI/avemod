import { Link } from "@tanstack/react-router";
import { ArrowRight, Wrench } from "lucide-react";
import type { MDataBlocker, DataQualityIssue } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatMoney, formatNumber } from "@/lib/format";
import { MoneyTrustBadge } from "@/components/MoneyTrustBadge";
import { moneyTrustFrom } from "@/lib/money-trust";
import { evidenceFrom } from "@/lib/evidence";
import {
  classifyIssue,
  ISSUE_NATURE_LABEL,
  ISSUE_NATURE_TONE,
  resolvePrimaryActionLabel,
  resolveTargetHref,
} from "@/lib/issue-classification";

type Props = {
  blocker: MDataBlocker;
  issue?: DataQualityIssue | null;
  onOpenWorkbench?: (issue: DataQualityIssue, blocker: MDataBlocker) => void;
  ownerKind?: string;
  nextScreenPath: string;
  nextScreenLabel: string;
  highlight?: boolean;
};

const PRIO_LABEL: Record<string, string> = {
  critical: "Критично",
  high: "Высокий",
  medium: "Средний",
  low: "Низкий",
};

const CAN_FIX_COPY: Record<string, string> = {
  user: "Можно исправить здесь",
  mixed: "Частично",
  system: "Системная проверка",
  admin: "Нужны права администратора",
  aggregate: "Сводный блокер",
};

function linkPropsForPath(path: string): {
  to: string;
  search?: Record<string, string>;
} {
  const [pathname, query = ""] = path.split("?");
  const search = Object.fromEntries(new URLSearchParams(query).entries());
  return Object.keys(search).length > 0
    ? { to: pathname, search }
    : { to: pathname };
}

export function DataFixMobileCard({
  blocker,
  issue,
  onOpenWorkbench,
  ownerKind,
  nextScreenPath,
  nextScreenLabel,
  highlight,
}: Props) {
  const ledger = evidenceFrom(blocker.evidence_ledger);
  const moneyTrust = moneyTrustFrom(blocker.money_trust, ledger?.money_trust);
  const prio = (blocker.priority ?? "medium").toLowerCase();
  const cls = classifyIssue(blocker as any);
  const canFix = cls.showApply
    ? "Можно исправить здесь"
    : (CAN_FIX_COPY[ownerKind ?? cls.owner ?? "user"] ?? "Требуется внимание");
  const actionLabel = resolvePrimaryActionLabel({
    ...(blocker as any),
    next_screen_label: nextScreenLabel,
  });
  const actionHref = resolveTargetHref(blocker as any, nextScreenPath);

  return (
    <Card
      id={`blocker-${blocker.code}`}
      className={`scroll-mt-24 border-border/70 transition-shadow ${
        highlight ? "ring-2 ring-primary shadow-lg" : ""
      }`}
    >
      <CardContent className="p-3 space-y-2.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline" className="text-[10px] uppercase">
            {PRIO_LABEL[prio] ?? prio}
          </Badge>
          <MoneyTrustBadge trust={moneyTrust} />
          {cls.nature ? (
            <Badge
              variant="outline"
              className={`text-[10px] ${ISSUE_NATURE_TONE[cls.nature] ?? ""}`}
            >
              {ISSUE_NATURE_LABEL[cls.nature]}
            </Badge>
          ) : null}
          <Badge variant="secondary" className="text-[10px]">
            {canFix}
          </Badge>
        </div>

        <div className="text-sm font-semibold leading-snug">
          {blocker.title}
        </div>
        {blocker.business_impact ? (
          <div className="text-xs text-muted-foreground leading-relaxed">
            {blocker.business_impact}
          </div>
        ) : null}

        {(blocker as any).disabled_reason && !cls.showApply ? (
          <div className="text-[11px] text-muted-foreground rounded border bg-muted/30 px-2 py-1.5">
            {(blocker as any).disabled_reason}
          </div>
        ) : null}

        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <div className="rounded-md border bg-muted/30 px-2 py-1.5">
            <div className="text-muted-foreground">SKU</div>
            <div className="font-semibold text-xs">
              {formatNumber(blocker.affected_sku_count ?? 0)}
            </div>
          </div>
          <div className="rounded-md border bg-muted/30 px-2 py-1.5">
            <div className="text-muted-foreground">Выручка</div>
            <div className="font-semibold text-xs">
              {formatMoney(blocker.affected_revenue ?? 0)}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5 pt-1">
          {issue && onOpenWorkbench && cls.showApply ? (
            <Button
              size="sm"
              className="h-auto min-h-8 flex-1 min-w-[7rem] whitespace-normal px-2 py-2 leading-snug"
              onClick={() => onOpenWorkbench(issue, blocker)}
            >
              <Wrench className="h-3.5 w-3.5 mr-1.5" />
              Открыть
            </Button>
          ) : null}
          <Button
            asChild
            size="sm"
            variant="outline"
            className="h-auto min-h-8 flex-1 min-w-[7rem] whitespace-normal px-2 py-2 leading-snug"
          >
            <Link
              {...(linkPropsForPath(actionHref ?? nextScreenPath) as any)}
              title={actionLabel}
            >
              <span className="min-w-0 truncate">{actionLabel}</span>
              <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
