import { createContext, useContext, useMemo, useRef, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, clearTokens, getAccessToken, setTokens, type TokenPair, type UserRead } from "./api";

interface AuthCtx {
  user: UserRead | null;
  isAuthenticated: boolean;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);

// Stable query key so every consumer hits the same cache entry.
const AUTH_ME_KEY = ["auth", "me"] as const;
const AUTH_ME_TIMEOUT_MS = 8_000;

function authMeSignal(): AbortSignal | undefined {
  if (typeof AbortSignal !== "undefined" && "timeout" in AbortSignal) {
    return AbortSignal.timeout(AUTH_ME_TIMEOUT_MS);
  }
  if (typeof AbortController === "undefined") return undefined;
  const controller = new AbortController();
  window.setTimeout(() => controller.abort(), AUTH_ME_TIMEOUT_MS);
  return controller.signal;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const loginInFlight = useRef<Promise<void> | null>(null);

  // /auth/me is fetched once and shared across the whole app.
  // staleTime = 5 min so route navigations within a session never refetch.
  // Combined with api()'s in-flight GET dedup, simultaneous mounts on the
  // same route collapse to a single network request.
  const query = useQuery<UserRead | null>({
    queryKey: AUTH_ME_KEY,
    enabled: typeof window !== "undefined",
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    retry: false,
    queryFn: async () => {
      if (!getAccessToken()) return null;
      try {
        return await api<UserRead>("/auth/me", { signal: authMeSignal() });
      } catch (e: any) {
        if (e?.name === "AbortError") return null;
        if (e instanceof ApiError && e.status === 401) clearTokens();
        return null;
      }
    },
  });

  const value = useMemo<AuthCtx>(() => ({
    user: query.data ?? null,
    isAuthenticated: !!query.data,
    loading: query.isLoading,
    refreshUser: async () => { await qc.invalidateQueries({ queryKey: AUTH_ME_KEY }); },
    logout: () => {
      clearTokens();
      qc.setQueryData(AUTH_ME_KEY, null);
      qc.clear();
    },
    login: async (email, password) => {
      if (loginInFlight.current) return loginInFlight.current;
      loginInFlight.current = (async () => {
        try {
          const pair = await api<TokenPair>("/auth/login", {
            method: "POST",
            body: { email, password },
            auth: false,
          });
          setTokens(pair.access_token, pair.refresh_token);
          await qc.invalidateQueries({ queryKey: AUTH_ME_KEY });
          await qc.refetchQueries({ queryKey: AUTH_ME_KEY });
        } finally {
          loginInFlight.current = null;
        }
      })();
      return loginInFlight.current;
    },
  }), [query.data, query.isLoading, qc]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
