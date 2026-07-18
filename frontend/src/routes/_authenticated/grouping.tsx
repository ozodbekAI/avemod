// @ts-nocheck
import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  Check,
  Clock3,
  Eye,
  FlaskConical,
  Info,
  Link2,
  Loader2,
  PackageOpen,
  Play,
  RefreshCw,
  Search,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { EndpointError } from "@/components/EndpointError";
import { PageHeader, PageShell } from "@/components/PageShell";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  fetchPortalActions,
  previewGrouping,
  updateGroupingCandidateStatus,
} from "@/lib/portal";
import { useModuleStatus } from "@/lib/modules-health";
import { useAccounts } from "@/lib/account-context";
import { routeSearchText } from "@/lib/action-center-routing";

export const Route = createFileRoute("/_authenticated/grouping")({
  validateSearch: (search: Record<string, unknown>): { nm_id?: string } => {
    const nmId = normalizeRouteNmId(search.nm_id);
    return nmId ? { nm_id: nmId } : {};
  },
  component: GroupingPage,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

const PAGE_SIZE = 30;

function normalizeRouteNmId(value: unknown): string {
  return routeSearchText(value)?.replace(/[^\d]/g, "") ?? "";
}

const STATUS_LABEL: Record<string, string> = {
  beta: "Beta",
  ok: "Готово",
  empty: "Нет рекомендаций",
  running: "Идёт анализ",
  partial: "Частично",
  failed: "Ошибка",
  not_analyzed: "Не анализировалось",
  disabled: "Отключён",
  unavailable: "Недоступен",
  not_configured: "Не настроен",
};

type BusyKey = "run" | "refresh" | "export";

type GroupingProfile = {
  key: string;
  name: string;
  description: string;
  scenario:
    | "article_family"
    | "imt_id_validation"
    | "variant_candidate"
    | "duplicate_candidate";
  tone: "primary" | "success" | "warning" | "info";
  config: GroupingConfig;
};

type GroupingConfig = {
  color_mode: string;
  minimum_confidence: number;
  maximum_risk: number;
  max_cards_in_group: number;
  same_brand_required: boolean;
  same_subject_required: boolean;
  complete_article_as_unit: boolean;
  diversity_limit: number;
};

type JsonRecord = Record<string, unknown>;

type PortalActionLike = {
  source_module?: string | null;
  source_id?: string | number | null;
  status?: string | null;
  payload?: JsonRecord | null;
};

type ModuleStatusLike = {
  status?: string | null;
  message?: string | null;
  beta?: boolean;
  last_run_id?: number | string | null;
  last_success_at?: string | null;
  unique_products_analyzed?: number | null;
  eligible_products?: number | null;
};

type PreviewLike = {
  summary?: JsonRecord;
  recommendations?: unknown[];
  raw?: JsonRecord;
};

type Recommendation = {
  id?: number | string;
  candidate_id?: number | string;
  candidate_group_id?: string;
  candidate_key?: string;
  scenario?: string;
  candidate_type?: string;
  nm_ids?: number[];
  anchor_nm_id?: number;
  confidence?: number;
  risk_level?: string;
  risk_score?: number;
  reasons?: string[];
  risk_reasons?: string[];
  conflicts?: string[];
  evidence?: JsonRecord;
  status?: string;
  auto_merge_enabled?: boolean;
  review_needed?: boolean;
  action?: PortalActionLike;
  preview_payload?: JsonRecord;
};

type ProductInfo = {
  nm_id?: number;
  title?: string;
  brand?: string;
  subject?: string;
  vendor_code?: string;
};

const DEFAULT_CONFIG: GroupingConfig = {
  color_mode: "SAME_COLOR_PRIORITY",
  minimum_confidence: 0.55,
  maximum_risk: 0.65,
  max_cards_in_group: 20,
  same_brand_required: true,
  same_subject_required: true,
  complete_article_as_unit: false,
  diversity_limit: 8,
};

const PROFILES: GroupingProfile[] = [
  {
    key: "article_family",
    name: "Семейство артикула",
    description:
      "Базовый режим: ищет карточки одной модели по бренду, предмету и ядру артикула. Подходит для ежедневной проверки.",
    scenario: "article_family",
    tone: "primary",
    config: DEFAULT_CONFIG,
  },
  {
    key: "imt_id_validation",
    name: "Проверка IMT",
    description:
      "Проверяет семейства по существующему WB imt_id и показывает наиболее безопасные совпадения.",
    scenario: "imt_id_validation",
    tone: "info",
    config: { ...DEFAULT_CONFIG, minimum_confidence: 0.6, maximum_risk: 0.55 },
  },
  {
    key: "strict_family",
    name: "Строгий режим",
    description:
      "Осторожный профиль для ручной проверки только самых очевидных кандидатов.",
    scenario: "article_family",
    tone: "success",
    config: {
      ...DEFAULT_CONFIG,
      minimum_confidence: 0.75,
      maximum_risk: 0.35,
      diversity_limit: 4,
    },
  },
];

function GroupingPage() {
  const { activeId } = useAccounts();
  const qc = useQueryClient();
  const moduleStatus = useModuleStatus("grouping") as ModuleStatusLike;
  const routeSearch = Route.useSearch();
  const routeNmId = normalizeRouteNmId(routeSearch.nm_id);
  const routeNmIdNumber = routeNmId ? Number(routeNmId) : null;
  const scopedActionQuery =
    routeNmIdNumber && Number.isFinite(routeNmIdNumber)
      ? { nm_id: routeNmIdNumber }
      : {};
  const [nmId, setNmId] = useState(routeNmId);
  const [search, setSearch] = useState(routeNmId);
  const [riskFilter, setRiskFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("active");
  const [profileKey, setProfileKey] = useState(PROFILES[0].key);
  const [showConfig, setShowConfig] = useState(false);
  const [preview, setPreview] = useState<PreviewLike | null>(null);
  const [selected, setSelected] = useState<Recommendation | null>(null);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState<Record<BusyKey, boolean>>({
    run: false,
    refresh: false,
    export: false,
  });

  useEffect(() => {
    if (!routeNmId) return;
    setNmId(routeNmId);
    setSearch(routeNmId);
    setPage(1);
  }, [routeNmId]);

  const activeProfile =
    PROFILES.find((item) => item.key === profileKey) ?? PROFILES[0];
  const statusKey = String(moduleStatus.status ?? "not_analyzed").toLowerCase();
  const canRun = !["disabled", "unavailable"].includes(statusKey);
  const trimmedNmId = nmId.trim();
  const nmIdIsValid = !trimmedNmId || /^\d+$/.test(trimmedNmId);

  const actionsQ = useQuery({
    queryKey: ["portal", "grouping", "actions", activeId, routeNmId],
    queryFn: () =>
      fetchPortalActions(activeId, {
        source_module: ["grouping"],
        limit: 100,
        ...scopedActionQuery,
      }),
    enabled: !!activeId,
    staleTime: 60_000,
  });

  const runMut = useMutation({
    mutationFn: () =>
      previewGrouping(activeId, {
        nm_id: trimmedNmId ? trimmedNmId : null,
        preset_key: activeProfile.scenario,
        custom_config: {
          scenario: activeProfile.scenario,
          grouping_v2_profile: activeProfile.key,
          recommendation_config: activeProfile.config,
        },
      }),
    onMutate: () => setBusy((prev) => ({ ...prev, run: true })),
    onSuccess: (data) => {
      setPreview(data);
      setSelected(null);
      setPage(1);
      toast.success("Анализ группировки завершён");
      qc.invalidateQueries({
        queryKey: ["portal", "grouping", "actions", activeId],
      });
      qc.invalidateQueries({
        queryKey: ["portal", "modules-health", activeId],
      });
    },
    onError: (e: unknown) =>
      toast.error(errorMessage(e, "Не удалось запустить анализ")),
    onSettled: () => setBusy((prev) => ({ ...prev, run: false })),
  });

  const reviewMut = useMutation({
    mutationFn: ({
      id,
      status: nextStatus,
    }: {
      id: number | string;
      status: "accepted" | "rejected" | "postponed";
    }) =>
      updateGroupingCandidateStatus(id, activeId, {
        status: nextStatus,
        reason: "seller_portal_grouping_review",
      }),
    onSuccess: (data) => {
      setPreview((prev) => patchPreviewCandidate(prev, data));
      setSelected((prev) => patchSelectedCandidate(prev, data));
      toast.success("Статус рекомендации обновлён");
      qc.invalidateQueries({
        queryKey: ["portal", "grouping", "actions", activeId],
      });
      qc.invalidateQueries({
        queryKey: ["portal", "modules-health", activeId],
      });
    },
    onError: (e: unknown) =>
      toast.error(errorMessage(e, "Не удалось обновить статус")),
  });

  const recommendations = useMemo(() => {
    const localRecommendations = Array.isArray(preview?.recommendations)
      ? preview.recommendations
      : [];
    if (localRecommendations.length)
      return localRecommendations.map(normalizeRecommendation);
    const actionItems = normalizeActionItems(actionsQ.data);
    return actionItems
      .filter(
        (item) =>
          String(item?.source_module ?? "").toLowerCase() === "grouping",
      )
      .map((item) =>
        normalizeRecommendation({
          ...(item.payload ?? {}),
          action: item,
          candidate_id: item.source_id ?? item.payload?.candidate_id,
        }),
      );
  }, [actionsQ.data, preview]);

  const filteredRecommendations = useMemo(() => {
    const q = search.trim().toLowerCase();
    return recommendations.filter((item) => {
      const risk = String(item.risk_level ?? "low").toLowerCase();
      const status = String(
        item.status ?? item.action?.status ?? "new",
      ).toLowerCase();
      if (riskFilter !== "all" && risk !== riskFilter) return false;
      if (
        statusFilter === "active" &&
        !["new", "reviewing", "postponed"].includes(status)
      )
        return false;
      if (statusFilter === "reviewed" && ["new", "reviewing"].includes(status))
        return false;
      if (routeNmId) {
        const ids = [item.anchor_nm_id, ...(item.nm_ids ?? [])];
        if (!ids.some((value) => String(value ?? "").trim() === routeNmId))
          return false;
      }
      if (!q) return true;
      const haystack = [
        item.candidate_key,
        item.scenario,
        item.candidate_type,
        item.anchor_nm_id,
        ...(item.nm_ids ?? []),
        ...(item.reasons ?? []),
        ...(item.risk_reasons ?? []),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [recommendations, riskFilter, routeNmId, search, statusFilter]);

  const totalPages = Math.max(
    1,
    Math.ceil(filteredRecommendations.length / PAGE_SIZE),
  );
  const pageItems = filteredRecommendations.slice(
    (page - 1) * PAGE_SIZE,
    page * PAGE_SIZE,
  );

  const stats = useMemo(() => {
    const high = recommendations.filter(
      (item) => String(item.risk_level).toLowerCase() === "high",
    ).length;
    const medium = recommendations.filter(
      (item) => String(item.risk_level).toLowerCase() === "medium",
    ).length;
    const reviewed = recommendations.filter((item) =>
      ["accepted", "rejected", "postponed"].includes(
        String(item.status ?? item.action?.status ?? "").toLowerCase(),
      ),
    ).length;
    const links = recommendations.reduce(
      (sum, item) => sum + Math.max(0, (item.nm_ids?.length ?? 1) - 1),
      0,
    );
    return { high, medium, reviewed, links };
  }, [recommendations]);

  if (!activeId) {
    return (
      <PageShell>
        <PageHeader
          title="Группировка товаров"
          description="Рекомендации по объединению карточек — только ручная проверка"
        />
        <NoAccountSelected />
      </PageShell>
    );
  }

  const analyzedCount =
    preview?.summary?.analyzed_product_count ??
    moduleStatus.unique_products_analyzed ??
    moduleStatus.eligible_products ??
    "—";
  const recommendationCount =
    preview?.summary?.candidate_groups ?? recommendations.length;
  const lastSuccess =
    preview?.summary?.analyzed_at ?? moduleStatus.last_success_at;
  const activeOperation = busy.run
    ? "Идёт анализ..."
    : busy.refresh
      ? "Обновляем список..."
      : busy.export
        ? "Готовим JSON..."
        : null;

  async function refreshData() {
    try {
      setBusy((prev) => ({ ...prev, refresh: true }));
      setPreview(null);
      setSelected(null);
      setPage(1);
      await Promise.all([
        qc.invalidateQueries({
          queryKey: ["portal", "grouping", "actions", activeId],
        }),
        qc.invalidateQueries({
          queryKey: ["portal", "modules-health", activeId],
        }),
      ]);
    } finally {
      setBusy((prev) => ({ ...prev, refresh: false }));
    }
  }

  function exportPreviewJson() {
    try {
      setBusy((prev) => ({ ...prev, export: true }));
      const payload = {
        exported_at: new Date().toISOString(),
        account_id: activeId,
        profile: activeProfile,
        summary: preview?.summary ?? null,
        recommendations,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `grouping_beta_${activeId}_${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setBusy((prev) => ({ ...prev, export: false }));
    }
  }

  return (
    <PageShell>
      <PageHeader
        title="Группировка товаров"
        description="Удобная лента NMID-связей в стиле WB Grouping v2: выберите профиль, запустите preview и проверьте рекомендации вручную."
      />

      {routeNmId && (
        <Card className="border-primary/20 bg-primary/5">
          <CardContent className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
            <div>
              <span className="font-medium">Фильтр по товару</span>{" "}
              <span className="font-mono text-muted-foreground">
                nm_id {routeNmId}
              </span>
            </div>
            <Badge variant="outline" className="bg-background/70">
              показываем только связанные группы
            </Badge>
          </CardContent>
        </Card>
      )}

      <Alert>
        <ShieldAlert className="h-4 w-4" />
        <AlertTitle>Только ручная проверка</AlertTitle>
        <AlertDescription>
          Finance portal не объединяет карточки автоматически. Preview и review
          сохраняются локально, WB merge/apply отключены.
        </AlertDescription>
      </Alert>

      <div className="grid gap-3 md:grid-cols-5">
        <MetricCard
          label="Статус модуля"
          value={STATUS_LABEL[statusKey] ?? statusKey}
          tone="primary"
        />
        <MetricCard
          label="Проанализировано"
          value={String(analyzedCount)}
          tone="success"
        />
        <MetricCard
          label="Кандидатов"
          value={String(recommendationCount ?? "—")}
          tone="info"
        />
        <MetricCard label="Связей" value={String(stats.links)} tone="warning" />
        <MetricCard
          label="Высокий риск"
          value={String(stats.high)}
          tone="danger"
        />
      </div>

      <Card>
        <CardContent className="p-4 space-y-4">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge
                  variant="outline"
                  className="border-primary/40 text-primary"
                >
                  <FlaskConical className="h-3.5 w-3.5 mr-1" />
                  Beta
                </Badge>
                <Badge variant="secondary">
                  Текущий профиль: {activeProfile.name}
                </Badge>
                {activeOperation ? (
                  <span className="text-xs text-muted-foreground inline-flex items-center gap-1">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    {activeOperation}
                  </span>
                ) : (
                  <span className="text-xs text-muted-foreground">
                    Готово к работе
                  </span>
                )}
              </div>
              <div className="text-xs text-muted-foreground">
                Последний успешный анализ:{" "}
                {lastSuccess
                  ? new Date(lastSuccess).toLocaleString("ru-RU")
                  : moduleStatus.last_run_id
                    ? `run #${moduleStatus.last_run_id}`
                    : "—"}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Input
                value={nmId}
                onChange={(event) => setNmId(event.target.value)}
                placeholder="nm_id"
                inputMode="numeric"
                className="h-9 w-36"
              />
              <Button
                disabled={!canRun || !nmIdIsValid || runMut.isPending}
                title={
                  canRun
                    ? undefined
                    : (moduleStatus.message ?? "Модуль недоступен")
                }
                onClick={() => runMut.mutate()}
              >
                {runMut.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Play className="h-4 w-4 mr-2" />
                )}
                Запустить анализ
              </Button>
              {!nmIdIsValid && (
                <span className="text-xs text-destructive">
                  nm_id должен быть числом
                </span>
              )}
              <Button
                variant="outline"
                onClick={() => void refreshData()}
                disabled={busy.refresh || runMut.isPending}
              >
                {busy.refresh ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4 mr-2" />
                )}
                Обновить
              </Button>
              <Button
                variant="outline"
                onClick={exportPreviewJson}
                disabled={!recommendations.length || busy.export}
              >
                <Link2 className="h-4 w-4 mr-2" />
                JSON
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <CardTitle className="text-base">Профиль автозаполнения</CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowConfig((value) => !value)}
            >
              <SlidersHorizontal className="h-4 w-4 mr-2" />
              {showConfig ? "Скрыть параметры" : "Параметры"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            {PROFILES.map((profile) => {
              const active = profile.key === profileKey;
              return (
                <button
                  key={profile.key}
                  className={`text-left rounded-md border p-3 transition-colors ${active ? "border-primary bg-primary/5" : "border-border hover:bg-muted/40"}`}
                  onClick={() => setProfileKey(profile.key)}
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm">{profile.name}</span>
                    <ToneBadge tone={profile.tone}>Профиль</ToneBadge>
                    {active && <Badge className="text-[10px]">Выбран</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
                    {profile.description}
                  </p>
                </button>
              );
            })}
          </div>

          {showConfig && (
            <div className="border-t pt-4 space-y-4">
              <div className="grid gap-3 md:grid-cols-4">
                <ConfigItem
                  label="color_mode"
                  value={activeProfile.config.color_mode}
                />
                <ConfigItem
                  label="minimum_confidence"
                  value={activeProfile.config.minimum_confidence}
                />
                <ConfigItem
                  label="maximum_risk"
                  value={activeProfile.config.maximum_risk}
                />
                <ConfigItem
                  label="max_cards_in_group"
                  value={activeProfile.config.max_cards_in_group}
                />
                <ConfigItem
                  label="same_brand_required"
                  value={
                    activeProfile.config.same_brand_required ? "да" : "нет"
                  }
                />
                <ConfigItem
                  label="same_subject_required"
                  value={
                    activeProfile.config.same_subject_required ? "да" : "нет"
                  }
                />
                <ConfigItem
                  label="complete_article_as_unit"
                  value={
                    activeProfile.config.complete_article_as_unit ? "да" : "нет"
                  }
                />
                <ConfigItem
                  label="diversity_limit"
                  value={activeProfile.config.diversity_limit}
                />
              </div>
              <Alert>
                <Info className="h-4 w-4" />
                <AlertDescription>
                  Эти параметры отправляются в предварительный запрос как профиль v2.
                  Бэкенд применяет безопасные пороги, а объединение WB остаётся
                  отключённым.
                </AlertDescription>
              </Alert>
            </div>
          )}
        </CardContent>
      </Card>

      <InsightsCard
        preview={preview}
        recommendations={recommendations}
        stats={stats}
        activeProfile={activeProfile}
      />

      <Tabs defaultValue="feed" className="space-y-3">
        <TabsList>
          <TabsTrigger value="feed">Лента рекомендаций</TabsTrigger>
          <TabsTrigger value="reviewed">Проверенные</TabsTrigger>
          <TabsTrigger value="settings">Настройки</TabsTrigger>
        </TabsList>

        <TabsContent value="feed" className="space-y-3">
          <RecommendationFilters
            search={search}
            riskFilter={riskFilter}
            statusFilter={statusFilter}
            setSearch={setSearch}
            setRiskFilter={setRiskFilter}
            setStatusFilter={setStatusFilter}
            resetPage={() => setPage(1)}
          />
          <RecommendationFeed
            loading={actionsQ.isLoading || runMut.isPending}
            recommendations={pageItems}
            selected={selected}
            setSelected={setSelected}
            reviewMut={reviewMut}
            page={page}
            totalPages={totalPages}
            totalItems={filteredRecommendations.length}
            setPage={setPage}
          />
        </TabsContent>

        <TabsContent value="reviewed">
          <RecommendationFeed
            loading={actionsQ.isLoading}
            recommendations={recommendations.filter(
              (item) =>
                !["new", "reviewing"].includes(
                  String(
                    item.status ?? item.action?.status ?? "new",
                  ).toLowerCase(),
                ),
            )}
            selected={selected}
            setSelected={setSelected}
            reviewMut={reviewMut}
            page={1}
            totalPages={1}
            totalItems={
              recommendations.filter(
                (item) =>
                  !["new", "reviewing"].includes(
                    String(
                      item.status ?? item.action?.status ?? "new",
                    ).toLowerCase(),
                  ),
              ).length
            }
            setPage={() => undefined}
          />
        </TabsContent>

        <TabsContent value="settings">
          <Card>
            <CardContent className="p-4 text-sm text-muted-foreground space-y-2">
              <div className="flex items-start gap-2">
                <Settings2 className="h-4 w-4 mt-0.5" />
                <div>
                  Сценарии и безопасные пороги управляются через политику бэкенда
                  и{" "}
                  <Link to="/settings" className="underline">
                    настройки портала
                  </Link>{" "}
                  . Этот экран отвечает только за безопасный предварительный просмотр и проверку.
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {selected && (
        <RecommendationDetail
          item={selected}
          onClose={() => setSelected(null)}
          reviewMut={reviewMut}
        />
      )}
    </PageShell>
  );
}

function RecommendationFilters(props: {
  search: string;
  riskFilter: string;
  statusFilter: string;
  setSearch: (value: string) => void;
  setRiskFilter: (value: string) => void;
  setStatusFilter: (value: string) => void;
  resetPage: () => void;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
          <div className="flex-1 space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              Поиск по NMID, candidate key или reason
            </label>
            <div className="relative">
              <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={props.search}
                onChange={(event) => {
                  props.setSearch(event.target.value);
                  props.resetPage();
                }}
                placeholder="Например: 123456789 или article_base"
                className="pl-9"
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              Риск
            </label>
            <select
              value={props.riskFilter}
              onChange={(event) => {
                props.setRiskFilter(event.target.value);
                props.resetPage();
              }}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="all">Все</option>
              <option value="low">Низкий</option>
              <option value="medium">Средний</option>
              <option value="high">Высокий</option>
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              Статус
            </label>
            <select
              value={props.statusFilter}
              onChange={(event) => {
                props.setStatusFilter(event.target.value);
                props.resetPage();
              }}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="active">Активные</option>
              <option value="reviewed">Проверенные</option>
              <option value="all">Все</option>
            </select>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function RecommendationFeed({
  loading,
  recommendations,
  selected,
  setSelected,
  reviewMut,
  page,
  totalPages,
  totalItems,
  setPage,
}: {
  loading: boolean;
  recommendations: Recommendation[];
  selected: Recommendation | null;
  setSelected: (value: Recommendation) => void;
  reviewMut: {
    isPending: boolean;
    mutate: (value: {
      id: number | string;
      status: "accepted" | "rejected" | "postponed";
    }) => void;
  };
  page: number;
  totalPages: number;
  totalItems: number;
  setPage: (value: number | ((prev: number) => number)) => void;
}) {
  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-28 w-full" />
        ))}
      </div>
    );
  }

  if (!recommendations.length) {
    return (
      <Card>
        <CardContent className="p-8">
          <div className="text-center space-y-2">
            <PackageOpen className="h-10 w-10 text-muted-foreground mx-auto" />
            <div className="font-medium">Связи не найдены</div>
            <div className="text-xs text-muted-foreground">
              Запустите preview или смягчите фильтры.
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <div className="hidden lg:grid grid-cols-[1.2fr_1.6fr_0.8fr] gap-3 border-b bg-muted/40 px-4 py-2 text-xs font-medium text-muted-foreground">
        <span>Главный товар</span>
        <span>Рекомендуемые NMID</span>
        <span>Review</span>
      </div>
      <div className="divide-y">
        {recommendations.map((item, index) => {
          const id = candidateReviewId(item);
          const sourceNmid = item.anchor_nm_id ?? item.nm_ids?.[0];
          const targets = (item.nm_ids ?? []).filter(
            (value) => value !== sourceNmid,
          );
          const source = productInfo(item, "source", sourceNmid);
          const active =
            selected && candidateIdentity(selected) === candidateIdentity(item);
          const openItem = () => setSelected(item);
          return (
            <div
              key={candidateIdentity(item) ?? index}
              role="button"
              tabIndex={0}
              className={`w-full text-left grid gap-3 p-4 transition-colors lg:grid-cols-[1.2fr_1.6fr_0.8fr] ${active ? "bg-primary/5" : "hover:bg-muted/40"}`}
              onClick={openItem}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  openItem();
                }
              }}
            >
              <div className="flex items-center gap-3 min-w-0">
                <ProductThumb
                  nmid={sourceNmid}
                  title={source.title ?? String(sourceNmid ?? "NMID")}
                  size="lg"
                />
                <div className="min-w-0 space-y-1">
                  <div className="font-medium truncate">
                    {source.title ??
                      (sourceNmid
                        ? `NMID ${sourceNmid}`
                        : "Рекомендация группировки")}
                  </div>
                  <div className="text-xs text-muted-foreground truncate">
                    {[
                      source.subject,
                      source.brand,
                      source.vendor_code ?? item.candidate_key ?? item.scenario,
                    ]
                      .filter(Boolean)
                      .join(" · ") || "Без описания"}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    <RiskBadge risk={item.risk_level} />
                    <Badge variant="outline" className="text-[10px]">
                      {item.status ?? item.action?.status ?? "new"}
                    </Badge>
                    <Badge variant="outline" className="text-[10px]">
                      merge WB: off
                    </Badge>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex gap-2 flex-wrap">
                  {(targets.length ? targets : (item.nm_ids ?? []))
                    .slice(0, 20)
                    .map((nmid) => {
                      const target = productInfo(item, "target", nmid);
                      return (
                        <div
                          key={`${id}-${nmid}`}
                          className="flex items-center gap-2 rounded-md border bg-background px-2 py-1"
                          title={target.title ?? String(nmid)}
                        >
                          <ProductThumb
                            nmid={nmid}
                            title={target.title ?? String(nmid)}
                          />
                          <div className="min-w-0">
                            <div className="text-xs font-medium truncate max-w-40">
                              {target.title ?? `NMID ${nmid}`}
                            </div>
                            <div className="text-[10px] text-muted-foreground font-mono">
                              {nmid}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                </div>
                <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                  {item.confidence != null && (
                    <span>
                      confidence:{" "}
                      <span className="text-foreground">
                        {Number(item.confidence).toFixed(2)}
                      </span>
                    </span>
                  )}
                  {item.risk_score != null && (
                    <span>
                      risk score:{" "}
                      <span className="text-foreground">
                        {Number(item.risk_score).toFixed(2)}
                      </span>
                    </span>
                  )}
                  {item.reasons?.slice(0, 3).map((reason) => (
                    <span key={reason}>{reason}</span>
                  ))}
                </div>
              </div>

              <div
                className="flex items-center gap-2 flex-wrap lg:justify-end"
                onClick={(event) => event.stopPropagation()}
              >
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 text-xs"
                  onClick={openItem}
                >
                  <Eye className="h-3.5 w-3.5 mr-1" />
                  Открыть
                </Button>
                {id != null && (
                  <>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 text-xs"
                      disabled={reviewMut.isPending}
                      onClick={() =>
                        reviewMut.mutate({ id, status: "accepted" })
                      }
                    >
                      <Check className="h-3.5 w-3.5 mr-1" />
                      Принять
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 text-xs"
                      disabled={reviewMut.isPending}
                      onClick={() =>
                        reviewMut.mutate({ id, status: "postponed" })
                      }
                    >
                      <Clock3 className="h-3.5 w-3.5 mr-1" />
                      Отложить
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 text-xs"
                      disabled={reviewMut.isPending}
                      onClick={() =>
                        reviewMut.mutate({ id, status: "rejected" })
                      }
                    >
                      <X className="h-3.5 w-3.5 mr-1" />
                      Отклонить
                    </Button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-between gap-3 border-t px-4 py-3 text-sm">
          <span className="text-muted-foreground">
            Страница {page} из {totalPages} · {totalItems} кандидатов
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
            >
              Назад
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
            >
              Далее
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

function RecommendationDetail({
  item,
  onClose,
  reviewMut,
}: {
  item: Recommendation;
  onClose: () => void;
  reviewMut: {
    isPending: boolean;
    mutate: (value: {
      id: number | string;
      status: "accepted" | "rejected" | "postponed";
    }) => void;
  };
}) {
  const id = candidateReviewId(item);
  const sourceNmid = item.anchor_nm_id ?? item.nm_ids?.[0];
  const targets = (item.nm_ids ?? []).filter((value) => value !== sourceNmid);
  const source = productInfo(item, "source", sourceNmid);

  return (
    <div
      className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm p-3 flex items-center justify-center"
      onClick={onClose}
    >
      <Card
        className="w-full max-w-5xl max-h-[90vh] overflow-hidden"
        onClick={(event) => event.stopPropagation()}
      >
        <CardHeader className="border-b">
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base">Рекомендации к товару</CardTitle>
              <p className="text-xs text-muted-foreground mt-1">
                Preview payload и evidence. Сохранение порядка в WB отключено,
                review выполняется локально.
              </p>
            </div>
            <Button variant="ghost" size="sm" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-4 space-y-4 overflow-y-auto max-h-[72vh]">
          <div className="rounded-md border p-3 flex items-center gap-3">
            <ProductThumb
              nmid={sourceNmid}
              title={source.title ?? String(sourceNmid ?? "NMID")}
              size="lg"
            />
            <div className="space-y-1 min-w-0">
              <div className="font-medium">
                {source.title ??
                  (sourceNmid ? `NMID ${sourceNmid}` : "Главный товар")}
              </div>
              <div className="text-xs text-muted-foreground truncate">
                {[
                  source.subject,
                  source.brand,
                  source.vendor_code ?? item.candidate_key ?? item.scenario,
                ]
                  .filter(Boolean)
                  .join(" · ") || "Без описания"}
              </div>
              <div className="flex gap-1 flex-wrap">
                <RiskBadge risk={item.risk_level} />
                <Badge variant="outline">
                  {item.status ?? item.action?.status ?? "new"}
                </Badge>
                {item.review_needed && (
                  <Badge variant="secondary">review needed</Badge>
                )}
              </div>
            </div>
          </div>

          <div>
            <div className="text-sm font-medium mb-2">Рекомендуемые товары</div>
            <div className="grid gap-2 md:grid-cols-2">
              {(targets.length ? targets : (item.nm_ids ?? [])).map(
                (nmid, index) => {
                  const target = productInfo(item, "target", nmid);
                  return (
                    <div
                      key={`${nmid}-${index}`}
                      className="rounded-md border p-2 flex items-center gap-3"
                    >
                      <span className="text-xs text-muted-foreground w-8">
                        #{index + 1}
                      </span>
                      <ProductThumb
                        nmid={nmid}
                        title={target.title ?? String(nmid)}
                        size="lg"
                      />
                      <div>
                        <div className="text-sm font-medium">
                          {target.title ?? `NMID ${nmid}`}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {[target.subject, target.brand, nmid]
                            .filter(Boolean)
                            .join(" · ")}
                        </div>
                      </div>
                    </div>
                  );
                },
              )}
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <InfoPanel
              title="Причины"
              values={item.reasons ?? []}
              empty="Позитивные причины не указаны"
            />
            <InfoPanel
              title="Риски"
              values={item.risk_reasons ?? []}
              empty="Риски не указаны"
              destructive
            />
          </div>

          <div className="rounded-md border p-3">
            <div className="text-sm font-medium mb-2">Evidence</div>
            <pre className="text-xs overflow-auto rounded bg-muted p-3 max-h-56">
              {JSON.stringify(item.evidence ?? {}, null, 2)}
            </pre>
          </div>

          <div className="flex flex-wrap gap-2 justify-end">
            {id != null && (
              <>
                <Button
                  disabled={reviewMut.isPending}
                  onClick={() => reviewMut.mutate({ id, status: "accepted" })}
                >
                  <Check className="h-4 w-4 mr-2" />
                  Принять
                </Button>
                <Button
                  variant="outline"
                  disabled={reviewMut.isPending}
                  onClick={() => reviewMut.mutate({ id, status: "postponed" })}
                >
                  <Clock3 className="h-4 w-4 mr-2" />
                  Отложить
                </Button>
                <Button
                  variant="outline"
                  disabled={reviewMut.isPending}
                  onClick={() => reviewMut.mutate({ id, status: "rejected" })}
                >
                  <X className="h-4 w-4 mr-2" />
                  Отклонить
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function InsightsCard({
  preview,
  recommendations,
  stats,
  activeProfile,
}: {
  preview: PreviewLike | null;
  recommendations: Recommendation[];
  stats: { high: number; medium: number; reviewed: number; links: number };
  activeProfile: GroupingProfile;
}) {
  const riskTotal = recommendations.length || 1;
  const low = recommendations.filter(
    (item) => String(item.risk_level ?? "low").toLowerCase() === "low",
  ).length;

  return (
    <Card>
      <CardContent className="p-4 space-y-4">
        <div>
          <CardTitle className="text-base">Как сработало</CardTitle>
          <p className="text-xs text-muted-foreground mt-1">
            Краткая сводка последнего preview и текущей ленты рекомендаций.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-4">
          <MetricCard
            label="Run ID"
            value={String(preview?.summary?.run_id ?? "—")}
            tone="primary"
          />
          <MetricCard
            label="Сценарий"
            value={String(preview?.summary?.scenario ?? activeProfile.scenario)}
            tone="info"
          />
          <MetricCard
            label="Проверено"
            value={String(stats.reviewed)}
            tone="success"
          />
          <MetricCard
            label="WB merge"
            value={preview?.summary?.auto_merge_enabled ? "on" : "off"}
            tone="danger"
          />
        </div>

        <div className="grid gap-3 lg:grid-cols-2">
          <div className="rounded-md border p-3 space-y-3">
            <div className="text-sm font-medium">Распределение risk</div>
            <ProgressRow label="Low" value={low} total={riskTotal} />
            <ProgressRow
              label="Medium"
              value={stats.medium}
              total={riskTotal}
            />
            <ProgressRow label="High" value={stats.high} total={riskTotal} />
          </div>
          <div className="rounded-md border p-3">
            <div className="text-sm font-medium mb-2">Применённый профиль</div>
            <div className="flex flex-wrap gap-2">
              <ToneBadge tone={activeProfile.tone}>
                {activeProfile.name}
              </ToneBadge>
              <Badge variant="outline">
                scenario: {activeProfile.scenario}
              </Badge>
              <Badge variant="outline">
                min confidence: {activeProfile.config.minimum_confidence}
              </Badge>
              <Badge variant="outline">
                max risk: {activeProfile.config.maximum_risk}
              </Badge>
              <Badge variant="outline">merge WB: off</Badge>
            </div>
          </div>
        </div>

        <Alert>
          <ShieldCheck className="h-4 w-4" />
          <AlertDescription>
            Заблокированные операции backend:{" "}
            {(
              preview?.raw?.blocked_operations ?? [
                "merge-wb",
                "auto_apply",
                "card_mutation",
              ]
            ).join(", ")}
            .
          </AlertDescription>
        </Alert>
      </CardContent>
    </Card>
  );
}

function MetricCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "primary" | "success" | "warning" | "danger" | "info";
}) {
  const toneClass = {
    primary: "border-primary/30 bg-primary/5",
    success: "border-emerald-500/30 bg-emerald-500/5",
    warning: "border-amber-500/30 bg-amber-500/5",
    danger: "border-destructive/30 bg-destructive/5",
    info: "border-sky-500/30 bg-sky-500/5",
  }[tone];
  return (
    <Card className={toneClass}>
      <CardContent className="p-3">
        <div className="text-[11px] uppercase text-muted-foreground">
          {label}
        </div>
        <div className="text-lg font-semibold mt-1 truncate">{value}</div>
      </CardContent>
    </Card>
  );
}

function ConfigItem({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-md border bg-background p-3">
      <div className="text-[11px] uppercase text-muted-foreground">{label}</div>
      <div className="text-sm font-medium mt-1">{value}</div>
    </div>
  );
}

function ProgressRow({
  label,
  value,
  total,
}: {
  label: string;
  value: number;
  total: number;
}) {
  const pct = Math.round((value / total) * 100);
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span>{label}</span>
        <span className="text-muted-foreground">
          {value} · {pct}%
        </span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function InfoPanel({
  title,
  values,
  empty,
  destructive,
}: {
  title: string;
  values: string[];
  empty: string;
  destructive?: boolean;
}) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-sm font-medium mb-2">{title}</div>
      {values.length ? (
        <div className="flex flex-wrap gap-2">
          {values.map((value) => (
            <Badge
              key={value}
              variant={destructive ? "destructive" : "secondary"}
            >
              {value}
            </Badge>
          ))}
        </div>
      ) : (
        <div className="text-xs text-muted-foreground">{empty}</div>
      )}
    </div>
  );
}

function RiskBadge({ risk }: { risk?: string | null }) {
  const normalized = String(risk ?? "low").toLowerCase();
  if (normalized === "high")
    return (
      <Badge variant="destructive" className="text-[10px]">
        риск: высокий
      </Badge>
    );
  if (normalized === "medium")
    return (
      <Badge variant="secondary" className="text-[10px]">
        риск: средний
      </Badge>
    );
  return (
    <Badge variant="outline" className="text-[10px]">
      риск: низкий
    </Badge>
  );
}

function ToneBadge({
  tone,
  children,
}: {
  tone: GroupingProfile["tone"];
  children: React.ReactNode;
}) {
  const className = {
    primary: "border-primary/40 text-primary",
    success: "border-emerald-500/40 text-emerald-700 dark:text-emerald-300",
    warning: "border-amber-500/40 text-amber-700 dark:text-amber-300",
    info: "border-sky-500/40 text-sky-700 dark:text-sky-300",
  }[tone];
  return (
    <Badge variant="outline" className={`text-[10px] ${className}`}>
      {children}
    </Badge>
  );
}

function ProductThumb({
  nmid,
  title,
  size = "sm",
}: {
  nmid?: number | null;
  title: string;
  size?: "sm" | "lg";
}) {
  const [failed, setFailed] = useState(false);
  const box = size === "lg" ? "h-12 w-10" : "h-8 w-7";
  if (!nmid || failed) {
    return (
      <div
        className={`${box} rounded border bg-muted flex items-center justify-center text-[10px] font-medium text-muted-foreground shrink-0`}
        title={title}
      >
        {String(title || nmid || "?")
          .slice(0, 1)
          .toUpperCase()}
      </div>
    );
  }
  return (
    <img
      className={`${box} rounded border object-cover bg-muted shrink-0`}
      src={getWbImageUrl(nmid)}
      alt={title}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}

function getWbBasketHost(volume: number) {
  if (volume <= 143) return "basket-01.wbbasket.ru";
  if (volume <= 287) return "basket-02.wbbasket.ru";
  if (volume <= 431) return "basket-03.wbbasket.ru";
  if (volume <= 719) return "basket-04.wbbasket.ru";
  if (volume <= 1007) return "basket-05.wbbasket.ru";
  if (volume <= 1061) return "basket-06.wbbasket.ru";
  if (volume <= 1115) return "basket-07.wbbasket.ru";
  if (volume <= 1169) return "basket-08.wbbasket.ru";
  if (volume <= 1313) return "basket-09.wbbasket.ru";
  if (volume <= 1601) return "basket-10.wbbasket.ru";
  if (volume <= 1655) return "basket-11.wbbasket.ru";
  if (volume <= 1919) return "basket-12.wbbasket.ru";
  if (volume <= 2045) return "basket-13.wbbasket.ru";
  if (volume <= 2189) return "basket-14.wbbasket.ru";
  if (volume <= 2405) return "basket-15.wbbasket.ru";
  if (volume <= 2621) return "basket-16.wbbasket.ru";
  if (volume <= 2837) return "basket-17.wbbasket.ru";
  if (volume <= 3053) return "basket-18.wbbasket.ru";
  if (volume <= 3269) return "basket-19.wbbasket.ru";
  if (volume <= 3485) return "basket-20.wbbasket.ru";
  if (volume <= 3701) return "basket-21.wbbasket.ru";
  if (volume <= 3917) return "basket-22.wbbasket.ru";
  if (volume <= 4133) return "basket-23.wbbasket.ru";
  return "basket-24.wbbasket.ru";
}

function getWbImageUrl(nmid: number) {
  const volume = Math.floor(nmid / 100000);
  const part = Math.floor(nmid / 1000);
  return `https://${getWbBasketHost(volume)}/vol${volume}/part${part}/${nmid}/images/c246x328/1.webp`;
}

function normalizeRecommendation(raw: unknown): Recommendation {
  const row = isRecord(raw) ? raw : {};
  const action = isRecord(row.action)
    ? (row.action as PortalActionLike)
    : undefined;
  const nmIds = Array.isArray(row.nm_ids)
    ? row.nm_ids.map((item) => Number(item)).filter(Number.isFinite)
    : [];
  return {
    ...row,
    id: toOptionalStringOrNumber(row.id),
    candidate_id: toOptionalStringOrNumber(row.candidate_id),
    candidate_group_id: toOptionalString(row.candidate_group_id),
    candidate_key: toOptionalString(row.candidate_key),
    scenario: toOptionalString(row.scenario),
    candidate_type: toOptionalString(row.candidate_type),
    nm_ids: nmIds,
    anchor_nm_id: toOptionalNumber(row.anchor_nm_id),
    confidence: toOptionalNumber(row.confidence),
    risk_level: toOptionalString(row.risk_level),
    risk_score: toOptionalNumber(row.risk_score),
    reasons: toStringArray(row.reasons),
    risk_reasons: toStringArray(row.risk_reasons),
    conflicts: toStringArray(row.conflicts),
    evidence: isRecord(row.evidence) ? row.evidence : {},
    status: toOptionalString(row.status),
    auto_merge_enabled:
      typeof row.auto_merge_enabled === "boolean"
        ? row.auto_merge_enabled
        : undefined,
    review_needed:
      typeof row.review_needed === "boolean" ? row.review_needed : undefined,
    action,
    preview_payload: isRecord(row.preview_payload)
      ? row.preview_payload
      : undefined,
  };
}

function productInfo(
  item: Recommendation,
  side: "source" | "target",
  nmid?: number | null,
): ProductInfo {
  const row = item as unknown as JsonRecord;
  const direct = side === "source" ? row.source_product : row.target_product;
  const product = isRecord(direct)
    ? direct
    : (findProductInArray(row[`${side}_products`], nmid) ??
      findProductInArray(row.products, nmid));
  if (!isRecord(product)) return nmid ? { nm_id: nmid } : {};
  return {
    nm_id: toOptionalNumber(product.nm_id) ?? nmid ?? undefined,
    title:
      toOptionalString(product.title) ??
      toOptionalString(product.article) ??
      toOptionalString(product.name),
    brand: toOptionalString(product.brand),
    subject:
      toOptionalString(product.subject) ??
      toOptionalString(product.subject_name),
    vendor_code:
      toOptionalString(product.vendor_code) ??
      toOptionalString(product.vendorCode) ??
      toOptionalString(product.article),
  };
}

function findProductInArray(value: unknown, nmid?: number | null) {
  if (!Array.isArray(value)) return undefined;
  return value.find((item) => {
    if (!isRecord(item)) return false;
    return toOptionalNumber(item.nm_id) === nmid;
  });
}

function candidateIdentity(item: Recommendation | null) {
  if (!item) return "";
  return String(
    item.id ??
      item.candidate_id ??
      item.candidate_group_id ??
      item.action?.source_id ??
      item.candidate_key ??
      item.nm_ids?.join("-") ??
      "",
  );
}

function candidateReviewId(item: Recommendation) {
  return (
    item.id ??
    item.candidate_id ??
    item.candidate_group_id ??
    item.action?.source_id
  );
}

function patchPreviewCandidate(prev: PreviewLike | null, data: unknown) {
  if (!prev || !Array.isArray(prev.recommendations)) return prev;
  const next = normalizeRecommendation(data);
  return {
    ...prev,
    recommendations: prev.recommendations.map((item) =>
      candidateIdentity(normalizeRecommendation(item)) ===
      candidateIdentity(next)
        ? { ...item, ...next }
        : item,
    ),
  };
}

function patchSelectedCandidate(prev: Recommendation | null, data: unknown) {
  if (!prev) return prev;
  const next = normalizeRecommendation(data);
  return candidateIdentity(prev) === candidateIdentity(next)
    ? { ...prev, ...next }
    : prev;
}

function normalizeActionItems(data: unknown): PortalActionLike[] {
  if (Array.isArray(data)) return data.filter(isRecord) as PortalActionLike[];
  if (!isRecord(data) || !Array.isArray(data.items)) return [];
  return data.items.filter(isRecord) as PortalActionLike[];
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toOptionalString(value: unknown) {
  return value == null ? undefined : String(value);
}

function toOptionalStringOrNumber(value: unknown) {
  if (typeof value === "number" || typeof value === "string") return value;
  return undefined;
}

function toOptionalNumber(value: unknown) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : undefined;
}

function toStringArray(value: unknown) {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}
