/**
 * CheckerCrossSections — сквозные группы проверки карточки товара.
 *
 * Показывает 9 групп из спецификации Phase 7.1:
 *   Название · Описание · Характеристики · Фото и медиа · Категория ·
 *   Заполненность · Блокеры данных · Возможности роста · Системные проверки
 *
 * Один issue может подпадать под несколько групп — показываем в наиболее
 * операционной по приоритету:
 *   1) Блокеры данных
 *   2) Системные проверки
 *   3) контентная группа (Название/Описание/Характеристики/Фото/Категория/Заполненность)
 *   4) Возможности роста
 *
 * Все состояния — через shared `EmptyState`; пустой текст группы —
 * «В этой группе проблем нет.». Копии по спецификации:
 *   - Возможность роста
 *   - Оценка
 *   - Блокер данных
 *   - Системное предупреждение
 *   - Не подтверждённый убыток
 */
import type { LucideIcon } from "lucide-react";
import {
  ArrowRight,
  Camera,
  ClipboardList,
  Cpu,
  FileText,
  Layers3,
  ListChecks,
  ShieldAlert,
  Sparkles,
  Tag,
  Type,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  type EmptyStateVariant,
} from "@/components/shell/EmptyState";

type Issue = Record<string, any>;

function n(x: unknown): string {
  return x === null || x === undefined ? "" : String(x);
}
function norm(x: unknown): string {
  return n(x).trim().toLowerCase();
}
function isOpen(issue: Issue): boolean {
  const st = norm(issue?.status);
  return st === "" || st === "new" || st === "in_progress" || st === "open";
}
function isDone(issue: Issue): boolean {
  const st = norm(issue?.status);
  return st === "done" || st === "resolved";
}

function isDataBlocker(issue: Issue): boolean {
  if (issue?.is_data_blocker === true) return true;
  if (issue?.blocks_calculation === true) return true;
  if (norm(issue?.impact_type) === "data_blocker") return true;
  const code = norm(issue?.code ?? issue?.issue_code);
  if (
    code === "missing_category" ||
    code === "missing_subject" ||
    code === "missing_required_field" ||
    code === "required_field_missing"
  )
    return true;
  return norm(issue?.confidence ?? issue?.trust_state) === "blocked";
}
function isSystemWarning(issue: Issue): boolean {
  if (norm(issue?.impact_type) === "system_warning") return true;
  if (issue?.requires_human_check === true) return true;
  const code = norm(issue?.code ?? issue?.issue_code);
  if (code.startsWith("ai_") || code.startsWith("detector_")) return true;
  const kind = norm(issue?.suggestion_kind);
  return kind === "candidate";
}
function isOpportunity(issue: Issue): boolean {
  if (norm(issue?.impact_type) === "opportunity") return true;
  const s = norm(issue?.severity);
  return s === "low" || s === "improvement" || s === "info";
}

type GroupKey =
  | "title"
  | "description"
  | "characteristics"
  | "media"
  | "category"
  | "completeness"
  | "blockers"
  | "opportunities"
  | "system";

interface GroupSpec {
  key: GroupKey;
  label: string;
  hint: string;
  icon: LucideIcon;
  impactLabel: string; // человекочитаемая метка «На что влияет?»
  trustLabel: string; // «Это факт или оценка?»
}

const GROUPS: GroupSpec[] = [
  {
    key: "blockers",
    label: "Блокеры данных",
    hint: "Обязательные данные отсутствуют — часть проверок не может отработать.",
    icon: ShieldAlert,
    impactLabel: "Блокер данных",
    trustLabel: "Не хватает данных",
  },
  {
    key: "system",
    label: "Системные проверки",
    hint: "Сервисные предупреждения: низкое доверие детектора, требует проверки человеком, тестовые правила.",
    icon: Cpu,
    impactLabel: "Системное предупреждение",
    trustLabel: "Требует проверки человеком",
  },
  {
    key: "title",
    label: "Название",
    hint: "Проверки заголовка карточки: длина, повторы, политика WB.",
    icon: Type,
    impactLabel: "Возможность роста",
    trustLabel: "Проверка по правилу",
  },
  {
    key: "description",
    label: "Описание",
    hint: "SEO и содержательность описания, ограничения WB.",
    icon: FileText,
    impactLabel: "Возможность роста",
    trustLabel: "Проверка по правилу",
  },
  {
    key: "characteristics",
    label: "Характеристики",
    hint: "Атрибуты и значения характеристик WB.",
    icon: ClipboardList,
    impactLabel: "Оценка",
    trustLabel: "Проверка по правилу",
  },
  {
    key: "media",
    label: "Фото и медиа",
    hint: "Изображения, инфографика, видео и обложка карточки.",
    icon: Camera,
    impactLabel: "Возможность роста",
    trustLabel: "Требует проверки человеком",
  },
  {
    key: "category",
    label: "Категория",
    hint: "Соответствие категории и сабжа WB, ошибки классификации.",
    icon: Tag,
    impactLabel: "Оценка",
    trustLabel: "AI-рекомендация",
  },
  {
    key: "completeness",
    label: "Заполненность",
    hint: "Обязательные поля, размеры, комплект, документы.",
    icon: Layers3,
    impactLabel: "Оценка",
    trustLabel: "Проверка по правилу",
  },
  {
    key: "opportunities",
    label: "Возможности роста",
    hint: "Не подтверждённый убыток, а оценка потенциала: SEO, дополнительные фото, ключевые слова.",
    icon: Sparkles,
    impactLabel: "Возможность роста",
    trustLabel: "Возможность, не факт убытка",
  },
];

