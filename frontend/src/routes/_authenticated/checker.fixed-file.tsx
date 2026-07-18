// @ts-nocheck
import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowUpDown,
  Check,
  Database,
  Download,
  FileSpreadsheet,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  TableProperties,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { EndpointError } from "@/components/EndpointError";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { PageHeader, PageShell } from "@/components/PageShell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useAccounts } from "@/lib/account-context";
import {
  clearCardQualityFixedFile,
  createCardQualityFixedFileEntry,
  deleteCardQualityFixedFileEntry,
  downloadCardQualityFixedFile,
  fetchCardQualityFixedFileEntries,
  fetchCardQualityFixedFileStatus,
  updateCardQualityFixedFileEntry,
  uploadCardQualityFixedFile,
  type CardQualityFixedFileEntry,
  type CardQualityFixedFileEntryPayload,
} from "@/lib/portal";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_authenticated/checker/fixed-file")({
  component: CheckerFixedFilePage,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

const PAGE_SIZE = 100;

type SortKey =
  | "nm_id"
  | "brand"
  | "subject_name"
  | "char_name"
  | "fixed_value"
  | "updated_at";

type SortDir = "asc" | "desc";

function numberText(value: unknown) {
  return Number(value ?? 0).toLocaleString("ru-RU");
}

