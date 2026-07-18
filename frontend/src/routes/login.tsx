import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { AlertTriangle, LifeBuoy, Loader2, RefreshCw, ShieldCheck, Sparkles, Target } from "lucide-react";
import { toast } from "sonner";
import { getBaseUrl, setBaseUrl } from "@/lib/api";

export const Route = createFileRoute("/login")({
  component: LoginPage,
});

function isNetworkError(err: unknown): boolean {
  if (!err) return false;
  const msg = (err instanceof Error ? err.message : String(err)).toLowerCase();
  return msg.includes("failed to fetch") || msg.includes("networkerror") || msg.includes("load failed");
}

function LoginPage() {
  const { login, isAuthenticated, loading } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [connError, setConnError] = useState<null | { message: string; endpoint?: string }>(null);
  const [showApiEdit, setShowApiEdit] = useState(false);
  const [apiBase, setApiBase] = useState(() => (typeof window !== "undefined" ? getBaseUrl() : ""));

  useEffect(() => {
    if (!loading && isAuthenticated) navigate({ to: "/dashboard" });
  }, [loading, isAuthenticated, navigate]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setConnError(null);
    try {
      await login(email, password);
      toast.success("Вход выполнен");
      navigate({ to: "/dashboard" });
    } catch (err) {
      if (isNetworkError(err)) {
        setConnError({ message: err instanceof Error ? err.message : String(err), endpoint: getBaseUrl() });
      } else {
        toast.error(err instanceof Error ? err.message : "Не удалось войти");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const applyApiBase = () => {
    setBaseUrl(apiBase);
    setApiBase(getBaseUrl());
    setConnError(null);
    setShowApiEdit(false);
    toast.success("Адрес API сохранён");
  };

  const resetApiBase = () => {
    setBaseUrl("");
    setApiBase(getBaseUrl());
    setConnError(null);
    toast.success("Адрес API сброшен к значению по умолчанию");
  };


  return (
    <div className="min-h-screen grid lg:grid-cols-[1.1fr_1fr] bg-background">
      {/* Левая панель — идентичность продукта */}
      <aside className="hidden lg:flex flex-col justify-between bg-gradient-to-br from-primary via-primary to-[oklch(0.32_0.14_265)] text-primary-foreground p-10 xl:p-14">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-primary-foreground/15 backdrop-blur p-2">
            <LifeBuoy className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-semibold tracking-tight">
              Control Tower
            </div>
            <div className="text-[11px] opacity-80">
              Операционный центр продавца
            </div>
          </div>
        </div>

        <div className="max-w-lg space-y-6">
          <h1 className="text-3xl xl:text-4xl font-semibold leading-tight tracking-tight">
            AI-контроль денег, карточек и задач на Wildberries
          </h1>
          <p className="text-base opacity-90">
            Найдите проблемы, поймите причину, назначьте задачу и проверьте
            результат.
          </p>

          <ul className="space-y-3 text-sm">
            <FeatureRow
              icon={<Target className="h-4 w-4" />}
              title="Проблема → доказательства → действие"
              hint="Каждая цифра со ссылкой на источник и формулу расчёта."
            />
            <FeatureRow
              icon={<ShieldCheck className="h-4 w-4" />}
              title="Только проверенные данные"
              hint="Предварительные и подтверждённые метрики разделены визуально."
            />
            <FeatureRow
              icon={<Sparkles className="h-4 w-4" />}
              title="Замкнутый цикл контроля"
              hint="Назначьте задачу, отследите статус, увидьте эффект."
            />
          </ul>
        </div>

        <div className="text-[11px] opacity-70">
          © {new Date().getFullYear()} Control Tower · Внутренний доступ
        </div>
      </aside>

      {/* Правая — форма входа */}
      <main className="flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-md">
          {/* Мобильный бренд */}
          <div className="lg:hidden flex items-center gap-2.5 mb-6">
            <div className="rounded-md bg-primary p-2 text-primary-foreground">
              <LifeBuoy className="h-4 w-4" />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight">
                Control Tower
              </div>
              <div className="text-[11px] text-muted-foreground">
                Операционный центр продавца
              </div>
            </div>
          </div>

          <Card className="border-border/60 shadow-sm">
            <CardHeader className="space-y-1.5">
              <CardTitle className="text-xl">Вход в Control Tower</CardTitle>
              <CardDescription>
                Введите рабочую почту и пароль, чтобы продолжить.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {connError ? (
                <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm space-y-2">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="h-4 w-4 text-destructive mt-0.5 shrink-0" />
                    <div className="space-y-1 min-w-0">
                      <div className="font-semibold text-destructive">Не удалось подключиться к API</div>
                      <p className="text-xs text-muted-foreground">
                        Проверьте адрес API или доступность сервера. Если вы используете временный tunnel/ngrok, убедитесь, что он запущен.
                      </p>
                      {connError.endpoint ? (
                        <div className="text-[11px] font-mono text-muted-foreground break-all">endpoint: {connError.endpoint}</div>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 pt-1">
                    <Button size="sm" variant="outline" type="button" onClick={() => { setConnError(null); }}>
                      <RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Повторить
                    </Button>
                    <Button size="sm" variant="ghost" type="button" onClick={() => setShowApiEdit((v) => !v)}>
                      Изменить адрес API
                    </Button>
                    <Button size="sm" variant="ghost" type="button" onClick={resetApiBase}>
                      Вернуть адрес по умолчанию
                    </Button>
                  </div>
                  {showApiEdit ? (
                    <div className="space-y-2 pt-2 border-t">
                      <Label htmlFor="api-base" className="text-xs">Адрес API</Label>
                      <div className="flex gap-2">
                        <Input
                          id="api-base"
                          value={apiBase}
                          onChange={(e) => setApiBase(e.target.value)}
                          placeholder="https://your-api.example.com/api/v1"
                          className="h-8 text-xs"
                        />
                        <Button size="sm" type="button" onClick={applyApiBase}>Сохранить</Button>
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}
              <form onSubmit={onSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email">Эл. почта</Label>
                  <Input
                    id="email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="email"
                    placeholder="you@company.com"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password">Пароль</Label>
                  <Input
                    id="password"
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                  />
                </div>
                <Button
                  type="submit"
                  className="w-full h-10"
                  disabled={submitting}
                >
                  {submitting && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Войти
                </Button>
              </form>
              <p className="mt-4 text-[11px] text-muted-foreground text-center">
                Нет доступа? Обратитесь к администратору вашего аккаунта.
              </p>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}

function FeatureRow({
  icon,
  title,
  hint,
}: {
  icon: React.ReactNode;
  title: string;
  hint: string;
}) {
  return (
    <li className="flex items-start gap-3">
      <span className="mt-0.5 rounded-md bg-primary-foreground/15 p-1.5">
        {icon}
      </span>
      <span>
        <span className="block font-medium">{title}</span>
        <span className="block text-[13px] opacity-80">{hint}</span>
      </span>
    </li>
  );
}
