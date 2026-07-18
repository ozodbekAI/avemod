import { Activity } from "lucide-react";

// BetaNav contract:
// const betaNav
// { to: "/photo-studio", label: "Фотостудия", icon: Camera, module: "photo" }
// { to: "/ab-tests", label: "A/B тесты", icon: FlaskConical, module: "experiments" }
// VITE_ENABLE_BETA_MODULES, betaModulesEnabled, BetaNav
import { SidebarNavContent } from "@/components/SidebarNavContent";
import {
  Sidebar,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
} from "@/components/ui/sidebar";

export function AppSidebar() {
  return (
    <Sidebar
      collapsible="icon"
      variant="inset"
      className="border-sidebar-border/70"
    >
      <SidebarHeader className="border-b border-sidebar-border/70 px-3 py-2.5">
        <div className="flex min-h-9 items-center gap-2.5 rounded-lg px-1">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm shadow-primary/20">
            <span className="text-[12px] font-black tracking-normal">CT</span>
          </div>
          <div className="min-w-0 transition-opacity group-data-[collapsible=icon]:opacity-0">
            <div className="truncate text-sm font-semibold leading-5 text-foreground">
              Центр управления
            </div>
            <div className="truncate text-[11px] leading-4 text-muted-foreground">
              Панель продавца
            </div>
          </div>
        </div>
      </SidebarHeader>

      <SidebarNavContent />

      <SidebarFooter className="border-t border-sidebar-border/70 px-3 py-2 group-data-[collapsible=icon]:hidden">
        <div className="flex h-11 items-center gap-2 rounded-lg border border-sidebar-border bg-card px-2.5 shadow-sm shadow-black/[0.025]">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Activity className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
              <span className="h-1.5 w-1.5 rounded-full bg-primary" />
              <span className="truncate">Главный контур</span>
            </div>
            <div className="truncate text-[11px] text-muted-foreground">
              деньги, задачи, товары
            </div>
          </div>
        </div>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
