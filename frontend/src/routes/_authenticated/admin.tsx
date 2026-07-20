import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import {
  api, apiList, getBaseUrl, setBaseUrl, type Paginated, type SyncRun, type SyncCursor, type WBAccount, type WBToken,
  type ManualCostRow, type ManualCostUpload, type UserRead,
} from "@/lib/api";
import { useAccounts } from "@/lib/account-context";
import { PageHeader, PageShell } from "@/components/PageShell";
import { fmtDate, fmtNum } from "@/components/Pager";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, Plus, Upload, Download, Play, RefreshCw, FileSpreadsheet, Link2 } from "lucide-react";
import { toast } from "sonner";
import { EndpointError } from "@/components/EndpointError";
import { ProblemRulesAdminPanel } from "@/components/problem-rules/ProblemRulesAdminPanel";

export const Route = createFileRoute("/_authenticated/admin")({
  component: AdminPage,
  errorComponent: ({ error, reset }) => <EndpointError error={error} reset={reset} />,
});

const DOMAINS = ["product_cards","prices","orders","sales","stocks","finance","ads","analytics","supplies","tariffs","documents"];

function AdminPage() {
  return (
    <PageShell>
      <PageHeader title="Администрирование" description="Аккаунты, токены, правила проблем, себестоимость, синхронизация и витрины" />
      <Tabs defaultValue="accounts">
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger value="accounts">Аккаунты</TabsTrigger>
          <TabsTrigger value="tokens">Токены</TabsTrigger>
          <TabsTrigger value="users">Пользователи</TabsTrigger>
          <TabsTrigger value="problem-rules">Правила проблем</TabsTrigger>
          <TabsTrigger value="costs">Себестоимость</TabsTrigger>
          <TabsTrigger value="sync">Синхронизация</TabsTrigger>
          <TabsTrigger value="marts">Витрины</TabsTrigger>
          <TabsTrigger value="exports">Экспорт</TabsTrigger>
          <TabsTrigger value="docs">Документы и тарифы</TabsTrigger>
          <TabsTrigger value="settings">Настройки</TabsTrigger>
        </TabsList>
        <TabsContent value="accounts"><AccountsTab /></TabsContent>
        <TabsContent value="tokens"><TokensTab /></TabsContent>
        <TabsContent value="users"><UsersTab /></TabsContent>
        <TabsContent value="problem-rules"><ProblemRulesAdminPanel /></TabsContent>
        <TabsContent value="costs"><CostsTab /></TabsContent>
        <TabsContent value="sync"><SyncTab /></TabsContent>
        <TabsContent value="marts"><MartsTab /></TabsContent>
        <TabsContent value="exports"><ExportsTab /></TabsContent>
        <TabsContent value="docs"><DocsTab /></TabsContent>
        <TabsContent value="settings"><SettingsTab /></TabsContent>
      </Tabs>
    </PageShell>
  );
}

