export type ActionCenterRouteContext = {
  action_id?: string | number | null;
  problem_instance_id?: string | number | null;
  nm_id?: string | number | null;
  source?: string | null;
  source_id?: string | number | null;
  code?: string | null;
};

export function routeSearchText(value: unknown): string | undefined {
  if (value === null || value === undefined) return undefined;
  if (Array.isArray(value)) {
    for (const item of value) {
      const normalized = routeSearchText(item);
      if (normalized) return normalized;
    }
    return undefined;
  }
  if (typeof value !== "string" && typeof value !== "number") return undefined;
  let result = String(value).trim();
  if (result.length >= 2 && result.startsWith('"') && result.endsWith('"')) {
    try {
      const parsed = JSON.parse(result);
      if (typeof parsed === "string" || typeof parsed === "number") {
        result = String(parsed).trim();
      }
    } catch {
      // Keep the original value when it is not a JSON-encoded search scalar.
    }
  }
  return result || undefined;
}

function text(value: string | number | null | undefined): string | null {
  const result = routeSearchText(value);
  return result ?? null;
}

function appendSearch(
  path: string,
  values: Record<string, string | number | null | undefined>,
): string {
  const [base, existing = ""] = path.split("?");
  const params = new URLSearchParams(existing);
  Object.entries(values).forEach(([key, value]) => {
    const normalized = text(value);
    if (normalized) params.set(key, normalized);
  });
  const query = params.toString();
  return query ? `${base}?${query}` : base;
}

export function actionCenterTaskSearch(ctx: ActionCenterRouteContext): Record<string, string> {
  const search: Record<string, string> = {};
  const actionId = text(ctx.action_id);
  const problemInstanceId = text(ctx.problem_instance_id);
  const nmId = text(ctx.nm_id);
  const source = text(ctx.source);
  const sourceId = text(ctx.source_id);
  const code = text(ctx.code);
  if (actionId) search.action_id = actionId;
  if (problemInstanceId) search.problem_instance_id = problemInstanceId;
  if (nmId) search.nm_id = nmId;
  if (source) search.source = source;
  if (sourceId) search.source_id = sourceId;
  if (code) search.code = code;
  return search;
}

export function actionCenterTaskHref(ctx: ActionCenterRouteContext): string {
  return appendSearch("/action-center", actionCenterTaskSearch(ctx));
}

export function actionCenterWorkScreenHref(
  code: string | null | undefined,
  ctx: ActionCenterRouteContext,
): string | null {
  const actionCode = text(code);
  const actionId = text(ctx.action_id);
  const problemInstanceId = text(ctx.problem_instance_id);
  const nmId = text(ctx.nm_id);
  if (actionCode === "open_data_fix") {
    return appendSearch("/data-fix", {
      action_id: actionId,
      problem_instance_id: problemInstanceId,
      nm_id: nmId,
    });
  }
  if (actionCode === "upload_cost") {
    return appendSearch("/costs?focus=missing-costs", {
      action_id: actionId,
      problem_instance_id: problemInstanceId,
      nm_id: nmId,
    });
  }
  if (actionCode === "map_sku") {
    return appendSearch("/data-fix?code=unmatched_sku", {
      action_id: actionId,
      problem_instance_id: problemInstanceId,
    });
  }
  if (actionCode === "open_supply_planner") {
    return appendSearch("/stock-control?tab=supply", {
      action_id: actionId,
      problem_instance_id: problemInstanceId,
      nm_id: nmId,
    });
  }
  if (actionCode === "open_price_review") {
    return nmId
      ? appendSearch(`/products/${nmId}?tab=price`, {
          action_id: actionId,
          problem_instance_id: problemInstanceId,
        })
      : appendSearch("/products", {
          action_id: actionId,
          problem_instance_id: problemInstanceId,
        });
  }
  if (actionCode === "open_promo_planner") {
    return nmId
      ? appendSearch(`/products/${nmId}?tab=promo`, {
          action_id: actionId,
          problem_instance_id: problemInstanceId,
        })
      : appendSearch("/products", {
          action_id: actionId,
          problem_instance_id: problemInstanceId,
        });
  }
  if (actionCode === "open_ads_dashboard") {
    return appendSearch("/ads", {
      action_id: actionId,
      problem_instance_id: problemInstanceId,
      nm_id: nmId,
    });
  }
  if (actionCode === "run_checker") {
    return nmId
      ? appendSearch(`/checker/${nmId}`, {
          action_id: actionId,
          problem_instance_id: problemInstanceId,
        })
      : appendSearch("/products", {
          action_id: actionId,
          problem_instance_id: problemInstanceId,
        });
  }
  if (actionCode === "open_results") {
    return appendSearch("/results", {
      action_id: actionId,
      problem_instance_id: problemInstanceId,
    });
  }
  if (actionCode === "open_product") {
    return nmId
      ? appendSearch(`/products/${nmId}`, {
          action_id: actionId,
          problem_instance_id: problemInstanceId,
        })
      : appendSearch("/products", {
          action_id: actionId,
          problem_instance_id: problemInstanceId,
        });
  }
  return null;
}
