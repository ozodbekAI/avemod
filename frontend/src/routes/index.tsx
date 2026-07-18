import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { getAccessToken } from "@/lib/api";

export const Route = createFileRoute("/")({
  beforeLoad: () => {
    if (typeof window === "undefined") return;
    throw redirect({ to: getAccessToken() ? "/dashboard" : "/login" });
  },
  component: IndexRedirect,
});

function IndexRedirect() {
  const navigate = useNavigate();
  useEffect(() => {
    navigate({ to: getAccessToken() ? "/dashboard" : "/login", replace: true });
  }, [navigate]);
  return null;
}
