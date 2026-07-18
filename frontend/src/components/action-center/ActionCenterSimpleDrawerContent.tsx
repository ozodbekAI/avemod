// @ts-nocheck
import { Link } from "@tanstack/react-router";
import {
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  Info,
  RefreshCw,
  Save,
  Wrench,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { EvidenceButton } from "@/components/EvidenceDrawer";
import { ActionCenterTaskDrawer } from "@/components/action-center/ActionCenterTaskDrawer";
import {
  dataFreshnessBlockingLabel,
  type ActionCenterItem,
} from "@/lib/action-center-contract";
import {
  actionEvidenceLedger,
  actionProductIdentity,
  statusOptionsForAction,
} from "@/lib/action-center-status";
import {
  primaryActionForItem,
  type ActionDraft,
  type RecheckResult,
} from "@/lib/action-center-actions";
import { formatMoney } from "@/lib/format";
import {
  problemCodeLabel,
  problemImpactLabel,
  problemStatusLabel,
  problemTrustLabel,
} from "@/lib/problem-ux-copy";
import type { EvidenceLedger } from "@/lib/evidence";
import type { PortalAssignableUser, PortalResultEventsPage } from "@/lib/portal";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  action: ActionCenterItem;
  rowKey: string;
  users?: PortalAssignableUser[] | null;
  claimsEnabled: boolean;
  busy: string | null;
  mutationPending: boolean;
  now: Date;
  draft: ActionDraft;
  resultPage?: PortalResultEventsPage | null;
  resultLoading?: boolean;
  resultError?: unknown;
  resultEndpointAvailable?: boolean;
  recheckResult?: RecheckResult;
  onDraftChange: (patch: Partial<ActionDraft>) => void;
  onSave: () => void;
  onRecheck: () => void;
  onOpenEvidence: (title: string, ledger: EvidenceLedger | null) => void;
};

