import { useLocation, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import {
  Bot,
  Check,
  Download,
  FileText,
  Loader2,
  Maximize2,
  Minimize2,
  PackageSearch,
  Search,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { useAccounts } from "@/lib/account-context";
import { buildAgentPageContext } from "@/lib/agent-page-context";
import {
  createAgentManualTask,
  sendAgentMessage,
  type AgentIntent,
  type AgentMessageResponse,
  type AgentProductRef,
  type AgentUIAction,
} from "@/lib/agent";
import { api } from "@/lib/api";
import { fetchPortalProducts, type PortalProductRow } from "@/lib/portal";
import { cn } from "@/lib/utils";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: AgentMessageResponse;
};

type PickerState = {
  open: boolean;
  intent: AgentIntent;
  query: string;
  draftMessage: string;
  products: AgentProductRef[];
};

type TitleState = {
  open: boolean;
  nmId: number | null;
  currentTitle: string;
  newTitle: string;
};

type PreviewState = {
  open: boolean;
  payload: Record<string, unknown>;
};

function nextId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function fileNameFromDisposition(header: string | null, fallback: string) {
  if (!header) return fallback;
  const value = header
    .split(";")
    .map((part) => part.trim())
    .find((part) => {
      const key = part.split("=", 1)[0]?.trim().toLowerCase();
      return key === "filename" || key === "filename*";
    });
  if (!value) return fallback;
  const separatorIndex = value.indexOf("=");
  if (separatorIndex < 0) return fallback;
  let filename = value.slice(separatorIndex + 1).trim();
  if (filename.toLowerCase().startsWith("utf-8''")) {
    filename = filename.slice("utf-8''".length);
  }
  if (filename.startsWith('"') && filename.endsWith('"')) {
    filename = filename.slice(1, -1);
  }
  if (!filename) return fallback;
  try {
    return decodeURIComponent(filename);
  } catch {
    return filename;
  }
}

function productTitle(product: AgentProductRef) {
  return product.title || product.vendor_code || `nm ${product.nm_id}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function compactText(value: unknown, maxLength = 420) {
  const text =
    typeof value === "string"
      ? value
      : JSON.stringify(value, null, 2) || String(value);
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
}

function summarizeApiActionResult(value: unknown) {
  if (value == null) return "";
  if (Array.isArray(value)) return `Получено элементов: ${value.length}.`;
  if (!isRecord(value)) return compactText(value);

  const parts: string[] = [];
  const preferredKeys = [
    "status",
    "message",
    "id",
    "scenario_id",
    "run_id",
    "scenario_type",
    "run_type",
    "total",
    "count",
    "scenarios_total",
    "active_scenarios",
    "runs_total",
    "runs_last_30d",
    "failed_runs_last_30d",
    "total_tokens",
    "estimated_cost_usd",
    "checked_accounts",
    "opened_count",
    "updated_count",
    "resolved_count",
    "active_count",
    "sku_rows",
    "stock_rows",
    "finance_rows",
  ];
  for (const key of preferredKeys) {
    const item = value[key];
    if (
      typeof item === "string" ||
      typeof item === "number" ||
      typeof item === "boolean"
    ) {
      parts.push(`${key}: ${item}`);
    }
  }
  const items = value.items;
  if (Array.isArray(items)) parts.push(`items: ${items.length}`);
  const previews = value.actions_preview_json;
  if (Array.isArray(previews)) {
    parts.push(`action previews: ${previews.length}`);
  }
  const output = value.output_json;
  if (isRecord(output) && typeof output.summary === "string") {
    parts.push(output.summary);
  }
  const warnings = value.warnings;
  if (Array.isArray(warnings) && warnings.length) {
    parts.push(`warnings: ${warnings.length}`);
  }
  if (parts.length) return parts.slice(0, 10).join("\n");
  return compactText(value);
}

function ProductThumbnail({ product }: { product: AgentProductRef }) {
  const [failed, setFailed] = useState(false);
  if (!product.thumbnail_url || failed) {
    return <PackageSearch className="h-5 w-5 text-muted-foreground" />;
  }
  return (
    <img
      src={product.thumbnail_url}
      alt=""
      className="h-full w-full object-cover"
      onError={() => setFailed(true)}
    />
  );
}

export function AgentDock() {
  const navigate = useNavigate();
  const location = useLocation();
  const { activeId } = useAccounts();
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [searchBusy, setSearchBusy] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      text: "Здравствуйте. Я на связи: можете задать вопрос или написать команду по товарам, остаткам, отзывам, ценам, логистике, отчётам и задачам.",
    },
  ]);
  const [lastResponse, setLastResponse] = useState<AgentMessageResponse | null>(
    null,
  );
  const [picker, setPicker] = useState<PickerState>({
    open: false,
    intent: "product_details",
    query: "",
    draftMessage: "",
    products: [],
  });
  const [titleEditor, setTitleEditor] = useState<TitleState>({
    open: false,
    nmId: null,
    currentTitle: "",
    newTitle: "",
  });
  const [preview, setPreview] = useState<PreviewState>({
    open: false,
    payload: {},
  });
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [busy, messages, open]);

  const send = async (message: string, extra: Record<string, unknown> = {}) => {
    const text = message.trim();
    if (!activeId) {
      toast.error("Аккаунт не выбран");
      return;
    }
    if (!text && !extra.intent) return;
    if (text) {
      setMessages((items) => [...items, { id: nextId(), role: "user", text }]);
    }
    setBusy(true);
    try {
      const response = await sendAgentMessage({
        account_id: activeId,
        message: text,
        context: buildAgentPageContext(),
        ...extra,
      });
      setLastResponse(response);
      setMessages((items) => [
        ...items,
        {
          id: nextId(),
          role: "assistant",
          text: response.message,
          response,
        },
      ]);
      handleAutoAction(response);
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleAutoAction = (response: AgentMessageResponse) => {
    const pickerAction = response.actions.find(
      (action) => action.type === "open_product_picker",
    );
    const titleAction = response.actions.find(
      (action) => action.type === "open_title_editor",
    );
    const previewAction = response.actions.find(
      (action) => action.type === "open_preview_dialog",
    );
    if (pickerAction && response.intent !== "help") {
      openPicker(pickerAction, response.products);
    }
    if (titleAction) openTitleEditor(titleAction);
    if (previewAction) openPreview(previewAction);
  };

  const openPicker = (
    action: AgentUIAction,
    products: AgentProductRef[] = [],
  ) => {
    const payload = action.payload ?? {};
    const intent = String(payload.intent || "product_details") as AgentIntent;
    setPicker({
      open: true,
      intent,
      query: String(payload.search_query || ""),
      draftMessage: String(payload.draft_message || ""),
      products,
    });
  };

  const openTitleEditor = (action: AgentUIAction) => {
    const payload = action.payload ?? {};
    setTitleEditor({
      open: true,
      nmId: Number(payload.nm_id || 0) || null,
      currentTitle: String(payload.current_title || ""),
      newTitle: "",
    });
  };

  const openPreview = (action: AgentUIAction) => {
    setPreview({ open: true, payload: action.payload ?? {} });
  };

  const runAction = async (action: AgentUIAction) => {
    if (action.type === "navigate" && action.href) {
      navigate({ to: action.href as never });
      return;
    }
    if (action.type === "open_product_picker") {
      openPicker(action, lastResponse?.products ?? []);
      return;
    }
    if (action.type === "open_title_editor") {
      openTitleEditor(action);
      return;
    }
    if (action.type === "open_preview_dialog") {
      openPreview(action);
      return;
    }
    if (action.type === "download_file" && action.href) {
      await downloadAction(action);
      return;
    }
    if (action.type === "api_request" && action.href) {
      await runApiAction(action);
      return;
    }
    if (action.type === "create_manual_task") {
      await createTask(action);
    }
  };

  const downloadAction = async (action: AgentUIAction) => {
    if (!action.href) return;
    setBusy(true);
    try {
      const res = await api<Response>(action.href, { raw: true });
      if (!res.ok) throw new Error(`Не удалось скачать файл (${res.status})`);
      const blob = await res.blob();
      const filename = fileNameFromDisposition(
        res.headers.get("content-disposition"),
        `${action.title || "выгрузка"}.xlsx`,
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Файл скачан");
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const createTask = async (action: AgentUIAction) => {
    setBusy(true);
    try {
      await createAgentManualTask(action.payload ?? {});
      toast.success("Задача создана");
      setPreview((value) => ({ ...value, open: false }));
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const runApiAction = async (action: AgentUIAction) => {
    if (!action.href) return;
    if (action.confirm_required) {
      const ok = window.confirm(
        `${action.description || "Действие изменит состояние портала."}\n\nВыполнить действие?`,
      );
      if (!ok) return;
    }
    const method = String(action.method || "GET").toUpperCase();
    const payload = action.payload ?? {};
    const body = method === "GET" ? undefined : payload.body;
    const successMessage =
      typeof payload.success_message === "string" && payload.success_message
        ? payload.success_message
        : "Действие выполнено.";
    setBusy(true);
    try {
      const result = await api<unknown>(action.href, {
        method,
        body,
      });
      const summary = summarizeApiActionResult(result);
      setMessages((items) => [
        ...items,
        {
          id: nextId(),
          role: "assistant",
          text: summary ? `${successMessage}\n${summary}` : successMessage,
        },
      ]);
      toast.success(successMessage);
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const searchProducts = async () => {
    if (!activeId) return;
    setSearchBusy(true);
    try {
      const page = await fetchPortalProducts(activeId, {
        search: picker.query,
        limit: 10,
        offset: 0,
      });
      setPicker((value) => ({
        ...value,
        products: (page.items ?? []).map((item: PortalProductRow) => ({
          nm_id: item.nm_id,
          vendor_code: item.vendor_code,
          title: item.title,
          brand: item.brand,
          subject_name: item.subject_name,
          thumbnail_url:
            item.thumbnail_url ||
            item.main_photo_url ||
            item.image_url ||
            item.photo_url ||
            item.thumbnail,
        })),
      }));
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setSearchBusy(false);
    }
  };

  const selectProduct = async (product: AgentProductRef) => {
    setPicker((value) => ({ ...value, open: false }));
    await send(`Выбран товар: ${productTitle(product)}`, {
      intent: picker.intent,
      selected_nm_id: product.nm_id,
      message: picker.draftMessage || `${picker.intent} ${product.nm_id}`,
    });
  };

  const submitTitle = async () => {
    if (!titleEditor.nmId || !titleEditor.newTitle.trim()) return;
    setTitleEditor((value) => ({ ...value, open: false }));
    await send(`title ${titleEditor.nmId}`, {
      intent: "title_update",
      selected_nm_id: titleEditor.nmId,
      new_title: titleEditor.newTitle.trim(),
    });
  };

  const createTaskAction =
    lastResponse?.actions.find(
      (action) => action.type === "create_manual_task",
    ) ?? null;
  const isReputationRoute = location.pathname.includes("/reputation");

  return (
    <>
      <div
        className={cn(
          "fixed bottom-3 right-3 z-40 flex flex-col items-end gap-2 sm:bottom-4 sm:right-4",
          isReputationRoute && !open ? "max-sm:hidden" : null,
        )}
      >
        {open ? (
          <div
            className={cn(
              "flex overflow-hidden rounded-lg border border-border bg-background shadow-2xl",
              expanded
                ? "h-[min(760px,calc(100vh-48px))] w-[min(760px,calc(100vw-32px))]"
                : "h-[520px] w-[min(420px,calc(100vw-32px))]",
            )}
          >
            <div className="flex min-w-0 flex-1 flex-col">
              <div className="flex h-12 shrink-0 items-center justify-between border-b px-3">
                <div className="flex min-w-0 items-center gap-2">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
                    <Bot className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold">
                      AI оператор
                    </div>
                    <div className="truncate text-[11px] text-muted-foreground">
                      Администратор портала
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-8 w-8"
                    onClick={() => setExpanded((value) => !value)}
                  >
                    {expanded ? (
                      <Minimize2 className="h-4 w-4" />
                    ) : (
                      <Maximize2 className="h-4 w-4" />
                    )}
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-8 w-8"
                    onClick={() => setOpen(false)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              <ScrollArea className="min-h-0 flex-1 px-3 py-3">
                <div className="space-y-3">
                  {messages.map((message) => (
                    <div
                      key={message.id}
                      className={cn(
                        "flex",
                        message.role === "user"
                          ? "justify-end"
                          : "justify-start",
                      )}
                    >
                      <div
                        className={cn(
                          "max-w-[88%] rounded-lg px-3 py-2 text-sm leading-snug",
                          message.role === "user"
                            ? "bg-primary text-primary-foreground"
                            : "border bg-muted/45 text-foreground",
                        )}
                      >
                        <div className="whitespace-pre-wrap break-words">
                          {message.text}
                        </div>
                        {message.response?.warnings?.length ? (
                          <div className="mt-2 flex flex-wrap gap-1">
                            {message.response.warnings
                              .slice(0, 3)
                              .map((warning) => (
                                <Badge
                                  key={warning}
                                  variant="outline"
                                  className="max-w-full truncate text-[10px]"
                                >
                                  {warning}
                                </Badge>
                              ))}
                          </div>
                        ) : null}
                        {message.response?.actions?.length ? (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {message.response.actions
                              .slice(0, 4)
                              .map((action, index) => (
                                <Button
                                  key={`${action.type}-${index}`}
                                  size="sm"
                                  variant={
                                    action.type === "download_file" ||
                                    (action.type === "api_request" &&
                                      action.confirm_required)
                                      ? "default"
                                      : "outline"
                                  }
                                  className="h-7 gap-1.5 px-2 text-xs"
                                  onClick={() => runAction(action)}
                                >
                                  {action.type === "download_file" ? (
                                    <Download className="h-3.5 w-3.5" />
                                  ) : action.type === "api_request" ? (
                                    <Check className="h-3.5 w-3.5" />
                                  ) : (
                                    <Sparkles className="h-3.5 w-3.5" />
                                  )}
                                  <span className="max-w-[180px] truncate">
                                    {action.title}
                                  </span>
                                </Button>
                              ))}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ))}
                  {busy ? (
                    <div className="flex justify-start">
                      <div className="flex items-center gap-2 rounded-lg border bg-muted/45 px-3 py-2 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Выполняю...
                      </div>
                    </div>
                  ) : null}
                  <div ref={messagesEndRef} />
                </div>
              </ScrollArea>

              <div className="shrink-0 border-t p-3">
                <div className="flex gap-2">
                  <Textarea
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        const text = input;
                        setInput("");
                        send(text);
                      }
                    }}
                    className="max-h-28 min-h-10 resize-none text-sm"
                    placeholder="Введите вопрос или команду..."
                  />
                  <Button
                    size="icon"
                    className="h-10 w-10 shrink-0"
                    disabled={busy || !input.trim()}
                    onClick={() => {
                      const text = input;
                      setInput("");
                      send(text);
                    }}
                  >
                    {busy ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Send className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        ) : null}

        {!open ? (
          <Button
            className="h-10 w-10 rounded-full p-0 shadow-xl sm:h-11 sm:w-11"
            onClick={() => setOpen(true)}
            title="AI оператор"
            aria-label="AI оператор"
          >
            <Bot className="h-4 w-4" />
          </Button>
        ) : null}
      </div>

      <Dialog
        open={picker.open}
        onOpenChange={(value) =>
          setPicker((state) => ({ ...state, open: value }))
        }
      >
        <DialogContent className="z-[70] max-h-[min(720px,calc(100vh-32px))] max-w-3xl overflow-hidden bg-background p-0 shadow-2xl">
          <DialogHeader className="border-b px-5 py-4 text-left">
            <DialogTitle className="flex items-center gap-2">
              <PackageSearch className="h-5 w-5" />
              Выберите товар
            </DialogTitle>
            <DialogDescription>
              AI оператор продолжит следующий шаг с выбранным товаром.
            </DialogDescription>
          </DialogHeader>
          <div className="border-b px-5 py-3">
            <div className="flex gap-2">
              <Input
                value={picker.query}
                onChange={(event) =>
                  setPicker((value) => ({
                    ...value,
                    query: event.target.value,
                  }))
                }
                placeholder="nmID, артикул или название"
                onKeyDown={(event) => {
                  if (event.key === "Enter") searchProducts();
                }}
              />
              <Button
                variant="outline"
                onClick={searchProducts}
                disabled={searchBusy}
              >
                {searchBusy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
          <ScrollArea className="h-[420px] px-5 py-4">
            <div className="grid gap-2">
              {picker.products.length ? (
                picker.products.map((product) => (
                  <button
                    key={product.nm_id}
                    type="button"
                    className="flex min-h-16 w-full items-center gap-3 rounded-md border bg-background p-2 text-left transition-colors hover:bg-muted"
                    onClick={() => selectProduct(product)}
                  >
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted">
                      <ProductThumbnail product={product} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold">
                        {productTitle(product)}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
                        <span>nm {product.nm_id}</span>
                        {product.vendor_code ? (
                          <span>{product.vendor_code}</span>
                        ) : null}
                        {product.subject_name ? (
                          <span>{product.subject_name}</span>
                        ) : null}
                      </div>
                    </div>
                    <Check className="h-4 w-4 text-muted-foreground" />
                  </button>
                ))
              ) : (
                <div className="py-10 text-center text-sm text-muted-foreground">
                  Товар не найден
                </div>
              )}
            </div>
          </ScrollArea>
        </DialogContent>
      </Dialog>

      <Dialog
        open={titleEditor.open}
        onOpenChange={(value) =>
          setTitleEditor((state) => ({ ...state, open: value }))
        }
      >
        <DialogContent className="z-[70] max-w-2xl bg-background shadow-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Название товара
            </DialogTitle>
            <DialogDescription>
              Сначала будет подготовлен предпросмотр. Карточка WB автоматически
              не изменится.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <div className="mb-1 text-xs font-semibold text-muted-foreground">
                Текущее название
              </div>
              <div className="rounded-md border bg-muted/35 px-3 py-2 text-sm">
                {titleEditor.currentTitle || "—"}
              </div>
            </div>
            <div>
              <div className="mb-1 text-xs font-semibold text-muted-foreground">
                Новое название
              </div>
              <Textarea
                value={titleEditor.newTitle}
                onChange={(event) =>
                  setTitleEditor((value) => ({
                    ...value,
                    newTitle: event.target.value,
                  }))
                }
                className="min-h-24"
                placeholder="Введите новое название..."
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() =>
                setTitleEditor((value) => ({ ...value, open: false }))
              }
            >
              Отмена
            </Button>
            <Button
              onClick={submitTitle}
              disabled={!titleEditor.newTitle.trim() || busy}
            >
              {busy ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="mr-2 h-4 w-4" />
              )}
              Предпросмотр
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={preview.open}
        onOpenChange={(value) =>
          setPreview((state) => ({ ...state, open: value }))
        }
      >
        <DialogContent className="z-[70] max-w-2xl bg-background shadow-2xl">
          <DialogHeader>
            <DialogTitle>Предпросмотр</DialogTitle>
            <DialogDescription>
              Запись в маркетплейс выполняется только через отдельный процесс
              предпросмотра, подтверждения и аудита.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <div className="mb-1 text-xs font-semibold text-muted-foreground">
                  Было
                </div>
                <div className="min-h-24 rounded-md border bg-muted/35 px-3 py-2 text-sm">
                  {String(preview.payload.before ?? "—")}
                </div>
              </div>
              <div>
                <div className="mb-1 text-xs font-semibold text-muted-foreground">
                  Будет
                </div>
                <div className="min-h-24 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
                  {String(preview.payload.after ?? "—")}
                </div>
              </div>
            </div>
            {Array.isArray(preview.payload.warnings) &&
            preview.payload.warnings.length ? (
              <div className="flex flex-wrap gap-1.5">
                {preview.payload.warnings.map((warning: string) => (
                  <Badge
                    key={warning}
                    variant="outline"
                    className="max-w-full truncate"
                  >
                    {warning}
                  </Badge>
                ))}
              </div>
            ) : null}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setPreview((value) => ({ ...value, open: false }))}
            >
              Закрыть
            </Button>
            {createTaskAction ? (
              <Button
                onClick={() => createTask(createTaskAction)}
                disabled={busy}
              >
                {busy ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Check className="mr-2 h-4 w-4" />
                )}
                Создать задачу
              </Button>
            ) : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
