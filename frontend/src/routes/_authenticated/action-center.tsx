import { createFileRoute } from "@tanstack/react-router";

import { ActionCenterPageContainer } from "@/components/action-center/ActionCenterPageContainer";
import { EndpointError } from "@/components/EndpointError";
import {
  validateActionCenterSearch,
  type ActionCenterSearch,
} from "@/hooks/action-center/useActionCenterFilters";

export const Route = createFileRoute("/_authenticated/action-center")({
  component: ActionCenterRoute,
  validateSearch: (s: Record<string, unknown>): ActionCenterSearch =>
    validateActionCenterSearch(s),
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

function ActionCenterRoute() {
  const routeSearch = Route.useSearch();
  return <ActionCenterPageContainer routeSearch={routeSearch} />;
}
