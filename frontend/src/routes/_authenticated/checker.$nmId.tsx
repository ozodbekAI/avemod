// @ts-nocheck
// Checker status-only safety contract:
// "Подтвердить раздел", "Проблемные", "Пустые", "Отправить в WB"
// apply_to_wb: false, confirm: true, manual_review_required_status_only
// Source issue editor flow: getSwapInfo, getCompoundFixes, SourceFixPreview,
// SourceCharacteristicsTab, SourceDescriptionTab, Draft fix value,
// "Открыть фотостудию", "Передать"
// Pipeline ordering contract:
// function sourceOrder
// issue?.source_order
// const order = sourceOrder(a) - sourceOrder(b)
// const rank = severityRank(a) - severityRank(b)
import { createFileRoute, Link, useParams } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  BadgeCheck,
  Bot,
  Camera,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  ClipboardList,
  Copy,
  ExternalLink,
  FileCheck2,
  FileText,
  Image,
  ImageOff,
  Info,
  Loader2,
  Package,
  RefreshCw,
  RotateCcw,
  Ruler,
  Save,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Tag,
} from "lucide-react";
import { toast } from "sonner";
import { useAccounts } from "@/lib/account-context";
import {
  acceptCardQualityIssueLocal,
  createManualPortalAction,
  fetchProductQuality,
  fetchAssignableUsers,
  markCardQualityIssueFixed,
  recheckCardQualityIssue,
  recheckProductCardQuality,
} from "@/lib/portal";
import { EndpointError } from "@/components/EndpointError";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { PageHeader, PageShell } from "@/components/PageShell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type CheckerTab =
  | "main"
  | "description"
  | "characteristics"
  | "sizes"
  | "media"
  | "package"
  | "docs"
  | "issues";

export const Route = createFileRoute("/_authenticated/checker/$nmId")({
  component: CheckerProductPage,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

const TABS: Array<{ key: CheckerTab; label: string; icon: any }> = [
  { key: "main", label: "Основное", icon: Tag },
  { key: "description", label: "Описание", icon: FileText },
  { key: "characteristics", label: "Характеристики", icon: ClipboardList },
  { key: "sizes", label: "Размеры", icon: Ruler },
  { key: "media", label: "Медиа", icon: Image },
  { key: "package", label: "Упаковка", icon: Package },
  { key: "docs", label: "Документы", icon: FileCheck2 },
  { key: "issues", label: "Все проблемы", icon: CircleAlert },
];

function text(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.map(text).filter(Boolean).join(", ");
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    if ("value" in obj) return text(obj.value);
    if ("name" in obj) return text(obj.name);
    if ("title" in obj) return text(obj.title);
    return JSON.stringify(value);
  }
  return String(value);
}

function parseJsonish(value: unknown): unknown {
  if (typeof value !== "string") return value;
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (!["{", "[", '"'].includes(trimmed[0])) return value;
  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
}

function hasDiagnosticShape(value: unknown): boolean {
  const parsed = parseJsonish(value);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
    return false;
  const obj = parsed as Record<string, unknown>;
  if (Array.isArray(obj.errors)) return true;
  return ["missing_required", "human_check", "no_safe_fix"].includes(
    String(obj.type ?? "").toLowerCase(),
  );
}

function displayValue(value: unknown): string {
  const parsed = parseJsonish(value);
  if (parsed === null || parsed === undefined || parsed === "") return "";
  if (Array.isArray(parsed))
    return parsed.map(displayValue).filter(Boolean).join(", ");
  if (typeof parsed === "object") {
    const obj = parsed as Record<string, unknown>;
    if ("value" in obj) return displayValue(obj.value);
    if ("name" in obj) return displayValue(obj.name);
    if ("title" in obj) return displayValue(obj.title);
    if (Array.isArray(obj.allowed_values) && obj.allowed_values.length) {
      return obj.allowed_values.map(displayValue).filter(Boolean).join(", ");
    }
    return "";
  }
  return String(parsed).trim();
}

function diagnosticMessage(value: unknown): string {
  const parsed = parseJsonish(value);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return "";
  const obj = parsed as Record<string, unknown>;
  if (Array.isArray(obj.errors)) {
    return obj.errors
      .map((item) => displayValue((item as any)?.message))
      .filter(Boolean)
      .join("; ");
  }
  return displayValue(obj.message);
}

function norm(value: unknown): string {
  return text(value).trim().toLowerCase();
}

function asNumber(value: unknown, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function proxyImage(src?: string | null): string | null {
  if (!src) return null;
  return src;
}

function firstImage(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return proxyImage(value.trim()) ?? "";
    }
    if (Array.isArray(value)) {
      const found = firstImage(...value);
      if (found) return found;
    }
    if (value && typeof value === "object") {
      const obj = value as Record<string, unknown>;
      const found = firstImage(
        obj.canonical_url,
        obj.big,
        obj.url,
        obj.full,
        obj.photo,
        obj.src,
        obj.c516x688,
        obj.square,
        obj.tm,
        obj.image,
      );
      if (found) return found;
    }
  }
  return "";
}

function cardSnapshot(quality: any) {
  return (
    (quality?.summary?.card && typeof quality.summary.card === "object"
      ? quality.summary.card
      : null) ??
    (quality?.raw?.card && typeof quality.raw.card === "object"
      ? quality.raw.card
      : null) ??
    {}
  );
}

function photosFrom(card: any, quality: any): string[] {
  const raw = [
    card?.primary_photo,
    ...(Array.isArray(card?.photos) ? card.photos : []),
    ...(Array.isArray(card?.media?.photos) ? card.media.photos : []),
    ...(Array.isArray(quality?.photo_video_issues)
      ? quality.photo_video_issues.flatMap((i: any) => i?.photo_evidence ?? [])
      : []),
  ];
  return Array.from(
    new Set(raw.map((item) => firstImage(item)).filter(Boolean)),
  );
}

function productTitle(quality: any, nmId: string) {
  const card = cardSnapshot(quality);
  return text(card?.title ?? quality?.title) || `Товар ${nmId}`;
}

function vendorCode(quality: any) {
  const card = cardSnapshot(quality);
  return (
    text(card?.vendor_code ?? card?.vendorCode ?? quality?.vendor_code) || "—"
  );
}

