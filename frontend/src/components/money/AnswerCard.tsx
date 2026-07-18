import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Link } from "@tanstack/react-router";
import { ArrowRight, AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DataTrustState } from "@/lib/copy";
import { TRUST_STATE_COPY } from "@/lib/copy";

export interface AnswerCardProps {
  trustState: DataTrustState;
  title: string;
  shortText: string;
  mainProblem?: string | null;
  mainNextStep?: string | null;
  primaryAction?: { label: string; href: string };
  secondaryAction?: { label: string; href: string };
  className?: string;
}

const TONE: Record<DataTrustState, { card: string; bar: string; Icon: typeof AlertTriangle }> = {
  trusted:      { card: "bg-success/5 border-success/30",         bar: "bg-success",      Icon: CheckCircle2 },
  test_only:    { card: "bg-warning/5 border-warning/30",         bar: "bg-warning",      Icon: AlertTriangle },
  data_blocked: { card: "bg-destructive/5 border-destructive/30", bar: "bg-destructive",  Icon: ShieldAlert },
};

export function AnswerCard({ trustState, title, shortText, mainProblem, mainNextStep, primaryAction, secondaryAction, className }: AnswerCardProps) {
  const tone = TONE[trustState] ?? TONE.test_only;
  const trust = TRUST_STATE_COPY[trustState] ?? TRUST_STATE_COPY.test_only;
  const Icon = tone.Icon;


  return (
    <Card className={cn("relative overflow-hidden border-2", tone.card, className)}>
      <div className={cn("absolute left-0 top-0 bottom-0 w-1", tone.bar)} />
      <CardContent className="p-6 space-y-4">
        <div className="flex items-start gap-3">
          <div className={cn("rounded-md p-2 text-white", tone.bar)}><Icon className="h-5 w-5" /></div>
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="outline" className="text-[10px] uppercase tracking-wide">{trust.label}</Badge>
            </div>
            <h2 className="text-xl font-semibold leading-tight">{title}</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">{shortText}</p>
          </div>
        </div>

        {(mainProblem || mainNextStep) && (
          <div className="grid gap-3 md:grid-cols-2 pt-2 border-t">
            {mainProblem && (
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Главная проблема</div>
                <div className="text-sm">{mainProblem}</div>
              </div>
            )}
            {mainNextStep && (
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Главный шаг сегодня</div>
                <div className="text-sm font-medium">{mainNextStep}</div>
              </div>
            )}
          </div>
        )}

        {(primaryAction || secondaryAction) && (
          <div className="flex flex-wrap gap-2 pt-2">
            {primaryAction && (
              <Button asChild size="sm">
                <Link to={primaryAction.href as any}>{primaryAction.label} <ArrowRight className="h-3.5 w-3.5 ml-1" /></Link>
              </Button>
            )}
            {secondaryAction && (
              <Button asChild size="sm" variant="outline">
                <Link to={secondaryAction.href as any}>{secondaryAction.label}</Link>
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
