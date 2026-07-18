import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAuth } from "@/lib/auth-context";
import { AppSidebar } from "@/components/AppSidebar";
import { AgentDock } from "@/components/agent/AgentDock";
import { GlobalTopBar } from "@/components/GlobalTopBar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { DateRangeProvider } from "@/lib/date-range-context";
import { getAccessToken } from "@/lib/api";
import { Loader2 } from "lucide-react";

export const Route = createFileRoute("/_authenticated")({
  beforeLoad: () => {
    if (typeof window === "undefined") return;
    if (!getAccessToken()) throw redirect({ to: "/login" });
  },
  component: AuthLayout,
});

function AuthLayout() {
  const { isAuthenticated, loading } = useAuth();
  const navigate = useNavigate();
  const [mounted, setMounted] = useState(false);
  const [slowLoading, setSlowLoading] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!loading) {
      setSlowLoading(false);
      return;
    }
    const id = window.setTimeout(() => setSlowLoading(true), 3000);
    return () => window.clearTimeout(id);
  }, [loading]);

  useEffect(() => {
    if (mounted && !loading && !isAuthenticated) navigate({ to: "/login" });
  }, [mounted, loading, isAuthenticated, navigate]);

  if (!mounted) {
    return <AuthLoadingState suppressHydrationWarning />;
  }

  if (loading) {
    return <AuthLoadingState slow={slowLoading} suppressHydrationWarning />;
  }
  if (!isAuthenticated) return null;

  return (
    <DateRangeProvider>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="min-w-0 overflow-x-hidden bg-background">
          <GlobalTopBar />
          <Outlet />
          <AgentDock />
        </SidebarInset>
      </SidebarProvider>
    </DateRangeProvider>
  );
}

function AuthLoadingState({
  slow = false,
  suppressHydrationWarning,
}: {
  slow?: boolean;
  suppressHydrationWarning?: boolean;
}) {
  return (
    <div
      className="flex min-h-screen items-center justify-center bg-background px-4"
      suppressHydrationWarning={suppressHydrationWarning}
    >
      <div className="flex max-w-sm flex-col items-center gap-3 rounded-lg border border-border/50 bg-card px-5 py-4 text-center shadow-sm">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        <div>
          <div className="text-sm font-medium text-foreground">
            Проверяем доступ
          </div>
          {slow && (
            <div className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Backend отвечает дольше обычного. Если страница не откроется,
              система вернёт вас на вход.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