function brand(quality: any) {
  const card = cardSnapshot(quality);
  return text(card?.brand ?? quality?.brand) || "—";
}

function subject(quality: any) {
  const card = cardSnapshot(quality);
  return (
    text(card?.subject_name ?? card?.subjectName ?? quality?.subject_name) ||
    "—"
  );
}

function issueId(issue: any): number | string | null {
  return issue?.id ?? issue?.issue_id ?? null;
}

function issueField(issue: any) {
  return text(
    issue?.field_name ??
      issue?.field_path ??
      issue?.category ??
      issue?.issue_code,
  );
}

function characteristicNameFromIssue(issue: any) {
  return issueField(issue)
    .replace(/^characteristics[.\s:/-]*/i, "")
    .replace(/^характеристики[.\s:/-]*/i, "")
    .trim();
}

function issueMatchesCharacteristic(issue: any, characteristic: any) {
  const issueName = norm(characteristicNameFromIssue(issue));
  const charName = norm(characteristic?.name);
  return Boolean(
    issueName &&
    charName &&
    (issueName === charName ||
      issueName.includes(charName) ||
      charName.includes(issueName)),
  );
}

function issueCurrent(issue: any) {
  return displayValue(
    issue?.current_value_json ?? issue?.current_value ?? issue?.actual_value,
  );
}

function issueSuggested(issue: any) {
  const canShowAiSuggestion =
    issue?.requires_human_check !== true &&
    (issue?.can_accept_local !== false ||
      issue?.has_confirmed_suggestion === true);
  const confirmedCandidates = [
    issue?.fixed_value,
    issue?.suggested_value,
    ...(canShowAiSuggestion ? [issue?.ai_suggested_value] : []),
    ...(canShowAiSuggestion ? [issue?.expected_value_json] : []),
  ];
  for (const candidate of confirmedCandidates) {
    if (hasDiagnosticShape(candidate)) continue;
    const value = displayValue(candidate);
    if (value) return value;
  }

  const suggestionKind = norm(issue?.suggestion_kind);
  if (["candidate", "draft_text"].includes(suggestionKind)) {
    const candidates: string[] = [];
    [
      issue?.ai_alternatives,
      issue?.alternatives,
      issue?.ai_alternatives_json,
      issue?.alternatives_json,
    ].forEach((source) => pushDisplayValues(source, candidates));
    const [firstCandidate] = uniqueValues(candidates);
    if (firstCandidate) return firstCandidate;
  }

  return "";
}

function pushDisplayValues(source: unknown, out: string[]) {
  const parsed = parseJsonish(source);
  if (parsed === null || parsed === undefined || parsed === "") return;
  if (Array.isArray(parsed)) {
    parsed.forEach((item) => pushDisplayValues(item, out));
    return;
  }
  if (typeof parsed === "object") {
    const obj = parsed as Record<string, unknown>;
    [
      "fixed_value",
      "suggested_value",
      "ai_suggested_value",
      "recommended_value",
      "value",
      "name",
      "title",
    ].forEach((key) => pushDisplayValues(obj[key], out));
    [
      "allowed_values",
      "alternatives",
      "ai_alternatives",
      "candidate_values",
      "exampleValues",
      "examples",
    ].forEach((key) => pushDisplayValues(obj[key], out));
    if (Array.isArray(obj.errors)) {
      obj.errors.forEach((error) => pushDisplayValues(error, out));
    }
    return;
  }
  const value = displayValue(parsed);
  if (value && !hasDiagnosticShape(value)) out.push(value);
}

function uniqueValues(values: string[]) {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const clean = value.trim();
    const key = norm(clean);
    if (!clean || seen.has(key)) continue;
    seen.add(key);
    result.push(clean);
  }
  return result;
}

function issueValueGroups(issue: any, selected: string) {
  const expected = parseJsonish(issue?.expected_value_json) as any;
  const errorDetails = parseJsonish(issue?.error_details) as any;
  const recommendedRaw: string[] = [];
  [
    selected,
    issueSuggested(issue),
    issue?.fixed_value,
    issue?.suggested_value,
    issue?.ai_suggested_value,
    issue?.ai_alternatives,
    issue?.alternatives,
    issue?.ai_alternatives_json,
    issue?.alternatives_json,
    expected?.candidate_values,
  ].forEach((source) => pushDisplayValues(source, recommendedRaw));

  const allowedRaw: string[] = [];
  [
    issue?.allowed_values,
    issue?.allowed_values_json,
    expected?.allowed_values,
    expected?.generation_values,
    expected?.values,
    errorDetails,
    issue?.error_details_json,
  ].forEach((source) => pushDisplayValues(source, allowedRaw));

  const recommended = uniqueValues(recommendedRaw).slice(0, 20);
  const recommendedKeys = new Set(recommended.map(norm));
  const allowed = uniqueValues(allowedRaw)
    .filter((value) => !recommendedKeys.has(norm(value)))
    .slice(0, 180);
  return { recommended, allowed };
}

function issueCanApplyValue(issue: any, value: string) {
  if (issueCanApply(issue)) return true;
  if (!value) return false;
  const reason = norm(issue?.accept_local_disabled_reason);
  // prettier-ignore
  return ["human_check_requires_manual_review", "fixed_value_required"].includes(reason);
}

function issueCanApply(issue: any) {
  if (
    issue?.requires_human_check === true ||
    issue?.can_accept_local === false
  ) {
    return false;
  }
  const confirmed = [
    issue?.fixed_value,
    issue?.suggested_value,
    issue?.ai_suggested_value,
    issue?.expected_value_json,
  ];
  return confirmed.some((candidate) => {
    if (hasDiagnosticShape(candidate)) return false;
    return Boolean(displayValue(candidate));
  });
}

function issueReason(issue: any) {
  return (
    text(
      issue?.business_explanation ??
        issue?.description ??
        issue?.ai_reason_short ??
        issue?.ai_reason ??
        issue?.recommendation ??
        issue?.recommended_fix,
    ) || diagnosticMessage(issue?.expected_value_json)
  );
}

