// @ts-nocheck
import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";

export const getRouter = () => {
  // Project-wide cache defaults — avoid duplicate endpoint spam, refetch
  // storms on tab focus, and unnecessary retries on hard 4xx errors.
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        // 2 minutes default freshness; per-query overrides bump this to
        // 5 min for heavy dashboard summary endpoints.
        staleTime: 2 * 60 * 1000,
        gcTime: 10 * 60 * 1000,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
        retry: (failureCount, error: unknown) => {
          // Don't retry hard client errors — they won't get better.
          const status = (error as { status?: number } | null)?.status;
          if (status && status >= 400 && status < 500) return false;
          return failureCount < 1;
        },
      },
      mutations: { retry: 0 },
    },
  });

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return router;
};
