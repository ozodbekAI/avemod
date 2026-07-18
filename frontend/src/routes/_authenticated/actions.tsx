import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/actions")({
  beforeLoad: () => {
    throw redirect({ to: "/action-center" });
  },
});