function contentGroup(issue: Issue): GroupKey {
  const path = norm(issue?.field_name ?? issue?.field_path);
  const cat = norm(issue?.category ?? issue?.type);
  const code = norm(issue?.code ?? issue?.issue_code);
  if (path === "title" || cat === "title" || code.startsWith("title"))
    return "title";
  if (
    path === "description" ||
    cat === "description" ||
    cat === "seo" ||
    code.startsWith("description")
  )
    return "description";
  if (
    cat === "media" ||
    cat === "photo" ||
    cat === "photos" ||
    cat === "video" ||
    path.startsWith("photos") ||
    path.startsWith("videos")
  )
    return "media";
  if (cat === "category" || cat === "subject" || code.includes("category"))
    return "category";
  if (
    path.startsWith("characteristics") ||
    cat === "characteristics" ||
    cat === "photo_mismatch"
  )
    return "characteristics";
  const isCompleteness =
    code.includes("required") ||
    code.includes("missing") ||
    code.includes("package") ||
    code.includes("docs") ||
    code.includes("size") ||
    code.includes("dimension");
  if (isCompleteness) return "completeness";
  return "characteristics";
}

function classify(issue: Issue): GroupKey {
  if (isDataBlocker(issue)) return "blockers";
  if (isSystemWarning(issue)) return "system";
  if (isOpportunity(issue)) return "opportunities";
  return contentGroup(issue);
}

type CheckerEmptyKind = EmptyStateVariant;

const GLOBAL_EMPTY: Record<
  CheckerEmptyKind,
  { title: string; hint: string }
> = {
  needs_sync: {
    title: "Нужна синхронизация",
    hint: "Обновите карточки, чтобы платформа могла проверить контент и характеристики.",
  },
  no_data: {
    title: "Нет данных карточки",
    hint: "Платформа пока не получила данные по этой карточке.",
  },
  no_problems: {
    title: "Проблем не найдено",
    hint: "По текущим правилам активных проблем в карточке нет.",
  },
  missing_data: {
    title: "Не хватает данных",
    hint: "Проверка недоступна без категории, характеристик или свежей синхронизации.",
  },
  disabled: {
    title: "Проверка карточек отключена",
    hint: "Этот раздел недоступен для текущего аккаунта или роли.",
  },
  beta: {
    title: "Бета-модуль",
    hint: "Часть проверок карточек доступна только в бета-режиме.",
  },
  error: {
    title: "Не удалось проверить карточку",
    hint: "Проверьте подключение или повторите попытку.",
  },
};

export interface CheckerCrossSectionsProps {
  issues: Issue[];
  nmId: string | number | null | undefined;
  loading?: boolean;
  hasError?: boolean;
  needsSync?: boolean;
  moduleDisabled?: boolean;
  isBeta?: boolean;
  missingCoreData?: boolean;
  onRetry?: () => void;
  className?: string;
}

function pickGlobalEmpty(p: CheckerCrossSectionsProps): CheckerEmptyKind {
  if (p.hasError) return "error";
  if (p.moduleDisabled) return "disabled";
  if (p.isBeta) return "beta";
  if (p.needsSync) return "needs_sync";
  if (p.missingCoreData) return "missing_data";
  if (!p.issues || p.issues.length === 0) return "no_data";
  return "no_problems";
}

function titleOf(issue: Issue): string {
  return n(issue?.title ?? issue?.code ?? issue?.issue_code ?? "Проблема");
}
function fieldOf(issue: Issue): string {
  return n(issue?.field_name ?? issue?.field_path ?? "");
}

