// @ts-nocheck
/**
 * Product360 — верхняя карточка товара.
 *
 * Единая идентичность товара + статус + безопасные действия.
 * Не тянет данные, работает поверх `data` из /portal/product/...
 * Никаких выдуманных эндпоинтов. Кнопка недоступна → disabled + причина.
 */
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  ExternalLink,
  ImageOff,
  ListChecks,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatMoney } from "@/lib/format";
import { proxyWbImageUrl } from "@/lib/wb-images";

/** WB basket hosts for image CDN fallback (nmId → basket). */
function wbBasketHost(vol: number): string {
  if (vol <= 143) return "basket-01.wbbasket.ru";
  if (vol <= 287) return "basket-02.wbbasket.ru";
  if (vol <= 431) return "basket-03.wbbasket.ru";
  if (vol <= 719) return "basket-04.wbbasket.ru";
  if (vol <= 1007) return "basket-05.wbbasket.ru";
  if (vol <= 1061) return "basket-06.wbbasket.ru";
  if (vol <= 1115) return "basket-07.wbbasket.ru";
  if (vol <= 1169) return "basket-08.wbbasket.ru";
  if (vol <= 1313) return "basket-09.wbbasket.ru";
  if (vol <= 1601) return "basket-10.wbbasket.ru";
  if (vol <= 1655) return "basket-11.wbbasket.ru";
  if (vol <= 1919) return "basket-12.wbbasket.ru";
  if (vol <= 2045) return "basket-13.wbbasket.ru";
  if (vol <= 2189) return "basket-14.wbbasket.ru";
  if (vol <= 2405) return "basket-15.wbbasket.ru";
  if (vol <= 2621) return "basket-16.wbbasket.ru";
  if (vol <= 2837) return "basket-17.wbbasket.ru";
  return "basket-18.wbbasket.ru";
}
function wbImageCandidates(nmId: string | number): string[] {
  const n = Number(nmId);
  if (!Number.isFinite(n) || n <= 0) return [];
  const vol = Math.floor(n / 100000);
  const part = Math.floor(n / 1000);
  const host = wbBasketHost(vol);
  return [
    `https://${host}/vol${vol}/part${part}/${n}/images/big/1.webp`,
    `https://${host}/vol${vol}/part${part}/${n}/images/c516x688/1.webp`,
  ];
}

function ProductHeroImage({
  src,
  nmId,
  alt,
}: {
  src?: string | null;
  nmId: string | number;
  alt: string;
}) {
  const candidates = useMemo(
    () =>
      [src, ...wbImageCandidates(nmId)]
        .filter((v): v is string => typeof v === "string" && v.length > 0)
        .map((value) => proxyWbImageUrl(value))
        .filter((v): v is string => typeof v === "string" && v.length > 0),
    [src, nmId],
  );
  const [idx, setIdx] = useState(0);
  if (candidates.length === 0 || idx >= candidates.length) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-1 bg-muted text-muted-foreground">
        <ImageOff className="h-6 w-6 opacity-70" />
        <span className="text-[10px] font-medium uppercase tracking-wide">
          Нет фото
        </span>
      </div>
    );
  }
  return (
    <img
      key={candidates[idx]}
      src={candidates[idx]}
      alt={alt}
      loading="lazy"
      className="h-full w-full object-cover"
      onError={() => setIdx((i) => i + 1)}
    />
  );
}

function txt(v: unknown, fb = ""): string {
  const s = String(v ?? "").trim();
  return s || fb;
}

function pick<T = unknown>(obj: any, keys: string[]): T | undefined {
  if (!obj || typeof obj !== "object") return undefined;
  for (const k of keys) {
    const v = obj[k];
    if (v !== undefined && v !== null && v !== "") return v as T;
  }
  return undefined;
}

