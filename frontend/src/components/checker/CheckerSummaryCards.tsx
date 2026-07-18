/**
 * CheckerSummaryCards — 6 сводных карточек качества карточки товара.
 *
 * Отвечают на: какая оценка, где ошибки контента, что с фото/характеристиками,
 * есть ли блокеры данных, какие возможности роста.
 *
 * Не подключается к API: считает всё из уже загруженного списка проблем.
 * Проблемы контента классифицируются как «Возможность/Оценка/Системное»,
 * а не как подтверждённый финансовый убыток.
 */
import type { LucideIcon } from "lucide-react";
import {
  Camera,
  ClipboardList,
  FileText,
  Gauge,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrustBadge, ImpactBadge } from "@/components/badges/StatusBadges";

type Issue = Record<string, any>;

function n(x: unknown): string {
  return x === null || x === undefined ? "" : String(x);
}
function norm(x: unknown): string {
  return n(x).trim().toLowerCase();
}
function sev(issue: Issue): number {
  const s = norm(issue?.severity);
  if (s === "critical" || s === "high") return 0;
  if (s === "warning" || s === "medium") return 1;
  return 2;
}
function isOpen(issue: Issue): boolean {
  const st = norm(issue?.status);
  return st === "" || st === "new" || st === "in_progress" || st === "open";
}

function classifyCategory(issue: Issue): string {
  const cat = norm(issue?.category ?? issue?.type);
  const path = norm(issue?.field_name ?? issue?.field_path);
  const code = norm(issue?.code ?? issue?.issue_code);
  if (path === "title" || cat === "title" || code.startsWith("title"))
    return "content";
  if (
    path === "description" ||
    cat === "description" ||
    code.startsWith("description") ||
    cat === "seo"
  )
    return "content";
  if (
    cat === "media" ||
    cat === "photo" ||
    cat === "photos" ||
    cat === "video" ||
    path.startsWith("photos") ||
    path.startsWith("videos")
  )
    return "media";
  if (
    path.startsWith("characteristics") ||
    cat === "characteristics" ||
    cat === "photo_mismatch"
  )
    return "chars";
  return "content";
}

function isDataBlocker(issue: Issue): boolean {
  // Признаки блокера данных: category/subject/required-поля отсутствуют,
  // либо явный признак от бэкенда.
  if (issue?.is_data_blocker === true) return true;
  if (issue?.blocks_calculation === true) return true;
  const code = norm(issue?.code ?? issue?.issue_code);
  if (
    code === "missing_category" ||
    code === "missing_subject" ||
    code === "missing_required_field" ||
    code === "required_field_missing"
  )
    return true;
  const conf = norm(issue?.confidence ?? issue?.trust_state);
  return conf === "blocked";
}

function isOpportunity(issue: Issue): boolean {
  // «Возможность роста» — низкая severity/improvement или явный impact_type
  if (norm(issue?.impact_type) === "opportunity") return true;
  const s = norm(issue?.severity);
  return s === "low" || s === "improvement" || s === "info";
}

export interface CheckerSummaryCardsProps {
  issues: Issue[];
  score?: number | null;
  lastCheckedAt?: string | null;
}

interface CardSpec {
  key: string;
  title: string;
  icon: LucideIcon;
  value: string;
  hint: string;
  trust?: "confirmed" | "provisional" | "estimated" | "blocked" | "opportunity";
  impact?:
    | "confirmed_loss"
    | "probable_loss"
    | "blocked_cash"
    | "opportunity"
    | "data_blocker"
    | "system_warning";
  tone: "success" | "warning" | "danger" | "info" | "muted";
}

function scoreTone(score: number | null | undefined): CardSpec["tone"] {
  if (score === null || score === undefined || Number.isNaN(Number(score)))
    return "muted";
  const s = Number(score);
  if (s >= 80) return "success";
  if (s >= 50) return "warning";
  return "danger";
}

function fmtDate(v: string | null | undefined): string {
  if (!v) return "—";
  try {
    return new Date(v).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return String(v);
  }
}

const TONE_BORDER: Record<CardSpec["tone"], string> = {
  success: "border-success/30",
  warning: "border-warning/30",
  danger: "border-destructive/30",
  info: "border-primary/30",
  muted: "border-border",
};

