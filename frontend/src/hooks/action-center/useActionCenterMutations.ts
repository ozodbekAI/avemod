import { useMutation, type QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import type { ActionCenterItem } from "@/lib/action-center-contract";
import {
  updateActionById,
  updateActionBySource,
  type PortalAction,
} from "@/lib/portal";

export type ActionCenterSaveVars = {
  a: ActionCenterItem;
  status: string;
  assigned_to_user_id?: number | null;
  deadline_at?: string | null;
  last_comment?: string | null;
};

type PortalActionsCacheObject = Record<string, unknown> & {
  items?: PortalAction[];
  actions?: PortalAction[];
};

function numericActionId(a: ActionCenterItem): number | null {
  return typeof a.action_id === "number" ? a.action_id : null;
}

function isPortalActionList(value: unknown): value is PortalAction[] {
  return Array.isArray(value);
}

function isPortalActionsCacheObject(
  value: unknown,
): value is PortalActionsCacheObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function useActionCenterMutations({
  activeId,
  queryClient,
  setBusy,
}: {
  activeId: number | null | undefined;
  queryClient: QueryClient;
  setBusy: (value: string | null) => void;
}) {
  return useMutation({
    mutationFn: async (vars: ActionCenterSaveVars) => {
      const { a, status } = vars;
      const updatePayload = {
        status,
        account_id: activeId,
        comment: vars.last_comment ?? "",
        status_reason: vars.last_comment ?? "",
        ...(vars.assigned_to_user_id != null
          ? { assigned_to_user_id: vars.assigned_to_user_id }
          : {}),
        ...(vars.deadline_at ? { deadline_at: vars.deadline_at } : {}),
      };
      if (a.source_module && a.source_id != null) {
        return updateActionBySource({
          source_module: a.source_module,
          source_id: String(a.source_id),
          ...updatePayload,
        });
      }
      const id = numericActionId(a);
      if (id != null) return updateActionById(id, updatePayload);
      throw new Error("Действие нельзя обновить — нет идентификатора.");
    },
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: ["portal-actions"] });
      const snapshots = queryClient.getQueriesData<unknown>({
        queryKey: ["portal-actions"],
      });
      const matches = (x: PortalAction) =>
        (vars.a.source_module &&
          vars.a.source_id != null &&
          x.source_module === vars.a.source_module &&
          String(x.source_id) === String(vars.a.source_id)) ||
        (vars.a.id != null && x.id === vars.a.id);
      const patch = (arr: PortalAction[]) =>
        arr.map((x) =>
          matches(x)
            ? {
                ...x,
                status: vars.status,
                ...(vars.assigned_to_user_id != null
                  ? { assigned_to_user_id: vars.assigned_to_user_id }
                  : {}),
                ...(vars.deadline_at ? { deadline_at: vars.deadline_at } : {}),
                ...(vars.last_comment
                  ? { last_comment: vars.last_comment }
                  : {}),
              }
            : x,
        );
      for (const [key, val] of snapshots) {
        if (!val) continue;
        if (isPortalActionList(val)) {
          queryClient.setQueryData(key, patch(val));
        } else if (
          isPortalActionsCacheObject(val) &&
          isPortalActionList(val.items)
        ) {
          queryClient.setQueryData(key, {
            ...val,
            items: patch(val.items),
          });
        } else if (
          isPortalActionsCacheObject(val) &&
          isPortalActionList(val.actions)
        ) {
          queryClient.setQueryData(key, {
            ...val,
            actions: patch(val.actions),
          });
        }
      }
      return { snapshots };
    },
    onError: (_e: unknown, _vars, ctx) => {
      if (ctx?.snapshots) {
        for (const [key, val] of ctx.snapshots) {
          queryClient.setQueryData(key, val);
        }
      }
      toast.error("Не удалось обновить статус задачи");
    },
    onSuccess: (_data, vars) => {
      toast.success("Статус задачи обновлён");
      queryClient.invalidateQueries({ queryKey: ["portal-actions"] });
      queryClient.invalidateQueries({ queryKey: ["portal-action-results"] });
      queryClient.invalidateQueries({ queryKey: ["portal-problem-results"] });
      queryClient.invalidateQueries({ queryKey: ["portal-results"] });
      queryClient.invalidateQueries({ queryKey: ["portal-doctor"] });
      queryClient.invalidateQueries({ queryKey: ["dash-data-blockers"] });
      queryClient.invalidateQueries({ queryKey: ["money-data-blockers"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-data-health"] });
      if (vars.a.nm_id != null) {
        queryClient.invalidateQueries({
          queryKey: ["portal-product-detail", activeId, vars.a.nm_id],
        });
      }
    },
    onSettled: () => setBusy(null),
  });
}