function formatDate(v: unknown): string | null {
  if (!v) return null;
  const d = new Date(String(v));
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

type HealthState =
  | "critical"
  | "missing_data"
  | "waiting_recheck"
  | "ok"
  | "unknown";

export interface ProductHeaderCardProps {
  nmId: string | number;
  identity?: any;
  business?: any;
  dataQuality?: any;
  cardQuality?: any;
  stock?: any;
  price?: any;
  image?: string | null;
  onCreateTask?: () => void;
  className?: string;
}

const STATUS_STYLE: Record<HealthState, string> = {
  critical: "border-destructive/40 bg-destructive/10 text-destructive",
  missing_data:
    "border-amber-500/40 bg-amber-500/10 text-amber-800 dark:text-amber-200",
  waiting_recheck:
    "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  ok: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  unknown: "border-border bg-muted text-muted-foreground",
};

const STATUS_LABEL: Record<HealthState, string> = {
  critical: "Предварительная оценка: есть критичные проблемы",
  missing_data: "Не хватает данных для оценки",
  waiting_recheck: "Ждёт перепроверки",
  ok: "По текущим данным проблем не найдено",
  unknown: "Требует проверки",
};

function computeHealthState(business: any, dataQuality: any): HealthState {
  const bi = business?.data ?? business ?? {};
  const summary = bi?.summary ?? {};
  const openCount = Number(summary?.open_count ?? bi?.open?.length ?? 0);
  const confirmed = Number(summary?.money_impact?.confirmed_loss_amount ?? 0);
  const dqStatus = txt(
    dataQuality?.status ?? dataQuality?.data?.status,
  ).toLowerCase();
  const dqBlocked =
    dqStatus === "blocked" || Number(dataQuality?.data?.missing_count ?? 0) > 0;
  if (confirmed > 0 || openCount > 3) return "critical";
  if (dqBlocked) return "missing_data";
  const recheckPending = Array.isArray(bi?.open)
    ? bi.open.some(
        (it: any) =>
          txt(it?.status).toLowerCase() === "in_progress" ||
          txt(it?.status).toLowerCase() === "waiting_recheck",
      )
    : false;
  if (recheckPending) return "waiting_recheck";
  if (openCount === 0 && !dqBlocked) return "ok";
  return "unknown";
}

export function ProductHeaderCard({
  nmId,
  identity,
  business,
  dataQuality,
  cardQuality,
  stock,
  price,
  image,
  onCreateTask,
  className,
}: ProductHeaderCardProps) {
  const id = identity?.data ?? identity ?? {};
  const name = pick<string>(id, ["title", "name"]) ?? `Артикул ${nmId}`;
  const vendorCode = pick<string>(id, [
    "vendor_code",
    "article",
    "supplier_article",
  ]);
  const brand = pick<string>(id, ["brand"]);
  const subject = pick<string>(id, ["subject_name", "subject", "category"]);
  const barcode = pick<string>(id, ["barcode", "barcodes", "sku_barcode"]);
  const wbUrl = pick<string>(id, [
    "wb_url",
    "external_url",
    "url",
    "wildberries_url",
  ]);

  const priceData = price?.data ?? price ?? {};
  const currentPrice = pick<number | string>({ ...id, ...priceData }, [
    "current_price",
    "price",
    "price_final",
    "price_after_discount",
  ]);

  const stockData = stock?.data ?? stock ?? {};
  const stockQty = pick<number>(stockData, [
    "quantity",
    "qty",
    "stock_qty",
    "available",
    "total_available",
  ]);

  const lastSync = pick<string>(
    { ...id, ...(dataQuality?.data ?? dataQuality ?? {}) },
    ["last_synced_at", "last_sync_at", "loaded_at", "updated_at"],
  );
  const freshness = pick<string>(
    { ...id, ...(dataQuality?.data ?? dataQuality ?? {}) },
    ["freshness_status", "freshness", "sync_status"],
  );

  const state = computeHealthState(business, dataQuality);

  const barcodeText = Array.isArray(barcode)
    ? String(barcode[0] ?? "")
    : txt(barcode);
  const priceText =
    currentPrice != null && currentPrice !== ""
      ? formatMoney(Number(currentPrice))
      : null;
  const stockText = Number.isFinite(Number(stockQty))
    ? `${stockQty} шт.`
    : null;
  const syncText = formatDate(lastSync);

  const openResultsHref = `/results?nm_id=${nmId}`;
  const checkerHref = `/checker/${nmId}`;

  return (
    <Card
      className={cn("border-border/60", className)}
      data-testid="product-header-card"
    >
      <CardContent className="p-3 sm:p-4">
        <div className="grid grid-cols-[80px_minmax(0,1fr)] gap-3 sm:grid-cols-[112px_minmax(0,1fr)_auto] sm:gap-4">
          {/* Изображение — с фолбэком на WB CDN, затем на заглушку. */}
          <div className="h-20 w-20 sm:h-28 sm:w-28 shrink-0 overflow-hidden rounded-lg border bg-muted">
            <ProductHeroImage
              src={image ?? null}
              nmId={nmId}
              alt={String(name)}
            />
          </div>

          {/* Идентичность и метрики */}
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="truncate text-base sm:text-lg font-semibold">
                {String(name)}
              </h2>
              <Badge
                variant="outline"
                className={cn("text-[10px]", STATUS_STYLE[state])}
                data-testid="product-header-status"
              >
                {STATUS_LABEL[state]}
              </Badge>
            </div>

            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span className="font-mono">nmID {nmId}</span>
              {vendorCode ? (
                <span className="font-mono">арт. {vendorCode}</span>
              ) : null}
              {barcodeText ? (
                <span className="font-mono">штрихкод {barcodeText}</span>
              ) : null}
              {brand ? <span>Бренд: {brand}</span> : null}
              {subject ? <span>Категория: {subject}</span> : null}
            </div>

            <div className="flex flex-wrap items-center gap-1.5">
              {priceText ? (
                <Badge variant="outline" className="text-[10px]">
                  Цена: {priceText}
                </Badge>
              ) : null}
              {stockText ? (
                <Badge variant="outline" className="text-[10px]">
                  Остаток: {stockText}
                </Badge>
              ) : null}
              {syncText ? (
                <Badge variant="outline" className="text-[10px]">
                  Синхронизация: {syncText}
                </Badge>
              ) : null}
              {freshness ? (
                <Badge variant="outline" className="text-[10px]">
                  {String(freshness)}
                </Badge>
              ) : null}
            </div>
          </div>

          {/* Действия — desktop справа, mobile снизу */}
          <div className="col-span-2 flex flex-wrap items-center gap-1.5 sm:col-span-1 sm:justify-end">
            {wbUrl ? (
              <Button
                asChild
                size="sm"
                variant="outline"
                className="h-8 text-xs"
              >
                <a href={String(wbUrl)} target="_blank" rel="noreferrer">
                  <ExternalLink className="mr-1 h-3.5 w-3.5" /> Открыть в WB
                </a>
              </Button>
            ) : (
              <Button
                size="sm"
                variant="outline"
                className="h-8 text-xs"
                disabled
                title="У товара нет публичной ссылки WB в данных карточки."
              >
                <ExternalLink className="mr-1 h-3.5 w-3.5" /> Открыть в WB
              </Button>
            )}
            <Button asChild size="sm" variant="outline" className="h-8 text-xs">
              <Link to={checkerHref}>
                <ShieldCheck className="mr-1 h-3.5 w-3.5" /> Проверить карточку
              </Link>
            </Button>
            <Button
              asChild
              size="sm"
              variant="outline"
              className="h-8 text-xs"
              data-testid="product-header-open-results"
            >
              <Link to={openResultsHref}>
                <ListChecks className="mr-1 h-3.5 w-3.5" /> Все результаты
              </Link>
            </Button>
            {onCreateTask ? (
              <Button size="sm" className="h-8 text-xs" onClick={onCreateTask}>
                Оформить задачу
              </Button>
            ) : null}
            <Button
              size="sm"
              variant="outline"
              className="h-8 text-xs"
              disabled
              title="Синхронизация товара будет доступна после подключения действия."
            >
              <RefreshCw className="mr-1 h-3.5 w-3.5" /> Синхронизировать
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