export function CheckerSummaryCards({
  issues,
  score,
  lastCheckedAt,
}: CheckerSummaryCardsProps) {
  const open = issues.filter(isOpen);

  const contentIssues = open.filter(
    (i) => classifyCategory(i) === "content" && !isDataBlocker(i),
  );
  const mediaIssues = open.filter(
    (i) => classifyCategory(i) === "media" && !isDataBlocker(i),
  );
  const charsIssues = open.filter(
    (i) => classifyCategory(i) === "chars" && !isDataBlocker(i),
  );
  const blockers = open.filter(isDataBlocker);
  const opportunities = open.filter(isOpportunity);

  const contentCritical = contentIssues.filter((i) => sev(i) === 0).length;
  const mediaCritical = mediaIssues.filter((i) => sev(i) === 0).length;
  const charsCritical = charsIssues.filter((i) => sev(i) === 0).length;

  const scoreVal =
    score === null || score === undefined || Number.isNaN(Number(score))
      ? "—"
      : `${Math.round(Number(score))}`;

  const cards: CardSpec[] = [
    {
      key: "score",
      title: "Оценка карточки",
      icon: Gauge,
      value: scoreVal,
      hint: lastCheckedAt
        ? `Проверено: ${fmtDate(lastCheckedAt)}`
        : "Проверка ещё не запускалась",
      trust: scoreVal === "—" ? "blocked" : "provisional",
      impact: "system_warning",
      tone: scoreTone(score),
    },
    {
      key: "content",
      title: "Ошибки контента",
      icon: FileText,
      value: `${contentIssues.length}`,
      hint:
        contentIssues.length === 0
          ? "Название и описание без замечаний"
          : `Критичных: ${contentCritical}`,
      trust: "provisional",
      impact: contentCritical > 0 ? "system_warning" : "opportunity",
      tone:
        contentCritical > 0
          ? "danger"
          : contentIssues.length > 0
            ? "warning"
            : "success",
    },
    {
      key: "media",
      title: "Фото и медиа",
      icon: Camera,
      value: `${mediaIssues.length}`,
      hint:
        mediaIssues.length === 0
          ? "Замечаний по фото и видео нет"
          : `Критичных: ${mediaCritical}`,
      trust: "provisional",
      impact: mediaCritical > 0 ? "system_warning" : "opportunity",
      tone:
        mediaCritical > 0
          ? "danger"
          : mediaIssues.length > 0
            ? "warning"
            : "success",
    },
    {
      key: "chars",
      title: "Характеристики",
      icon: ClipboardList,
      value: `${charsIssues.length}`,
      hint:
        charsIssues.length === 0
          ? "Атрибуты заполнены корректно"
          : `Критичных: ${charsCritical}`,
      trust: "provisional",
      impact: charsCritical > 0 ? "system_warning" : "opportunity",
      tone:
        charsCritical > 0
          ? "danger"
          : charsIssues.length > 0
            ? "warning"
            : "success",
    },
    {
      key: "blockers",
      title: "Блокеры данных",
      icon: ShieldAlert,
      value: `${blockers.length}`,
      hint:
        blockers.length === 0
          ? "Все обязательные данные на месте"
          : "Не хватает категории, характеристик или обязательных полей",
      trust: "blocked",
      impact: "data_blocker",
      tone: blockers.length > 0 ? "warning" : "muted",
    },
    {
      key: "opportunities",
      title: "Возможности роста",
      icon: Sparkles,
      value: `${opportunities.length}`,
      hint:
        opportunities.length === 0
          ? "Рекомендаций пока нет"
          : "Не подтверждённый убыток — оценка потенциала",
      trust: "opportunity",
      impact: "opportunity",
      tone: opportunities.length > 0 ? "info" : "muted",
    },
  ];

  return (
    <div className="grid gap-3 grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {cards.map((c) => {
        const Icon = c.icon;
        return (
          <Card key={c.key} className={`border ${TONE_BORDER[c.tone]}`}>
            <CardContent className="p-3 space-y-2">
              <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                <Icon className="h-3.5 w-3.5" />
                <span className="truncate">{c.title}</span>
              </div>
              <div className="text-2xl font-semibold leading-none">
                {c.value}
              </div>
              <div className="flex flex-wrap items-center gap-1">
                {c.trust ? <TrustBadge value={c.trust} /> : null}
                {c.impact ? <ImpactBadge value={c.impact} /> : null}
              </div>
              <div className="text-[11px] leading-snug text-muted-foreground">
                {c.hint}
              </div>
              {c.key === "opportunities" && opportunities.length > 0 ? (
                <Badge
                  variant="outline"
                  className="text-[10px] border-primary/30"
                >
                  Возможность роста
                </Badge>
              ) : null}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