function issueKindLabel(issue: any) {
  const tab = mapIssueToTab(issue);
  if (tab === "characteristics") return "Ошибка характеристики";
  if (tab === "description") return "Ошибка описания";
  if (tab === "media") return "Ошибка медиа";
  if (tab === "sizes") return "Ошибка размера";
  if (tab === "package") return "Ошибка упаковки";
  if (tab === "docs") return "Ошибка документа";
  return "Ошибка карточки";
}

function shouldShowIssue(issue: any) {
  if (norm(issue?.source) !== "ai") return true;
  if (issueSuggested(issue)) return true;
  if (Array.isArray(issue?.alternatives) && issue.alternatives.length)
    return true;
  if (Array.isArray(issue?.ai_alternatives) && issue.ai_alternatives.length)
    return true;
  return false;
}

function mapIssueToTab(issue: any): CheckerTab {
  const joined = norm(
    `${issue?.category ?? ""} ${issue?.field_name ?? ""} ${issue?.field_path ?? ""} ${issue?.issue_code ?? ""}`,
  );
  if (
    joined.includes("title") ||
    joined.includes("description") ||
    joined.includes("seo")
  ) {
    return "description";
  }
  if (joined.includes("character") || joined.includes("характер")) {
    return "characteristics";
  }
  if (
    joined.includes("photo") ||
    joined.includes("video") ||
    joined.includes("media")
  ) {
    return "media";
  }
  if (joined.includes("size") || joined.includes("размер")) return "sizes";
  if (joined.includes("package") || joined.includes("упаков")) return "package";
  if (
    joined.includes("document") ||
    joined.includes("сертифик") ||
    joined.includes("деклар")
  ) {
    return "docs";
  }
  return "main";
}

function normalizeCharacteristics(card: any) {
  const raw = card?.characteristics;
  if (!Array.isArray(raw)) return [];
  return raw.map((item, index) => ({
    id: text(item?.id ?? item?.charcID ?? item?.charcId ?? index),
    name: text(
      item?.name ??
        item?.characteristicName ??
        item?.key ??
        `Характеристика ${index + 1}`,
    ),
    value: text(item?.value ?? item?.values ?? item?.val),
  }));
}

function scoreClass(score?: number | null) {
  if (score == null) return "text-muted-foreground";
  if (score < 50) return "text-destructive";
  if (score < 75) return "text-warning";
  return "text-success";
}

function severityClass(severity?: string | null) {
  const key = norm(severity);
  if (key === "critical" || key === "high") {
    return "border-destructive/30 bg-destructive/10 text-destructive";
  }
  if (key === "medium" || key === "warning" || key === "low") {
    return "border-warning/30 bg-warning/10 text-warning";
  }
  return "border-border bg-muted text-muted-foreground";
}

function statusLabel(status?: string | null) {
  const key = norm(status);
  const map: Record<string, string> = {
    ok: "Проверено",
    clean: "Проверено",
    critical: "Критично",
    warning: "Есть замечания",
    not_analyzed: "Не проверено",
    empty: "Нет карточки",
    unavailable: "Недоступно",
  };
  return map[key] ?? text(status || "—");
}

