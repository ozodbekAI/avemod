import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchABTestStats,
  startABTestCompany,
  stopABTestCompany,
} from "@/lib/ab-tests";
import { useAccounts } from "@/lib/account-context";
import { PageHeader, PageShell } from "@/components/PageShell";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { EndpointError } from "@/components/EndpointError";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatNumber } from "@/lib/format";
import {
  ArrowLeft,
  CheckCircle2,
  CircleDot,
  Eye,
  Loader2,
  PauseCircle,
  Play,
  Trophy,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/ab-tests/$companyId")({
  component: ABTestDetailPage,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function confirmWBWrite(preview: Record<string, unknown>, fallback: string) {
  const diff = (preview.diff || {}) as Record<string, unknown>;
  const proposed = Array.isArray(diff.proposed_media)
    ? diff.proposed_media.length
    : Number(preview.photos_count || 0);
  const current = Array.isArray(diff.current_media) ? diff.current_media.length : 0;
  return window.confirm(
    [
      fallback,
      "",
      `Текущих фото: ${current}`,
      `Новых вариантов: ${proposed}`,
      "После подтверждения запрос может изменить WB кампанию или медиа карточки.",
    ].join("\n"),
  );
}

function ABTestDetailPage() {
  const { activeId } = useAccounts();
  const { companyId } = Route.useParams();
  const queryClient = useQueryClient();
  const numericCompanyId = Number(companyId);

  const statsQ = useQuery({
    queryKey: ["ab-test", activeId, numericCompanyId],
    queryFn: () => fetchABTestStats(activeId!, numericCompanyId),
    enabled: !!activeId && Number.isFinite(numericCompanyId),
    staleTime: 20_000,
  });

  const startMut = useMutation({
    mutationFn: async () => {
      const preview = await startABTestCompany(activeId!, numericCompanyId);
      if (preview.requires_confirmation) {
        if (!confirmWBWrite(preview, "Запустить A/B тест и применить фото к WB карточке?")) {
          throw new Error("Запуск A/B теста отменён");
        }
      }
      return startABTestCompany(activeId!, numericCompanyId, { confirm: true });
    },
    onSuccess: async () => {
      toast.success("Тест запущен");
      await queryClient.invalidateQueries({
        queryKey: ["ab-test", activeId, numericCompanyId],
      });
      await queryClient.invalidateQueries({ queryKey: ["ab-tests", activeId] });
    },
    onError: (error: unknown) =>
      toast.error(errorMessage(error, "Не удалось запустить тест")),
  });
  const stopMut = useMutation({
    mutationFn: async () => {
      const preview = await stopABTestCompany(activeId!, numericCompanyId);
      if (preview.requires_confirmation) {
        if (!confirmWBWrite(preview, "Остановить A/B тест и восстановить медиа карточки?")) {
          throw new Error("Остановка A/B теста отменена");
        }
      }
      return stopABTestCompany(activeId!, numericCompanyId, { confirm: true });
    },
    onSuccess: async () => {
      toast.success("Тест остановлен");
      await queryClient.invalidateQueries({
        queryKey: ["ab-test", activeId, numericCompanyId],
      });
      await queryClient.invalidateQueries({ queryKey: ["ab-tests", activeId] });
    },
    onError: (error: unknown) =>
      toast.error(errorMessage(error, "Не удалось остановить тест")),
  });

  if (!activeId) {
    return (
      <PageShell>
        <PageHeader title="A/B тест" />
        <NoAccountSelected message="Выберите WB-аккаунт в верхней панели." />
      </PageShell>
    );
  }

  const item = statsQ.data;
  const totalShows =
    item?.photos?.reduce((sum, photo) => sum + (photo.shows || 0), 0) ?? 0;
  const totalClicks =
    item?.photos?.reduce((sum, photo) => sum + (photo.clicks || 0), 0) ?? 0;
  const ctr = totalShows > 0 ? (totalClicks / totalShows) * 100 : 0;
  const normalizedStatus = normalizeStatus(item?.status);
  const bestCtr =
    item?.photos?.reduce(
      (max, photo) => Math.max(max, Number(photo.ctr || 0)),
      0,
    ) ?? 0;
  const bestPhotoOrder = (() => {
    if (!item?.photos?.length) return null;
    return item.photos.reduce((best, photo) =>
      Number(photo.ctr || 0) > Number(best.ctr || 0) ? photo : best,
    ).order;
  })();
  const progressTotal = Math.max(
    item?.photos_count || item?.photos?.length || 0,
    1,
  );
  const progressCount =
    normalizedStatus === "finished"
      ? progressTotal
      : Math.min(
          Math.max(
            Number(item?.current_photo_order || 0),
            totalShows > 0 ? 1 : 0,
          ),
          progressTotal,
        );
  const progressPercent = Math.max(
    0,
    Math.min(100, (progressCount / progressTotal) * 100),
  );
  const banner = item
    ? winnerBanner(item.status, item.winner_decision, item.last_error)
    : null;

  return (
    <PageShell>
      <PageHeader
        title={item?.title || "A/B тест"}
        description={
          item
            ? `nmID ${item.nm_id}${item.wb_advert_id ? ` · advert ${item.wb_advert_id}` : ""}`
            : "Загрузка теста"
        }
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" asChild>
              <Link to="/ab-tests">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Назад
              </Link>
            </Button>
            {item?.can_start ? (
              <Button
                onClick={() => startMut.mutate()}
                disabled={startMut.isPending}
              >
                {startMut.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Play className="mr-2 h-4 w-4" />
                )}
                Запустить
              </Button>
            ) : null}
            {item?.can_stop ? (
              <Button
                variant="outline"
                onClick={() => stopMut.mutate()}
                disabled={stopMut.isPending}
              >
                {stopMut.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <PauseCircle className="mr-2 h-4 w-4" />
                )}
                Остановить
              </Button>
            ) : null}
          </div>
        }
      />

      {statsQ.isLoading ? (
        <div className="grid gap-3">
          <Skeleton className="h-28" />
          <Skeleton className="h-96" />
        </div>
      ) : statsQ.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Не удалось загрузить тест</AlertTitle>
          <AlertDescription>
            {statsQ.error instanceof Error
              ? statsQ.error.message
              : "Проверьте backend."}
          </AlertDescription>
        </Alert>
      ) : item ? (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-4">
            <MetricCard
              label="Статус"
              value={statusLabel(item.status, item.winner_decision)}
            />
            <MetricCard label="Показы" value={formatNumber(totalShows)} />
            <MetricCard label="Клики" value={formatNumber(totalClicks)} />
            <MetricCard label="CTR" value={`${ctr.toFixed(2)}%`} />
          </div>

          {item.last_error ? (
            <Alert>
              <AlertTitle>Комментарий системы</AlertTitle>
              <AlertDescription>{item.last_error}</AlertDescription>
            </Alert>
          ) : null}

          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="text-muted-foreground">
                  Период проведения теста:
                </span>
                <strong>
                  {progressCount} из {progressTotal} фото
                </strong>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </CardContent>
          </Card>

          {banner ? (
            <Alert
              variant={banner.tone === "danger" ? "destructive" : "default"}
            >
              <AlertTitle>{banner.title}</AlertTitle>
              <AlertDescription>
                {banner.text}
                <div className="mt-1 text-xs text-muted-foreground">
                  {banner.subtext}
                </div>
              </AlertDescription>
            </Alert>
          ) : null}

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {item.photos.map((photo) => (
              <Card
                key={photo.order}
                className={photo.is_winner ? "border-success" : undefined}
              >
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">
                      Вариант #{photo.order}
                    </CardTitle>
                    {photo.is_winner ? (
                      <Badge className="bg-success text-white">
                        <Trophy className="mr-1 h-3 w-3" />
                        Победитель
                      </Badge>
                    ) : null}
                    {item.current_photo_order === photo.order &&
                    item.status === "running" ? (
                      <Badge>
                        <Play className="mr-1 h-3 w-3" />
                        Сейчас
                      </Badge>
                    ) : null}
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="aspect-[3/4] overflow-hidden rounded-md border bg-muted">
                    {photo.preview_url || photo.file_url ? (
                      <img
                        src={photo.preview_url || photo.file_url}
                        alt=""
                        className="h-full w-full object-cover"
                      />
                    ) : null}
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-sm">
                    <MiniMetric
                      label="Показы"
                      value={formatNumber(photo.shows || 0)}
                    />
                    <MiniMetric
                      label="Клики"
                      value={formatNumber(photo.clicks || 0)}
                    />
                    <MiniMetric
                      label="CTR"
                      value={`${Number(photo.ctr || 0).toFixed(2)}%`}
                    />
                  </div>
                  {photo.winner_score_reason ? (
                    <p className="text-xs text-muted-foreground">
                      {photo.winner_score_reason}
                    </p>
                  ) : null}
                </CardContent>
              </Card>
            ))}
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Сравнение вариантов</CardTitle>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Показатель</th>
                    {item.photos.map((photo) => (
                      <th key={photo.order} className="py-2 pr-4 font-medium">
                        Фото {photo.order}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-b">
                    <td className="py-2 pr-4 text-muted-foreground">Статус</td>
                    {item.photos.map((photo) => (
                      <td key={photo.order} className="py-2 pr-4">
                        <PhotoStatusBadge
                          isCurrent={
                            normalizedStatus === "running" &&
                            photo.order === item.current_photo_order
                          }
                          isBest={
                            normalizedStatus === "finished" &&
                            bestPhotoOrder === photo.order &&
                            bestCtr > 0
                          }
                          hasShows={photo.shows > 0}
                        />
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b">
                    <td className="py-2 pr-4 text-muted-foreground">Показов</td>
                    {item.photos.map((photo) => (
                      <td key={photo.order} className="py-2 pr-4">
                        {formatNumber(photo.shows || 0)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b">
                    <td className="py-2 pr-4 text-muted-foreground">Кликов</td>
                    {item.photos.map((photo) => (
                      <td key={photo.order} className="py-2 pr-4">
                        {formatNumber(photo.clicks || 0)}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b">
                    <td className="py-2 pr-4 text-muted-foreground">CTR</td>
                    {item.photos.map((photo) => (
                      <td key={photo.order} className="py-2 pr-4 font-semibold">
                        {Number(photo.ctr || 0).toFixed(2)}%
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="py-2 pr-4 text-muted-foreground">
                      В сравнении с лучшим CTR
                    </td>
                    {item.photos.map((photo) => {
                      if (bestCtr <= 0)
                        return (
                          <td key={photo.order} className="py-2 pr-4">
                            —
                          </td>
                        );
                      if (bestPhotoOrder === photo.order)
                        return (
                          <td key={photo.order} className="py-2 pr-4">
                            <Badge>
                              <Trophy className="mr-1 h-3 w-3" />
                              Лучший
                            </Badge>
                          </td>
                        );
                      const diff =
                        ((Number(photo.ctr || 0) - bestCtr) / bestCtr) * 100;
                      return (
                        <td
                          key={photo.order}
                          className="py-2 pr-4 text-muted-foreground"
                        >
                          {diff > 0 ? "+" : ""}
                          {diff.toFixed(1)}%
                        </td>
                      );
                    })}
                  </tr>
                </tbody>
              </table>
            </CardContent>
          </Card>

          <Alert>
            <AlertDescription>
              Тест работает последовательно: в карточке держим максимум 1
              тестовое фото. Загружаем, делаем главным, собираем статистику,
              переключаемся на следующее.
            </AlertDescription>
          </Alert>
        </div>
      ) : null}
    </PageShell>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="mt-1 text-xl font-semibold">{value}</div>
      </CardContent>
    </Card>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/30 p-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}

function normalizeStatus(status?: string) {
  const raw = String(status || "").toLowerCase();
  if (raw.includes("running")) return "running";
  if (raw.includes("finish") || raw.includes("completed")) return "finished";
  if (raw.includes("failed")) return "failed";
  if (raw.includes("stop")) return "stopped";
  return "pending";
}

function winnerBanner(
  status: string,
  decision?: string | null,
  lastError?: string | null,
) {
  const normalized = normalizeStatus(status);
  if (normalized === "running" || normalized === "pending") {
    return {
      tone: "muted",
      title: "Тест в процессе",
      text: "Победитель будет определён после окончания серии тестов.",
      subtext:
        "Ниже показана промежуточная статистика без финального объявления победителя.",
    };
  }
  if (decision === "winner_found") {
    return {
      tone: "success",
      title: "Победитель найден",
      text: "Система определила лучший вариант по CTR и накопленной статистике.",
      subtext: "Ниже показаны финальные результаты теста по всем фото.",
    };
  }
  if (decision === "no_clear_winner") {
    return {
      tone: "warning",
      title: "Явного победителя нет",
      text: "Разница между вариантами получилась слишком близкой.",
      subtext:
        "Рекомендуется собрать больше показов или протестировать новые фото.",
    };
  }
  if (decision === "insufficient_data") {
    return {
      tone: "info",
      title: "Недостаточно данных",
      text: "Тест завершён, но статистики пока недостаточно для уверенного вывода.",
      subtext:
        "Можно запустить тест повторно с большим количеством показов на фото.",
    };
  }
  if (normalized === "failed" || normalized === "stopped") {
    return {
      tone: "danger",
      title:
        normalized === "failed" ? "Тест завершился ошибкой" : "Тест остановлен",
      text: lastError || "Серия тестов была прервана до финального сравнения.",
      subtext: "При необходимости тест можно перезапустить из этого же экрана.",
    };
  }
  return {
    tone: "muted",
    title: "Итоги теста",
    text: "Статистика по фото собрана и готова для просмотра.",
    subtext: "Сравнение ниже поможет быстро увидеть лучший результат.",
  };
}

function PhotoStatusBadge({
  isCurrent,
  isBest,
  hasShows,
}: {
  isCurrent: boolean;
  isBest: boolean;
  hasShows: boolean;
}) {
  if (isCurrent)
    return (
      <Badge>
        <CircleDot className="mr-1 h-3 w-3" />
        Тестируется
      </Badge>
    );
  if (isBest)
    return (
      <Badge>
        <Trophy className="mr-1 h-3 w-3" />
        Лучший
      </Badge>
    );
  if (hasShows)
    return (
      <Badge variant="outline">
        <Eye className="mr-1 h-3 w-3" />
        Нормально
      </Badge>
    );
  return <Badge variant="secondary">Ожидание</Badge>;
}

function statusLabel(status: string, decision?: string | null) {
  if (decision === "winner_found") return "Победитель выбран";
  if (decision === "insufficient_data") return "Мало данных";
  if (decision === "no_clear_winner") return "Без явного лидера";
  const normalized = normalizeStatus(status);
  if (normalized === "running") return "Запущен";
  if (normalized === "finished") return "Завершён";
  if (normalized === "stopped") return "Остановлен";
  if (normalized === "failed") return "Ошибка";
  return "Ожидает";
}