function AccountsTab() {
  const qc = useQueryClient();
  const { data: accounts, isLoading } = useQuery({
    queryKey: ["accounts-all"],
    queryFn: () => apiList<WBAccount>("/accounts", { query: { include_inactive: true } }),
  });
  const [form, setForm] = useState({ name: "", seller_name: "", external_account_id: "", timezone: "Europe/Moscow", is_active: true });
  const create = useMutation({
    mutationFn: () => api<WBAccount>("/accounts", { method: "POST", body: form }),
    onSuccess: () => { toast.success("Аккаунт создан"); qc.invalidateQueries({ queryKey: ["accounts-all"] }); qc.invalidateQueries({ queryKey: ["accounts"] }); setForm({ name: "", seller_name: "", external_account_id: "", timezone: "Europe/Moscow", is_active: true }); },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
      <Card className="lg:col-span-2">
        <CardHeader className="pb-2"><CardTitle className="text-base">Аккаунты</CardTitle></CardHeader>
        <CardContent className="p-0">
          {isLoading ? <div className="p-6 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin inline mr-2" />Загрузка…</div> : (
            <Table>
              <TableHeader><TableRow><TableHead>ID</TableHead><TableHead>Название</TableHead><TableHead>Продавец</TableHead><TableHead>Внеш. ID</TableHead><TableHead>Часовой пояс</TableHead><TableHead>Активен</TableHead><TableHead>Создан</TableHead></TableRow></TableHeader>
              <TableBody>
                {accounts?.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell className="font-mono text-xs">{a.id}</TableCell>
                    <TableCell className="font-medium">{a.name}</TableCell>
                    <TableCell className="text-xs">{a.seller_name ?? "—"}</TableCell>
                    <TableCell className="text-xs font-mono">{a.external_account_id ?? "—"}</TableCell>
                    <TableCell className="text-xs">{a.timezone}</TableCell>
                    <TableCell><Badge variant={a.is_active ? "outline" : "secondary"}>{a.is_active ? "активен" : "неактивен"}</Badge></TableCell>
                    <TableCell className="text-xs">{fmtDate(a.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Новый аккаунт</CardTitle></CardHeader>
        <CardContent>
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
            <div><Label>Название</Label><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
            <div><Label>Имя продавца</Label><Input value={form.seller_name} onChange={(e) => setForm({ ...form, seller_name: e.target.value })} /></div>
            <div><Label>Внешний ID</Label><Input value={form.external_account_id} onChange={(e) => setForm({ ...form, external_account_id: e.target.value })} /></div>
            <div><Label>Часовой пояс</Label><Input value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} /></div>
            <div className="flex items-center gap-2"><Switch checked={form.is_active} onCheckedChange={(v) => setForm({ ...form, is_active: v })} /><Label>Активен</Label></div>
            <Button type="submit" disabled={create.isPending} className="w-full">{create.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <Plus className="h-4 w-4 mr-1.5" />}Создать</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function TokensTab() {
  const { activeId, accounts } = useAccounts();
  const qc = useQueryClient();
  const { data: tokens, isLoading } = useQuery({
    queryKey: ["tokens", activeId],
    queryFn: () => apiList<WBToken>(`/accounts/${activeId}/tokens`),
    enabled: !!activeId,
  });
  const [form, setForm] = useState({ category: "statistics", token: "", comment: "", is_active: true });
  const upsert = useMutation({
    mutationFn: () => api<WBToken>(`/accounts/${activeId}/tokens`, { method: "POST", body: form }),
    onSuccess: () => { toast.success("Токен сохранён"); qc.invalidateQueries({ queryKey: ["tokens", activeId] }); setForm({ ...form, token: "", comment: "" }); },
    onError: (e: Error) => toast.error(e.message),
  });

  const acc = accounts.find((a) => a.id === activeId);
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
      <Card className="lg:col-span-2">
        <CardHeader className="pb-2"><CardTitle className="text-base">Токены {acc?.name ?? "аккаунта"}</CardTitle></CardHeader>
        <CardContent className="p-0">
          {!activeId && <div className="p-4 text-sm text-muted-foreground">Сначала выберите аккаунт.</div>}
          {activeId && isLoading && <div className="p-6 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin inline mr-2" />Загрузка…</div>}
          {tokens && (
            <Table>
              <TableHeader><TableRow><TableHead>ID</TableHead><TableHead>Категория</TableHead><TableHead>Комментарий</TableHead><TableHead>Активен</TableHead><TableHead>Создан</TableHead></TableRow></TableHeader>
              <TableBody>
                {tokens.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell className="font-mono text-xs">{t.id}</TableCell>
                    <TableCell><Badge variant="outline">{t.category}</Badge></TableCell>
                    <TableCell className="text-xs">{t.comment ?? "—"}</TableCell>
                    <TableCell><Badge variant={t.is_active ? "outline" : "secondary"}>{t.is_active ? "активен" : "неактивен"}</Badge></TableCell>
                    <TableCell className="text-xs">{fmtDate(t.created_at)}</TableCell>
                  </TableRow>
                ))}
                {tokens.length === 0 && <TableRow><TableCell colSpan={5} className="text-center py-6 text-muted-foreground">Токенов нет</TableCell></TableRow>}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Добавить / обновить токен</CardTitle><CardDescription className="text-xs">Повторная отправка по той же категории обновляет токен.</CardDescription></CardHeader>
        <CardContent>
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); upsert.mutate(); }}>
            <div><Label>Категория</Label>
              <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["statistics","content","marketplace","analytics","promotion","finance","feedbacks","question","supplies","documents"].map((c) =>
                    <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div><Label>Токен</Label><Textarea required rows={3} value={form.token} onChange={(e) => setForm({ ...form, token: e.target.value })} className="font-mono text-xs" /></div>
            <div><Label>Комментарий</Label><Input value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} /></div>
            <div className="flex items-center gap-2"><Switch checked={form.is_active} onCheckedChange={(v) => setForm({ ...form, is_active: v })} /><Label>Активен</Label></div>
            <Button type="submit" disabled={!activeId || upsert.isPending} className="w-full">{upsert.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <Plus className="h-4 w-4 mr-1.5" />}Сохранить</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function CostsTab() {
  const { activeId } = useAccounts();
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [commit, setCommit] = useState(false);

  const { data: rows } = useQuery({
    queryKey: ["cost-rows", activeId],
    queryFn: () => api<Paginated<ManualCostRow>>("/costs/rows", { query: { account_id: activeId ?? undefined, limit: 50 } }),
    enabled: !!activeId,
  });
  const { data: imports } = useQuery({
    queryKey: ["cost-imports"],
    queryFn: () => apiList<ManualCostUpload>("/costs/imports"),
  });
  const { data: unresolved } = useQuery({
    queryKey: ["cost-unresolved", activeId],
    queryFn: () => apiList<ManualCostRow>("/costs/unresolved", { query: { account_id: activeId ?? undefined, limit: 50 } }),
    enabled: !!activeId,
  });
  const relink = useMutation({
    mutationFn: () => api(`/costs/relink`, { method: "POST", query: { account_id: activeId ?? undefined } }),
    onSuccess: () => { toast.success("Перепривязка выполнена"); qc.invalidateQueries({ queryKey: ["cost-rows"] }); qc.invalidateQueries({ queryKey: ["cost-unresolved"] }); },
    onError: (e: Error) => toast.error(e.message),
  });

  const upload = useMutation({
    mutationFn: async () => {
      if (!file || !activeId) throw new Error("Нужен файл и аккаунт");
      const fd = new FormData();
      fd.append("account_id", String(activeId));
      fd.append("commit_rows", String(commit));
      fd.append("file", file);
      return api("/costs/upload", { method: "POST", formData: fd });
    },
    onSuccess: () => { toast.success("Себестоимость загружена"); qc.invalidateQueries({ queryKey: ["cost-rows"] }); setFile(null); },
    onError: (e: Error) => toast.error(e.message),
  });

  const downloadTemplate = async () => {
    if (!activeId) return;
    try {
      const res = await api<Response>(`/costs/template`, { query: { account_id: activeId }, raw: true });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `cost-template-${activeId}.csv`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error((e as Error).message); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Загрузка</CardTitle></CardHeader>
        <CardContent>
          <form className="space-y-2" onSubmit={(e: FormEvent) => { e.preventDefault(); upload.mutate(); }}>
            <Input type="file" accept=".csv,.xlsx,.xls" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <div className="flex items-center gap-2"><Switch checked={commit} onCheckedChange={setCommit} /><Label className="text-sm">Подтвердить строки (иначе предпросмотр)</Label></div>
            <Button type="submit" disabled={!file || !activeId || upload.isPending} className="w-full"><Upload className="h-4 w-4 mr-1.5" />{commit ? "Применить" : "Предпросмотр"}</Button>
            <Button type="button" variant="outline" disabled={!activeId} onClick={downloadTemplate} className="w-full"><Download className="h-4 w-4 mr-1.5" />Скачать шаблон</Button>
            <Button type="button" variant="secondary" disabled={!activeId || relink.isPending} onClick={() => relink.mutate()} className="w-full">{relink.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <Link2 className="h-4 w-4 mr-1.5" />}Перепривязать к SKU</Button>
          </form>
        </CardContent>
      </Card>
      <Card className="lg:col-span-2">
        <CardHeader className="pb-2"><CardTitle className="text-base">Последние строки себестоимости</CardTitle></CardHeader>
        <CardContent className="p-0">
          {rows && (
            <Table>
              <TableHeader><TableRow><TableHead>nm ID</TableHead><TableHead>Артикул</TableHead><TableHead>Штрихкод</TableHead><TableHead className="text-right">Себест.</TableHead><TableHead className="text-right">Упаковка</TableHead><TableHead className="text-right">Логистика</TableHead><TableHead>Поставщик</TableHead></TableRow></TableHeader>
              <TableBody>
                {rows.items.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-mono text-xs">{r.nm_id ?? "—"}</TableCell>
                    <TableCell className="text-xs">{r.vendor_code ?? "—"}</TableCell>
                    <TableCell className="text-xs">{r.barcode ?? "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtNum(r.cost_price)}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtNum(r.packaging_cost)}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtNum(r.inbound_logistics_cost)}</TableCell>
                    <TableCell className="text-xs">{r.supplier ?? "—"}</TableCell>
                  </TableRow>
                ))}
                {rows.items.length === 0 && <TableRow><TableCell colSpan={7} className="py-6 text-center text-muted-foreground">Нет</TableCell></TableRow>}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <Card className="lg:col-span-3 grid grid-cols-1 md:grid-cols-2">
        <div>
          <CardHeader className="pb-2"><CardTitle className="text-base">Загрузки (история)</CardTitle></CardHeader>
          <CardContent className="p-0 max-h-[280px] overflow-y-auto">
            <Table>
              <TableHeader><TableRow><TableHead>ID</TableHead><TableHead>Файл</TableHead><TableHead>Статус</TableHead><TableHead className="text-right">Строк</TableHead><TableHead>Когда</TableHead></TableRow></TableHeader>
              <TableBody>
                {imports?.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="font-mono text-xs">{u.id}</TableCell>
                    <TableCell className="text-xs truncate max-w-[200px]">{u.filename ?? "—"}</TableCell>
                    <TableCell><Badge variant="outline">{u.status}</Badge></TableCell>
                    <TableCell className="text-right text-xs tabular-nums">{u.rows_committed ?? u.rows_total ?? "—"}</TableCell>
                    <TableCell className="text-xs">{fmtDate(u.uploaded_at)}</TableCell>
                  </TableRow>
                ))}
                {(imports?.length ?? 0) === 0 && <TableRow><TableCell colSpan={5} className="py-6 text-center text-muted-foreground text-sm">Нет</TableCell></TableRow>}
              </TableBody>
            </Table>
          </CardContent>
        </div>
        <div>
          <CardHeader className="pb-2"><CardTitle className="text-base">Несвязанные строки</CardTitle><CardDescription className="text-xs">Не сопоставились с SKU</CardDescription></CardHeader>
          <CardContent className="p-0 max-h-[280px] overflow-y-auto">
            <Table>
              <TableHeader><TableRow><TableHead>nm ID</TableHead><TableHead>Артикул</TableHead><TableHead>Штрихкод</TableHead><TableHead className="text-right">Себест.</TableHead></TableRow></TableHeader>
              <TableBody>
                {unresolved?.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-mono text-xs">{r.nm_id ?? "—"}</TableCell>
                    <TableCell className="text-xs">{r.vendor_code ?? "—"}</TableCell>
                    <TableCell className="text-xs">{r.barcode ?? "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtNum(r.cost_price)}</TableCell>
                  </TableRow>
                ))}
                {(unresolved?.length ?? 0) === 0 && <TableRow><TableCell colSpan={4} className="py-6 text-center text-muted-foreground text-sm">Все привязаны</TableCell></TableRow>}
              </TableBody>
            </Table>
          </CardContent>
        </div>
      </Card>
    </div>
  );
}

function SyncTab() {
  const { activeId } = useAccounts();
  const qc = useQueryClient();
  const { data: runs } = useQuery({
    queryKey: ["sync-runs"],
    queryFn: () => apiList<SyncRun>("/sync/runs"),
    refetchInterval: 5000,
  });
  const [domain, setDomain] = useState("product_cards");
  const [forceFull, setForceFull] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const trigger = useMutation({
    mutationFn: () => api("/sync/trigger", { method: "POST", body: { account_id: activeId, domain, force_full: forceFull } }),
    onSuccess: () => { toast.success(`Синхронизация ${domain} запущена`); qc.invalidateQueries({ queryKey: ["sync-runs"] }); },
    onError: (e: Error) => toast.error(e.message),
  });
  const backfill = useMutation({
    mutationFn: () => api("/sync/backfill", { method: "POST", body: { account_id: activeId, domain, date_from: dateFrom || null, date_to: dateTo || null, force_full: forceFull } }),
    onSuccess: () => { toast.success(`Перезагрузка ${domain} запущена`); qc.invalidateQueries({ queryKey: ["sync-runs"] }); },
    onError: (e: Error) => toast.error(e.message),
  });
  const { data: cursors } = useQuery({
    queryKey: ["sync-cursors"],
    queryFn: () => apiList<SyncCursor>("/sync/cursors"),
    refetchInterval: 15000,
  });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Новая синхронизация</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <div><Label>Домен</Label>
            <Select value={domain} onValueChange={setDomain}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{DOMAINS.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div><Label className="text-xs">Дата с</Label><Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div>
            <div><Label className="text-xs">Дата по</Label><Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div>
          </div>
          <div className="flex items-center gap-2"><Switch checked={forceFull} onCheckedChange={setForceFull} /><Label className="text-sm">Полная загрузка</Label></div>
          <div className="flex gap-2 pt-2">
            <Button className="flex-1" disabled={!activeId || trigger.isPending} onClick={() => trigger.mutate()}><Play className="h-4 w-4 mr-1.5" />Запустить</Button>
            <Button variant="outline" className="flex-1" disabled={!activeId || backfill.isPending} onClick={() => backfill.mutate()}><RefreshCw className="h-4 w-4 mr-1.5" />Перезагрузка</Button>
          </div>
        </CardContent>
      </Card>
      <Card className="lg:col-span-2">
        <CardHeader className="pb-2"><CardTitle className="text-base">Последние запуски</CardTitle><CardDescription className="text-xs">Обновляется каждые 5 секунд</CardDescription></CardHeader>
        <CardContent className="p-0 max-h-[600px] overflow-y-auto">
          <Table>
            <TableHeader><TableRow><TableHead>ID</TableHead><TableHead>Аккаунт</TableHead><TableHead>Домен</TableHead><TableHead>Статус</TableHead><TableHead>Источник</TableHead><TableHead>Начато</TableHead><TableHead>Завершено</TableHead></TableRow></TableHeader>
            <TableBody>
              {runs?.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-xs">{r.id}</TableCell>
                  <TableCell className="text-xs">{r.account_id}</TableCell>
                  <TableCell className="font-mono text-xs">{r.domain}</TableCell>
                  <TableCell><Badge variant={r.status === "success" ? "outline" : r.status === "failed" ? "destructive" : "secondary"}>{r.status}</Badge>{r.is_backfill && <Badge variant="outline" className="ml-1">Перезагр.</Badge>}</TableCell>
                  <TableCell className="text-xs">{r.trigger}</TableCell>
                  <TableCell className="text-xs">{fmtDate(r.started_at)}</TableCell>
                  <TableCell className="text-xs">{fmtDate(r.finished_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <Card className="lg:col-span-3">
        <CardHeader className="pb-2"><CardTitle className="text-base">Курсоры синхронизации</CardTitle></CardHeader>
        <CardContent className="p-0 max-h-[360px] overflow-y-auto">
          <Table>
            <TableHeader><TableRow><TableHead>Аккаунт</TableHead><TableHead>Домен</TableHead><TableHead>Курсор</TableHead><TableHead>Статус</TableHead><TableHead>Последний раз</TableHead></TableRow></TableHeader>
            <TableBody>
              {cursors?.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="text-xs">{c.account_id}</TableCell>
                  <TableCell className="font-mono text-xs">{c.domain}</TableCell>
                  <TableCell className="text-xs font-mono truncate max-w-[280px]">{c.cursor_key ?? "—"}</TableCell>
                  <TableCell><Badge variant="outline">{c.status ?? "—"}</Badge></TableCell>
                  <TableCell className="text-xs">{fmtDate(c.last_synced_at)}</TableCell>
                </TableRow>
              ))}
              {(cursors?.length ?? 0) === 0 && <TableRow><TableCell colSpan={5} className="py-6 text-center text-muted-foreground text-sm">Нет</TableCell></TableRow>}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function MartsTab() {
  const { activeId } = useAccounts();
  const qc = useQueryClient();
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const refresh = useMutation({
    mutationFn: () => api<Record<string, number | string>>("/marts/refresh", { method: "POST", body: { account_id: activeId, date_from: dateFrom || null, date_to: dateTo || null } }),
    onSuccess: (r) => { toast.success(`Витрины обновлены: SKU ${r.sku_rows}, finance ${r.finance_rows}`); qc.invalidateQueries(); },
    onError: (e: Error) => toast.error(e.message),
  });
  const runDq = useMutation({
    mutationFn: () => api<Record<string, number>>("/dq/run", { method: "POST", body: { account_id: activeId } }),
    onSuccess: (r) => toast.success(`DQ: открыто ${r.opened_count}, закрыто ${r.resolved_count}`),
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Обновление витрин</CardTitle><CardDescription className="text-xs">sku-daily, stock-daily, reconciliation, expenses</CardDescription></CardHeader>
        <CardContent className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <div><Label className="text-xs">Дата с</Label><Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div>
            <div><Label className="text-xs">Дата по</Label><Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div>
          </div>
          <Button className="w-full" disabled={!activeId || refresh.isPending} onClick={() => refresh.mutate()}>{refresh.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <RefreshCw className="h-4 w-4 mr-1.5" />}Обновить витрины</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Проверка качества данных</CardTitle></CardHeader>
        <CardContent>
          <Button className="w-full" disabled={!activeId || runDq.isPending} onClick={() => runDq.mutate()}>{runDq.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <Play className="h-4 w-4 mr-1.5" />}Запустить проверки DQ</Button>
        </CardContent>
      </Card>
    </div>
  );
}

function SettingsTab() {
  const [base, setBase] = useState(getBaseUrl());
  return (
    <Card className="max-w-2xl">
      <CardHeader className="pb-2"><CardTitle className="text-base">Настройки API</CardTitle><CardDescription>Адрес backend (хранится в localStorage)</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        <div><Label>Адрес API</Label><Input value={base} onChange={(e) => setBase(e.target.value)} className="font-mono text-xs" /></div>
        <Button onClick={() => { setBaseUrl(base); toast.success("Сохранено"); }}>Сохранить</Button>
      </CardContent>
    </Card>
  );
}

function UsersTab() {
  const qc = useQueryClient();
  const { data: users, isLoading } = useQuery({
    queryKey: ["users-all"],
    queryFn: () => apiList<UserRead>("/users"),
  });
  const [form, setForm] = useState({ email: "", full_name: "", password: "", is_active: true, is_superuser: false });
  const create = useMutation({
    mutationFn: () => api<UserRead>("/users", { method: "POST", body: form }),
    onSuccess: () => { toast.success("Пользователь создан"); qc.invalidateQueries({ queryKey: ["users-all"] }); setForm({ email: "", full_name: "", password: "", is_active: true, is_superuser: false }); },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
      <Card className="lg:col-span-2">
        <CardHeader className="pb-2"><CardTitle className="text-base">Пользователи</CardTitle></CardHeader>
        <CardContent className="p-0">
          {isLoading ? <div className="p-6 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin inline mr-2" />Загрузка…</div> : (
            <Table>
              <TableHeader><TableRow><TableHead>ID</TableHead><TableHead>Эл. почта</TableHead><TableHead>Имя</TableHead><TableHead>Активен</TableHead><TableHead>Админ</TableHead><TableHead>Создан</TableHead></TableRow></TableHeader>
              <TableBody>
                {users?.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="font-mono text-xs">{u.id}</TableCell>
                    <TableCell className="text-sm">{u.email}</TableCell>
                    <TableCell className="text-sm">{u.full_name || "—"}</TableCell>
                    <TableCell><Badge variant={u.is_active ? "outline" : "secondary"}>{u.is_active ? "да" : "нет"}</Badge></TableCell>
                    <TableCell>{u.is_superuser ? <Badge>админ</Badge> : <span className="text-xs text-muted-foreground">—</span>}</TableCell>
                    <TableCell className="text-xs">{fmtDate(u.created_at)}</TableCell>
                  </TableRow>
                ))}
                {users?.length === 0 && <TableRow><TableCell colSpan={6} className="py-6 text-center text-muted-foreground">Нет пользователей</TableCell></TableRow>}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Новый пользователь</CardTitle></CardHeader>
        <CardContent>
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
            <div><Label>Эл. почта</Label><Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
            <div><Label>Имя</Label><Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></div>
            <div><Label>Пароль</Label><Input type="password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
            <div className="flex items-center gap-2"><Switch checked={form.is_active} onCheckedChange={(v) => setForm({ ...form, is_active: v })} /><Label>Активен</Label></div>
            <div className="flex items-center gap-2"><Switch checked={form.is_superuser} onCheckedChange={(v) => setForm({ ...form, is_superuser: v })} /><Label>Суперпользователь</Label></div>
            <Button type="submit" disabled={create.isPending} className="w-full">{create.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <Plus className="h-4 w-4 mr-1.5" />}Создать</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function ExportsTab() {
  const { activeId } = useAccounts();
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const download = async (path: string, filename: string, withDates = false) => {
    if (!activeId) return toast.error("Выберите аккаунт");
    try {
      const query: Record<string, string | number> = { account_id: activeId };
      if (withDates) {
        if (dateFrom) query.date_from = dateFrom;
        if (dateTo) query.date_to = dateTo;
      }
      const res = await api<Response>(path, { query, raw: true });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
      toast.success("Файл скачан");
    } catch (e) { toast.error((e as Error).message); }
  };

  const items = [
    { p: "/export/profit-by-sku.xlsx", n: "profit-by-sku.xlsx", t: "Прибыль по SKU", d: true },
    { p: "/export/reconciliation.xlsx", n: "reconciliation.xlsx", t: "Сверка финансов", d: true },
    { p: "/export/stock.xlsx", n: "stock.xlsx", t: "Остатки", d: true },
    { p: "/export/missing-costs.xlsx", n: "missing-costs.xlsx", t: "Отсутствующая себестоимость", d: false },
    { p: "/export/data-quality.xlsx", n: "data-quality.xlsx", t: "Качество данных", d: false },
  ];
  return (
    <div className="space-y-3">
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Период (для отчётов с датой)</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-2 gap-2 max-w-md">
          <div><Label className="text-xs">Дата с</Label><Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div>
          <div><Label className="text-xs">Дата по</Label><Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div>
        </CardContent>
      </Card>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {items.map((it) => (
          <Card key={it.p}>
            <CardContent className="p-4 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                <FileSpreadsheet className="h-5 w-5 text-success shrink-0" />
                <div className="min-w-0">
                  <div className="font-medium text-sm truncate">{it.t}</div>
                  <div className="text-xs text-muted-foreground font-mono truncate">{it.n}</div>
                </div>
              </div>
              <Button size="sm" variant="outline" onClick={() => download(it.p, it.n, it.d)} disabled={!activeId}><Download className="h-3.5 w-3.5 mr-1" />Скачать</Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function DocsTab() {
  const { activeId } = useAccounts();
  const docs = useQuery({
    queryKey: ["documents", activeId],
    queryFn: () => api<Paginated<Record<string, unknown>>>("/documents", { query: { account_id: activeId ?? undefined, limit: 50 } }),
    enabled: !!activeId,
  });
  const supplies = useQuery({
    queryKey: ["supplies", activeId],
    queryFn: () => api<Paginated<Record<string, unknown>>>("/supplies", { query: { account_id: activeId ?? undefined, limit: 50 } }),
    enabled: !!activeId,
  });
  const tariffs = useQuery({
    queryKey: ["tariffs", activeId],
    queryFn: () => apiList<Record<string, unknown>>("/tariffs", { query: { account_id: activeId ?? undefined, limit: 50 } }),
    enabled: !!activeId,
  });
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Документы</CardTitle><CardDescription className="text-xs">Всего: {docs.data?.total ?? "—"}</CardDescription></CardHeader>
        <CardContent className="p-0 max-h-[480px] overflow-y-auto">
          <Table><TableBody>
            {docs.data?.items.map((d, i) => (
              <TableRow key={i}><TableCell className="text-xs">{(d.type as string) ?? (d.doc_type as string) ?? "doc"}</TableCell><TableCell className="text-xs font-mono">{(d.number as string) ?? (d.id as number) ?? "—"}</TableCell><TableCell className="text-xs text-right">{fmtDate((d.date as string | null) ?? (d.created_at as string | null))}</TableCell></TableRow>
            ))}
            {(docs.data?.items.length ?? 0) === 0 && <TableRow><TableCell className="py-6 text-center text-muted-foreground text-sm">Нет</TableCell></TableRow>}
          </TableBody></Table>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Поставки</CardTitle><CardDescription className="text-xs">Всего: {supplies.data?.total ?? "—"}</CardDescription></CardHeader>
        <CardContent className="p-0 max-h-[480px] overflow-y-auto">
          <Table><TableBody>
            {supplies.data?.items.map((s, i) => (
              <TableRow key={i}><TableCell className="text-xs font-mono">{(s.supply_id as string) ?? (s.id as number)}</TableCell><TableCell className="text-xs">{(s.name as string) ?? "—"}</TableCell><TableCell className="text-xs text-right">{fmtDate((s.created_at as string | null) ?? null)}</TableCell></TableRow>
            ))}
            {(supplies.data?.items.length ?? 0) === 0 && <TableRow><TableCell className="py-6 text-center text-muted-foreground text-sm">Нет</TableCell></TableRow>}
          </TableBody></Table>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Тарифы</CardTitle></CardHeader>
        <CardContent className="p-0 max-h-[480px] overflow-y-auto">
          <Table><TableBody>
            {tariffs.data?.map((t, i) => (
              <TableRow key={i}><TableCell className="text-xs">{(t.name as string) ?? (t.type as string) ?? "—"}</TableCell><TableCell className="text-xs text-right tabular-nums">{fmtNum(t.value as number ?? t.rate as number)}</TableCell></TableRow>
            ))}
            {(tariffs.data?.length ?? 0) === 0 && <TableRow><TableCell className="py-6 text-center text-muted-foreground text-sm">Нет</TableCell></TableRow>}
          </TableBody></Table>
        </CardContent>
      </Card>
    </div>
  );
}
