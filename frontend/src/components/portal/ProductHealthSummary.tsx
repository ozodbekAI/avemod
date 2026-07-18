// @ts-nocheck
/**
 * Product360 — health summary.
 *
 * Компактный обзор 6 категорий по одному товару:
 * прибыльность, остатки, цена, реклама и промо, карточка, данные.
 * Каждая карточка отвечает за один вопрос:
 *   всё ли ок / сколько открытых проблем / короткая причина.
 *
 * Не тянет данные сам. Работает поверх business_issues / card_quality /
 * data_quality, которые уже приходят из /portal/product/... .
 */
import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  CircleHelp,
  Sparkles,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  portalActionToActionCenterItem,
  type ActionCenterItem,
} from "@/lib/action-center-contract";
import type { PortalAction } from "@/lib/portal";

type Status = "ok" | "problem" | "blocked" | "waiting_data" | "unknown";

type CategoryKey =
  | "profitability"
  | "stock"
  | "price"
  | "ads_promo"
  | "card"
  | "data";

const CATEGORY_TITLES: Record<CategoryKey, string> = {
  profitability: "Прибыльность",
  stock: "Остатки",
  price: "Цена",
  ads_promo: "Реклама и промо",
  card: "Карточка",
  data: "Данные",
};

const STATUS_TONE: Record<Status, string> = {
  ok: "border-emerald-500/30 bg-emerald-500/5",
  problem: "border-destructive/35 bg-destructive/5",
  blocked: "border-amber-500/40 bg-amber-500/5",
  waiting_data: "border-sky-500/30 bg-sky-500/5",
  unknown: "border-border bg-muted/30",
};

const STATUS_LABEL: Record<Status, string> = {
  ok: "Всё в порядке",
  problem: "Есть проблемы",
  blocked: "Заблокировано",
  waiting_data: "Ждём данных",
  unknown: "Нет данных",
};

const STATUS_ICON: Record<Status, ReactNode> = {
  ok: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />,
  problem: <AlertTriangle className="h-3.5 w-3.5 text-destructive" />,
  blocked: <CircleAlert className="h-3.5 w-3.5 text-amber-600" />,
  waiting_data: <CircleHelp className="h-3.5 w-3.5 text-sky-600" />,
  unknown: <CircleHelp className="h-3.5 w-3.5 text-muted-foreground" />,
};

function text(value: unknown, fallback = ""): string {
  const raw = String(value ?? "").trim();
  return raw || fallback;
}

function isResolved(a: ActionCenterItem): boolean {
  const raw = text(a.status).toLowerCase();
  return ["done", "resolved", "dismissed", "ignored", "closed"].includes(raw);
}

function categorize(a: ActionCenterItem): CategoryKey {
  const raw = text(a.source_kind).toLowerCase();
  const code = text(a.issue_code ?? a.problem_code ?? a.action_type).toLowerCase();
  const impact = text(a.impact_type).toLowerCase();
  const joined = `${raw} ${code} ${impact}`;
  if (
    joined.includes("data") ||
    joined.includes("missing_cost") ||
    joined.includes("blocker") ||
    joined.includes("unmatched_sku")
  )
    return "data";
  if (
    joined.includes("stock") ||
    joined.includes("overstock") ||
    joined.includes("depletion") ||
    joined.includes("dead_stock")
  )
    return "stock";
  if (joined.includes("price") || joined.includes("margin")) return "price";
  if (joined.includes("ads") || joined.includes("promo")) return "ads_promo";
  if (
    raw === "checker" ||
    joined.includes("content") ||
    joined.includes("card_quality") ||
    joined.includes("photo")
  )
    return "card";
  return "profitability";
}

function normalizeItems(items: unknown[] | undefined): ActionCenterItem[] {
  return (Array.isArray(items) ? items : [])
    .map((raw) => {
      if (!raw || typeof raw !== "object") return null;
      if ("source_kind" in raw && "evidence_state" in raw)
        return raw as ActionCenterItem;
      return portalActionToActionCenterItem(raw as PortalAction);
    })
    .filter((x): x is ActionCenterItem => !!x);
}

function pickSectionData<T>(section: unknown): T | null {
  if (!section) return null;
  if (typeof section === "object" && section && "data" in (section as any))
    return ((section as any).data ?? null) as T | null;
  return section as T;
}

function sectionStatus(section: unknown): string {
  if (!section || typeof section !== "object") return "";
  const s = section as any;
  return text(s.status).toLowerCase();
}

type CategoryCardProps = {
  category: CategoryKey;
  status: Status;
  openCount: number;
  reason?: string | null;
  href?: string | null;
};

