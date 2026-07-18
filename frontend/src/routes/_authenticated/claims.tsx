import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useAccounts } from "@/lib/account-context";
import {
  createClaimCase,
  createCaseFromCandidate,
  extractClaimMedia,
  fetchCases,
  fetchClaimCandidates,
  fetchClaimSupportCategories,
  generateClaimAppealDraft,
  generateClaimDraft,
  lookupClaimOrder,
  proofCheckCase,
  startClaimScan,
  submitCase,
} from "@/lib/portal";
import { useModuleStatus, useModuleVisible } from "@/lib/modules-health";
import { PageShell, PageHeader } from "@/components/PageShell";
import { NoAccountSelected } from "@/components/portal/NoAccountSelected";
import { DataDependencyNotice } from "@/components/data-health/DataCoveragePanel";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { EndpointError } from "@/components/EndpointError";
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  Copy,
  FileText,
  Info,
  ImagePlus,
  Loader2,
  Plus,
  Search,
  ShieldCheck,
  Send,
  Sparkles,
  FlaskConical,
  Video as VideoIcon,
  X,
} from "lucide-react";
import { formatMoney } from "@/lib/format";
import { routeSearchText } from "@/lib/action-center-routing";
import { toast } from "sonner";

type ClaimsSearch = {
  nm_id?: string;
  tab?: string;
};

const CLAIMS_TABS = new Set([
  "candidates",
  "cases",
  "drafts",
  "history",
  "settings",
]);

function normalizeRouteNmId(value: unknown): string {
  return routeSearchText(value)?.replace(/[^\d]/g, "") ?? "";
}

export const Route = createFileRoute("/_authenticated/claims")({
  validateSearch: (search: Record<string, unknown>): ClaimsSearch => {
    const tab = routeSearchText(search.tab);
    const nmId = normalizeRouteNmId(search.nm_id);
    return {
      ...(nmId ? { nm_id: nmId } : {}),
      ...(tab && CLAIMS_TABS.has(tab) ? { tab } : {}),
    };
  },
  component: ClaimsPage,
  errorComponent: ({ error, reset }) => (
    <EndpointError error={error} reset={reset} />
  ),
});

function isAuditCase(c: any): boolean {
  if (!c) return false;
  if (c?.data?.audit === true) return true;
  if (c?.audit === true || c?.is_audit === true || c?.is_test === true)
    return true;
  const src = String(
    c?.source_module ?? c?.source ?? c?.data?.source_module ?? "",
  ).toLowerCase();
  if (src === "audit" || src === "test" || src === "synthetic") return true;
  const t = String(c?.title ?? c?.summary ?? "").toLowerCase();
  if (
    t.includes("runtime audit") ||
    t.includes("runtime-audit") ||
    t.includes("synthetic")
  )
    return true;
  return false;
}

function isSubmittable(c: any): { ok: boolean; reason: string } {
  if (isAuditCase(c))
    return { ok: false, reason: "Тестовый кейс — подача отключена" };
  const status = String(c.status ?? "").toLowerCase();
  if (["submitted", "closed", "resolved", "rejected"].includes(status)) {
    return {
      ok: false,
      reason: `Кейс в статусе «${c.status}» — подача невозможна`,
    };
  }
  const proof = String(c.proof_state ?? "").toLowerCase();
  if (proof && !["ok", "verified", "ready", "passed"].includes(proof)) {
    return { ok: false, reason: "Доказательства не подтверждены" };
  }
  if (
    (c.evidence_count ?? 0) === 0 &&
    (c.draft_count ?? 0) === 0 &&
    proof === ""
  ) {
    return { ok: false, reason: "Нет приложенных доказательств" };
  }
  return { ok: true, reason: "" };
}

const STATIC_SUPPORT_CATEGORIES = [
  {
    label: "Возврат товара продавцу",
    subcategories: [{ label: "Вернулся товар с дефектами" }],
  },
];

