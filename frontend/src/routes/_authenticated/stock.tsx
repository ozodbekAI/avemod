// @ts-nocheck
// /stock — legacy redirect → /stock-control?tab=overview
// Canonical "Остатки и регионы" page lives at /stock-control.
import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/stock")({
  beforeLoad: () => {
    throw redirect({ to: "/stock-control", search: { tab: "overview" } });
  },
});
