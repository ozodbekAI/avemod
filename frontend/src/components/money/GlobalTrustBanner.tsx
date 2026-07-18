import { Link } from "@tanstack/react-router";
import { AlertTriangle, Info, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { humanizeBlockedReason } from "@/lib/copy";

type Variant = "blocked" | "provisional";

export function GlobalTrustBanner({ reasons, variant = "blocked" }: { reasons: string[]; variant?: Variant }) {
  const [hidden, setHidden] = useState(false);
  if (hidden || !reasons.length) return null;
  const shown = reasons.slice(0, 4).map(humanizeBlockedReason).join(", ");
  const more = reasons.length > 4 ? ` и ещё ${reasons.length - 4}` : "";

  if (variant === "provisional") {
    return (
      <div className="bg-warning/10 border-b border-warning/30 text-warning">
        <div className="px-6 py-2.5 flex items-center gap-3 text-sm">
          <Info className="h-4 w-4 shrink-0" />
          <div className="flex-1 min-w-0">
            <span className="font-medium">Анализ доступен, но цифры приблизительные.</span>{" "}
            <span className="opacity-80">Для точности подключите: {shown}{more}.</span>
          </div>
          <Button asChild size="sm" variant="outline" className="h-7 border-warning/40 text-warning hover:bg-warning/10">
            <Link to="/data-fix">Открыть починку</Link>
          </Button>
          <button onClick={() => setHidden(true)} className="opacity-60 hover:opacity-100"><X className="h-4 w-4" /></button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-destructive/10 border-b border-destructive/30 text-destructive">
      <div className="px-6 py-2.5 flex items-center gap-3 text-sm">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <div className="flex-1 min-w-0">
          <span className="font-medium">Данные пока не надёжны для бизнес-решений.</span>{" "}
          <span className="text-destructive/80">Сначала нужно закрыть: {shown}{more}.</span>
        </div>
        <Button asChild size="sm" variant="outline" className="h-7 border-destructive/40 text-destructive hover:bg-destructive/10">
          <Link to="/data-fix">Перейти к починке</Link>
        </Button>
        <button onClick={() => setHidden(true)} className="opacity-60 hover:opacity-100"><X className="h-4 w-4" /></button>
      </div>
    </div>
  );
}
