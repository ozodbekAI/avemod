import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { defaultDateRange as fallback } from "./endpoints";

interface DateRangeCtx {
  from: string;
  to: string;
  setRange: (from: string, to: string) => void;
  setPreset: (days: number) => void;
}

const Ctx = createContext<DateRangeCtx | null>(null);

const KEY = "wb_global_date_range_v2";

function loadInitial(): { from: string; to: string } {
  if (typeof window === "undefined") return fallback(7);
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const j = JSON.parse(raw);
      if (j?.from && j?.to) return normalizeRange(j.from, j.to);
    }
  } catch {
    /* ignore */
  }
  return fallback(7);
}

export function DateRangeProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ from: string; to: string }>(loadInitial);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(state));
    } catch {
      /* ignore */
    }
  }, [state]);

  const setRange = useCallback(
    (from: string, to: string) => setState(normalizeRange(from, to)),
    [],
  );
  const setPreset = useCallback((days: number) => setState(fallback(days)), []);

  return (
    <Ctx.Provider
      value={{ from: state.from, to: state.to, setRange, setPreset }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useDateRange(): DateRangeCtx {
  const ctx = useContext(Ctx);
  if (ctx) return ctx;
  // Fallback for components rendered outside provider (e.g. /login, SSR)
  const f = fallback(7);
  return { from: f.from, to: f.to, setRange: () => {}, setPreset: () => {} };
}

function normalizeRange(
  from: string,
  to: string,
): { from: string; to: string } {
  return from <= to ? { from, to } : { from: to, to: from };
}
