import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiList, getActiveAccountId, setActiveAccountId, type WBAccount } from "./api";
import { useAuth } from "./auth-context";

interface AccountCtx {
  accounts: WBAccount[];
  activeId: number | null;
  setActiveId: (id: number | null) => void;
  loading: boolean;
}

const Ctx = createContext<AccountCtx | null>(null);

export function AccountProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [activeId, setActiveIdState] = useState<number | null>(getActiveAccountId());

  const { data: accounts = [], isLoading } = useQuery({
    queryKey: ["accounts"],
    queryFn: () => apiList<WBAccount>("/accounts", { query: { include_inactive: true } }),
    enabled: isAuthenticated,
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    refetchOnMount: false,
  });

  useEffect(() => {
    if (!activeId && accounts.length) {
      const id = accounts[0].id;
      setActiveIdState(id);
      setActiveAccountId(id);
    }
  }, [accounts, activeId]);

  const setActiveId = (id: number | null) => {
    setActiveIdState(id);
    setActiveAccountId(id);
  };

  return (
    <Ctx.Provider value={{ accounts, activeId, setActiveId, loading: isLoading }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAccounts() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAccounts must be used within AccountProvider");
  return ctx;
}