function text(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function emptyDraft(): CardQualityFixedFileEntryPayload {
  return {
    nm_id: undefined,
    brand: "",
    subject_name: "",
    char_name: "",
    fixed_value: "",
  };
}

function normalizePayload(payload: CardQualityFixedFileEntryPayload) {
  return {
    nm_id: Number(payload.nm_id),
    brand: text(payload.brand).trim() || null,
    subject_name: text(payload.subject_name).trim() || null,
    char_name: text(payload.char_name).trim(),
    fixed_value: text(payload.fixed_value).trim(),
  };
}

function validatePayload(payload: CardQualityFixedFileEntryPayload) {
  const normalized = normalizePayload(payload);
  if (!Number.isFinite(normalized.nm_id) || normalized.nm_id <= 0) {
    throw new Error("nmID обязателен");
  }
  if (!normalized.char_name) throw new Error("Характеристика обязательна");
  if (!normalized.fixed_value)
    throw new Error("Эталонное значение обязательно");
  return normalized;
}

function CheckerFixedFilePage() {
  const { activeId } = useAccounts();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [search, setSearch] = useState("");
  const [nmId, setNmId] = useState("");
  const [brand, setBrand] = useState("");
  const [subjectName, setSubjectName] = useState("");
  const [charName, setCharName] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("nm_id");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [offset, setOffset] = useState(0);
  const [replaceAll, setReplaceAll] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] =
    useState<CardQualityFixedFileEntryPayload>(emptyDraft);
  const [createOpen, setCreateOpen] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const [newDraft, setNewDraft] =
    useState<CardQualityFixedFileEntryPayload>(emptyDraft);
  const debouncedSearch = useDebouncedValue(search.trim(), 250);
  const debouncedNmId = useDebouncedValue(nmId.trim(), 250);
  const debouncedBrand = useDebouncedValue(brand.trim(), 250);
  const debouncedSubjectName = useDebouncedValue(subjectName.trim(), 250);
  const debouncedCharName = useDebouncedValue(charName.trim(), 250);

  const filters = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset,
      ...(debouncedSearch ? { search: debouncedSearch } : {}),
      ...(debouncedNmId ? { nm_id: debouncedNmId } : {}),
      ...(debouncedBrand ? { brand: debouncedBrand } : {}),
      ...(debouncedSubjectName ? { subject_name: debouncedSubjectName } : {}),
      ...(debouncedCharName ? { char_name: debouncedCharName } : {}),
      sort_by: sortBy,
      sort_dir: sortDir,
    }),
    [
      debouncedBrand,
      debouncedCharName,
      debouncedNmId,
      debouncedSearch,
      debouncedSubjectName,
      offset,
      sortBy,
      sortDir,
    ],
  );

  const statusQuery = useQuery({
    queryKey: ["checker-fixed-file-status", activeId],
    enabled: !!activeId,
    queryFn: () => fetchCardQualityFixedFileStatus(activeId),
    staleTime: 30_000,
  });

  const entriesQuery = useQuery({
    queryKey: ["checker-fixed-file-entries", activeId, filters],
    enabled: !!activeId,
    queryFn: () => fetchCardQualityFixedFileEntries(activeId, filters),
    staleTime: 15_000,
  });

  function invalidateFixedFile() {
    queryClient.invalidateQueries({
      queryKey: ["checker-fixed-file-status", activeId],
    });
    queryClient.invalidateQueries({
      queryKey: ["checker-fixed-file-entries", activeId],
    });
    queryClient.invalidateQueries({ queryKey: ["checker-products"] });
  }

  const uploadMutation = useMutation({
    mutationFn: (file: File) =>
      uploadCardQualityFixedFile(activeId, file, replaceAll),
    onSuccess: (result: any) => {
      toast.success(result?.message ?? "Fixed file загружен");
      setOffset(0);
      invalidateFixedFile();
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось загрузить fixed file"),
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: number;
      payload: CardQualityFixedFileEntryPayload;
    }) =>
      updateCardQualityFixedFileEntry(activeId, id, validatePayload(payload)),
    onSuccess: () => {
      toast.success("Строка обновлена");
      setEditingId(null);
      invalidateFixedFile();
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось сохранить строку"),
  });

  const createMutation = useMutation({
    mutationFn: (payload: CardQualityFixedFileEntryPayload) =>
      createCardQualityFixedFileEntry(activeId, validatePayload(payload)),
    onSuccess: () => {
      toast.success("Строка добавлена");
      setCreateOpen(false);
      setNewDraft(emptyDraft());
      setOffset(0);
      invalidateFixedFile();
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось добавить строку"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteCardQualityFixedFileEntry(activeId, id),
    onSuccess: () => {
      toast.success("Строка удалена");
      invalidateFixedFile();
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось удалить строку"),
  });

  const clearMutation = useMutation({
    mutationFn: () => clearCardQualityFixedFile(activeId),
    onSuccess: (result: any) => {
      toast.success(`Удалено: ${numberText(result?.deleted)}`);
      setClearOpen(false);
      setOffset(0);
      invalidateFixedFile();
    },
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось очистить fixed file"),
  });

  const exportMutation = useMutation({
    mutationFn: () =>
      downloadCardQualityFixedFile(activeId, {
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
        ...(debouncedNmId ? { nm_id: debouncedNmId } : {}),
        ...(debouncedBrand ? { brand: debouncedBrand } : {}),
        ...(debouncedSubjectName ? { subject_name: debouncedSubjectName } : {}),
        ...(debouncedCharName ? { char_name: debouncedCharName } : {}),
        sort_by: sortBy,
        sort_dir: sortDir,
      }),
    onError: (error: any) =>
      toast.error(error?.message ?? "Не удалось скачать файл"),
  });

  const rows = entriesQuery.data?.items ?? [];
  const total = Number(entriesQuery.data?.total ?? 0);
  const summary = entriesQuery.data?.summary ?? statusQuery.data;
  const busy =
    uploadMutation.isPending ||
    updateMutation.isPending ||
    createMutation.isPending ||
    deleteMutation.isPending ||
    clearMutation.isPending ||
    exportMutation.isPending;

  function resetFilters() {
    setSearch("");
    setNmId("");
    setBrand("");
    setSubjectName("");
    setCharName("");
    setSortBy("nm_id");
    setSortDir("asc");
    setOffset(0);
  }

  function onFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    if (file) uploadMutation.mutate(file);
    event.currentTarget.value = "";
  }

  function startEdit(row: CardQualityFixedFileEntry) {
    setEditingId(row.id);
    setDraft({
      nm_id: row.nm_id,
      brand: row.brand ?? "",
      subject_name: row.subject_name ?? "",
      char_name: row.char_name,
      fixed_value: row.fixed_value,
    });
  }

  if (!activeId) {
    return (
      <PageShell>
        <PageHeader title="Fixed file" />
        <NoAccountSelected message="Выберите WB-аккаунт в верхней панели." />
      </PageShell>
    );
  }

  return (
    <PageShell>
      <PageHeader
        title="Fixed file"
        description="Эталонные значения характеристик, которые checker сверяет перед AI-решениями."
        actions={
          <>
            <Button asChild variant="outline">
              <Link to="/checker">
                <ArrowLeft className="h-4 w-4" />К checker
              </Link>
            </Button>
            <input
              ref={inputRef}
              type="file"
              accept=".xlsx,.xls,.xlsm"
              className="hidden"
              onChange={onFileSelected}
            />
            <Button
              variant="outline"
              onClick={() => inputRef.current?.click()}
              disabled={uploadMutation.isPending}
            >
              {uploadMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              Загрузить Excel
            </Button>
            <Button
              variant="outline"
              onClick={() => exportMutation.mutate()}
              disabled={exportMutation.isPending || !summary?.has_fixed_file}
            >
              {exportMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              Скачать
            </Button>
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" />
              Строка
            </Button>
          </>
        }
      />

      <div className="mb-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard
          icon={Database}
          label="Значения"
          value={summary?.total ?? 0}
        />
        <MetricCard
          icon={TableProperties}
          label="Карточки"
          value={summary?.total_cards ?? 0}
        />
        <MetricCard
          icon={FileSpreadsheet}
          label="Характеристики"
          value={summary?.total_characteristics ?? 0}
        />
        <MetricCard
          icon={Check}
          label="Категории"
          value={summary?.total_subjects ?? 0}
        />
        <MetricCard
          icon={RefreshCw}
          label="Обновлено"
          value={formatDate(summary?.last_updated_at)}
        />
      </div>

      <Card className="mb-4">
        <CardContent className="space-y-3 p-3">
          <div className="grid gap-2 xl:grid-cols-[minmax(240px,1.2fr)_140px_180px_180px_200px_160px_118px]">
            <FilterInput
              icon
              placeholder="Поиск по таблице..."
              value={search}
              onChange={setSearch}
            />
            <FilterInput
              placeholder="nmID"
              value={nmId}
              onChange={setNmId}
              inputMode="numeric"
            />
            <FilterInput
              placeholder="Бренд"
              value={brand}
              onChange={setBrand}
            />
            <FilterInput
              placeholder="Категория"
              value={subjectName}
              onChange={setSubjectName}
            />
            <FilterInput
              placeholder="Характеристика"
              value={charName}
              onChange={setCharName}
            />
            <Select
              value={sortBy}
              onValueChange={(value) => setSortBy(value as SortKey)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="nm_id">nmID</SelectItem>
                <SelectItem value="brand">Бренд</SelectItem>
                <SelectItem value="subject_name">Категория</SelectItem>
                <SelectItem value="char_name">Характеристика</SelectItem>
                <SelectItem value="fixed_value">Значение</SelectItem>
                <SelectItem value="updated_at">Обновлено</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              onClick={() =>
                setSortDir((value) => (value === "asc" ? "desc" : "asc"))
              }
            >
              <ArrowUpDown className="h-4 w-4" />
              {sortDir.toUpperCase()}
            </Button>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <div className="flex flex-wrap items-center gap-2">
              <span>Показано: {numberText(rows.length)}</span>
              <span>· найдено: {numberText(total)}</span>
              <Badge variant="outline" className="text-[11px]">
                account {activeId}
              </Badge>
              <label className="flex items-center gap-2 rounded-md border px-2 py-1 text-[11px]">
                <Checkbox
                  checked={replaceAll}
                  onCheckedChange={(checked) => setReplaceAll(Boolean(checked))}
                />
                Заменить при загрузке
              </label>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={resetFilters}>
                <X className="h-3.5 w-3.5" />
                Сбросить
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => entriesQuery.refetch()}
                disabled={entriesQuery.isFetching}
              >
                <RefreshCw
                  className={cn(
                    "h-3.5 w-3.5",
                    entriesQuery.isFetching && "animate-spin",
                  )}
                />
                Обновить
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={() => setClearOpen(true)}
                disabled={busy || !summary?.has_fixed_file}
              >
                <Trash2 className="h-3.5 w-3.5" />
                Очистить
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {entriesQuery.isError ? (
        <Alert className="mb-4 border-destructive/40">
          <FileSpreadsheet className="h-4 w-4" />
          <AlertTitle>Fixed file не загрузился</AlertTitle>
          <AlertDescription>
            {entriesQuery.error?.message ??
              "Проверьте backend endpoint fixed-file."}
          </AlertDescription>
        </Alert>
      ) : null}

      <Card className="overflow-hidden">
        <CardContent className="p-0">
          {entriesQuery.isLoading ? (
            <div className="space-y-2 p-3">
              {Array.from({ length: 10 }).map((_, index) => (
                <Skeleton key={index} className="h-10 rounded-md" />
              ))}
            </div>
          ) : rows.length ? (
            <div className="max-h-[64vh] overflow-auto">
              <Table className="min-w-[1120px] text-xs">
                <TableHeader className="sticky top-0 z-10 bg-muted/95 backdrop-blur">
                  <TableRow className="hover:bg-muted/95">
                    <SortableHead
                      label="nmID"
                      active={sortBy === "nm_id"}
                      onClick={() => setSortBy("nm_id")}
                    />
                    <SortableHead
                      label="Бренд"
                      active={sortBy === "brand"}
                      onClick={() => setSortBy("brand")}
                    />
                    <SortableHead
                      label="Категория"
                      active={sortBy === "subject_name"}
                      onClick={() => setSortBy("subject_name")}
                    />
                    <SortableHead
                      label="Характеристика"
                      active={sortBy === "char_name"}
                      onClick={() => setSortBy("char_name")}
                    />
                    <SortableHead
                      label="Эталонное значение"
                      active={sortBy === "fixed_value"}
                      onClick={() => setSortBy("fixed_value")}
                    />
                    <SortableHead
                      label="Обновлено"
                      active={sortBy === "updated_at"}
                      onClick={() => setSortBy("updated_at")}
                    />
                    <TableHead className="w-[116px] text-right">
                      Действия
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <FixedFileRow
                      key={row.id}
                      row={row}
                      editing={editingId === row.id}
                      draft={draft}
                      setDraft={setDraft}
                      busy={busy}
                      onEdit={() => startEdit(row)}
                      onCancel={() => setEditingId(null)}
                      onSave={() =>
                        updateMutation.mutate({ id: row.id, payload: draft })
                      }
                      onDelete={() => deleteMutation.mutate(row.id)}
                    />
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <div className="flex min-h-[260px] flex-col items-center justify-center gap-3 p-8 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg border bg-muted text-muted-foreground">
                <FileSpreadsheet className="h-6 w-6" />
              </div>
              <div>
                <div className="font-semibold">Fixed file пустой</div>
                <div className="mt-1 max-w-md text-sm text-muted-foreground">
                  Загрузите Excel или добавьте первую строку вручную.
                </div>
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                <Button
                  variant="outline"
                  onClick={() => inputRef.current?.click()}
                >
                  <Upload className="h-4 w-4" />
                  Загрузить
                </Button>
                <Button onClick={() => setCreateOpen(true)}>
                  <Plus className="h-4 w-4" />
                  Добавить строку
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="mt-4 flex items-center justify-between">
        <Button
          variant="outline"
          disabled={offset === 0 || entriesQuery.isFetching}
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        >
          Назад
        </Button>
        <div className="text-xs text-muted-foreground">
          {total
            ? `${numberText(offset + 1)}-${numberText(offset + rows.length)} из ${numberText(total)}`
            : "0"}
        </div>
        <Button
          variant="outline"
          disabled={offset + PAGE_SIZE >= total || entriesQuery.isFetching}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          Далее
        </Button>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Новая строка fixed file</DialogTitle>
          </DialogHeader>
          <EntryForm value={newDraft} onChange={setNewDraft} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Отмена
            </Button>
            <Button
              onClick={() => createMutation.mutate(newDraft)}
              disabled={createMutation.isPending}
            >
              {createMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Добавить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={clearOpen} onOpenChange={setClearOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Очистить fixed file</DialogTitle>
            <DialogDescription>
              Все эталонные значения текущего аккаунта будут удалены. Checker
              перестанет сверять fixed-file до следующей загрузки.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setClearOpen(false)}>
              Отмена
            </Button>
            <Button
              variant="destructive"
              onClick={() => clearMutation.mutate()}
              disabled={clearMutation.isPending}
            >
              {clearMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Очистить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}

function MetricCard({ icon: Icon, label, value }: any) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-primary/20 bg-primary/10 text-primary">
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-xs text-muted-foreground">{label}</div>
          <div className="truncate text-lg font-semibold tabular-nums">
            {typeof value === "number" ? numberText(value) : value}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function FilterInput({ icon, value, onChange, ...props }: any) {
  return (
    <div className="relative">
      {icon ? (
        <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
      ) : null}
      <Input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={cn(icon && "pl-9")}
        {...props}
      />
    </div>
  );
}

function SortableHead({ label, active, onClick }: any) {
  return (
    <TableHead>
      <button
        onClick={onClick}
        className={cn(
          "inline-flex items-center gap-1 text-left text-[11px] font-semibold uppercase",
          active ? "text-foreground" : "text-muted-foreground",
        )}
      >
        {label}
        <ArrowUpDown className="h-3 w-3" />
      </button>
    </TableHead>
  );
}

function FixedFileRow({
  row,
  editing,
  draft,
  setDraft,
  busy,
  onEdit,
  onCancel,
  onSave,
  onDelete,
}: any) {
  if (editing) {
    return (
      <TableRow className="bg-primary/5 hover:bg-primary/5">
        <TableCell className="w-[120px]">
          <CellInput
            value={draft.nm_id ?? ""}
            onChange={(value) => setDraft({ ...draft, nm_id: value })}
          />
        </TableCell>
        <TableCell className="w-[170px]">
          <CellInput
            value={draft.brand ?? ""}
            onChange={(value) => setDraft({ ...draft, brand: value })}
          />
        </TableCell>
        <TableCell className="w-[190px]">
          <CellInput
            value={draft.subject_name ?? ""}
            onChange={(value) => setDraft({ ...draft, subject_name: value })}
          />
        </TableCell>
        <TableCell className="w-[240px]">
          <CellInput
            value={draft.char_name ?? ""}
            onChange={(value) => setDraft({ ...draft, char_name: value })}
          />
        </TableCell>
        <TableCell>
          <CellInput
            value={draft.fixed_value ?? ""}
            onChange={(value) => setDraft({ ...draft, fixed_value: value })}
          />
        </TableCell>
        <TableCell className="w-[140px] text-muted-foreground">
          {formatDate(row.updated_at)}
        </TableCell>
        <TableCell className="w-[116px]">
          <div className="flex justify-end gap-1">
            <Button
              size="icon"
              className="h-8 w-8"
              onClick={onSave}
              disabled={busy}
            >
              <Check className="h-4 w-4" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8"
              onClick={onCancel}
              disabled={busy}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </TableCell>
      </TableRow>
    );
  }

  return (
    <TableRow>
      <TableCell className="font-mono tabular-nums">{row.nm_id}</TableCell>
      <TableCell className="max-w-[170px] truncate">
        {row.brand || "—"}
      </TableCell>
      <TableCell className="max-w-[190px] truncate">
        {row.subject_name || "—"}
      </TableCell>
      <TableCell className="max-w-[240px] truncate font-medium">
        {row.char_name}
      </TableCell>
      <TableCell className="max-w-[360px] truncate">
        {row.fixed_value}
      </TableCell>
      <TableCell className="whitespace-nowrap text-muted-foreground">
        {formatDate(row.updated_at)}
      </TableCell>
      <TableCell>
        <div className="flex justify-end gap-1">
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            onClick={onEdit}
            disabled={busy}
          >
            <Pencil className="h-4 w-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8 text-destructive hover:text-destructive"
            onClick={onDelete}
            disabled={busy}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

function CellInput({ value, onChange }: any) {
  return (
    <Input
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-8 bg-background text-xs"
    />
  );
}

function EntryForm({ value, onChange }: any) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <InputField
        label="nmID"
        value={value.nm_id ?? ""}
        onChange={(v) => onChange({ ...value, nm_id: v })}
      />
      <InputField
        label="Бренд"
        value={value.brand ?? ""}
        onChange={(v) => onChange({ ...value, brand: v })}
      />
      <InputField
        label="Категория"
        value={value.subject_name ?? ""}
        onChange={(v) => onChange({ ...value, subject_name: v })}
      />
      <InputField
        label="Характеристика"
        value={value.char_name ?? ""}
        onChange={(v) => onChange({ ...value, char_name: v })}
      />
      <div className="sm:col-span-2">
        <InputField
          label="Эталонное значение"
          value={value.fixed_value ?? ""}
          onChange={(v) => onChange({ ...value, fixed_value: v })}
        />
      </div>
    </div>
  );
}

function InputField({ label, value, onChange }: any) {
  return (
    <label className="space-y-1.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <Input value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}
