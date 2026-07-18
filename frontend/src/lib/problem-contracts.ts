import type {
  DynamicProblemAction as PortalDynamicProblemAction,
  ProblemResultEvent,
  ProblemResultStatus,
  ProblemStatusHistoryItem,
} from "@/lib/portal";
import type { EvidenceLedger as EvidenceLedgerContract } from "@/lib/evidence";
import type {
  MoneyTrustInfo,
  MoneyTrustState as MoneyTrustStateContract,
} from "@/lib/money-trust";

export type JsonRecord = Record<string, unknown>;

export type AllowedActionCode =
  | "create_task"
  | "assign"
  | "recheck"
  | "dismiss"
  | "open_data_fix"
  | "open_price_review"
  | "open_promo_planner"
  | "open_supply_planner"
  | "open_ads_dashboard"
  | "run_checker"
  | "upload_cost"
  | "map_sku"
  | "classify_expense"
  | "open_product"
  | "open_results";

export type ImpactType =
  | "confirmed_loss"
  | "probable_loss"
  | "blocked_cash"
  | "lost_sales_risk"
  | "opportunity"
  | "data_blocker"
  | "system_warning";

export type MoneyTrustState = MoneyTrustStateContract;
export type EvidenceLedger = EvidenceLedgerContract;
export type DynamicProblemAction = PortalDynamicProblemAction;
export type { ProblemStatusHistoryItem };

export type ProblemMetricComparison = {
  before?: number | null;
  after?: number | null;
  delta?: number | null;
  direction?: "improved" | "worse" | "neutral" | string | null;
  unit?: string | null;
};

export type ProblemResultSummary = {
  status: ProblemResultStatus;
  before_snapshot: JsonRecord;
  current_snapshot: JsonRecord;
  after_snapshot: JsonRecord;
  comparison: JsonRecord | string | null;
  metrics: Record<string, ProblemMetricComparison | JsonRecord>;
  finance_windows: JsonRecord;
  status_history: ProblemStatusHistoryItem[];
  calculation_note?: string | null;
  disclaimer?: string | null;
  confidence?: string | null;
  events: ProblemResultEvent[];
};

export type PriceSafetyContract = {
  status?: string | null;
  reason?: string | null;
  target_margin_pct?: number | string | null;
  current_price?: number | string | null;
  price_after_discount?: number | string | null;
  reference_price?: number | string | null;
  min_safe_price?: number | string | null;
  target_price?: number | string | null;
  max_safe_discount_pct?: number | string | null;
  margin_after_discount?: number | string | null;
  margin_after_recommended_price?: number | string | null;
  missing_required_metrics?: unknown;
  warnings?: unknown;
  component_breakdown?: unknown;
};

export type SellerProblemResultContract = {
  status: ProblemResultStatus;
  detail?: string | null;
  amount?: number | null;
};

export type SellerProblemContract = {
  id?: string | number | null;
  title: string;
  why: string;
  impactText: string;
  impactAmount?: number | null;
  trustState: MoneyTrustState | string;
  impactType: ImpactType | string;
  severity: string;
  status?: string | null;
  nextStep: string;
  canFixHere: boolean;
  canFixHereText: string;
  recheckRule: string;
  result?: SellerProblemResultContract | null;
  showResultBlock: boolean;
  evidenceLedger?: EvidenceLedger | null;
  evidenceQuality: "full" | "partial";
  allowedActions: AllowedActionCode[] | string[];
  sourceLabel?: string | null;
  moneyTrust?: MoneyTrustInfo | null;
  actionCenterSearch?: {
    source?: string;
    source_id?: string;
    code?: string;
    nm_id?: string;
    problem_instance_id?: string;
  };
  priceSafety?: PriceSafetyContract | null;
  needsPriceSafety?: boolean;
};