export function CheckerCrossSections(props: CheckerCrossSectionsProps) {
  const { issues, nmId, className } = props;
  const list = issues ?? [];
  const open = list.filter(isOpen);

  const openByGroup = new Map<GroupKey, Issue[]>();
  const doneByGroup = new Map<GroupKey, number>();
  for (const g of GROUPS) {
    openByGroup.set(g.key, []);
    doneByGroup.set(g.key, 0);
  }
  for (const issue of open) openByGroup.get(classify(issue))!.push(issue);
  for (const issue of list.filter(isDone)) {
    const k = classify(issue);
    doneByGroup.set(k, (doneByGroup.get(k) ?? 0) + 1);
  }

  const nothing = open.length === 0;
  if (nothing) {
    const kind = pickGlobalEmpty(props);
    const cfg = GLOBAL_EMPTY[kind];
    return (
      <EmptyState
        variant={kind}
        title={cfg.title}
        hint={cfg.hint}
        onRetry={props.onRetry}
        className={className}
      />
    );
  }

  return (
    <div className={`space-y-3 ${className ?? ""}`}>
      {GROUPS.map((group) => {
        const items = openByGroup.get(group.key) ?? [];
        const done = doneByGroup.get(group.key) ?? 0;
        const Icon = group.icon;
        return (
          <Card key={group.key} className="border">
            <CardContent className="p-4 space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    <h3 className="text-sm font-semibold">{group.label}</h3>
                    <Badge variant="outline" className="text-[10px]">
                      Открытых: {items.length}
                    </Badge>
                    {done > 0 ? (
                      <Badge
                        variant="outline"
                        className="text-[10px] border-success/30 text-success"
                      >
                        Закрыто: {done}
                      </Badge>
                    ) : null}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {group.hint}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-1">
                  <Badge variant="outline" className="text-[10px]">
                    На что влияет: {group.impactLabel}
                  </Badge>
                  <Badge variant="outline" className="text-[10px]">
                    Это факт или оценка: {group.trustLabel}
                  </Badge>
                </div>
              </div>

              {items.length === 0 ? (
                <EmptyState
                  variant="no_problems"
                  title="В этой группе проблем нет."
                  hint="По текущим правилам активных проблем в этой группе не найдено."
                />
              ) : (
                <ul className="divide-y rounded-md border">
                  {items.slice(0, 8).map((issue, idx) => {
                    const key = String(issue?.id ?? issue?.code ?? idx);
                    const field = fieldOf(issue);
                    const cautious =
                      group.key === "blockers" &&
                      norm(issue?.impact_type) !== "data_blocker" &&
                      norm(issue?.trust_state) !== "blocked";
                    return (
                      <li
                        key={key}
                        className="flex flex-col gap-1 px-3 py-2 text-sm sm:flex-row sm:items-start sm:justify-between"
                      >
                        <div className="min-w-0">
                          <div className="truncate font-medium">
                            {titleOf(issue)}
                          </div>
                          {field ? (
                            <div className="truncate text-xs text-muted-foreground">
                              {field}
                            </div>
                          ) : null}
                          {cautious ? (
                            <div className="mt-1 text-[11px] text-warning">
                              Платформа считает это блокером по текущим
                              признакам.
                            </div>
                          ) : null}
                        </div>
                        <div className="flex shrink-0 flex-wrap items-center gap-1">
                          <Badge variant="outline" className="text-[10px]">
                            {group.impactLabel}
                          </Badge>
                          <Badge variant="outline" className="text-[10px]">
                            {group.trustLabel}
                          </Badge>
                        </div>
                      </li>
                    );
                  })}
                  {items.length > 8 ? (
                    <li className="px-3 py-2 text-xs text-muted-foreground">
                      И ещё {items.length - 8}. Раскройте раздел, чтобы увидеть
                      все.
                    </li>
                  ) : null}
                </ul>
              )}

              {nmId ? (
                <div className="flex flex-wrap justify-end gap-2">
                  {group.key === "blockers" ? (
                    <Button asChild variant="outline" size="sm">
                      <a
                        href={`/data-fix?nm_id=${encodeURIComponent(String(nmId))}`}
                      >
                        <ListChecks className="mr-1 h-3.5 w-3.5" />
                        Исправление данных
                      </a>
                    </Button>
                  ) : null}
                  <Button asChild variant="ghost" size="sm">
                    <a
                      href={`/results?source_module=checker&nm_id=${encodeURIComponent(String(nmId))}&section=${group.key}`}
                    >
                      Открыть результаты раздела
                      <ArrowRight className="ml-1 h-3.5 w-3.5" />
                    </a>
                  </Button>
                </div>
              ) : null}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