function formatBytes(size: number): string {
  if (!Number.isFinite(size)) return "";
  if (size < 1024) return `${size} Б`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} КБ`;
  return `${(size / 1024 / 1024).toFixed(1)} МБ`;
}

function getCategoryName(item: any): string {
  return String(
    item?.label ?? item?.name ?? item?.title ?? item?.category ?? item?.id ?? "",
  );
}

function getSubcategories(item: any): any[] {
  return Array.isArray(item?.subcategories)
    ? item.subcategories
    : Array.isArray(item?.children)
      ? item.children
      : Array.isArray(item?.items)
        ? item.items
        : Array.isArray(item?.subs)
          ? item.subs
          : [];
}

function hasOrderIdentifier(fields: Record<string, any>): boolean {
  return ["srid", "order_id", "shk_id", "sticker_id", "barcode", "nm_id"].some(
    (key) => String(fields?.[key] ?? "").trim(),
  );
}

function makeManualClaimForm(nmId = "") {
  return {
    case_type: "defect",
    priority: "P2",
    title: "",
    summary: "",
    nm_id: nmId,
    vendor_code: "",
    order_id: "",
    srid: "",
    estimated_amount: "",
    sticker_id: "",
    shk_id: "",
    pvz_address: "",
    auto_prepare: true,
  };
}

function claimItemMatchesNmId(item: any, nmId: string): boolean {
  if (!nmId) return true;
  const nested = [
    item,
    item?.data,
    item?.payload,
    item?.order_fields,
    item?.product,
    item?.product_data,
    item?.candidate,
  ];
  return nested.some((source) => {
    if (!source || typeof source !== "object") return false;
    const values = [
      source.nm_id,
      source.nmId,
      source.nmid,
      source.product_nm_id,
      source.card_nm_id,
      source.article,
    ];
    if (Array.isArray(source.nm_ids)) values.push(...source.nm_ids);
    return values.some((value) => String(value ?? "").trim() === nmId);
  });
}

function ClaimsPage() {
  const { activeId } = useAccounts();
  const qc = useQueryClient();
  const visible = useModuleVisible("claims");
  const { status } = useModuleStatus("claims");
  const routeSearch = Route.useSearch();
  const routeNmId = normalizeRouteNmId(routeSearch.nm_id);
  const routeNmIdNumber = routeNmId ? Number(routeNmId) : null;
  const scopedQuery =
    routeNmIdNumber && Number.isFinite(routeNmIdNumber)
      ? { nm_id: routeNmIdNumber }
      : {};
  const [confirmCase, setConfirmCase] = useState<any | null>(null);
  const [manualOpen, setManualOpen] = useState(false);
  const [manualForm, setManualForm] = useState(() =>
    makeManualClaimForm(routeNmId),
  );
  const [qrStep, setQrStep] = useState(0);
  const [qrImages, setQrImages] = useState<File[]>([]);
  const [qrVideo, setQrVideo] = useState<File | null>(null);
  const [qrPreviews, setQrPreviews] = useState<string[]>([]);
  const [qrFields, setQrFields] = useState<Record<string, any>>({});
  const [qrRawText, setQrRawText] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [selectedSubcategory, setSelectedSubcategory] = useState("");
  const [defectDescription, setDefectDescription] = useState("");
  const [operatorNote, setOperatorNote] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [appealDraft, setAppealDraft] = useState<any | null>(null);
  const [createdQrCase, setCreatedQrCase] = useState<any | null>(null);

  const qrFiles = [...qrImages, ...(qrVideo ? [qrVideo] : [])];

  useEffect(() => {
    if (!routeNmId) return;
    setManualForm((current) =>
      current.nm_id === routeNmId ? current : { ...current, nm_id: routeNmId },
    );
  }, [routeNmId]);

  useEffect(() => {
    const urls = qrFiles.map((file) => URL.createObjectURL(file));
    setQrPreviews(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [qrImages, qrVideo]);

  const casesQ = useQuery({
    queryKey: ["portal", "cases", activeId, routeNmId],
    queryFn: () =>
      fetchCases(activeId, { limit: 50, offset: 0, ...scopedQuery }),
    enabled: visible && !!activeId,
    staleTime: 60_000,
  });

  const candidatesQ = useQuery({
    queryKey: ["portal", "claims", "candidates", activeId, routeNmId],
    queryFn: () =>
      fetchClaimCandidates(activeId, {
        limit: 50,
        offset: 0,
        ...scopedQuery,
      }),
    enabled: visible && !!activeId,
    staleTime: 60_000,
  });

  const categoriesQ = useQuery({
    queryKey: ["portal", "claims", "support-categories", activeId],
    queryFn: () => fetchClaimSupportCategories(activeId),
    enabled: visible && !!activeId,
    staleTime: 5 * 60_000,
  });

  const invalidateClaims = () => {
    qc.invalidateQueries({ queryKey: ["portal", "cases", activeId] });
    qc.invalidateQueries({
      queryKey: ["portal", "claims", "candidates", activeId],
    });
  };

  const scanMut = useMutation({
    mutationFn: () =>
      startClaimScan(activeId, { detector_types: ["all"], force: false }),
    onSuccess: () => {
      toast.success("Скан претензий запущен");
      invalidateClaims();
    },
    onError: (e: any) => toast.error(e?.message ?? "Не удалось запустить скан"),
  });

  const createCaseMut = useMutation({
    mutationFn: (id: number | string) => createCaseFromCandidate(id, activeId),
    onSuccess: () => {
      toast.success("Кейс создан");
      invalidateClaims();
    },
    onError: (e: any) => toast.error(e?.message ?? "Не удалось создать кейс"),
  });

  const orderLookupMut = useMutation({
    mutationFn: ({
      fields,
    }: {
      fields?: Record<string, any>;
      advance?: boolean;
    } = {}) => lookupClaimOrder(activeId, fields ?? qrFields),
    onSuccess: (res: any, variables) => {
      const fields = res?.order_fields ?? {};
      setQrFields((prev) => ({ ...prev, ...fields }));
      setQrRawText(String(res?.raw_text ?? fields.raw_text ?? qrRawText ?? ""));
      if (Array.isArray(res?.warnings) && res.warnings.length) {
        toast.message(res.warnings.join(", "));
      } else {
        toast.success("Данные заказа сверены с WB");
      }
      setQrStep(variables?.advance === false ? 1 : 2);
    },
    onError: (e: any) =>
      toast.error(e?.message ?? "Не удалось найти заказ в WB"),
  });

  const qrExtractMut = useMutation({
    mutationFn: async () => {
      if (!qrImages.length)
        throw new Error("Сначала загрузите хотя бы одну картинку");
      return await extractClaimMedia(activeId, qrFiles);
    },
    onSuccess: (res: any) => {
      const fields = res?.order_fields ?? {};
      setQrFields(fields);
      setQrRawText(String(res?.raw_text ?? fields.raw_text ?? ""));
      toast.success("Материалы добавлены");
      setQrStep(1);
      if (hasOrderIdentifier(fields)) {
        orderLookupMut.mutate({ fields, advance: false });
      }
      if (Array.isArray(res?.warnings) && res.warnings.length) {
        toast.message(res.warnings.join(", "));
      }
    },
    onError: (e: any) => toast.error(e?.message ?? "Не удалось прочитать QR"),
  });

  const appealDraftMut = useMutation({
    mutationFn: () =>
      generateClaimAppealDraft(activeId, {
        category: selectedCategory,
        subcategory: selectedSubcategory,
        order_fields: qrFields,
        defect_description: defectDescription,
        operator_note: operatorNote,
        video_url: videoUrl.trim() || null,
      }),
    onSuccess: (res: any) => {
      setAppealDraft(res);
      toast.success("Обращение сгенерировано");
      setQrStep(4);
      if (Array.isArray(res?.warnings) && res.warnings.length) {
        toast.message(res.warnings.join(", "));
      }
    },
    onError: (e: any) =>
      toast.error(e?.message ?? "Не удалось сгенерировать обращение"),
  });

  const prepareCase = async (id: number | string, source: string) => {
    await generateClaimDraft(id, {
      instructions:
        "Сформируй обращение по шаблону претензии WB: факты, идентификаторы, просьба о проверке и компенсации.",
      payload: { source },
    });
    await proofCheckCase(id, { payload: { source } });
  };

  const autoPrepareMut = useMutation({
    mutationFn: async (id: number | string) => {
      const created = await createCaseFromCandidate(id, activeId);
      const caseId = created?.id ?? created?.case_id;
      if (caseId == null)
        throw new Error("Кейс создан, но backend не вернул id");
      await prepareCase(caseId, "candidate_auto_prepare");
      return created;
    },
    onSuccess: () => {
      toast.success("Кейс создан, черновик подготовлен");
      invalidateClaims();
    },
    onError: (e: any) =>
      toast.error(e?.message ?? "Не удалось подготовить кейс"),
  });

  const prepareExistingMut = useMutation({
    mutationFn: (id: number | string) => prepareCase(id, "case_quick_prepare"),
    onSuccess: () => {
      toast.success("Черновик подготовлен, доказательства проверены");
      qc.invalidateQueries({ queryKey: ["portal", "cases", activeId] });
    },
    onError: (e: any) => toast.error(e?.message ?? "Не удалось подготовить"),
  });

  const manualCreateMut = useMutation({
    mutationFn: async () => {
      const amount = Number(manualForm.estimated_amount);
      const nmId = Number(manualForm.nm_id);
      const created = await createClaimCase(activeId, {
        case_type: manualForm.case_type,
        priority: manualForm.priority,
        title: manualForm.title.trim(),
        summary: manualForm.summary.trim(),
        nm_id: Number.isFinite(nmId) && manualForm.nm_id.trim() ? nmId : null,
        vendor_code: manualForm.vendor_code.trim() || null,
        order_id: manualForm.order_id.trim() || null,
        srid: manualForm.srid.trim() || null,
        estimated_amount:
          Number.isFinite(amount) && manualForm.estimated_amount.trim()
            ? amount
            : null,
        payload: {
          "manual": true,
          sticker_id: manualForm.sticker_id.trim() || null,
          shk_id: manualForm.shk_id.trim() || null,
          pvz_address: manualForm.pvz_address.trim() || null,
        },
      });
      const caseId = created?.id ?? created?.case_id;
      if (manualForm.auto_prepare && caseId != null) {
        await prepareCase(caseId, "manual_auto_prepare");
      }
      return created;
    },
    onSuccess: () => {
      toast.success(
        manualForm.auto_prepare ? "Кейс создан и подготовлен" : "Кейс создан",
      );
      setManualOpen(false);
      setManualForm((prev) => ({
        ...prev,
        title: "",
        summary: "",
        nm_id: routeNmId,
        vendor_code: "",
        order_id: "",
        srid: "",
        estimated_amount: "",
        sticker_id: "",
        shk_id: "",
        pvz_address: "",
      }));
      invalidateClaims();
    },
    onError: (e: any) =>
      toast.error(e?.message ?? "Не удалось создать претензию"),
  });

  const saveAppealCaseMut = useMutation({
    mutationFn: async () => {
      if (!appealDraft?.body) throw new Error("Сначала сгенерируйте обращение");
      const nmId = Number(qrFields.nm_id);
      const created = await createClaimCase(activeId, {
        case_type: "defect",
        priority: "P2",
        title: appealDraft.subject || "Обращение по возврату с дефектом",
        summary: defectDescription || appealDraft.body,
        nm_id:
          Number.isFinite(nmId) && String(qrFields.nm_id ?? "").trim()
            ? nmId
            : null,
        vendor_code: String(qrFields.vendor_code ?? "").trim() || null,
        order_id: String(qrFields.order_id ?? "").trim() || null,
        srid: String(qrFields.srid ?? "").trim() || null,
        payload: {
          ...qrFields,
          category: appealDraft.category,
          subcategory: appealDraft.subcategory,
          appeal_subject: appealDraft.subject,
          appeal_body: appealDraft.body,
          evidence_files: qrFiles.map((file) => ({
            name: file.name,
            type: file.type,
            size: file.size,
          })),
          source: "qr_ai_appeal",
        },
      });
      const caseId = created?.id ?? created?.case_id;
      if (caseId == null)
        throw new Error("Кейс создан, но backend не вернул id");
      await generateClaimDraft(caseId, {
        instructions:
          "Использовать готовый текст обращения от ИИ без переписывания.",
        payload: {
          body: appealDraft.body,
          category: appealDraft.category,
          subcategory: appealDraft.subcategory,
          source: "qr_ai_appeal",
        },
      });
      return created;
    },
    onSuccess: (created: any) => {
      setCreatedQrCase(created);
      toast.success("Кейс и черновик сохранены");
      setQrStep(5);
      invalidateClaims();
    },
    onError: (e: any) => toast.error(e?.message ?? "Не удалось сохранить кейс"),
  });

  const draftMut = useMutation({
    mutationFn: (id: number | string) => generateClaimDraft(id),
    onSuccess: () => {
      toast.success("Черновик создан");
      qc.invalidateQueries({ queryKey: ["portal", "cases", activeId] });
    },
    onError: (e: any) =>
      toast.error(e?.message ?? "Не удалось создать черновик"),
  });

  const proofMut = useMutation({
    mutationFn: (id: number | string) => proofCheckCase(id, {}),
    onSuccess: () => {
      toast.success("Проверка доказательств запущена");
      qc.invalidateQueries({ queryKey: ["portal", "cases", activeId] });
    },
    onError: (e: any) => toast.error(e?.message ?? "Не удалось проверить"),
  });

  const submitMut = useMutation({
    mutationFn: (id: number | string) => submitCase(id, { confirm: true }),
    onSuccess: (res: any) => {
      const attempted =
        res?.data?.external_submit_attempted === true ||
        res?.external_submitted === true;
      toast.success(
        attempted
          ? "Претензия отправлена в WB"
          : "Ручная подача зафиксирована локально",
      );
      setConfirmCase(null);
      qc.invalidateQueries({ queryKey: ["portal", "cases", activeId] });
    },
    onError: (e: any) => toast.error(e?.message ?? "Не удалось подать"),
  });

  if (!activeId) {
    return (
      <PageShell>
        <PageHeader
          title="Претензии"
          description="Безопасный режим — подача только вручную"
        />
        <NoAccountSelected />
      </PageShell>
    );
  }

  // Per spec §3: do NOT disable the whole page just because external_submit is off.
  // We render Кандидаты/Кейсы/Черновики/История/Настройки regardless; only the
  // "Подать вручную" submit confirmation is gated by per-case `isSubmittable()`.
  const allCases = Array.isArray(casesQ.data)
    ? casesQ.data
    : ((casesQ.data as any)?.items ?? []);
  const allCandidates = Array.isArray(candidatesQ.data)
    ? candidatesQ.data
    : ((candidatesQ.data as any)?.items ?? []);
  const cases = allCases.filter((item: any) =>
    claimItemMatchesNmId(item, routeNmId),
  );
  const candidates = allCandidates.filter((item: any) =>
    claimItemMatchesNmId(item, routeNmId),
  );
  const realCases = cases.filter((c: any) => !isAuditCase(c));
  const auditCases = cases.filter((c: any) => isAuditCase(c));
  const openCases = realCases.filter(
    (c: any) =>
      !["closed", "resolved", "rejected"].includes(
        String(c.status ?? "").toLowerCase(),
      ),
  ).length;
  const draftsReady = realCases.reduce(
    (n: number, c: any) => n + (Number(c.draft_count) || 0),
    0,
  );
  const externalOn = visible === true;
  const supportCategoriesRaw = Array.isArray(categoriesQ.data?.categories)
    ? categoriesQ.data.categories
    : Array.isArray(categoriesQ.data?.items)
      ? categoriesQ.data.items
      : Array.isArray(categoriesQ.data)
        ? categoriesQ.data
        : [];
  const supportCategories =
    supportCategoriesRaw.length > 0
      ? supportCategoriesRaw
      : STATIC_SUPPORT_CATEGORIES;
  const activeCategory = supportCategories.find(
    (item: any) =>
      item.value === selectedCategory ||
      item.label === selectedCategory ||
      getCategoryName(item) === selectedCategory,
  );
  const activeSubcategories = getSubcategories(activeCategory);

  return (
    <PageShell>
      <PageHeader
        title="Фабрика претензий"
        description={
          <div className="flex items-center gap-2 flex-wrap">
            <Badge
              variant="outline"
              className="text-[10px] border-warning/30 text-warning bg-warning/10"
            >
              Бета — подача вручную
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              локальный режим
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              Внешняя отправка: {externalOn ? "включена" : "выключена"}
            </Badge>
            {status && status !== "ok" && (
              <Badge variant="outline" className="text-[10px]">
                {status}
              </Badge>
            )}
          </div>
        }
      />

      <DataDependencyNotice accountId={activeId} domains={["buyer_returns", "sales", "orders", "finance", "product_cards"]} />

      {routeNmId && (
        <Card className="mb-3 border-primary/20 bg-primary/5">
          <CardContent className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
            <div>
              <span className="font-medium">Фильтр по товару</span>{" "}
              <span className="font-mono text-muted-foreground">
                nm_id {routeNmId}
              </span>
            </div>
            <Badge variant="outline" className="bg-background/70">
              показываем только связанные претензии
            </Badge>
          </CardContent>
        </Card>
      )}

      {/* Header counters strip — spec §3 */}
      <Card className="mb-3">
        <CardContent className="p-3 grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
          <Stat label="Открытые кандидаты" value={String(candidates.length)} />
          <Stat label="Открытые кейсы" value={String(openCases)} />
          <Stat label="Готовые черновики" value={String(draftsReady)} />
          <Stat label="Последний скан" value="—" />
          <Stat label="Внешняя отправка" value={externalOn ? "Вкл" : "Выкл"} />
        </CardContent>
      </Card>

      {/* Source detectors status — spec §2 */}
      <Card className="mb-4">
        <CardContent className="p-3 flex flex-wrap gap-2 text-[11px]">
          {[
            "Браки",
            "Поставки",
            "Пропавшие товары",
            "Отчётные аномалии",
            "Компенсации",
          ].map((s) => (
            <Badge
              key={s}
              variant="outline"
              className="text-[11px] text-muted-foreground"
            >
              {s} · —
            </Badge>
          ))}
        </CardContent>
      </Card>

      <Alert className="mb-4 border-warning/30 bg-warning/5">
        <Info className="h-4 w-4" />
        <AlertTitle>Бета — подача вручную</AlertTitle>
        <AlertDescription>
          {externalOn
            ? "В WB ничего не отправляется без вашего подтверждения. Все претензии готовятся локально, проверка доказательств и подача — только по вашему действию."
            : "Автоматическая отправка отключена. Скачайте черновик или зафиксируйте ручную подачу — страница и все кандидаты остаются доступными."}
        </AlertDescription>
      </Alert>

      <Card className="mb-4">
        <CardContent className="p-4 space-y-4">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <div className="text-sm font-medium">Новое обращение по QR</div>
              <div className="text-xs text-muted-foreground mt-1">
                Опишите дефект, загрузите QR, фото и видео, проверьте данные
                заказа WB и создайте кейс из ИИ-черновика.
              </div>
            </div>
            <Badge variant="outline" className="text-[10px]">
              шаг {Math.min(qrStep + 1, 6)}/6
            </Badge>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
            {["Дефект и медиа", "Заказ", "Категория", "Данные для ИИ", "Черновик", "Готово"].map(
              (label, index) => (
                <div
                  key={label}
                  className={`rounded-md border px-3 py-2 text-xs ${qrStep === index ? "border-primary bg-primary/5 text-foreground" : qrStep > index ? "border-success/30 bg-success/10 text-foreground" : "text-muted-foreground"}`}
                >
                  {index + 1}. {label}
                </div>
              ),
            )}
          </div>

          {qrStep === 0 && (
            <div className="space-y-3">
              <div>
                <Label className="text-xs">1. Описание дефекта</Label>
                <Textarea
                  className="min-h-28 rounded-xl bg-surface"
                  value={defectDescription}
                  onChange={(e) => {
                    setDefectDescription(e.target.value);
                    setAppealDraft(null);
                  }}
                  placeholder="Например: молния выдрана, товар утратил товарный вид."
                />
              </div>

              <div>
                <Label className="text-xs">2. QR, фото и видео</Label>
                <Input
                  type="file"
                  accept="image/*,video/*"
                  multiple
                  className="hidden"
                  id="claim-qr-media"
                  onChange={(e) => {
                    const selected = Array.from(e.target.files ?? []);
                    setQrImages((prev) => [
                      ...prev,
                      ...selected.filter((file) =>
                        file.type.startsWith("image/"),
                      ),
                    ]);
                    const selectedVideo =
                      selected.find((file) => file.type.startsWith("video/")) ??
                      null;
                    if (selectedVideo) {
                      setQrVideo(selectedVideo);
                      setVideoUrl(selectedVideo.name);
                    }
                    setAppealDraft(null);
                    e.currentTarget.value = "";
                  }}
                />

                {qrFiles.length === 0 ? (
                  <label
                    htmlFor="claim-qr-media"
                    className="mt-2 flex w-full cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border bg-muted/30 py-10 text-sm text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
                  >
                    <div className="flex gap-3 text-primary">
                      <Camera className="h-7 w-7" />
                      <VideoIcon className="h-7 w-7" />
                    </div>
                    <span className="font-semibold text-foreground">
                      Прикрепите фото QR и видео
                    </span>
                    <span className="text-[11px]">
                      Нужно хотя бы одно фото QR/штрихкода, видео можно
                      приложить дополнительно
                    </span>
                  </label>
                ) : (
                  <div className="mt-2 space-y-3">
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5">
                      {qrFiles.map((file, index) => {
                        const isImage = file.type.startsWith("image/");
                        const isVideo = file.type.startsWith("video/");
                        return (
                          <div
                            key={`${file.name}-${index}`}
                            className="relative aspect-square overflow-hidden rounded-xl bg-muted ring-1 ring-border"
                          >
                            {isImage ? (
                              <img
                                src={qrPreviews[index]}
                                alt={file.name}
                                className="h-full w-full object-cover"
                              />
                            ) : isVideo ? (
                              <video
                                src={qrPreviews[index]}
                                className="h-full w-full object-cover"
                                muted
                              />
                            ) : (
                              <div className="flex h-full w-full items-center justify-center text-muted-foreground">
                                <ImagePlus className="h-6 w-6" />
                              </div>
                            )}
                            <button
                              type="button"
                              onClick={() => {
                                if (isImage) {
                                  const imageIndex = qrImages.indexOf(file);
                                  setQrImages((prev) =>
                                    prev.filter((_, i) => i !== imageIndex),
                                  );
                                } else if (file === qrVideo) {
                                  setQrVideo(null);
                                  setVideoUrl("");
                                }
                                setAppealDraft(null);
                              }}
                              className="absolute right-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-foreground/85 text-background"
                              aria-label="Удалить"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                            <div className="absolute inset-x-0 bottom-0 bg-card/95 px-1.5 py-1 backdrop-blur-sm">
                              <div className="truncate text-[10px] font-medium">
                                {file.name}
                              </div>
                              <div className="font-mono text-[9px] text-muted-foreground">
                                {formatBytes(file.size)}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="w-full"
                      onClick={() =>
                        document.getElementById("claim-qr-media")?.click()
                      }
                    >
                      <ImagePlus className="h-4 w-4 mr-2" />
                      Добавить ещё
                    </Button>
                  </div>
                )}
              </div>

              <div className="flex justify-end">
                <Button
                  disabled={
                    !defectDescription.trim() ||
                    !qrImages.length ||
                    qrExtractMut.isPending
                  }
                  onClick={() => qrExtractMut.mutate()}
                >
                  {qrExtractMut.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Обработка...
                    </>
                  ) : (
                    "Продолжить"
                  )}
                </Button>
              </div>
            </div>
          )}

          {qrStep === 1 && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {[
                  ["nm_id", "nm_id"],
                  ["barcode", "Баркод"],
                  ["shk_id", "ШК"],
                  ["sticker_id", "Стикер"],
                  ["order_id", "Заказ"],
                  ["srid", "SRID"],
                ].map(([key, label]) => (
                  <div key={key}>
                    <Label className="text-[11px]">{label}</Label>
                    <Input
                      className="h-8 text-xs"
                      value={String(qrFields[key] ?? "")}
                      onChange={(e) =>
                        setQrFields((prev) => ({
                          ...prev,
                          [key]: e.target.value,
                        }))
                      }
                    />
                  </div>
                ))}
              </div>
              <div>
                <Label className="text-[11px]">ПВЗ</Label>
                <Input
                  className="h-8 text-xs"
                  value={String(qrFields.pvz_address ?? "")}
                  onChange={(e) =>
                    setQrFields((prev) => ({
                      ...prev,
                      pvz_address: e.target.value,
                    }))
                  }
                />
              </div>
              {qrRawText && (
                <div className="rounded-md border bg-muted/30 p-2 text-[11px] text-muted-foreground max-h-24 overflow-auto">
                  {qrRawText}
                </div>
              )}
              {(orderLookupMut.isPending || qrFields.source_system) && (
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {orderLookupMut.isPending ? (
                    <Badge variant="outline" className="gap-1">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      Идёт поиск данных WB...
                    </Badge>
                  ) : (
                    <Badge
                      variant="outline"
                      className="border-emerald-200 bg-emerald-50 text-emerald-700"
                    >
                      Данные найдены: {String(qrFields.source_system)}
                    </Badge>
                  )}
                </div>
              )}
              <div className="flex justify-between">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setQrStep(0)}
                >
                  Назад
                </Button>
                <Button
                  size="sm"
                  disabled={orderLookupMut.isPending}
                  onClick={() => orderLookupMut.mutate({ advance: true })}
                >
                  {orderLookupMut.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Идёт поиск в WB...
                    </>
                  ) : qrFields.source_system ? (
                    "Далее"
                  ) : (
                    "Найти в WB и далее"
                  )}
                </Button>
              </div>
            </div>
          )}

          {qrStep === 2 && (
            <div className="space-y-3">
              <div className="grid gap-3 md:grid-cols-2">
                <div>
                <Label className="text-xs">Категория</Label>
                  <Select
                    value={selectedCategory}
                    onValueChange={(v) => {
                      setSelectedCategory(v);
                      setSelectedSubcategory("");
                      setAppealDraft(null);
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Выберите категорию" />
                    </SelectTrigger>
                    <SelectContent>
                      {supportCategories.map((item: any) => (
                        <SelectItem
                          key={item.value ?? getCategoryName(item)}
                          value={getCategoryName(item)}
                        >
                          {getCategoryName(item)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Подкатегория</Label>
                  <Select
                    value={selectedSubcategory}
                    onValueChange={(v) => {
                      setSelectedSubcategory(v);
                      setAppealDraft(null);
                    }}
                    disabled={!selectedCategory}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Выберите подкатегорию" />
                    </SelectTrigger>
                    <SelectContent>
                      {activeSubcategories.map((item: any) => (
                        <SelectItem
                          key={item.value ?? getCategoryName(item)}
                          value={getCategoryName(item)}
                        >
                          {getCategoryName(item)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex justify-between">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setQrStep(1)}
                >
                  Назад
                </Button>
                <Button
                  size="sm"
                  disabled={!selectedCategory || !selectedSubcategory}
                  onClick={() => setQrStep(3)}
                >
                  Далее
                </Button>
              </div>
            </div>
          )}

          {qrStep === 3 && (
            <div className="space-y-3">
              <div className="rounded-xl bg-muted/30 p-3 ring-1 ring-border">
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  Описание дефекта
                </div>
                <div className="mt-1 text-sm">{defectDescription}</div>
                <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                  <span>{qrImages.length} фото</span>
                  <span>{qrVideo ? "1 видео" : "Видео не прикреплено"}</span>
                </div>
              </div>
              <div>
                <Label className="text-xs">Дополнительный комментарий</Label>
                <Textarea
                  className="min-h-20"
                  value={operatorNote}
                  onChange={(e) => {
                    setOperatorNote(e.target.value);
                    setAppealDraft(null);
                  }}
                  placeholder="Что ИИ должен учесть. Например: запросить компенсацию и обязательно указать данные из QR."
                />
              </div>
              <div className="flex justify-between">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setQrStep(2)}
                >
                  Назад
                </Button>
                <Button
                  size="sm"
                  disabled={
                    !defectDescription.trim() || appealDraftMut.isPending
                  }
                  onClick={() => appealDraftMut.mutate()}
                >
                  <Sparkles className="h-4 w-4 mr-2" />
                  Сгенерировать
                </Button>
              </div>
            </div>
          )}

          {qrStep === 4 && (
            <div className="space-y-3">
              {appealDraft ? (
                <>
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="outline" className="text-[10px]">
                      {appealDraft.category}
                    </Badge>
                    <Badge variant="outline" className="text-[10px]">
                      {appealDraft.subcategory}
                    </Badge>
                    <Badge variant="secondary" className="text-[10px]">
                      {appealDraft.model_name}
                    </Badge>
                  </div>
                  {appealDraft.subject && (
                    <div className="text-sm font-medium">
                      {appealDraft.subject}
                    </div>
                  )}
                  <div className="relative">
                    <Textarea
                      className="min-h-56 rounded-xl pr-12 font-mono text-xs"
                      value={appealDraft.body ?? ""}
                      onChange={(e) =>
                        setAppealDraft((prev: any) => ({
                          ...prev,
                          body: e.target.value,
                        }))
                      }
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      className="absolute right-2 top-2 h-8 w-8"
                      onClick={() => {
                        void navigator.clipboard.writeText(
                          appealDraft.body ?? "",
                        );
                        toast.success("Скопировано");
                      }}
                    >
                      <Copy className="h-4 w-4" />
                    </Button>
                  </div>
                </>
              ) : (
                <EmptyState
                  title="Черновик ещё не создан"
                  text="Вернитесь на предыдущий шаг и нажмите «Сгенерировать»."
                />
              )}
              <div className="flex justify-between">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setQrStep(3)}
                >
                  Назад
                </Button>
                <Button
                  size="sm"
                  disabled={!appealDraft?.body || saveAppealCaseMut.isPending}
                  onClick={() => saveAppealCaseMut.mutate()}
                >
                  {saveAppealCaseMut.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Создание...
                    </>
                  ) : (
                    <>
                      <FileText className="h-4 w-4 mr-2" />
                      Создать кейс
                    </>
                  )}
                </Button>
              </div>
            </div>
          )}

          {qrStep === 5 && (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-success/15 text-success ring-1 ring-success/30">
                <CheckCircle2 className="h-8 w-8" />
              </div>
              <div>
                <div className="text-lg font-semibold">Кейс создан</div>
                <div className="mt-1 text-sm text-muted-foreground">
                  Данные QR и заказа, название видео и ИИ-черновик сохранены в
                  данных кейса.
                </div>
              </div>
              {createdQrCase?.id != null && (
                <Badge variant="outline" className="font-mono">
                  кейс #{createdQrCase.id}
                </Badge>
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setQrStep(0);
                  setQrImages([]);
                  setQrVideo(null);
                  setQrFields({});
                  setQrRawText("");
                  setSelectedCategory("");
                  setSelectedSubcategory("");
                  setDefectDescription("");
                  setOperatorNote("");
                  setVideoUrl("");
                  setAppealDraft(null);
                  setCreatedQrCase(null);
                }}
              >
                Создать новый кейс
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="mb-3 flex justify-end gap-2">
        <Button size="sm" variant="default" onClick={() => setManualOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Создать вручную
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => scanMut.mutate()}
          disabled={scanMut.isPending}
        >
          <Search className="h-4 w-4 mr-2" />
          Найти новые обращения
        </Button>
      </div>

      <Tabs defaultValue={routeSearch.tab ?? "cases"} className="space-y-3">
        <TabsList>
          <TabsTrigger value="candidates">Кандидаты</TabsTrigger>
          <TabsTrigger value="cases">Кейсы</TabsTrigger>
          <TabsTrigger value="drafts">Черновики</TabsTrigger>
          <TabsTrigger value="history">История</TabsTrigger>
          <TabsTrigger value="settings">Настройки</TabsTrigger>
        </TabsList>

        <TabsContent value="candidates">
          <CandidatesList
            candidates={candidates}
            loading={candidatesQ.isLoading}
            error={candidatesQ.error}
            createCaseMut={createCaseMut}
            autoPrepareMut={autoPrepareMut}
          />
        </TabsContent>

        <TabsContent value="cases" className="space-y-2">
          {casesQ.isLoading && (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-28 w-full" />
              ))}
            </div>
          )}
          {casesQ.error && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                {(casesQ.error as Error).message}
              </AlertDescription>
            </Alert>
          )}
          {casesQ.data && (
            <CasesList
              realCases={realCases}
              auditCases={auditCases}
              draftMut={draftMut}
              proofMut={proofMut}
              prepareMut={prepareExistingMut}
              setConfirmCase={setConfirmCase}
            />
          )}
        </TabsContent>

        <TabsContent value="drafts">
          <EmptyState
            title="Черновиков пока нет"
            text="Создайте черновик из карточки кандидата или кейса."
          />
        </TabsContent>

        <TabsContent value="history">
          <EmptyState
            title="История пуста"
            text="Здесь будет показано: проверка доказательств, фиксация ручной подачи, изменения статуса."
          />
        </TabsContent>

        <TabsContent value="settings">
          <Card>
            <CardContent className="p-4 text-sm text-muted-foreground">
              Параметры детекторов и внешней отправки задаются в общих{" "}
              <Link to="/settings" className="underline">
                настройках портала
              </Link>
              .
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={manualOpen} onOpenChange={setManualOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Создать претензию вручную</DialogTitle>
            <DialogDescription>
              Заполните ключевые идентификаторы. Можно сразу подготовить
              черновик и запустить проверку доказательств.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 py-1">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <Label className="text-xs">Тип</Label>
                <Select
                  value={manualForm.case_type}
                  onValueChange={(v) =>
                    setManualForm((p) => ({ ...p, case_type: v }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="defect">Брак / дефект</SelectItem>
                    <SelectItem value="supply_discrepancy">
                      Расхождение поставки
                    </SelectItem>
                    <SelectItem value="missing_goods">
                      Пропавший товар
                    </SelectItem>
                    <SelectItem value="report_anomaly">
                      Аномалия отчета
                    </SelectItem>
                    <SelectItem value="compensation_underpayment">
                      Недоплата компенсации
                    </SelectItem>
                    <SelectItem value="repeat_claim">
                      Повторная претензия
                    </SelectItem>
                    <SelectItem value="pretrial">Досудебная</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Приоритет</Label>
                <Select
                  value={manualForm.priority}
                  onValueChange={(v) =>
                    setManualForm((p) => ({ ...p, priority: v }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {["P0", "P1", "P2", "P3", "P4"].map((p) => (
                      <SelectItem key={p} value={p}>
                        {p}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Сумма</Label>
                <Input
                  inputMode="decimal"
                  value={manualForm.estimated_amount}
                  onChange={(e) =>
                    setManualForm((p) => ({
                      ...p,
                      estimated_amount: e.target.value,
                    }))
                  }
                  placeholder="0"
                />
              </div>
            </div>
            <div>
              <Label className="text-xs">Заголовок</Label>
              <Input
                value={manualForm.title}
                onChange={(e) =>
                  setManualForm((p) => ({ ...p, title: e.target.value }))
                }
                placeholder="Например: Поврежденный товар в возврате"
              />
            </div>
            <div>
              <Label className="text-xs">Описание ситуации</Label>
              <Textarea
                className="min-h-24"
                value={manualForm.summary}
                onChange={(e) =>
                  setManualForm((p) => ({ ...p, summary: e.target.value }))
                }
                placeholder="Что произошло, какие доказательства есть, что нужно запросить у WB"
              />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div>
                <Label className="text-xs">nm_id</Label>
                <Input
                  value={manualForm.nm_id}
                  onChange={(e) =>
                    setManualForm((p) => ({ ...p, nm_id: e.target.value }))
                  }
                />
              </div>
              <div>
                <Label className="text-xs">Артикул</Label>
                <Input
                  value={manualForm.vendor_code}
                  onChange={(e) =>
                    setManualForm((p) => ({
                      ...p,
                      vendor_code: e.target.value,
                    }))
                  }
                />
              </div>
              <div>
                <Label className="text-xs">Заказ</Label>
                <Input
                  value={manualForm.order_id}
                  onChange={(e) =>
                    setManualForm((p) => ({ ...p, order_id: e.target.value }))
                  }
                />
              </div>
              <div>
                <Label className="text-xs">SRID</Label>
                <Input
                  value={manualForm.srid}
                  onChange={(e) =>
                    setManualForm((p) => ({ ...p, srid: e.target.value }))
                  }
                />
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <Label className="text-xs">ШК</Label>
                <Input
                  value={manualForm.shk_id}
                  onChange={(e) =>
                    setManualForm((p) => ({ ...p, shk_id: e.target.value }))
                  }
                />
              </div>
              <div>
                <Label className="text-xs">Стикер</Label>
                <Input
                  value={manualForm.sticker_id}
                  onChange={(e) =>
                    setManualForm((p) => ({ ...p, sticker_id: e.target.value }))
                  }
                />
              </div>
              <div>
                <Label className="text-xs">ПВЗ / склад</Label>
                <Input
                  value={manualForm.pvz_address}
                  onChange={(e) =>
                    setManualForm((p) => ({
                      ...p,
                      pvz_address: e.target.value,
                    }))
                  }
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Checkbox
                checked={manualForm.auto_prepare}
                onCheckedChange={(v) =>
                  setManualForm((p) => ({ ...p, auto_prepare: Boolean(v) }))
                }
              />
              Сразу создать черновик и проверить доказательства
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setManualOpen(false)}>
              Отмена
            </Button>
            <Button
              onClick={() => manualCreateMut.mutate()}
              disabled={manualCreateMut.isPending || !manualForm.title.trim()}
            >
              {manualForm.auto_prepare && <Sparkles className="h-4 w-4 mr-2" />}
              Создать
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={!!confirmCase}
        onOpenChange={(o) => !o && setConfirmCase(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Подтвердить ручную подачу</DialogTitle>
            <DialogDescription>
              Кейс #{confirmCase?.id} —{" "}
              {confirmCase?.title ?? confirmCase?.summary ?? ""}. Автоматическая
              отправка в WB отключена: претензия будет зафиксирована как готовая
              к ручной подаче.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmCase(null)}>
              Отмена
            </Button>
            <Button
              onClick={() =>
                confirmCase?.id != null && submitMut.mutate(confirmCase.id)
              }
              disabled={submitMut.isPending}
            >
              Подтвердить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="text-sm font-medium tabular-nums mt-0.5">{value}</div>
    </div>
  );
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <Card>
      <CardContent className="p-6 text-center space-y-1">
        <div className="text-sm font-medium">{title}</div>
        <div className="text-xs text-muted-foreground">{text}</div>
      </CardContent>
    </Card>
  );
}

function CasesList({
  realCases,
  auditCases,
  draftMut,
  proofMut,
  prepareMut,
  setConfirmCase,
}: {
  realCases: any[];
  auditCases: any[];
  draftMut: { isPending: boolean; mutate: (id: any) => void };
  proofMut: { isPending: boolean; mutate: (id: any) => void };
  prepareMut: { isPending: boolean; mutate: (id: any) => void };
  setConfirmCase: (c: any) => void;
}) {
  const renderCard = (c: any, i: number) => {
    const audit = isAuditCase(c);
    const sub = isSubmittable(c);
    return (
      <Card key={c.id ?? i} className={audit ? "border-dashed opacity-80" : ""}>
        <CardContent className="p-4 space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            {audit && (
              <Badge
                variant="outline"
                className="text-[10px] border-muted-foreground/40 text-muted-foreground"
              >
                <FlaskConical className="h-3 w-3 mr-1" />
                Тестовый кейс
              </Badge>
            )}
            {(c.case_type ?? c.kind) && (
              <Badge variant="outline" className="text-[10px]">
                {c.case_type ?? c.kind}
              </Badge>
            )}
            {c.status && (
              <Badge variant="secondary" className="text-[10px]">
                {c.status}
              </Badge>
            )}
            {c.priority && (
              <Badge variant="outline" className="text-[10px]">
                {c.priority}
              </Badge>
            )}
            {c.proof_state && (
              <Badge variant="outline" className="text-[10px]">
                Доказательства: {c.proof_state}
              </Badge>
            )}
          </div>

          <div className="text-sm font-medium">
            {c.title ?? c.summary ?? `Кейс #${c.id ?? i}`}
          </div>
          {c.reason && (
            <div className="text-xs text-muted-foreground">{c.reason}</div>
          )}

          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {(c.amount_claimed ?? c.amount) != null && (
              <span>
                Сумма:{" "}
                <span className="tabular-nums font-medium text-foreground">
                  {formatMoney(c.amount_claimed ?? c.amount)}
                </span>
              </span>
            )}
            {c.evidence_count != null && (
              <span>
                Доказательств:{" "}
                <span className="text-foreground">{c.evidence_count}</span>
              </span>
            )}
            {c.draft_count != null && (
              <span>
                Черновиков:{" "}
                <span className="text-foreground">{c.draft_count}</span>
              </span>
            )}
            {c.opened_at && (
              <span>
                Открыт:{" "}
                <span className="text-foreground">
                  {new Date(c.opened_at).toLocaleDateString("ru-RU")}
                </span>
              </span>
            )}
            {c.nm_id && <span className="font-mono">nm_id: {c.nm_id}</span>}
          </div>

          {c.id != null && (
            <div className="flex items-center gap-2 flex-wrap pt-1">
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                disabled={draftMut.isPending || audit}
                onClick={() => draftMut.mutate(c.id)}
              >
                <FileText className="h-3 w-3 mr-1" /> Создать черновик
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                disabled={proofMut.isPending || audit}
                onClick={() => proofMut.mutate(c.id)}
              >
                <ShieldCheck className="h-3 w-3 mr-1" /> Проверить
                доказательства
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                disabled={prepareMut.isPending || audit}
                onClick={() => prepareMut.mutate(c.id)}
              >
                <Sparkles className="h-3 w-3 mr-1" /> Подготовить
              </Button>
              <Button
                size="sm"
                variant="default"
                className="h-7 text-xs"
                disabled={!sub.ok}
                title={
                  sub.ok
                    ? "Подача вручную — без авто-отправки в WB"
                    : sub.reason
                }
                onClick={() => sub.ok && setConfirmCase(c)}
              >
                <Send className="h-3 w-3 mr-1" /> Подать вручную
              </Button>
              {!sub.ok && (
                <span className="text-[11px] text-muted-foreground">
                  {sub.reason}
                </span>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    );
  };

  return (
    <>
      {realCases.length > 0 ? (
        <div className="space-y-2">{realCases.map(renderCard)}</div>
      ) : (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground text-center">
            {auditCases.length > 0
              ? "Реальных претензий пока нет. Ниже можно открыть тестовые кейсы для проверки процесса."
              : "Нет открытых претензий."}
          </CardContent>
        </Card>
      )}

      {auditCases.length > 0 && (
        <details className="mt-6 group">
          <summary className="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground flex items-center gap-2 select-none">
            <FlaskConical className="h-4 w-4" />
            Тестовые кейсы ({auditCases.length})
            <span className="text-[11px] text-muted-foreground/70">
              — синтетические данные, подача отключена
            </span>
          </summary>
          <div className="space-y-2 mt-3">{auditCases.map(renderCard)}</div>
        </details>
      )}
    </>
  );
}

function CandidatesList({
  candidates,
  loading,
  error,
  createCaseMut,
  autoPrepareMut,
}: {
  candidates: any[];
  loading: boolean;
  error: unknown;
  createCaseMut: { isPending: boolean; mutate: (id: any) => void };
  autoPrepareMut: { isPending: boolean; mutate: (id: any) => void };
}) {
  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    );
  }
  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>{(error as Error).message}</AlertDescription>
      </Alert>
    );
  }
  if (!candidates.length) {
    return (
      <EmptyState
        title="Кандидаты появятся после первого скана"
        text="Запустите «Найти новые обращения», чтобы детекторы предложили кандидатов для проверки."
      />
    );
  }
  return (
    <div className="space-y-2">
      {candidates.map((c: any, i: number) => (
        <Card key={c.id ?? i}>
          <CardContent className="p-4 space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              {c.detector_type && (
                <Badge variant="outline" className="text-[10px]">
                  {c.detector_type}
                </Badge>
              )}
              {c.status && (
                <Badge variant="secondary" className="text-[10px]">
                  {c.status}
                </Badge>
              )}
              {c.severity && (
                <Badge variant="outline" className="text-[10px]">
                  {c.severity}
                </Badge>
              )}
            </div>
            <div className="text-sm font-medium">
              {c.title ?? `Кандидат #${c.id ?? i}`}
            </div>
            {c.business_explanation && (
              <div className="text-xs text-muted-foreground">
                {c.business_explanation}
              </div>
            )}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              {c.expected_amount != null && (
                <span>
                  Оценка:{" "}
                  <span className="tabular-nums font-medium text-foreground">
                    {formatMoney(c.expected_amount)}
                  </span>
                </span>
              )}
              {c.nm_id && <span className="font-mono">nm_id: {c.nm_id}</span>}
              {c.supply_id && (
                <span>
                  Поставка:{" "}
                  <span className="text-foreground">{c.supply_id}</span>
                </span>
              )}
            </div>
            <div className="flex flex-wrap gap-2 pt-1">
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                disabled={
                  createCaseMut.isPending ||
                  c.id == null ||
                  String(c.status ?? "").toLowerCase() === "case_created"
                }
                onClick={() => createCaseMut.mutate(c.id)}
              >
                <FileText className="h-3 w-3 mr-1" /> Создать кейс
              </Button>
              <Button
                size="sm"
                variant="default"
                className="h-7 text-xs"
                disabled={
                  autoPrepareMut.isPending ||
                  c.id == null ||
                  String(c.status ?? "").toLowerCase() === "case_created"
                }
                onClick={() => autoPrepareMut.mutate(c.id)}
              >
                <Sparkles className="h-3 w-3 mr-1" /> Создать + подготовить
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
