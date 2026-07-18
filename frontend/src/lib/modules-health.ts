import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { JsonObject } from "./api";
import { useAccounts } from "./account-context";
import { API_ENDPOINTS } from "./endpoints";

export interface PortalModuleHealth {
  module: string;
  status:
    | "ok"
    | "degraded"
    | "not_configured"
    | "unavailable"
    | "disabled"
    | string;
  enabled?: boolean;
  configured?: boolean;
  visible?: boolean;
  beta?: boolean;
  navigation_group?: string;
  runtime_status?:
    | "disabled"
    | "not_configured"
    | "beta_readonly"
    | "beta_draft_only"
    | "enabled_safe"
    | "enabled_write_actions"
    | string;
  marketplace_write_policy?: JsonObject;
  message?: string | null;
  detail?: string | null;
  warnings?: string[];
  last_run_id?: number | null;
  last_success_at?: string | null;
  eligible_products?: number | null;
  unique_products_analyzed?: number | null;
  candidate_groups?: number | null;
  runtime_mode?: "local" | "external_adapter" | "disabled" | string;
  dangerous_actions_enabled?: boolean;
  publish_enabled?: boolean;
  auto_publish_enabled?: boolean;
  chat_send_enabled?: boolean;
}

const optionalAccountQuery = (accountId?: number | null) =>
  accountId != null ? { account_id: accountId } : {};

export const fetchModulesHealth = async (
  accountId?: number | null,
): Promise<PortalModuleHealth[]> => {
  const res = await api<any>(API_ENDPOINTS.portal.modulesHealth, {
    query: optionalAccountQuery(accountId),
  });
  if (!res) return [];
  if (Array.isArray(res)) return res as PortalModuleHealth[];
  if (res && typeof res === "object") {
    const modules = (res as any).modules ?? res;
    if (modules && typeof modules === "object" && !Array.isArray(modules)) {
      return Object.entries(modules).map(([key, value]) => {
        const moduleHealth = (value ?? {}) as any;
        return {
          ...moduleHealth,
          module: moduleHealth.module ?? key,
        } as PortalModuleHealth;
      });
    }
    if (Array.isArray((res as any).items)) return (res as any).items;
  }
  return [];
};

export function useModulesHealth() {
  const { activeId } = useAccounts();
  return useQuery({
    queryKey: ["portal", "modules-health", activeId],
    queryFn: () => fetchModulesHealth(activeId),
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
}

/** Returns true when the named module is visible (default true if backend has not reported it). */
export function useModuleVisible(name: string): boolean {
  const { data } = useModulesHealth();
  if (!data) return true;
  const moduleHealth = data.find((item) => item.module === name);
  if (!moduleHealth) return true;
  if (moduleHealth.visible === false) return false;
  return (
    moduleHealth.status !== "unavailable" &&
    moduleHealth.status !== "disabled"
  );
}

/** Returns the raw status fields for a named module, or nulls if unknown. */
export function useModuleStatus(name: string): {
  status: string | null;
  message: string | null;
  beta: boolean;
  visible: boolean;
  last_run_id?: number | null;
  last_success_at?: string | null;
  eligible_products?: number | null;
  unique_products_analyzed?: number | null;
  candidate_groups?: number | null;
  runtime_mode?: string | null;
  runtime_status?: string | null;
  marketplace_write_policy?: JsonObject | null;
  dangerous_actions_enabled: boolean;
  publish_enabled: boolean;
  auto_publish_enabled: boolean;
  chat_send_enabled: boolean;
} {
  const { data } = useModulesHealth();
  const moduleHealth = data?.find((item) => item.module === name);
  return {
    status: moduleHealth?.status ?? null,
    message: moduleHealth?.message ?? null,
    beta: !!moduleHealth?.beta,
    visible:
      moduleHealth?.visible !== false &&
      moduleHealth?.status !== "unavailable" &&
      moduleHealth?.status !== "disabled",
    last_run_id: moduleHealth?.last_run_id ?? null,
    last_success_at: moduleHealth?.last_success_at ?? null,
    eligible_products: moduleHealth?.eligible_products ?? null,
    unique_products_analyzed: moduleHealth?.unique_products_analyzed ?? null,
    candidate_groups: moduleHealth?.candidate_groups ?? null,
    runtime_mode: moduleHealth?.runtime_mode ?? null,
    runtime_status: moduleHealth?.runtime_status ?? null,
    marketplace_write_policy: moduleHealth?.marketplace_write_policy ?? null,
    dangerous_actions_enabled: !!moduleHealth?.dangerous_actions_enabled,
    publish_enabled: !!moduleHealth?.publish_enabled,
    auto_publish_enabled: !!moduleHealth?.auto_publish_enabled,
    chat_send_enabled: !!moduleHealth?.chat_send_enabled,
  };
}
