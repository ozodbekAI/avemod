// Central API endpoint map — single source of truth for backend paths.
// All business pages MUST use these constants. Never hard-code paths like
// "/money", "/cards", "/finance" in callers — those are UI routes, not API
// endpoints, and the backend will 404.
// Legacy spacing contract markers:
// claimsScans:          "/portal/claims/scans"
// claimCandidates:      "/portal/claims/candidates"
// stockControlPreview:         "/portal/stock-control/preview"

export const API_ENDPOINTS = {
  auth: {
    login: "/auth/login",
    refresh: "/auth/refresh",
    me: "/auth/me",
    ping: "/auth/ping",
  },
  money: {
    summary: "/money/summary",
    filters: "/money/filters",
    articles: "/money/articles",
    articleDetail: (nmId: number | string) => `/money/articles/${nmId}`,
    cards: "/money/cards",
    cardDetail: (skuId: number | string) => `/money/cards/${skuId}`,
    actions: "/money/actions",
    actionsToday: "/money/actions/today",
    dataBlockers: "/money/data-blockers",
    expensesBreakdown: "/money/expenses/breakdown",
    expensesLogistics: "/money/expenses/logistics",
    expensesReportRows: "/money/expenses/report-rows",
    profitCascade: "/money/profit-cascade",
  },
  dashboard: {
    dataHealth: "/dashboard/data-health",
    owner: "/dashboard/owner",
    ownerAiSummary: "/dashboard/owner-ai-summary",
    articleAudit: "/dashboard/article-audit",
    skuProfitability: "/dashboard/sku-profitability",
  },
  actions: {
    legacyList: "/actions",
    update: (actionId: number | string) => `/actions/${actionId}`,
  },
  dq: {
    issues: "/dq/issues",
    summary: "/dq/issues/summary",
    investigator: "/dq/issues/investigator",
    resolutionContext: (issueId: number | string) =>
      `/dq/issues/${issueId}/resolution-context`,
    affectedRowsCsv: (issueId: number | string) =>
      `/dq/issues/${issueId}/affected-rows.csv`,
    guidedAction: (issueId: number | string) =>
      `/dq/issues/${issueId}/guided-action`,
    classify: (issueId: number | string) => `/dq/issues/${issueId}/classify`,
    resolve: (issueId: number | string) => `/dq/issues/${issueId}/resolve`,
    comment: (issueId: number | string) => `/dq/issues/${issueId}/comment`,
    reopen: (issueId: number | string) => `/dq/issues/${issueId}/reopen`,
    run: "/dq/run",
  },
  costs: {
    rows: "/costs/rows",
    imports: "/costs/imports",
    unresolved: "/costs/unresolved",
    missing: "/costs/missing",
    template: "/costs/template",
    upload: "/costs/upload",
    previewUpload: (uploadId: number | string) =>
      `/costs/uploads/${uploadId}/preview`,
    confirmUpload: (uploadId: number | string) =>
      `/costs/uploads/${uploadId}/confirm`,
    inlineSave: "/costs/inline-save",
    updateRow: (costId: number | string) => `/costs/${costId}`,
    relink: "/costs/relink",
  },
  finance: {
    reports: "/finance/reports",
    rows: "/finance/report-rows",
    balance: "/balance",
    reconciliation: "/marts/finance-reconciliation",
    businessDaily: "/marts/business-daily",
    accountExpenseDaily: "/marts/account-expense-daily",
    reconciliationDaily: "/marts/reconciliation-daily",
  },
  inventory: {
    purchasePlan: "/inventory/purchase-plan",
    stockDaily: "/marts/stock-daily",
    stockSnapshots: "/stocks/snapshots",
    supplies: "/supplies",
  },
  pricing: {
    safety: "/pricing/safety",
    simulate: "/pricing/simulate",
  },
  ads: {
    efficiency: "/ads/efficiency",
    stats: "/ads/stats",
    clusters: "/ads/clusters",
    campaigns: "/ads/campaigns",
    campaignDetail: (advertId: number | string) => `/ads/campaigns/${advertId}`,
  },
  analytics: {
    overview: "/analytics/overview",
    exportCsv: "/analytics/export.csv",
    funnel: "/analytics/funnel",
    regions: "/analytics/regions",
  },
  catalog: {
    products: "/products",
    prices: "/prices",
    coreSku: "/core-sku",
    coreSkuDetail: (skuId: number | string) => `/core-sku/${skuId}`,
    controlSkus: "/skus",
    controlSkuDetail: (skuId: number | string) => `/skus/${skuId}`,
  },
  settings: {
    business: "/settings/business",
    policies: "/settings/business/policies",
  },
  portal: {
    modulesHealth: "/portal/modules/health",
    agentMessage: "/portal/agent/message",
    agentMcp: "/portal/agent/mcp",
    agentTools: "/portal/agent/tools",
    agentToolCall: "/portal/agent/tool-call",
    agentManualTask: "/portal/agent/manual-task",
    agentScenarioTemplates: "/portal/agent/scenario-templates",
    agentScenarios: "/portal/agent/scenarios",
    agentScenarioDetail: (id: number | string) =>
      `/portal/agent/scenarios/${id}`,
    agentScenarioRun: (id: number | string) =>
      `/portal/agent/scenarios/${id}/run`,
    agentScenarioRuns: "/portal/agent/scenario-runs",
    agentFinance: "/portal/agent/finance",
    doctor: "/portal/doctor",
    overview: "/portal/overview",
    actions: "/portal/actions",
    actionCenterCapabilities: "/portal/action-center/capabilities",
    manualActionCreate: "/portal/actions/manual",
    manualTaskItemUpdate: (actionId: number | string, itemKey: string) =>
      `/portal/actions/${actionId}/manual-items/${encodeURIComponent(itemKey)}`,
    assignableUsers: "/portal/assignable-users",
    actionUpdateBySource: "/portal/actions/by-source",
    problemRecheck: (id: number | string) => `/portal/problems/${id}/recheck`,
    problemResults: (id: number | string) => `/portal/problems/${id}/results`,
    actionResults: (id: number | string) => `/portal/actions/${id}/results`,
    actionResultEvent: (id: number | string) =>
      `/portal/actions/${id}/result-event`,
    actionUpdate: (id: number | string) => `/portal/actions/${id}`,
    products: "/portal/products",
    product360: (nmId: number | string) => `/portal/products/${nmId}`,
    productQuality: (nmId: number | string) =>
      `/portal/products/${nmId}/quality`,
    cardQualityAnalyze: "/portal/card-quality/analyze",
    cardQualityProducts: "/portal/card-quality/products",
    cardQualityProductAnalyze: (nmId: number | string) =>
      `/portal/card-quality/products/${nmId}/analyze`,
    cardQualityProductRecheck: (nmId: number | string) =>
      `/portal/card-quality/products/${nmId}/recheck`,
    cardQualityIssues: "/portal/card-quality/issues",
    cardQualityIssuesGrouped: "/portal/card-quality/issues/grouped",
    cardQualityIssueQueueNext: "/portal/card-quality/issues/queue/next",
    cardQualityIssueQueueProgress: "/portal/card-quality/issues/queue/progress",
    cardQualityIssueStatus: (id: number | string) =>
      `/portal/card-quality/issues/${id}/status`,
    cardQualityIssuePreview: (id: number | string) =>
      `/portal/card-quality/issues/${id}/preview`,
    cardQualityIssueFix: (id: number | string) =>
      `/portal/card-quality/issues/${id}/fix`,
    cardQualityIssueAcceptLocal: (id: number | string) =>
      `/portal/card-quality/issues/${id}/accept-local`,
    cardQualityIssueMarkFixed: (id: number | string) =>
      `/portal/card-quality/issues/${id}/mark-fixed`,
    cardQualityIssueDraft: (id: number | string) =>
      `/portal/card-quality/issues/${id}/draft`,
    cardQualityIssueApplyWb: (id: number | string) =>
      `/portal/card-quality/issues/${id}/apply-wb`,
    cardQualityIssueRecheck: (id: number | string) =>
      `/portal/card-quality/issues/${id}/recheck`,
    cardQualityFixedFileStatus: "/portal/card-quality/fixed-file/status",
    cardQualityFixedFile: "/portal/card-quality/fixed-file",
    cardQualityFixedFileEntry: (id: number | string) =>
      `/portal/card-quality/fixed-file/${id}`,
    cardQualityFixedFileExport: "/portal/card-quality/fixed-file/export",
    cardQualityFixedFileUpload: "/portal/card-quality/fixed-file/upload",
    cardQualityRuns: "/portal/card-quality/runs",
    cardQualityRunDetail: (id: number | string) =>
      `/portal/card-quality/runs/${id}`,
    cardQualityRunRetry: (id: number | string) =>
      `/portal/card-quality/runs/${id}/retry`,
    productGrouping: (nmId: number | string) =>
      `/portal/products/${nmId}/grouping`,
    groupingPreview: "/portal/grouping/preview",
    groupingCandidateStatus: (id: number | string) =>
      `/portal/grouping/candidates/${id}/status`,
    productEvents: (nmId: number | string) => `/portal/products/${nmId}/events`,
    results: "/portal/results",
    logisticsOverview: "/portal/logistics/overview",
    logisticsExportCsv: "/portal/logistics/export.csv",
    reputationSummary: "/portal/reputation/summary",
    reputationInbox: "/portal/reputation/inbox",
    reputationAnalytics: "/portal/reputation/analytics",
    reputationSettings: "/portal/reputation/settings",
    reputationBrands: "/portal/reputation/brands",
    reputationLearning: "/portal/reputation/learning",
    reputationLearningToggle: "/portal/reputation/learning/toggle",
    reputationLearningApply: "/portal/reputation/learning/apply",
    reputationLearningReset: "/portal/reputation/learning/reset",
    reputationLearningEntry: (id: number | string) =>
      `/portal/reputation/learning/entries/${id}`,
    reputationPrompts: "/portal/reputation/prompts",
    reputationProductInsights: (nmId: number | string) =>
      `/portal/reputation/product-insights/${nmId}`,
    reputationItem: (id: number | string) => `/portal/reputation/items/${id}`,
    reputationDraft: (id: number | string) =>
      `/portal/reputation/items/${id}/draft`,
    reputationNoReply: (id: number | string) =>
      `/portal/reputation/items/${id}/no-reply-needed`,
    reputationSync: "/portal/reputation/sync",
    reputationDrafts: "/portal/reputation/drafts",
    reputationDraftApproveAll: "/portal/reputation/drafts/approve-all",
    reputationDraftApprove: (id: number | string) =>
      `/portal/reputation/drafts/${id}/approve`,
    reputationDraftRegenerate: (id: number | string) =>
      `/portal/reputation/drafts/${id}/regenerate`,
    reputationDraftReject: (id: number | string) =>
      `/portal/reputation/drafts/${id}/reject`,
    reputationDraftPublish: (id: number | string) =>
      `/portal/reputation/drafts/${id}/publish`,
    reputationChats: "/portal/reputation/chats",
    reputationChatEvents: (id: number | string) =>
      `/portal/reputation/chats/${id}/events`,
    reputationChatDraft: (id: number | string) =>
      `/portal/reputation/chats/${id}/draft`,
    reputationAdminPromptDebug: "/portal/admin/reputation/prompt-debug",
    reputationAdminPromptProbe: "/portal/admin/reputation/prompt-probe",
    reputationAdminProviderStatus: "/portal/admin/reputation/provider-status",
    reputationAdminGenerationLogs: "/portal/admin/reputation/generation-logs",
    reputationAdminGenerationLogDetail: (id: number | string) =>
      `/portal/admin/reputation/generation-logs/${id}`,
    cases: "/portal/cases",
    caseFromSignal: "/portal/cases/from-signal",
    caseDetail: (id: number | string) => `/portal/cases/${id}`,
    caseProofCheck: (id: number | string) => `/portal/cases/${id}/proof-check`,
    caseGenerateDraft: (id: number | string) =>
      `/portal/cases/${id}/generate-draft`,
    caseSubmit: (id: number | string) => `/portal/cases/${id}/submit`,
    claimsScans: "/portal/claims/scans",
    claimCandidates: "/portal/claims/candidates",
    claimsQrExtract: "/portal/claims/qr/extract",
    claimsMediaExtract: "/portal/claims/media/extract",
    claimsOrderLookup: "/portal/claims/order/lookup",
    claimsSupportCategories: "/portal/claims/support/categories",
    claimsAppealDraft: "/portal/claims/appeal-draft",
    claimCandidateCreateCase: (id: number | string) =>
      `/portal/claims/candidates/${id}/create-case`,
    casesDetectDefects: "/portal/cases/detect/defects",
    casesDetectReportAnomalies: "/portal/cases/detect/report-anomalies",
    casesDetectSupplyDiscrepancies: "/portal/cases/detect/supply-discrepancies",
    casesDetectCompensationUnderpayments:
      "/portal/cases/detect/compensation-underpayments",
    // Stock control (Остатки и регионы) — real backend mapping
    // Source of truth: GET https://operator.ozodbek-akramov.uz/openapi.json
    //
    // Old aliases (stockControlOverview, stockControlRunRows, stockControlRunExport,
    // stockControlTemplate, stockControlUpload, stockControlPreview) point to the
    // correct URLs so existing callers keep working.
    stockControlStatus: "/portal/stock-control/status",
    stockControlOverview: "/portal/stock-control/status", // alias → status
    stockControlSettings: "/portal/stock-control/settings",

    // Runs
    stockControlRuns: "/portal/stock-control/runs",
    stockControlRunDetail: (id: number | string) =>
      `/portal/stock-control/runs/${id}`,
    stockControlRunOverview: (id: number | string) =>
      `/portal/stock-control/runs/${id}/overview`,
    stockControlRunRegionRows: (id: number | string) =>
      `/portal/stock-control/runs/${id}/region-rows`,
    stockControlRunMovements: (id: number | string) =>
      `/portal/stock-control/runs/${id}/movements`,
    stockControlRunUnmatched: (id: number | string) =>
      `/portal/stock-control/runs/${id}/unmatched`,
    stockControlRunExport: (id: number | string) =>
      `/portal/stock-control/runs/${id}/export`,
    stockControlRunCancel: (id: number | string) =>
      `/portal/stock-control/runs/${id}/cancel`,
    stockControlRunRetry: (id: number | string) =>
      `/portal/stock-control/runs/${id}/retry`,
    /** @deprecated use stockControlRunRegionRows */
    stockControlRunRows: (id: number | string) =>
      `/portal/stock-control/runs/${id}/region-rows`,

    // Templates
    stockControlTemplateHandStock: "/portal/stock-control/templates/hand-stock",
    /** @deprecated use stockControlTemplateHandStock */
    stockControlTemplate: "/portal/stock-control/templates/hand-stock",

    // Imports (upload + preview): two separate flows — hand-stock and regional-supply
    stockControlImportHandStockPreview:
      "/portal/stock-control/imports/hand-stock/preview",
    stockControlImportRegionalSupply:
      "/portal/stock-control/imports/regional-supply",
    stockControlImportRegionalSupplyPreview:
      "/portal/stock-control/imports/regional-supply/preview",
    /** @deprecated default upload → regional-supply import. Use the specific endpoint for hand-stock. */
    stockControlUpload: "/portal/stock-control/imports/regional-supply",
    stockControlPreview: "/portal/stock-control/preview",

    // Hand-stock drafts CRUD
    stockControlHandStockDrafts: "/portal/stock-control/hand-stock-drafts",
    stockControlHandStockDraftDetail: (id: number | string) =>
      `/portal/stock-control/hand-stock-drafts/${id}`,

    // Store-balance uses POST /portal/stock-control/preview and POST /portal/stock-control/runs.

    // ─── Photo Studio (изображения карточек) ─────────────────────────
    photoStatus: "/portal/photo/status",
    photoSettings: "/portal/photo/settings",
    photoProjects: "/portal/photo/projects",
    photoProjectDetail: (id: number | string) => `/portal/photo/projects/${id}`,
    photoProjectImportWb: (id: number | string) =>
      `/portal/photo/projects/${id}/assets/import-wb`,
    photoProjectAssets: (id: number | string) =>
      `/portal/photo/projects/${id}/assets`,
    photoProjectAssetUpload: (id: number | string) =>
      `/portal/photo/projects/${id}/assets/upload`,
    photoProjectJobs: (id: number | string) =>
      `/portal/photo/projects/${id}/jobs`,
    photoProjectVersions: (id: number | string) =>
      `/portal/photo/projects/${id}/versions`,
    photoProjectMessages: (id: number | string) =>
      `/portal/photo/projects/${id}/messages`,
    photoProjectComments: (id: number | string) =>
      `/portal/photo/projects/${id}/messages`,
    photoAssetDownloadUrl: (assetId: number | string) =>
      `/portal/photo/assets/${assetId}/download-url`,
    photoVersionExperiment: (id: number | string, vid: number | string) =>
      `/portal/photo/projects/${id}/versions/${vid}/experiment`,
    photoJobCancel: (jobId: number | string) =>
      `/portal/photo/jobs/${jobId}/cancel`,
    photoJobRetry: (jobId: number | string) =>
      `/portal/photo/jobs/${jobId}/retry`,
    photoVersionReview: (id: number | string, vid: number | string) =>
      `/portal/photo/projects/${id}/versions/${vid}/review`,
    photoVersionPrefer: (id: number | string, vid: number | string) =>
      `/portal/photo/projects/${id}/versions/${vid}/review`,
    photoVersionApprove: (id: number | string, vid: number | string) =>
      `/portal/photo/projects/${id}/versions/${vid}/review`,
    photoVersionReject: (id: number | string, vid: number | string) =>
      `/portal/photo/projects/${id}/versions/${vid}/review`,
    photoVersionApplyWb: (id: number | string, vid: number | string) =>
      `/portal/photo/projects/${id}/versions/${vid}/apply-wb`,
    photoProjectCardPhotosSaveWb: (id: number | string) =>
      `/portal/photo/projects/${id}/card-photos/save-wb`,
  },
  photoStudioCards: {
    wbLive: (accountId: number | string) =>
      `/stores/${accountId}/cards/wb/live`,
  },
  sync: {
    runs: "/sync/runs",
    cursors: "/sync/cursors",
    trigger: "/sync/trigger",
  },
  portalExtras: {
    dataReadiness: "/portal/data-readiness",
    dataSyncStatus: "/portal/data-sync/status",
  },
  exports: {
    dataQuality: "/export/data-quality.xlsx",
    missingCosts: "/export/missing-costs.xlsx",
    profitBySku: "/export/profit-by-sku.xlsx",
    reconciliation: "/export/reconciliation.xlsx",
    stock: "/export/stock.xlsx",
  },
} as const;

