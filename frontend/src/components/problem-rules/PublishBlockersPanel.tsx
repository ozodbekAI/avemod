import { useState } from "react";
import { AlertTriangle, Archive, Loader2, Pause, Rocket } from "lucide-react";

import { formatMoneyCompact } from "@/lib/format";
import type {
  ProblemRuleVersion,
  RuleBacktestResponse,
  RuleValidationResponse,
} from "@/lib/problem-rules";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  AdminRuleStepper,
  InfoTile,
  StatusBadge,
  type PublishIssue,
} from "./ProblemRulesAdminShared";

export function PublishBlockersPanel({
  selectedVersion,
  validation,
  backtest,
  blockers,
  warnings,
  sellerPreviewReviewed,
  override,
  overrideReason,
  onOverride,
  onOverrideReason,
  publishDisabled,
  publishPending,
  pausePending,
  archivePending,
  onPublish,
  onPause,
  onArchive,
}: {
  selectedVersion: ProblemRuleVersion | null;
  validation: RuleValidationResponse | null;
  backtest: RuleBacktestResponse | null;
  blockers: PublishIssue[];
  warnings: string[];
  sellerPreviewReviewed: boolean;
  override: boolean;
  overrideReason: string;
  onOverride: (value: boolean) => void;
  onOverrideReason: (value: string) => void;
  publishDisabled: boolean;
  publishPending: boolean;
  pausePending: boolean;
  archivePending: boolean;
  onPublish: () => void;
  onPause: () => void;
  onArchive: () => void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  return (
    <>
      <div className="rounded-md border p-3" data-admin-rule-publish-gate="1">
        <AdminRuleStepper activeStep={10} />
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-sm font-medium">11. Публикация правила</div>
            <div className="text-xs text-muted-foreground">
              Перед публикацией обязательны валидация, тестовый прогон и предпросмотр влияния.
            </div>
          </div>
          {selectedVersion && <StatusBadge status={selectedVersion.status} />}
        </div>

        <div className="grid gap-2 md:grid-cols-5">
          <InfoTile label="Валидация" value={validation?.valid ? "пройдена" : "не пройдена"} />
          <InfoTile label="Предпросмотр влияния" value={backtest ? "готов" : "не запускался"} />
          <InfoTile label="Карточки продавца" value={sellerPreviewReviewed ? "проверены" : "не подтверждены"} />
          <InfoTile label="Найдено" value={backtest ? `${backtest.matched_count}/${backtest.evaluated_count}` : "—"} />
          <InfoTile
            label="Оценка влияния"
            value={backtest ? formatMoneyCompact(Number(backtest.total_impact_amount ?? 0)) : "—"}
          />
        </div>

        {blockers.length > 0 ? (
          <Alert variant="destructive" className="mt-3">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Публикация заблокирована</AlertTitle>
            <AlertDescription>
              <ul className="space-y-2 pl-1">
                {blockers.map((item) => (
                  <li key={`${item.key}-${item.message}`} className="rounded-md border border-destructive/40 bg-background/50 p-2 text-xs">
                    <div className="flex items-start justify-between gap-2">
                      <div className="font-medium">{item.message}</div>
                      <span className="text-[10px] uppercase tracking-wide text-destructive">
                        {item.severity === "warning" ? "предупр." : "блокер"}
                      </span>
                    </div>
                    <div className="mt-1 text-[10px] text-muted-foreground">
                      <span className="font-mono">{item.key}</span>
                    </div>
                    {item.why ? (
                      <div className="mt-1 text-[11px]">
                        <span className="font-medium">Почему это важно: </span>
                        <span className="text-muted-foreground">{item.why}</span>
                      </div>
                    ) : null}
                    {item.fix ? (
                      <div className="mt-0.5 text-[11px]">
                        <span className="font-medium">Как исправить: </span>
                        <span className="text-muted-foreground">{item.fix}</span>
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        ) : null}

        {warnings.length > 0 ? (
          <Alert className="mt-3">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Предупреждения перед публикацией</AlertTitle>
            <AlertDescription>
              <ul className="list-disc pl-4">
                {warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        ) : null}

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={override}
              onCheckedChange={(checked) => onOverride(Boolean(checked))}
            />
            Разрешить широкий охват с причиной
          </label>
          <Input
            className="max-w-md"
            disabled={!override}
            value={overrideReason}
            onChange={(event) => onOverrideReason(event.target.value)}
            placeholder="Причина ручного подтверждения"
          />
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button onClick={() => setConfirmOpen(true)} disabled={publishDisabled}>
            {publishPending ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Rocket className="mr-1.5 h-4 w-4" />
            )}
            Опубликовать
          </Button>
          <Button
            variant="outline"
            onClick={onPause}
            disabled={!selectedVersion || pausePending}
          >
            {pausePending ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Pause className="mr-1.5 h-4 w-4" />
            )}
            Пауза
          </Button>
          <Button
            variant="outline"
            onClick={onArchive}
            disabled={!selectedVersion || archivePending}
          >
            {archivePending ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Archive className="mr-1.5 h-4 w-4" />
            )}
            Архив
          </Button>
        </div>
      </div>
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Подтвердить публикацию правила?</DialogTitle>
            <DialogDescription>
              После публикации правило начнёт создавать динамические проблемы для продавцов. Проверьте охват, влияние и доказательства.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <div className="grid gap-2 sm:grid-cols-2">
              <InfoTile label="Версия" value={selectedVersion ? `v${selectedVersion.version}` : "—"} />
              <InfoTile label="Найдено в тесте" value={backtest ? `${backtest.matched_count}/${backtest.evaluated_count}` : "—"} />
            </div>
            {warnings.length > 0 ? (
              <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3">
                <div className="font-medium">Остаются предупреждения</div>
                <ul className="mt-1 list-disc pl-4 text-muted-foreground">
                  {warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3">
                Критичных предупреждений нет. Предпросмотр влияния выполнен.
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              Вернуться к проверке
            </Button>
            <Button
              onClick={() => {
                setConfirmOpen(false);
                onPublish();
              }}
              disabled={publishPending || blockers.length > 0}
            >
              {publishPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Rocket className="mr-1.5 h-4 w-4" />}
              Подтвердить публикацию
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
