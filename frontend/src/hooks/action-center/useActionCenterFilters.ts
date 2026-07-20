import { useMemo } from "react";

import {
  actionCenterStateFromSearch,
  type ActionCenterFilterState,
} from "@/lib/action-center-filters";
import { routeSearchText } from "@/lib/action-center-routing";

export type ActionCenterSearch = Partial<ActionCenterFilterState> & {
  action_id?: string;
  code?: string;
  group?: string;
  source?: string;
  source_id?: string;
  nm_id?: string;
  problem_instance_id?: string;
  beta?: string;
};

export function validateActionCenterSearch(
  s: Record<string, unknown>,
): ActionCenterSearch {
  return {
    ...actionCenterStateFromSearch(s),
    action_id: routeSearchText(s.action_id),
    code: routeSearchText(s.code),
    group: routeSearchText(s.group),
    source: routeSearchText(s.source),
    source_id: routeSearchText(s.source_id),
    nm_id: routeSearchText(s.nm_id),
    problem_instance_id: routeSearchText(s.problem_instance_id),
    beta: routeSearchText(s.beta),
  };
}

export function useActionCenterFilters(
  routeSearch: ActionCenterSearch,
): ActionCenterFilterState {
  return useMemo(
    () => actionCenterStateFromSearch(routeSearch as Record<string, unknown>),
    [routeSearch],
  );
}
