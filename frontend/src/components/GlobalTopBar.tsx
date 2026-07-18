import { useState } from "react";
import { useLocation } from "@tanstack/react-router";
import {
  CalendarDays,
  ChevronDown,
  LogOut,
  Store,
  User as UserIcon,
} from "lucide-react";
import { format, parse } from "date-fns";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { TopBarSyncStatus } from "@/components/TopBarSyncStatus";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAccounts } from "@/lib/account-context";
import { useAuth } from "@/lib/auth-context";
import { useDateRange } from "@/lib/date-range-context";
import { cn } from "@/lib/utils";

const PRESETS = [
  { label: "7 дней", days: 7 },
  { label: "30 дней", days: 30 },
  { label: "60 дней", days: 60 },
  { label: "90 дней", days: 90 },
];

const PAGE_TITLES: Array<{ prefix: string; title: string; subtitle: string }> =
  [
    {
      prefix: "/dashboard",
      title: "Панель владельца",
      subtitle: "деньги, задачи, товары",
    },
    {
      prefix: "/action-center",
      title: "Фокус на сегодня",
      subtitle: "что требует внимания",
    },
    { prefix: "/money", title: "Деньги", subtitle: "прибыль, расходы, сверка" },
    {
      prefix: "/products",
      title: "Товары",
      subtitle: "карточки, риски, действия",
    },
    {
      prefix: "/checker",
      title: "Проверка карточек",
      subtitle: "контент и качество",
    },
    {
      prefix: "/data-fix",
      title: "Качество данных",
      subtitle: "синхронизация и ошибки",
    },
    { prefix: "/results", title: "Результаты", subtitle: "эффект решений" },
    {
      prefix: "/costs",
      title: "Себестоимость",
      subtitle: "закупочная цена и доверие к марже",
    },
    {
      prefix: "/pricing",
      title: "Цены",
      subtitle: "скидки, цена и риск маржи",
    },
    {
      prefix: "/purchase-plan",
      title: "Закупки",
      subtitle: "план поставок и потребность",
    },
    {
      prefix: "/ads",
      title: "Реклама",
      subtitle: "расход, DRR и вклад в прибыль",
    },
    {
      prefix: "/stock-control",
      title: "Остатки и поставки",
      subtitle: "склады, дефицит и перемещения",
    },
    { prefix: "/reputation", title: "Отзывы", subtitle: "репутация и ответы" },
    { prefix: "/claims", title: "Претензии", subtitle: "дефекты и разборы" },
    {
      prefix: "/photo-studio",
      title: "Фотостудия",
      subtitle: "визуалы карточек и генерации",
    },
    {
      prefix: "/ab-tests",
      title: "A/B тесты",
      subtitle: "эксперименты карточек",
    },
    {
      prefix: "/grouping",
      title: "Группировка",
      subtitle: "связи товаров и наборы",
    },
    {
      prefix: "/finance",
      title: "Финансы WB",
      subtitle: "сырьевые отчёты маркетплейса",
    },
    {
      prefix: "/expenses",
      title: "Расходы WB",
      subtitle: "детализация удержаний и трат",
    },
    { prefix: "/operations", title: "Операции", subtitle: "заказы и статусы" },
    { prefix: "/analytics", title: "Аналитика", subtitle: "сводные разрезы" },
    { prefix: "/marts", title: "Витрины", subtitle: "технические таблицы" },
    {
      prefix: "/admin/problem-rules",
      title: "Правила проблем",
      subtitle: "логика задач и сигналов",
    },
    {
      prefix: "/admin",
      title: "Администрирование",
      subtitle: "аккаунты, токены и пользователи",
    },
    {
      prefix: "/doctor",
      title: "Диагностика",
      subtitle: "legacy-разбор данных",
    },
    {
      prefix: "/cards",
      title: "Карточки WB",
      subtitle: "legacy-карточки и проверки",
    },
    {
      prefix: "/sku",
      title: "SKU / размер",
      subtitle: "детальная проверка позиции",
    },
    {
      prefix: "/catalog",
      title: "Товары",
      subtitle: "каталог открыт как технический deep link",
    },
    { prefix: "/settings", title: "Настройки", subtitle: "аккаунт и модули" },
  ];

function pageTitle(pathname: string) {
  return (
    PAGE_TITLES.find(
      (item) =>
        pathname === item.prefix || pathname.startsWith(`${item.prefix}/`),
    ) ?? { title: "Центр управления", subtitle: "операционное управление" }
  );
}

function fmtDate(iso: string) {
  try {
    return format(parse(iso, "yyyy-MM-dd", new Date()), "dd.MM.yyyy");
  } catch {
    return iso;
  }
}

function initials(name?: string | null, email?: string | null) {
  const src = (name || email || "?").trim();
  const parts = src.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return src.slice(0, 2).toUpperCase();
}

