import { useQuery } from "@tanstack/react-query";

import {
  fetchAssignableUsers,
  fetchPortalActions,
} from "@/lib/portal";

export function useActionCenterData({
  activeId,
  canAssignTasks,
  dateFrom,
  dateTo,
  queryFilters,
}: {
  activeId: number | null | undefined;
  canAssignTasks: boolean;
  dateFrom: string | null | undefined;
  dateTo: string | null | undefined;
  queryFilters: Record<string, unknown>;
}) {
  const actionsQuery = useQuery({
    queryKey: ["portal-actions", activeId, dateFrom, dateTo, queryFilters],
    queryFn: () =>
      fetchPortalActions(activeId, queryFilters, { dateFrom, dateTo }),
    enabled: !!activeId,
    staleTime: 30_000,
  });

  const usersQuery = useQuery({
    queryKey: ["portal-assignable-users", activeId],
    queryFn: () => fetchAssignableUsers(activeId),
    enabled: !!activeId && canAssignTasks,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  return { actionsQuery, usersQuery };
}