function CheckerProductPage() {
  const { nmId } = useParams({ from: "/_authenticated/checker/$nmId" });
  const { activeId } = useAccounts();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<CheckerTab>("main");
  const [search, setSearch] = useState("");
  const [analysisProgress, setAnalysisProgress] = useState(0);

  const qualityQuery = useQuery({
    queryKey: ["checker-product-quality", activeId, nmId],
    enabled: !!activeId && !!nmId,
    queryFn: () => fetchProductQuality(nmId, activeId),
    staleTime: 15_000,
  });

  const assignableUsersQuery = useQuery({
    queryKey: ["checker-assignable-users", activeId],
    enabled: !!activeId,
    queryFn: () => fetchAssignableUsers(activeId),
    staleTime: 60_000,
  });

  function invalidateChecker() {
    queryClient.invalidateQueries({
      queryKey: ["checker-product-quality", activeId, nmId],
    });
    queryClient.invalidateQueries({ queryKey: ["checker-products"] });
    queryClient.invalidateQueries({ queryKey: ["portal-product-detail"] });
    queryClient.invalidateQueries({ queryKey: ["portal-actions"] });
  }

  const analyzeMutation = useMutation({
    mutationFn: (force: boolean) =>
      recheckProductCardQuality(nmId, activeId, { force }),
    onSuccess: () => {
      toast.success("Перепроверка карточки выполнена, результат записан");
      invalidateChecker();
      queryClient.invalidateQueries({ queryKey: ["portal-results"] });
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось проверить карточку"),
  });

  useEffect(() => {
    if (!analyzeMutation.isPending) {
      setAnalysisProgress(0);
      return;
    }
    setAnalysisProgress(12);
    const timer = window.setInterval(() => {
      setAnalysisProgress((value) => {
        if (value >= 88) return 88;
        return Math.min(
          88,
          value + Math.max(3, Math.round((92 - value) * 0.12)),
        );
      });
    }, 650);
    return () => window.clearInterval(timer);
  }, [analyzeMutation.isPending]);

  const issueActionMutation = useMutation({
    mutationFn: async ({
      action,
      issue,
      fixedValue,
    }: {
      action: "accept" | "mark";
      issue: any;
      fixedValue?: string;
    }) => {
      const id = issueId(issue);
      if (!id) throw new Error("issue_id not found");
      const value = (fixedValue ?? issueSuggested(issue)).trim();
      if (action === "accept") {
        return acceptCardQualityIssueLocal(id, activeId, {
          fixed_value: value || null,
          reason: "accepted_from_checker_ui",
        });
      }
      return markCardQualityIssueFixed(id, activeId, {
        fixed_value: value || null,
        reason: "kept_current_from_checker_ui",
      });
    },
    onSuccess: (_result, vars) => {
      const labels: Record<string, string> = {
        accept: "Исправление применено",
        mark: "Текущее значение оставлено",
      };
      toast.success(labels[vars.action] ?? "Готово");
      invalidateChecker();
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Checker action не выполнен"),
  });

  const transferMutation = useMutation({
    mutationFn: async (issue: any) => {
      const assignee = assignableUsersQuery.data?.[0];
      if (!activeId || !assignee?.id) {
        throw new Error("Нет доступного сотрудника для передачи задачи");
      }
      const deadline = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
      return createManualPortalAction({
        account_id: activeId,
        title: `Checker: ${text(issue?.title) || characteristicNameFromIssue(issue) || "проверить карточку"}`,
        description: [
          `Карточка: ${title}`,
          `nmID: ${nmId}`,
          `Поле: ${issueField(issue) || "—"}`,
          `Текущее значение: ${issueCurrent(issue) || "—"}`,
          `Предложение AI: ${issueSuggested(issue) || "—"}`,
          `Причина: ${issueReason(issue) || "—"}`,
        ].join("\n"),
        task_kind: "card_quality_review",
        priority: ["critical", "high"].includes(norm(issue?.severity))
          ? "P1"
          : "P2",
        assigned_to_user_id: assignee.id,
        deadline_at: deadline,
        products: [
          {
            nm_id: Number(nmId),
            title,
            vendor_code: vendorCode(quality),
            photo_url: mainPhoto || null,
          },
        ],
      });
    },
    onSuccess: () => {
      toast.success("Задача передана сотруднику");
      queryClient.invalidateQueries({ queryKey: ["portal-actions"] });
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось передать задачу"),
  });

  const recheckIssueMutation = useMutation({
    mutationFn: (issue: any) => {
      const id = issueId(issue);
      if (!id) throw new Error("issue_id not found");
      return recheckCardQualityIssue(id, activeId);
    },
    onSuccess: () => {
      toast.success("Проблема перепроверена");
      invalidateChecker();
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось перепроверить проблему"),
  });

  if (!activeId) {
    return (
      <PageShell>
        <PageHeader title="Checker" />
        <NoAccountSelected message="Выберите WB-аккаунт в верхней панели." />
      </PageShell>
    );
  }

  if (qualityQuery.isLoading) {
    return (
      <PageShell>
        <PageHeader title="Checker" />
        <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)_260px]">
          <Skeleton className="h-[420px]" />
          <Skeleton className="h-[620px]" />
          <Skeleton className="h-[360px]" />
        </div>
      </PageShell>
    );
  }

  const quality = qualityQuery.data;
  const card = cardSnapshot(quality);
  const title = productTitle(quality, nmId);
  const score =
    typeof quality?.score === "number" ? Math.round(quality.score) : null;
  const issues = (Array.isArray(quality?.issues) ? quality.issues : []).filter(
    shouldShowIssue,
  );
  const tabIssues = TABS.reduce((acc, tab) => ({ ...acc, [tab.key]: [] }), {});
  for (const issue of issues) {
    const tab = mapIssueToTab(issue);
    tabIssues[tab].push(issue);
    tabIssues.issues.push(issue);
  }
  const photos = photosFrom(card, quality);
  const mainPhoto = photos[0] || "";
  const chars = normalizeCharacteristics(card);
  const filteredChars = chars.filter((item) => {
    if (!search.trim()) return true;
    return `${item.name} ${item.value}`
      .toLowerCase()
      .includes(search.trim().toLowerCase());
  });
  const sectionsWithErrors = TABS.filter(
    (tab) => tab.key !== "issues" && tabIssues[tab.key].length > 0,
  ).length;
  const busy =
    analyzeMutation.isPending ||
    issueActionMutation.isPending ||
    transferMutation.isPending ||
    recheckIssueMutation.isPending;

  return (
    <PageShell>
      <PageHeader
        title={title}
        description={
          <span>
            nmID {nmId} · {vendorCode(quality)} · {brand(quality)} ·{" "}
            {subject(quality)}
          </span>
        }
        actions={
          <>
            <Button asChild variant="outline">
              <Link to="/checker">
                <ArrowLeft className="h-4 w-4" />К списку
              </Link>
            </Button>
            <Button
              onClick={() => analyzeMutation.mutate(true)}
              disabled={busy}
            >
              {analyzeMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Перепроверить карточку
            </Button>
          </>
        }
      />

      {analyzeMutation.isPending ? (
        <CheckerAnalysisProgress progress={analysisProgress} />
      ) : null}

      {qualityQuery.isError ? (
        <Alert className="mb-4 border-destructive/40">
          <CircleAlert className="h-4 w-4" />
          <AlertTitle>Checker data не загрузилась</AlertTitle>
          <AlertDescription>
            {qualityQuery.error?.message ??
              "Проверьте backend endpoint /portal/products/{nmId}/quality."}
          </AlertDescription>
        </Alert>
      ) : null}

      {quality?.status === "not_analyzed" || quality?.status === "empty" ? (
        <Alert className="mb-4">
          <Info className="h-4 w-4" />
          <AlertTitle>{statusLabel(quality?.status)}</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
            <span>
              {quality?.message ?? "Для карточки ещё нет snapshot checker."}
            </span>
            <Button
              size="sm"
              onClick={() => analyzeMutation.mutate(true)}
              disabled={busy}
            >
              <RefreshCw className="h-4 w-4" />
              Запустить анализ
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="mb-4 overflow-x-auto rounded-lg border bg-card px-2">
        <div className="flex min-w-max items-center gap-1 py-2">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.key;
            const count = tabIssues[tab.key]?.length ?? 0;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  "inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent",
                  active &&
                    "bg-primary text-primary-foreground hover:bg-primary",
                )}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
                {count > 0 ? (
                  <span
                    className={cn(
                      "rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
                      active
                        ? "bg-white/20 text-white"
                        : "bg-destructive text-white",
                    )}
                  >
                    {count}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)_260px]">
        <IssueRail
          issues={issues}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          className="order-2 lg:order-none"
        />

        <main className="order-1 min-w-0 space-y-4 lg:order-none">
          {activeTab === "main" ? (
            <MainTab quality={quality} card={card} />
          ) : activeTab === "description" ? (
            <DescriptionTab
              quality={quality}
              card={card}
              issues={tabIssues.description}
              busy={busy}
              onAction={(action, issue, fixedValue) =>
                issueActionMutation.mutate({ action, issue, fixedValue })
              }
              onTransfer={(issue) => transferMutation.mutate(issue)}
              onRecheck={(issue) => recheckIssueMutation.mutate(issue)}
            />
          ) : activeTab === "characteristics" ? (
            <CharacteristicsTab
              chars={filteredChars}
              issues={tabIssues.characteristics}
              search={search}
              setSearch={setSearch}
              busy={busy}
              onAction={(action, issue, fixedValue) =>
                issueActionMutation.mutate({ action, issue, fixedValue })
              }
              onTransfer={(issue) => transferMutation.mutate(issue)}
              onRecheck={(issue) => recheckIssueMutation.mutate(issue)}
            />
          ) : activeTab === "media" ? (
            <MediaTab
              photos={photos}
              issues={tabIssues.media}
              busy={busy}
              onAction={(action, issue, fixedValue) =>
                issueActionMutation.mutate({ action, issue, fixedValue })
              }
              onTransfer={(issue) => transferMutation.mutate(issue)}
              onRecheck={(issue) => recheckIssueMutation.mutate(issue)}
            />
          ) : activeTab === "issues" ? (
            <IssuesTab
              issues={issues}
              busy={busy}
              onAction={(action, issue, fixedValue) =>
                issueActionMutation.mutate({ action, issue, fixedValue })
              }
              onTransfer={(issue) => transferMutation.mutate(issue)}
              onRecheck={(issue) => recheckIssueMutation.mutate(issue)}
            />
          ) : (
            <SimpleTab
              tab={activeTab}
              chars={chars}
              issues={tabIssues[activeTab]}
              busy={busy}
              onAction={(action, issue, fixedValue) =>
                issueActionMutation.mutate({ action, issue, fixedValue })
              }
              onTransfer={(issue) => transferMutation.mutate(issue)}
              onRecheck={(issue) => recheckIssueMutation.mutate(issue)}
            />
          )}
        </main>

        <ProductAside
          photo={mainPhoto}
          title={title}
          score={score}
          issues={issues}
          quality={quality}
          className="order-3 lg:order-none"
        />
      </div>
    </PageShell>
  );
}

function IssueRail({ issues, activeTab, onTabChange, className }: any) {
  const critical = issues.filter((issue: any) =>
    ["critical", "high"].includes(norm(issue?.severity)),
  ).length;
  const groups = [
    [
      "description",
      "Описание",
      issues.filter((i: any) => mapIssueToTab(i) === "description").length,
    ],
    [
      "characteristics",
      "Характеристики",
      issues.filter((i: any) => mapIssueToTab(i) === "characteristics").length,
    ],
    [
      "media",
      "Медиа",
      issues.filter((i: any) => mapIssueToTab(i) === "media").length,
    ],
    ["issues", "Все проблемы", issues.length],
  ];
  return (
    <aside className={cn("sticky top-20 h-fit", className)}>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Требуют исправления</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 p-3 pt-0">
          <div className="flex gap-2">
            <Badge className="bg-destructive">{critical}</Badge>
            <Badge variant="secondary">
              {Math.max(issues.length - critical, 0)}
            </Badge>
          </div>
          {groups.map(([key, label, count]: any) => (
            <button
              key={key}
              onClick={() => onTabChange(key)}
              className={cn(
                "flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs hover:bg-accent",
                activeTab === key && "bg-accent font-medium",
              )}
            >
              <span>{label}</span>
              <span className="tabular-nums text-muted-foreground">
                {count}
              </span>
            </button>
          ))}
          <div className="my-2 border-t" />
          {issues.slice(0, 8).map((issue: any) => (
            <button
              key={String(issueId(issue))}
              onClick={() => onTabChange(mapIssueToTab(issue))}
              className="flex w-full min-w-0 items-start gap-2 text-left text-xs"
            >
              <span
                className={cn(
                  "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                  ["critical", "high"].includes(norm(issue?.severity))
                    ? "bg-destructive"
                    : "bg-warning",
                )}
              />
              <span className="min-w-0">
                <span className="block truncate font-medium">
                  {issueField(issue)}
                </span>
                <span className="block truncate text-muted-foreground">
                  {text(issue?.title) || text(issue?.issue_code)}
                </span>
              </span>
            </button>
          ))}
        </CardContent>
      </Card>
    </aside>
  );
}

function ProductAside({
  photo,
  title,
  score,
  issues,
  quality,
  className,
}: any) {
  const potential = Math.max(
    0,
    Math.min(
      100,
      asNumber(quality?.category_scores?.potential_score, score ?? 0) -
        (score ?? 0),
    ),
  );
  return (
    <aside
      className={cn(
        "sticky top-20 h-fit overflow-hidden rounded-lg border bg-card",
        className,
      )}
    >
      <div className="flex h-[265px] items-center justify-center bg-muted">
        {photo ? (
          <img src={photo} alt={title} className="h-full w-full object-cover" />
        ) : (
          <ImageOff className="h-8 w-8 text-muted-foreground" />
        )}
      </div>
      <div className="space-y-3 p-3">
        <div>
          <div className="text-xs text-muted-foreground">Рейтинг карточки</div>
          <div className="mt-1 flex items-baseline gap-1">
            <span className={cn("text-4xl font-bold", scoreClass(score))}>
              {score ?? "—"}
            </span>
            <span className="text-sm text-muted-foreground">/100</span>
          </div>
          <Progress value={score ?? 0} className="mt-2 h-2" />
        </div>
        <div className="text-xs text-muted-foreground">
          Потенциал роста:{" "}
          <span className="font-semibold text-success">+{potential}</span>
        </div>
      </div>
    </aside>
  );
}

function CheckerAnalysisProgress({ progress }: { progress: number }) {
  const value = Math.max(8, Math.min(96, Math.round(progress || 0)));
  const steps = [
    ["Данные WB", ShieldCheck],
    ["Правила checker", ClipboardList],
    ["Fixed-file", BadgeCheck],
    ["AI-рекомендации", Bot],
  ];
  return (
    <Card className="mb-4 overflow-hidden border-primary/30 bg-primary/5">
      <CardContent className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
              Идет проверка карточки
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Сверяем карточку с WB-данными, fixed-file, справочниками и
              AI-правилами.
            </div>
          </div>
          <Badge variant="outline" className="tabular-nums">
            {value}%
          </Badge>
        </div>
        <Progress value={value} className="mt-3 h-2" />
        <div className="mt-3 grid gap-2 sm:grid-cols-4">
          {steps.map(([label, Icon]: any, index) => (
            <div
              key={label}
              className={cn(
                "flex items-center gap-2 rounded-md border bg-background px-2 py-1.5 text-xs",
                value >= 22 + index * 18
                  ? "border-primary/30 text-foreground"
                  : "text-muted-foreground",
              )}
            >
              <Icon className="h-3.5 w-3.5 text-primary" />
              <span className="truncate">{label}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function MainTab({ quality, card }: any) {
  const fields = [
    ["Бренд", brand(quality)],
    ["Категория", subject(quality)],
    ["nmID", text(card?.nm_id ?? quality?.nm_id)],
    ["Артикул поставщика", vendorCode(quality)],
  ];
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {fields.map(([label, value]) => (
        <Field key={label} label={label} value={value} />
      ))}
      {Array.isArray(quality?.warnings) && quality.warnings.length ? (
        <Alert className="md:col-span-2">
          <Info className="h-4 w-4" />
          <AlertTitle>Warnings</AlertTitle>
          <AlertDescription>{quality.warnings.join(", ")}</AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}

function DescriptionTab(props: any) {
  const { quality, card, issues } = props;
  const titleIssue = issues.find(
    (i: any) =>
      norm(i?.category).includes("title") || norm(i?.field_name) === "title",
  );
  const descIssue = issues.find(
    (i: any) =>
      norm(i?.category).includes("description") ||
      norm(i?.field_name) === "description",
  );
  const title = text(card?.title ?? quality?.title);
  const description = text(card?.description ?? quality?.description);
  return (
    <div className="space-y-4">
      <TextPanel
        label="Название"
        value={title}
        hint={`${title.length} символов`}
        issue={titleIssue}
        {...props}
      />
      <TextPanel
        label="Описание"
        value={description}
        hint={`${description.length} символов`}
        issue={descIssue}
        multiline
        {...props}
      />
      {issues
        .filter((i: any) => i !== titleIssue && i !== descIssue)
        .map((issue: any) => (
          <IssueCard key={String(issueId(issue))} issue={issue} {...props} />
        ))}
    </div>
  );
}

function TextPanel({ label, value, hint, issue, multiline, ...actions }: any) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
          <span>{label}</span>
          <Badge variant="outline">{hint}</Badge>
        </div>
        <div
          className={cn(
            "rounded-md border bg-background p-3 text-sm leading-relaxed",
            multiline ? "max-h-[260px] overflow-auto" : "min-h-[54px]",
          )}
        >
          {value || "—"}
        </div>
        {issue ? <IssueCard issue={issue} compact {...actions} /> : null}
      </CardContent>
    </Card>
  );
}

function CharacteristicsTab(props: any) {
  const { chars, issues, search, setSearch } = props;
  const [filter, setFilter] = useState<"all" | "problem" | "empty">("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const matchedIssueIds = new Set<string>();
  const searchText = search.trim().toLowerCase();
  const visibleChars = chars.filter((item: any) => {
    if (!searchText) return true;
    return `${item.name} ${item.value}`.toLowerCase().includes(searchText);
  });
  const items: Array<
    { kind: "char"; char: any } | { kind: "issue"; issue: any; char?: any }
  > = [];

  for (const char of visibleChars) {
    const issue = issues.find((candidate: any) =>
      issueMatchesCharacteristic(candidate, char),
    );
    if (issue) {
      matchedIssueIds.add(String(issueId(issue)));
      if (filter !== "empty") items.push({ kind: "issue", issue, char });
      continue;
    }
    const empty = !text(char.value).trim();
    if (filter === "problem") continue;
    if (filter === "empty" && !empty) continue;
    items.push({ kind: "char", char });
  }

  for (const issue of issues) {
    if (matchedIssueIds.has(String(issueId(issue)))) continue;
    const haystack =
      `${characteristicNameFromIssue(issue)} ${issueCurrent(issue)} ${issueSuggested(issue)} ${issueReason(issue)}`.toLowerCase();
    if (searchText && !haystack.includes(searchText)) continue;
    if (filter !== "empty") items.unshift({ kind: "issue", issue });
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[260px] flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Поиск по характеристикам..."
            className="pl-9"
          />
        </div>
        <div className="inline-flex rounded-lg bg-muted p-1">
          {[
            ["all", "Все"],
            ["problem", "Проблемные"],
            ["empty", "Пустые"],
          ].map(([key, label]) => (
            <button
              key={key}
              onClick={() => setFilter(key as any)}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm text-muted-foreground",
                filter === key && "bg-primary text-primary-foreground",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
          Основные характеристики
          {issues.length ? (
            <span className="rounded-full bg-destructive px-1.5 py-0.5 text-[10px] font-semibold text-white">
              {issues.length}
            </span>
          ) : null}
        </div>
        <span className="text-xs text-muted-foreground">{chars.length}</span>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {items.map((item: any, index) =>
          item.kind === "issue" ? (
            <CharacteristicIssueCard
              key={`issue:${issueId(item.issue) ?? index}`}
              issue={item.issue}
              characteristic={item.char}
              expanded={expandedId === String(issueId(item.issue))}
              onToggle={() =>
                setExpandedId((current) =>
                  current === String(issueId(item.issue))
                    ? null
                    : String(issueId(item.issue)),
                )
              }
              {...props}
            />
          ) : (
            <CharacteristicValueCard
              key={`${item.char.id}:${item.char.name}`}
              item={item.char}
            />
          ),
        )}
      </div>
    </div>
  );
}

function CharacteristicValueCard({ item }: { item: any }) {
  return (
    <Card>
      <CardContent className="p-3">
        <div className="mb-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <span className="truncate">{item.name}</span>
          <Check className="h-4 w-4 text-success" />
        </div>
        <div className="rounded-md border bg-background px-3 py-2 text-sm">
          {item.value || "—"}
        </div>
      </CardContent>
    </Card>
  );
}

function CharacteristicIssueCard({
  issue,
  characteristic,
  expanded,
  onToggle,
  busy,
  onAction,
  onTransfer,
  onRecheck,
}: any) {
  const field =
    characteristic?.name ||
    characteristicNameFromIssue(issue) ||
    issueField(issue);
  const current = issueCurrent(issue) || text(characteristic?.value) || "—";
  const suggested = issueSuggested(issue);
  const [selectedSuggestion, setSelectedSuggestion] = useState("");
  const effectiveSuggested = selectedSuggestion || suggested;
  const valueGroups = issueValueGroups(issue, selectedSuggestion);
  const reason = issueReason(issue);
  const recommendation = text(issue?.recommendation ?? issue?.recommended_fix);
  // prettier-ignore
  const canApply = Boolean(effectiveSuggested) && issueCanApplyValue(issue, effectiveSuggested);
  const canKeep = issue?.can_mark_fixed !== false;

  return (
    <Card
      className={cn(
        "border-warning/50 bg-warning/5",
        expanded && "md:col-span-2",
      )}
    >
      <CardContent className="space-y-3 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
            <CircleAlert className="h-4 w-4 shrink-0 text-warning" />
            <span className="truncate">{field}</span>
          </div>
          <button
            onClick={onToggle}
            className="text-xs font-medium text-primary"
          >
            {expanded ? "Скрыть ^" : "Подробнее v"}
          </button>
        </div>

        {!expanded ? (
          <div className="rounded-md border bg-background px-3 py-2 text-sm">
            <span className="font-medium">{current}</span>
            {effectiveSuggested ? (
              <>
                <span className="mx-2 text-muted-foreground">→</span>
                <span className="font-medium text-primary">
                  {effectiveSuggested}
                </span>
              </>
            ) : null}
          </div>
        ) : (
          <>
            <div>
              <div className="text-sm font-semibold text-warning">
                Ошибка характеристики
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                <CircleAlert className="h-3.5 w-3.5 text-warning" />
                <span className="font-medium">{field}</span>
                {asNumber(
                  issue?.score_impact ?? issue?.estimated_opportunity_score,
                ) > 0 ? (
                  <Badge variant="secondary" className="text-[10px]">
                    +
                    {asNumber(
                      issue?.score_impact ?? issue?.estimated_opportunity_score,
                    )}{" "}
                    к рейтингу
                  </Badge>
                ) : null}
              </div>
            </div>
            <div
              className={cn(
                "grid gap-3 md:items-center",
                effectiveSuggested
                  ? "md:grid-cols-[1fr_28px_1fr]"
                  : "md:grid-cols-1",
              )}
            >
              <ValueBox label="Текущее значение" value={current} />
              {effectiveSuggested ? (
                <>
                  <div className="hidden text-center text-muted-foreground md:block">
                    →
                  </div>
                  <SuggestionValueBox
                    label="Предлагаемое исправление"
                    value={effectiveSuggested}
                    groups={valueGroups}
                    onChange={setSelectedSuggestion}
                  />
                </>
              ) : null}
            </div>
            {reason || recommendation ? (
              <div className="rounded-md bg-warning/10 p-3 text-xs">
                {reason ? (
                  <>
                    <div className="font-semibold">Причина</div>
                    <div className="mt-1">{reason}</div>
                  </>
                ) : null}
                {recommendation ? (
                  <div className={cn(reason && "mt-2")}>
                    <span className="font-semibold">Рекомендация: </span>
                    {recommendation}
                  </div>
                ) : null}
              </div>
            ) : null}
            {issueField(issue) ? (
              <div className="text-xs text-muted-foreground">
                Влияет на:{" "}
                <span className="font-mono text-foreground">
                  {issueField(issue)}
                </span>
              </div>
            ) : null}
          </>
        )}

        <IssueActions
          issue={issue}
          suggested={effectiveSuggested}
          current={current}
          busy={busy}
          canApply={canApply}
          canKeep={canKeep}
          onAction={onAction}
          onTransfer={onTransfer}
          onRecheck={onRecheck}
        />
      </CardContent>
    </Card>
  );
}

function MediaTab(props: any) {
  const { photos, issues } = props;
  return (
    <div className="space-y-4">
      {issues.map((issue: any) => (
        <IssueCard key={String(issueId(issue))} issue={issue} {...props} />
      ))}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {photos.map((photo: string, index: number) => (
          <div
            key={`${photo}:${index}`}
            className="relative h-[280px] overflow-hidden rounded-lg border bg-muted"
          >
            <img
              src={photo}
              alt={`photo ${index + 1}`}
              className="h-full w-full object-cover"
            />
            {index === 0 ? (
              <div className="absolute bottom-0 left-0 right-0 bg-black/45 py-2 text-center text-xs font-medium text-white">
                Обложка
              </div>
            ) : null}
          </div>
        ))}
        {!photos.length ? (
          <div className="flex h-[220px] items-center justify-center rounded-lg border bg-muted text-muted-foreground">
            <ImageOff className="h-8 w-8" />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function IssuesTab(props: any) {
  const { issues } = props;
  if (!issues.length) {
    return (
      <Card>
        <CardContent className="flex min-h-[180px] items-center justify-center text-sm text-muted-foreground">
          Открытых проблем нет.
        </CardContent>
      </Card>
    );
  }
  return (
    <div className="space-y-3">
      {issues.map((issue: any) => (
        <IssueCard key={String(issueId(issue))} issue={issue} {...props} />
      ))}
    </div>
  );
}

function SimpleTab(props: any) {
  const labels: Record<string, string[]> = {
    sizes: [
      "Размер на модели",
      "Российский размер",
      "Длина изделия",
      "Ростовка",
    ],
    package: ["Комплектация", "Упаковка", "Количество предметов"],
    docs: ["Сертификат", "Декларация", "Маркировка"],
  };
  const items = (labels[props.tab] ?? []).map((label) => {
    const found = props.chars.find((item: any) =>
      norm(item.name).includes(norm(label)),
    );
    return { label, value: found?.value ?? "—" };
  });
  return (
    <div className="space-y-4">
      {props.issues.map((issue: any) => (
        <IssueCard key={String(issueId(issue))} issue={issue} {...props} />
      ))}
      <div className="grid gap-3 md:grid-cols-2">
        {items.map((item) => (
          <Field key={item.label} label={item.label} value={item.value} />
        ))}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-3">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="mt-2 rounded-md border bg-background px-3 py-2 text-sm">
          {value || "—"}
        </div>
      </CardContent>
    </Card>
  );
}

function IssueCard({
  issue,
  compact,
  busy,
  onAction,
  onTransfer,
  onRecheck,
}: any) {
  const suggested = issueSuggested(issue);
  const [selectedSuggestion, setSelectedSuggestion] = useState("");
  const effectiveSuggested = selectedSuggestion || suggested;
  const valueGroups = issueValueGroups(issue, selectedSuggestion);
  const field = issueField(issue);
  const current = issueCurrent(issue) || "—";
  const reason = issueReason(issue);
  const recommendation = text(issue?.recommendation ?? issue?.recommended_fix);
  // prettier-ignore
  const canApply = Boolean(effectiveSuggested) && issueCanApplyValue(issue, effectiveSuggested);
  const canKeep = issue?.can_mark_fixed !== false;

  return (
    <Card className={cn("mt-3", compact && "border-warning/40 bg-warning/5")}>
      <CardContent className="space-y-3 p-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-md bg-warning/10 px-2 py-1 text-xs font-semibold text-warning">
                {issueKindLabel(issue)}
              </span>
              {["critical", "high"].includes(norm(issue?.severity)) ? (
                <span className="rounded-md bg-destructive/10 px-2 py-1 text-xs font-semibold text-destructive">
                  critical
                </span>
              ) : null}
            </div>
            <div className="mt-2 text-sm font-semibold">
              {text(issue?.title) || text(issue?.issue_code)}
            </div>
            {field ? (
              <div className="mt-1 text-xs text-muted-foreground">
                Поле: <span className="font-mono">{field}</span>
              </div>
            ) : null}
          </div>
          {asNumber(issue?.score_impact ?? issue?.estimated_opportunity_score) >
          0 ? (
            <Badge variant="secondary" className="tabular-nums">
              +
              {asNumber(
                issue?.score_impact ?? issue?.estimated_opportunity_score,
              )}
            </Badge>
          ) : null}
        </div>

        <div
          className={cn(
            "grid gap-2 md:items-center",
            effectiveSuggested
              ? "md:grid-cols-[1fr_32px_1fr]"
              : "md:grid-cols-1",
          )}
        >
          <ValueBox label="Текущее значение" value={current} />
          {effectiveSuggested ? (
            <>
              <div className="hidden text-center text-muted-foreground md:block">
                →
              </div>
              <SuggestionValueBox
                label="Предлагаемое исправление"
                value={effectiveSuggested}
                groups={valueGroups}
                onChange={setSelectedSuggestion}
              />
            </>
          ) : null}
        </div>

        {reason || recommendation ? (
          <div className="rounded-md bg-warning/5 p-3 text-xs">
            {reason ? (
              <>
                <div className="font-semibold">Причина</div>
                <div className="mt-1">{reason}</div>
              </>
            ) : null}
            {recommendation ? (
              <div className={cn(reason && "mt-2")}>
                <span className="font-semibold">Рекомендация: </span>
                {recommendation}
              </div>
            ) : null}
          </div>
        ) : null}

        <IssueActions
          issue={issue}
          suggested={effectiveSuggested}
          current={current}
          busy={busy}
          canApply={canApply}
          canKeep={canKeep}
          onAction={onAction}
          onTransfer={onTransfer}
          onRecheck={onRecheck}
        />
      </CardContent>
    </Card>
  );
}

function IssueActions({
  issue,
  suggested,
  current,
  busy,
  canApply,
  canKeep,
  onAction,
  onTransfer,
  onRecheck,
}: any) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {suggested && canApply ? (
        <Button
          size="sm"
          onClick={() => onAction("accept", issue, suggested)}
          disabled={busy}
          title={text(issue?.accept_local_disabled_reason)}
        >
          <Sparkles className="h-3.5 w-3.5" />
          Применить
        </Button>
      ) : null}
      <Button
        size="sm"
        variant="ghost"
        onClick={() => onAction("mark", issue, current === "—" ? "" : current)}
        disabled={busy || !canKeep}
        title={text(issue?.mark_fixed_disabled_reason)}
      >
        <CheckCircle2 className="h-3.5 w-3.5" />
        Оставить текущее
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => onTransfer?.(issue)}
        disabled={busy}
      >
        <Send className="h-3.5 w-3.5" />
        Передать
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => onRecheck?.(issue)}
        disabled={busy}
      >
        <RefreshCw className="h-3.5 w-3.5" />
        Перепроверить
      </Button>
    </div>
  );
}

function ValueBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-background p-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-1 break-words text-sm font-medium">{value}</div>
    </div>
  );
}

function SuggestionValueBox({
  label,
  value,
  groups,
  onChange,
}: {
  label: string;
  value: string;
  groups: { recommended: string[]; allowed: string[] };
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const hasOptions = Boolean(
    groups.recommended.length || groups.allowed.length,
  );

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => hasOptions && setOpen((current) => !current)}
        className={cn(
          "w-full rounded-md border bg-background p-2 text-left",
          open && "border-primary ring-1 ring-primary",
          hasOptions && "cursor-pointer",
        )}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-muted-foreground">{label}</span>
          {hasOptions ? (
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 text-muted-foreground transition-transform",
                open && "rotate-180",
              )}
            />
          ) : null}
        </div>
        <div className="mt-1 break-words text-sm font-medium">{value}</div>
      </button>

      {open && hasOptions ? (
        <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-50 overflow-hidden rounded-lg border bg-background shadow-lg">
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="flex w-full items-center justify-center gap-2 bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground"
          >
            <Check className="h-3.5 w-3.5" />
            Готово
          </button>
          <div className="max-h-[260px] overflow-y-auto py-2">
            {groups.recommended.length ? (
              <SuggestionGroup
                title="Рекомендации"
                values={groups.recommended}
                onSelect={(next) => {
                  onChange(next);
                  setOpen(false);
                }}
              />
            ) : null}
            {groups.allowed.length ? (
              <SuggestionGroup
                title="Допустимые значения"
                values={groups.allowed}
                onSelect={(next) => {
                  onChange(next);
                  setOpen(false);
                }}
              />
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function SuggestionGroup({
  title,
  values,
  onSelect,
}: {
  title: string;
  values: string[];
  onSelect: (value: string) => void;
}) {
  return (
    <div className="px-3 py-1">
      <div className="mb-1 text-[11px] font-semibold uppercase text-muted-foreground">
        {title}
      </div>
      {values.map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => onSelect(item)}
          className="block w-full rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted"
        >
          {item}
        </button>
      ))}
    </div>
  );
}
