import { Link, useLocation } from "@tanstack/react-router";
import { useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  Boxes,
  Camera,
  ChevronDown,
  CircleDollarSign,
  ClipboardCheck,
  FileWarning,
  FlaskConical,
  Layers as LayersIcon,
  LineChart,
  Megaphone,
  MessageSquare,
  Network,
  Package,
  Receipt,
  Scale,
  Settings as SettingsIcon,
  ShieldAlert,
  ShoppingCart,
  Stethoscope,
  Tag,
  Target,
  TrendingUp,
  Truck,
  Wallet,
  type LucideIcon,
} from "lucide-react";

import {
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "@/components/ui/sidebar";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useAuth } from "@/lib/auth-context";
import { legacyDiagnosticsEnabled } from "@/lib/legacy-diagnostics";
import { useModuleStatus } from "@/lib/modules-health";
import { cn } from "@/lib/utils";

type NavItem = { to: string; label: string; icon: LucideIcon };
type BetaItemDef = NavItem & { module: string };

const sellerNav: readonly NavItem[] = [
  { to: "/dashboard", label: "Обзор", icon: Activity },
  { to: "/action-center", label: "Фокус на сегодня", icon: Target },
  { to: "/money", label: "Деньги", icon: CircleDollarSign },
  { to: "/products", label: "Товары", icon: Package },
  { to: "/checker", label: "Проверка карточек", icon: ClipboardCheck },
  { to: "/data-fix", label: "Качество данных", icon: ShieldAlert },
  { to: "/results", label: "Результаты", icon: TrendingUp },
];

const dataAndCostsNav: readonly NavItem[] = [
  { to: "/costs", label: "Себестоимость", icon: Wallet },
];

const commerceNav: readonly NavItem[] = [
  { to: "/pricing", label: "Цены", icon: Tag },
  { to: "/purchase-plan", label: "Закупки", icon: Truck },
  { to: "/ads", label: "Реклама", icon: Megaphone },
];

const betaNav: readonly BetaItemDef[] = [
  {
    to: "/stock-control",
    label: "Остатки и поставки",
    icon: Boxes,
    module: "stockops",
  },
  {
    to: "/reputation",
    label: "Отзывы",
    icon: MessageSquare,
    module: "reputation",
  },
  { to: "/claims", label: "Претензии", icon: FileWarning, module: "claims" },
  { to: "/photo-studio", label: "Фотостудия", icon: Camera, module: "photo" },
  {
    to: "/ab-tests",
    label: "A/B тесты",
    icon: FlaskConical,
    module: "experiments",
  },
  { to: "/grouping", label: "Группировка", icon: Network, module: "grouping" },
];

const superuserNav: readonly NavItem[] = [
  { to: "/finance", label: "Финансы Вайлдберриз", icon: Scale },
  { to: "/expenses", label: "Расходы Вайлдберриз", icon: Receipt },
];

const legacyDiagnosticsNav: readonly NavItem[] = [
  { to: "/doctor", label: "Диагностика (старая)", icon: Stethoscope },
  { to: "/cards", label: "Карточки Вайлдберриз (старые)", icon: LayersIcon },
];

const adminNav: readonly NavItem[] = [
  { to: "/settings", label: "Настройки", icon: SettingsIcon },
  { to: "/operations", label: "Операции", icon: ShoppingCart },
  { to: "/analytics", label: "Аналитика", icon: LineChart },
  { to: "/marts", label: "Витрины", icon: LayersIcon },
  { to: "/admin", label: "Администрирование", icon: SettingsIcon },
];

function isActivePath(pathname: string, to: string) {
  return pathname === to || pathname.startsWith(to + "/");
}

export interface SidebarNavContentProps {
  onNavigate?: () => void;
}