// ─── Standard business params ─────────────────────────────────────────────
// account_id + date_from + date_to must be sent on every business endpoint
// that supports them. Use buildBizQuery to assemble the query object.

export interface BizQueryInput {
  accountId: number | null | undefined;
  dateFrom: string;
  dateTo: string;
  limit?: number;
  offset?: number;
  extra?: Record<string, string | number | boolean | null | undefined>;
}

/** Default account when no selector exists in the UI. */
export const DEFAULT_ACCOUNT_ID = 1;

export function buildBizQuery(
  p: BizQueryInput,
): Record<string, string | number | boolean | null | undefined> {
  return {
    account_id: p.accountId ?? DEFAULT_ACCOUNT_ID,
    date_from: p.dateFrom,
    date_to: p.dateTo,
    ...(p.limit != null ? { limit: p.limit } : {}),
    ...(p.offset != null ? { offset: p.offset } : {}),
    ...(p.extra ?? {}),
  };
}

// ─── Shared default date range ────────────────────────────────────────────
export interface DateRangeISO {
  from: string;
  to: string;
}

export function defaultDateRange(days = 30): DateRangeISO {
  const safeDays = Math.max(1, Math.floor(days));
  const today = new Date();
  const from = new Date(today);
  from.setDate(today.getDate() - safeDays + 1);
  return {
    from: localIsoDate(from),
    to: localIsoDate(today),
  };
}

function localIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

// Whitelist of UI routes that must NEVER be used as API paths.
// Kept here as documentation; not enforced at runtime.
export const FORBIDDEN_API_PATHS = [
  "/money",
  "/cards",
  "/cards/{id}",
  "/sku/{id}",
  "/data-fix",
  "/costs",
  "/finance",
  "/operations",
  "/pricing",
  "/purchase-plan",
] as const;