function CategoryCard({
  category,
  status,
  openCount,
  reason,
  href,
}: CategoryCardProps) {
  const title = CATEGORY_TITLES[category];
  const body = (
    <Card
      className={cn(
        "flex h-full flex-col border transition-colors",
        STATUS_TONE[status],
        href && "cursor-pointer hover:border-primary/40",
      )}
    >
      <CardContent className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs font-semibold">{title}</div>
          <div className="flex items-center gap-1">
            {STATUS_ICON[status]}
          </div>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-muted-foreground">
            {STATUS_LABEL[status]}
          </span>
          {openCount > 0 ? (
            <Badge variant="outline" className="text-[10px]">
              открыто {openCount}
            </Badge>
          ) : null}
        </div>
        <div className="mt-auto text-[11px] leading-snug text-muted-foreground line-clamp-2 min-h-[2.25rem]">
          {reason ?? ""}
        </div>
      </CardContent>
    </Card>
  );
  if (!href) return body;
  return (
    <Link to={href} className="block no-underline">
      {body}
    </Link>
  );
}

export interface ProductHealthSummaryProps {
  businessIssues?: unknown;
  cardQuality?: unknown;
  dataQuality?: unknown;
  nmId: string | number;
}

export function ProductHealthSummary({
  businessIssues,
  cardQuality,
  dataQuality,
  nmId,
}: ProductHealthSummaryProps) {
  const biData = pickSectionData<any>(businessIssues) ?? {};
  const open = normalizeItems(biData.open);
  const resolved = normalizeItems(biData.resolved);
  const all = [...open, ...resolved];

  const cardStatus = sectionStatus(cardQuality);
  const dataStatus = sectionStatus(dataQuality);
  const cardData = pickSectionData<any>(cardQuality) ?? {};
  const dataData = pickSectionData<any>(dataQuality) ?? {};

  // Итог по 5 бизнес-категориям
  const buckets: Record<CategoryKey, ActionCenterItem[]> = {
    profitability: [],
    stock: [],
    price: [],
    ads_promo: [],
    card: [],
    data: [],
  };
  for (const item of all) {
    buckets[categorize(item)].push(item);
  }

  const categoryCard = (key: CategoryKey): CategoryCardProps => {
    const items = buckets[key];
    const openItems = items.filter((i) => !isResolved(i));
    if (key === "card") {
      const raw = cardStatus;
      const openIssues =
        Number(cardData?.open_issues_count ?? cardData?.open_count ?? NaN);
      const totalOpen =
        (Number.isFinite(openIssues) ? openIssues : 0) + openItems.length;
      if (raw === "blocked" || raw === "waiting_for_data")
        return {
          category: key,
          status: "blocked",
          openCount: totalOpen,
          reason: "Проверка карточки заблокирована",
          href: `/checker/${nmId}`,
        };
      if (raw === "not_configured" || raw === "disabled")
        return {
          category: key,
          status: "unknown",
          openCount: totalOpen,
          reason: "Модуль недоступен",
          href: null,
        };
      if (totalOpen > 0)
        return {
          category: key,
          status: "problem",
          openCount: totalOpen,
          reason: "Есть контентные возможности для роста",
          href: `/checker/${nmId}`,
        };
      return {
        category: key,
        status: raw ? "ok" : "unknown",
        openCount: 0,
        reason: raw ? "Замечаний нет" : null,
        href: `/checker/${nmId}`,
      };
    }
    if (key === "data") {
      const raw = dataStatus;
      const dqOpen = Number(
        dataData?.open_issues_count ??
          dataData?.open_count ??
          dataData?.missing_count ??
          NaN,
      );
      const totalOpen =
        (Number.isFinite(dqOpen) ? dqOpen : 0) + openItems.length;
      if (raw === "blocked" || totalOpen > 0)
        return {
          category: key,
          status: "blocked",
          openCount: totalOpen,
          reason: "Не хватает данных для точного расчёта",
          href: `/data-fix?nm_id=${nmId}`,
        };
      if (raw === "waiting_for_data" || raw === "needs_sync")
        return {
          category: key,
          status: "waiting_data",
          openCount: totalOpen,
          reason: "Ждём синхронизацию",
          href: null,
        };
      return {
        category: key,
        status: raw ? "ok" : "unknown",
        openCount: 0,
        reason: raw ? "Данные полные" : null,
        href: `/data-fix?nm_id=${nmId}`,
      };
    }
    if (openItems.length === 0)
      return {
        category: key,
        status: items.length === 0 ? "unknown" : "ok",
        openCount: 0,
        reason:
          items.length === 0 ? "Нет данных за период" : "Проблем не найдено",
        href: null,
      };
    const first = openItems[0];
    const reason = text(first.title) || text(first.short_summary) || null;
    return {
      category: key,
      status: "problem",
      openCount: openItems.length,
      reason,
      href: null,
    };
  };

  const cards: CategoryCardProps[] = (
    ["profitability", "stock", "price", "ads_promo", "card", "data"] as CategoryKey[]
  ).map(categoryCard);

  return (
    <section
      data-testid="product-health-summary"
      aria-label="Состояние товара по категориям"
      className="space-y-2"
    >
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Sparkles className="h-4 w-4 text-primary" />
        Состояние товара
      </div>
      <div className="grid auto-rows-fr grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {cards.map((c) => (
          <CategoryCard key={c.category} {...c} />
        ))}
      </div>
    </section>
  );
}