export function SidebarNavContent({ onNavigate }: SidebarNavContentProps) {
  const { user } = useAuth();
  const location = useLocation();

  const isSuperuser = !!user?.is_superuser;
  const betaModulesEnabled =
    isSuperuser || import.meta.env.VITE_ENABLE_BETA_MODULES === "true";

  const visibleCommerce = isSuperuser ? commerceNav : [];
  const visibleMore = isSuperuser
    ? [
        ...(legacyDiagnosticsEnabled() ? legacyDiagnosticsNav : []),
        ...superuserNav,
      ]
    : [];
  const visibleAdmin = isSuperuser
    ? adminNav
    : adminNav.filter((item) => item.to === "/settings");

  const dataActive = dataAndCostsNav.some((n) =>
    isActivePath(location.pathname, n.to),
  );
  const commerceActive = visibleCommerce.some((n) =>
    isActivePath(location.pathname, n.to),
  );
  const betaActive =
    betaModulesEnabled &&
    betaNav.some((n) => isActivePath(location.pathname, n.to));
  const moreActive = visibleMore.some((n) =>
    isActivePath(location.pathname, n.to),
  );
  const adminActive = visibleAdmin.some((n) =>
    isActivePath(location.pathname, n.to),
  );

  const [dataOpen, setDataOpen] = useState(dataActive);
  const [commerceOpen, setCommerceOpen] = useState(commerceActive);
  const [betaOpen, setBetaOpen] = useState(betaActive);
  const [moreOpen, setMoreOpen] = useState(moreActive);
  const [adminOpen, setAdminOpen] = useState(adminActive);

  useEffect(() => {
    if (dataActive) setDataOpen(true);
    if (commerceActive) setCommerceOpen(true);
    if (betaActive) setBetaOpen(true);
    if (moreActive) setMoreOpen(true);
    if (adminActive) setAdminOpen(true);
  }, [adminActive, betaActive, commerceActive, dataActive, moreActive]);

  return (
    <SidebarContent className="gap-0.5 px-3 py-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      <SidebarGroup className="px-1 py-0.5">
        <SidebarGroupLabel className="h-5 px-2 text-[10px] font-semibold uppercase text-muted-foreground">
          Главное
        </SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            {sellerNav.map((item) => (
              <NavLink
                key={item.to}
                item={item}
                pathname={location.pathname}
                onNavigate={onNavigate}
              />
            ))}
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      <CollapsibleGroup
        label="Данные"
        open={dataOpen}
        onOpenChange={setDataOpen}
        active={dataActive}
      >
        {dataAndCostsNav.map((item) => (
          <SubNavLink
            key={item.to}
            item={item}
            pathname={location.pathname}
            onNavigate={onNavigate}
          />
        ))}
      </CollapsibleGroup>

      {visibleCommerce.length > 0 && (
        <CollapsibleGroup
          label="Коммерция"
          open={commerceOpen}
          onOpenChange={setCommerceOpen}
          active={commerceActive}
        >
          {visibleCommerce.map((item) => (
            <SubNavLink
              key={item.to}
              item={item}
              pathname={location.pathname}
              onNavigate={onNavigate}
            />
          ))}
        </CollapsibleGroup>
      )}

      {betaModulesEnabled && (
        <CollapsibleGroup
          label="Рост и операции"
          open={betaOpen}
          onOpenChange={setBetaOpen}
          active={betaActive}
        >
          {betaNav.map((item) => (
            <BetaNavLink
              key={item.to}
              item={item}
              pathname={location.pathname}
              onNavigate={onNavigate}
            />
          ))}
        </CollapsibleGroup>
      )}

      {visibleMore.length > 0 && (
        <CollapsibleGroup
          label="Отчёты WB"
          open={moreOpen}
          onOpenChange={setMoreOpen}
          active={moreActive}
        >
          {visibleMore.map((item) => (
            <SubNavLink
              key={item.to}
              item={item}
              pathname={location.pathname}
              onNavigate={onNavigate}
            />
          ))}
        </CollapsibleGroup>
      )}

      {visibleAdmin.length > 0 && (
        <CollapsibleGroup
          label="Система"
          open={adminOpen}
          onOpenChange={setAdminOpen}
          active={adminActive}
        >
          {visibleAdmin.map((item) => (
            <SubNavLink
              key={item.to}
              item={item}
              pathname={location.pathname}
              onNavigate={onNavigate}
            />
          ))}
        </CollapsibleGroup>
      )}
    </SidebarContent>
  );
}