export function GlobalTopBar() {
  const location = useLocation();
  const { accounts, activeId, setActiveId, loading } = useAccounts();
  const { user, logout } = useAuth();
  const { from, to, setRange, setPreset } = useDateRange();
  const [open, setOpen] = useState(false);
  const [draftFrom, setDraftFrom] = useState(from);
  const [draftTo, setDraftTo] = useState(to);
  const page = pageTitle(location.pathname);

  return (
    <header className="sticky top-0 z-30 border-b border-border/70 bg-card/90 shadow-sm shadow-black/[0.025] backdrop-blur-xl">
      <div className="flex min-h-14 flex-wrap items-center gap-1.5 px-3 py-2 sm:min-h-16 sm:gap-2 sm:px-5 lg:flex-nowrap">
        <SidebarTrigger className="h-9 w-9 rounded-lg border border-border/70 bg-background shadow-sm shadow-black/[0.025] hover:bg-accent sm:h-10 sm:w-10" />

        <div className="hidden min-w-0 flex-col lg:flex">
          <div className="truncate text-[15px] font-semibold leading-5 text-foreground">
            {page.title}
          </div>
          <div className="flex items-center gap-2 truncate text-xs text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" />
            <span className="truncate">{page.subtitle}</span>
          </div>
        </div>

        <div className="ml-auto flex min-w-0 flex-1 flex-wrap items-center justify-end gap-2 lg:flex-none">
          <Select
            value={activeId ? String(activeId) : undefined}
            onValueChange={(v) => setActiveId(Number(v))}
            disabled={loading || !accounts.length}
          >
            <SelectTrigger className="h-9 w-[122px] rounded-lg border-border/70 bg-background px-2.5 shadow-sm shadow-black/[0.025] sm:h-10 sm:w-[230px]">
              <Store className="h-4 w-4 text-muted-foreground" />
              <SelectValue
                placeholder={loading ? "Загрузка…" : "Выберите аккаунт"}
              />
            </SelectTrigger>
            <SelectContent>
              {accounts.map((a) => (
                <SelectItem key={a.id} value={String(a.id)}>
                  <span className="flex items-center gap-2">
                    <span
                      className={cn(
                        "h-1.5 w-1.5 rounded-full",
                        a.is_active ? "bg-success" : "bg-muted-foreground/50",
                      )}
                    />
                    {a.name}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Popover
            open={open}
            onOpenChange={(v) => {
              setOpen(v);
              if (v) {
                setDraftFrom(from);
                setDraftTo(to);
              }
            }}
          >
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="h-9 w-[116px] justify-start gap-2 rounded-lg border-border/70 bg-background px-2.5 shadow-sm shadow-black/[0.025] hover:bg-accent sm:h-10 sm:w-auto"
              >
                <CalendarDays className="h-4 w-4 text-muted-foreground" />
                <span className="hidden tabular-nums sm:inline">
                  {fmtDate(from)} — {fmtDate(to)}
                </span>
                <span className="tabular-nums sm:hidden">{fmtDate(from)}</span>
                <ChevronDown className="hidden h-3 w-3 opacity-60 sm:block" />
              </Button>
            </PopoverTrigger>
            <PopoverContent
              className="w-[calc(100vw-2rem)] max-w-[430px] rounded-xl p-3"
              align="end"
            >
              <div className="flex flex-wrap gap-1.5 mb-3">
                {PRESETS.map((p) => (
                  <Button
                    key={p.days}
                    size="sm"
                    variant="outline"
                    className="h-8 rounded-lg"
                    onClick={() => {
                      setPreset(p.days);
                      setOpen(false);
                    }}
                  >
                    {p.label}
                  </Button>
                ))}
              </div>
              <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
                <div>
                  <div className="mb-1 text-xs text-muted-foreground">От</div>
                  <Input
                    type="date"
                    value={draftFrom}
                    onChange={(e) => setDraftFrom(e.target.value)}
                    className="h-9"
                  />
                </div>
                <div>
                  <div className="mb-1 text-xs text-muted-foreground">До</div>
                  <Input
                    type="date"
                    value={draftTo}
                    onChange={(e) => setDraftTo(e.target.value)}
                    className="h-9"
                  />
                </div>
                <Button
                  size="sm"
                  className="h-9 rounded-lg"
                  onClick={() => {
                    setRange(draftFrom, draftTo);
                    setOpen(false);
                  }}
                >
                  Применить
                </Button>
              </div>
            </PopoverContent>
          </Popover>

          <TopBarSyncStatus accountId={activeId} />

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-9 gap-2 rounded-lg px-1.5 hover:bg-accent sm:h-10 sm:w-auto sm:pr-2"
              >
                <Avatar className="h-7 w-7">
                  <AvatarFallback className="bg-primary/10 text-[11px] font-semibold text-primary">
                    {initials(user?.full_name, user?.email)}
                  </AvatarFallback>
                </Avatar>
                <span className="hidden max-w-[150px] truncate text-sm sm:inline">
                  {user?.full_name || user?.email || "Пользователь"}
                </span>
                <ChevronDown className="hidden h-3 w-3 opacity-60 sm:block" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel className="flex flex-col gap-0.5">
                <span className="text-sm">
                  {user?.full_name || "Пользователь"}
                </span>
                <span className="text-[11px] text-muted-foreground font-normal truncate">
                  {user?.email}
                </span>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <a
                  href="/settings"
                  className="flex items-center gap-2 cursor-pointer"
                >
                  <UserIcon className="h-3.5 w-3.5" />
                  Настройки аккаунта
                </a>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={logout}
                className="text-destructive focus:text-destructive cursor-pointer"
              >
                <LogOut className="h-3.5 w-3.5 mr-2" />
                Выйти
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}