function text(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

function simpleProblemTitle(action: ActionCenterItem): string {
  const codeLabel = problemCodeLabel(action.problem_code ?? action.issue_code);
  if (codeLabel && codeLabel !== "Проблема" && codeLabel !== "Проверка данных") {
    return codeLabel;
  }
  return text(action.title) ?? "Задача";
}

function simpleReason(action: ActionCenterItem): string {
  return (
    text(action.reason) ??
    text(action.short_explanation) ??
    text(action.summary) ??
    "Платформа нашла риск по товару. Проверьте данные и выполните следующий шаг."
  );
}

function simpleNextStep(action: ActionCenterItem): string {
  return (
    text(action.next_step) ??
    text(action.recommendation) ??
    "Откройте место исправления, внесите правку и запустите повторную проверку."
  );
}

function SimpleInfo({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 min-h-5 break-words text-sm font-medium">
        {text(value) ?? "—"}
      </div>
    </div>
  );
}

export function ActionCenterSimpleDrawerContent({
  open,
  onOpenChange,
  action,
  rowKey,
  users,
  busy,
  mutationPending,
  draft,
  recheckResult,
  onDraftChange,
  onSave,
  onRecheck,
  onOpenEvidence,
}: Props) {
  const ledger = actionEvidenceLedger(action);
  const primaryAction = primaryActionForItem(action);
  const statusOptions = statusOptionsForAction(action);
  const productIdentity = actionProductIdentity(action) || "Товар не указан";
  const saveDisabled = mutationPending || busy === rowKey || !action.can_update;
  const canRecheck = Boolean(action.can_recheck || action.problem_instance_id);
  const mainHref = primaryAction?.href ?? action.guided_fix?.href ?? null;
  const mainLabel =
    primaryAction?.label ??
    action.guided_fix?.label ??
    (action.problem_code?.includes("cost") ? "Заполнить себестоимость" : "Открыть исправление");

  return (
    <ActionCenterTaskDrawer open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto p-0 sm:max-w-2xl">
        <div className="border-b px-4 py-4 pr-12 sm:px-6">
          <SheetHeader className="text-left">
            <SheetTitle className="line-clamp-2 leading-snug">
              {simpleProblemTitle(action)}
            </SheetTitle>
            <SheetDescription>
              Простая карточка: что случилось, что сделать и как проверить.
            </SheetDescription>
          </SheetHeader>
        </div>

        <div className="space-y-4 p-4 sm:p-6">
          <div className="flex flex-wrap gap-2">
            {action.priority ? <Badge variant="outline">{action.priority}</Badge> : null}
            <Badge variant="secondary">{problemStatusLabel(action.status)}</Badge>
            {action.impact_type ? (
              <Badge variant="outline">{problemImpactLabel(action.impact_type)}</Badge>
            ) : null}
            {action.trust_state ? (
              <Badge variant="outline">{problemTrustLabel(action.trust_state)}</Badge>
            ) : null}
          </div>

          <section className="space-y-2 rounded-md border p-4">
            <div className="text-sm font-semibold">Что случилось</div>
            <div className="text-sm text-muted-foreground">{simpleReason(action)}</div>
          </section>

          <section className="grid gap-2 sm:grid-cols-2">
            <SimpleInfo label="Товар" value={productIdentity} />
            <SimpleInfo
              label="Влияние"
              value={
                action.money_impact_amount != null
                  ? formatMoney(action.money_impact_amount)
                  : action.impact_type
                    ? problemImpactLabel(action.impact_type)
                    : null
              }
            />
            <SimpleInfo
              label="Данные"
              value={dataFreshnessBlockingLabel(action.data_freshness)}
            />
            <SimpleInfo
              label="Результат"
              value={action.result_status === "improved" ? "Есть улучшение" : "Ждём проверки"}
            />
          </section>

          <section className="space-y-3 rounded-md border p-4">
            <div>
              <div className="text-sm font-semibold">Что сделать</div>
              <div className="mt-1 text-sm text-muted-foreground">
                {simpleNextStep(action)}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {mainHref ? (
                mainHref.startsWith("/") ? (
                  <Button asChild>
                    <Link to={mainHref}>
                      <Wrench className="mr-1 h-4 w-4" />
                      {mainLabel}
                    </Link>
                  </Button>
                ) : (
                  <Button asChild>
                    <a href={mainHref} target="_blank" rel="noreferrer">
                      <Wrench className="mr-1 h-4 w-4" />
                      {mainLabel}
                      <ExternalLink className="ml-1 h-4 w-4" />
                    </a>
                  </Button>
                )
              ) : null}
              {ledger ? (
                <EvidenceButton
                  ledger={ledger}
                  onClick={() => onOpenEvidence(action.title ?? "Как посчитано", ledger)}
                />
              ) : null}
            </div>
          </section>

          <section className="space-y-3 rounded-md border p-4">
            <div className="text-sm font-semibold">Работа по задаче</div>
            {action.can_update ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1">
                  <span className="text-xs font-medium">Статус</span>
                  <Select
                    value={draft.status}
                    disabled={saveDisabled}
                    onValueChange={(value) => onDraftChange({ status: value })}
                  >
                    <SelectTrigger className="min-h-10">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {statusOptions.map((status) => (
                        <SelectItem key={status.value} value={status.value}>
                          {status.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium">Ответственный</span>
                  {users?.length ? (
                    <Select
                      value={draft.assigned_to_user_id || "__none__"}
                      disabled={saveDisabled}
                      onValueChange={(value) =>
                        onDraftChange({
                          assigned_to_user_id: value === "__none__" ? "" : value,
                        })
                      }
                    >
                      <SelectTrigger className="min-h-10">
                        <SelectValue placeholder="Не назначен" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">Не назначен</SelectItem>
                        {users.map((user) => (
                          <SelectItem key={user.id} value={String(user.id)}>
                            {user.full_name || user.email || `Пользователь ${user.id}`}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      value={draft.assigned_to_user_id}
                      disabled={saveDisabled}
                      onChange={(event) =>
                        onDraftChange({ assigned_to_user_id: event.target.value })
                      }
                      placeholder="ID пользователя"
                    />
                  )}
                </label>
                <label className="space-y-1 sm:col-span-2">
                  <span className="text-xs font-medium">Комментарий</span>
                  <Textarea
                    value={draft.last_comment}
                    disabled={saveDisabled}
                    className="min-h-20"
                    onChange={(event) =>
                      onDraftChange({ last_comment: event.target.value })
                    }
                    placeholder="Что сделали или что нужно сделать"
                  />
                </label>
                <Button
                  disabled={saveDisabled}
                  className="min-h-10 sm:col-span-2"
                  onClick={onSave}
                >
                  <Save className="mr-1 h-4 w-4" />
                  {busy === rowKey ? "Сохраняем" : "Сохранить"}
                </Button>
              </div>
            ) : (
              <Alert>
                <Info className="h-4 w-4" />
                <AlertTitle>Статус менять нельзя</AlertTitle>
                <AlertDescription>
                  Эта задача пришла как сигнал. Исправьте данные в нужном разделе и запустите проверку.
                </AlertDescription>
              </Alert>
            )}
          </section>

          <section className="space-y-3 rounded-md border p-4">
            <div className="text-sm font-semibold">Проверка после исправления</div>
            <div className="text-sm text-muted-foreground">
              {action.recheck_rule || "После исправления запустите повторную проверку. Если проблема ушла, задача обновится."}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                disabled={!canRecheck}
                onClick={onRecheck}
              >
                <RefreshCw className="mr-1 h-4 w-4" />
                Перепроверить
              </Button>
              <Button asChild variant="outline">
                <Link to="/results">
                  Результаты
                  <ArrowRight className="ml-1 h-4 w-4" />
                </Link>
              </Button>
            </div>
            {recheckResult ? (
              <Alert className={recheckResult.status === "ok" ? "" : "border-destructive/40"}>
                <CheckCircle2 className="h-4 w-4" />
                <AlertTitle>
                  {recheckResult.status === "ok" ? "Проверка запущена" : "Не удалось проверить"}
                </AlertTitle>
                <AlertDescription>{recheckResult.message}</AlertDescription>
              </Alert>
            ) : null}
          </section>
        </div>
      </SheetContent>
    </ActionCenterTaskDrawer>
  );
}