function CollapsibleGroup({
  label,
  open,
  onOpenChange,
  active,
  children,
}: {
  label: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <SidebarGroup className="px-1 py-0.5 group-data-[collapsible=icon]:hidden">
      <Collapsible open={open} onOpenChange={onOpenChange}>
        <CollapsibleTrigger
          className={cn(
            "flex h-6 w-full items-center justify-between rounded-lg px-2 text-[10px] font-semibold uppercase text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
            active && "bg-sidebar-accent text-sidebar-accent-foreground",
          )}
        >
          <span className="truncate">{label}</span>
          <ChevronDown
            className={cn(
              "h-3.5 w-3.5 shrink-0 transition-transform",
              open && "rotate-180",
            )}
          />
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-0.5">
          <SidebarMenuSub className="mx-2 gap-0.5 border-sidebar-border/70 px-2">
            {children}
          </SidebarMenuSub>
        </CollapsibleContent>
      </Collapsible>
    </SidebarGroup>
  );
}

function NavLink({
  item,
  pathname,
  onNavigate,
}: {
  item: NavItem;
  pathname: string;
  onNavigate?: () => void;
}) {
  const active = isActivePath(pathname, item.to);
  const Icon = item.icon;

  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        asChild
        isActive={active}
        tooltip={item.label}
        className={navButtonClass(active)}
      >
        <Link to={item.to} onClick={onNavigate}>
          <span className={navIconBoxClass(active)}>
            <Icon className="h-3.5 w-3.5" />
          </span>
          <span className="truncate">{item.label}</span>
        </Link>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

function SubNavLink({
  item,
  pathname,
  onNavigate,
}: {
  item: NavItem;
  pathname: string;
  onNavigate?: () => void;
}) {
  const active = isActivePath(pathname, item.to);
  const Icon = item.icon;

  return (
    <SidebarMenuSubItem>
      <SidebarMenuSubButton
        asChild
        isActive={active}
        className={cn(
          "h-7 rounded-lg px-2 text-[12.5px] font-medium",
          active
            ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-sm shadow-primary/10"
            : "text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        )}
      >
        <Link to={item.to} onClick={onNavigate}>
          <span className={subNavIconBoxClass(active)}>
            <Icon className="h-3.5 w-3.5" />
          </span>
          <span className="truncate">{item.label}</span>
        </Link>
      </SidebarMenuSubButton>
    </SidebarMenuSubItem>
  );
}

function BetaNavLink({
  item,
  pathname,
  onNavigate,
}: {
  item: BetaItemDef;
  pathname: string;
  onNavigate?: () => void;
}) {
  const { visible } = useModuleStatus(item.module);
  if (!visible) return null;

  const active = isActivePath(pathname, item.to);
  const Icon = item.icon;

  return (
    <SidebarMenuSubItem>
      <SidebarMenuSubButton
        asChild
        isActive={active}
        className={cn(
          "h-7 rounded-lg px-2 text-[12.5px] font-medium",
          active
            ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-sm shadow-primary/10"
            : "text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        )}
      >
        <Link to={item.to} onClick={onNavigate} data-nav-module={item.module}>
          <span className={subNavIconBoxClass(active)}>
            <Icon className="h-3.5 w-3.5" />
          </span>
          <span className="truncate">{item.label}</span>
        </Link>
      </SidebarMenuSubButton>
    </SidebarMenuSubItem>
  );
}

function navButtonClass(active: boolean) {
  return cn(
    "relative h-9 rounded-lg px-2 text-[13px] font-medium transition-colors",
    active
      ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-sm shadow-primary/10 before:absolute before:bottom-2 before:left-0 before:top-2 before:w-1 before:rounded-full before:bg-primary hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
      : "text-sidebar-foreground/78 hover:bg-sidebar-accent/80 hover:text-sidebar-accent-foreground",
  );
}

function navIconBoxClass(active: boolean) {
  return cn(
    "flex h-6 w-6 shrink-0 items-center justify-center rounded-md transition-colors",
    active
      ? "bg-primary text-primary-foreground shadow-sm shadow-primary/20"
      : "bg-sidebar-accent/45 text-muted-foreground group-hover/menu-item:bg-sidebar-accent group-hover/menu-item:text-sidebar-accent-foreground",
  );
}

function subNavIconBoxClass(active: boolean) {
  return cn(
    "flex h-5 w-5 shrink-0 items-center justify-center rounded-md transition-colors",
    active
      ? "bg-primary/12 text-primary"
      : "bg-transparent text-muted-foreground",
  );
}
