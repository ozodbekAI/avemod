import type { Page, Route } from "@playwright/test";

type JsonBody = Record<string, unknown> | unknown[];

const json = (body: JsonBody, status = 200) => ({
  status,
  contentType: "application/json",
  body: JSON.stringify(body),
});

const tokenPair = {
  access_token: "e2e-access-token",
  refresh_token: "e2e-refresh-token",
  token_type: "bearer",
};

const user = {
  id: 1,
  email: "owner@example.com",
  full_name: "E2E Owner",
  is_active: true,
  is_superuser: true,
  roles: ["superuser"],
  accounts: [{ id: 1, name: "E2E WB", role: "admin", is_default: true }],
};

const overview = {
  account_id: 1,
  period: {
    date_from: "2026-07-12",
    date_to: "2026-07-18",
    previous_date_from: "2026-07-05",
    previous_date_to: "2026-07-11",
  },
  hero: {
    title: "Магазин готов к управлению",
    subtitle: "Корреляция, а не гарантия: данные демонстрационные.",
    status: "operational",
  },
  money: { revenue: 125000, profit: 32000, expenses: 93000 },
  tasks: [
    {
      id: 1,
      title: "До действия",
      description: "После изменения проверьте результат.",
      priority: "P1",
      status: "open",
    },
  ],
  products: [],
  trust: { status: "provisional", message: "Корреляция, а не гарантия" },
};

const products = {
  items: [
    {
      nm_id: 1001001,
      vendor_code: "E2E-001",
      title: "Product 360 deep link",
      brand: "E2E",
      subject_name: "Брюки",
    },
  ],
  total: 1,
  limit: 10,
  offset: 0,
};

const assignableUsers = [
  {
    id: 1,
    email: "owner@example.com",
    full_name: "E2E Owner",
    display_name: "E2E Owner",
    role: "admin",
    is_active: true,
    is_superuser: true,
  },
];

const portalAction = {
  id: "42",
  action_id: 42,
  external_id: "problem:42",
  source: "problem_engine",
  source_module: "problem_engine",
  source_id: "problem:42",
  account_id: 1,
  action_type: "upload_cost",
  detector_code: "missing_cost_blocks_profit",
  problem_code: "missing_cost_blocks_profit",
  title: "Открыть задачу",
  reason: "По товару E2E-001 есть выручка, но не заполнена себестоимость.",
  next_step: "Загрузите себестоимость и перепроверьте товар.",
  priority: "P1",
  severity: "high",
  status: "new",
  confidence: "medium",
  nm_id: 1001001,
  sku_id: 7007001,
  created_at: "2026-07-18T09:00:00Z",
  assigned_to_user_id: 1,
  deadline_at: "2026-07-21T09:00:00Z",
  expected_impact_amount: 12000,
  impact_type: "data_blocker",
  trust_state: "blocked",
  evidence_state: "partial_evidence",
  can_update: true,
  can_update_status: true,
  can_execute: true,
  source_sync_state: "source_updated",
  allowed_actions: [
    "upload_cost",
    "open_data_fix",
    "open_results",
    "open_product",
    "recheck",
  ],
  data_freshness: {
    source_status: "fresh",
    required_sources: ["sales", "costs"],
    blocking_sources: ["costs"],
    freshness_notes: ["E2E mock data"],
  },
  money_trust: {
    state: "blocked",
    impact_kind: "data_blocker",
    display_label: "Не хватает данных",
    amount_label: "Не хватает данных",
    seller_visible_by_default: true,
    saved_money_claimed: false,
  },
  guided_fix: {
    route_key: "costs",
    label: "Загрузить себестоимость",
    href: "/costs?problem_instance_id=42&nm_id=1001001",
  },
  linked_entity: {
    entity_type: "product",
    nm_id: 1001001,
    sku_id: 7007001,
    vendor_code: "E2E-001",
  },
  payload: {
    problem_instance_id: 42,
    problem_code: "missing_cost_blocks_profit",
    nm_id: 1001001,
    sku_id: 7007001,
    vendor_code: "E2E-001",
    title: "Открыть задачу",
    reason: "Себестоимость отсутствует, прибыль нельзя подтвердить.",
    next_step: "Загрузите себестоимость и перепроверьте товар.",
    allowed_actions: [
      "upload_cost",
      "open_data_fix",
      "open_results",
      "open_product",
      "recheck",
    ],
  },
};

const portalActionsPage = {
  items: [portalAction],
  total: 1,
  limit: 50,
  offset: 0,
  summary: {
    open: 1,
    urgent: 1,
    data_blockers: 1,
  },
};

const resultEvent = {
  id: "result-42",
  account_id: 1,
  action_id: 42,
  problem_instance_id: 42,
  problem_code: "missing_cost_blocks_profit",
  source_module: "problem_engine",
  source_id: "problem:42",
  external_id: "problem:42",
  nm_id: 1001001,
  sku_id: 7007001,
  event_type: "result_evaluated",
  outcome: "not_enough_data",
  result_status: "not_enough_data",
  impact_type: "data_blocker",
  trust_state: "blocked",
  confidence: "medium",
  created_at: "2026-07-18T12:00:00Z",
  message: "Себестоимость ещё не заполнена, результат ждёт данных.",
  product_identity: {
    title: "Product 360 deep link",
    vendor_code: "E2E-001",
  },
  before_snapshot: {
    title: "Product 360 deep link",
    unit_profit: null,
    cost_price: null,
  },
  after_snapshot: {
    title: "Product 360 deep link",
    unit_profit: null,
    cost_price: null,
  },
  comparison: {
    metrics: [],
    status: "not_enough_data",
  },
  payload: {
    title: "Открыть задачу",
    problem_instance_id: 42,
    problem_code: "missing_cost_blocks_profit",
    nm_id: 1001001,
    vendor_code: "E2E-001",
  },
};

const actionCompletedEvent = {
  ...resultEvent,
  id: "result-42-action-completed",
  event_type: "action_completed",
  outcome: "pending_data",
  result_status: "pending_data",
  message: "Действие выполнено, ждём свежие данные после изменения.",
};

const recheckResultEvent = {
  ...resultEvent,
  id: "result-42-recheck",
  event_type: "recheck_result",
  outcome: "not_enough_data",
  result_status: "not_enough_data",
  message:
    "Повторная проверка выполнена, данных для финального результата пока мало.",
};

const resultEventsPage = {
  status: "ok",
  items: [resultEvent, actionCompletedEvent, recheckResultEvent],
  recent_events: [resultEvent, actionCompletedEvent, recheckResultEvent],
  total: 3,
  limit: 10,
  offset: 0,
  summary: {
    total: 3,
    improved: 0,
    worse: 0,
    neutral: 0,
    not_enough_data: 2,
    pending_data: 1,
  },
  by_module: { problem_engine: 3 },
  by_outcome: { not_enough_data: 2, pending_data: 1 },
  pending_followups: [],
  finance_windows: {},
};

const logisticsOverview = {
  account_id: 1,
  period: { date_from: "2026-07-12", date_to: "2026-07-18" },
  generated_at: "2026-07-18T12:40:00Z",
  kpis: {
    orders_qty: 1840,
    sales_qty: 1420,
    revenue: 5880000,
    for_pay: 3712000,
    logistics_cost: 420000,
    storage_cost: 86000,
    acceptance_cost: 32000,
    return_logistics_cost: 74000,
    missed_orders_qty: 390,
    missed_revenue: 1264000,
    cancelled_orders_qty: 112,
    cancelled_revenue: 284000,
    stock_units: 21460,
    in_way_to_client: 820,
    in_way_from_client: 184,
    active_warehouses: 7,
    risky_warehouses: 3,
    available_acceptance_slots: 5,
    avg_logistics_per_order: 332,
    logistics_share_percent: 10.4,
    buyout_percent: 77.2,
    margin_percent: 31.8,
    paid_storage_detail_cost: 86000,
    paid_storage_detail_rows: 4,
    acceptance_detail_cost: 32000,
    acceptance_detail_rows: 3,
    transit_route_count: 3,
    seller_warehouse_count: 2,
    seller_stock_units: 760,
  },
  warehouses: [
    {
      warehouse_id: 507,
      warehouse_name: "Коледино",
      region_name: "Центральный",
      stock_units: 3200,
      in_way_to_client: 190,
      in_way_from_client: 38,
      orders_qty: 520,
      sales_qty: 398,
      revenue: 1780000,
      for_pay: 1110000,
      revenue_source: "finance",
      finance_rows: 244,
      logistics_cost: 156000,
      storage_cost: 28000,
      acceptance_cost: 9000,
      return_logistics_cost: 23000,
      cancelled_orders_qty: 44,
      cancelled_revenue: 101000,
      missed_orders_qty: 142,
      missed_revenue: 482000,
      buyout_percent: 76.5,
      logistics_share_percent: 12.1,
      margin_percent: 29.4,
      turnover_days: 8.1,
      acceptance_coefficient: "1.4",
      acceptance_status: "expensive",
      allow_unload: true,
      acceptance_next_available_at: "2026-07-20T08:00:00Z",
      acceptance_box_type_id: 2,
      box_type_ids: [2, 5],
      delivery_base: 48,
      delivery_liter: 11,
      storage_base: 0.14,
      region_sales_qty: 780,
      region_sales_amount: 2980000,
      region_sales_share_percent: 48.2,
      supply_count: 5,
      open_supply_count: 2,
      risk_level: "danger",
      recommendation:
        "Быстро довезти топовые SKU: склад даёт максимальную потерю заказов.",
    },
    {
      warehouse_id: 120762,
      warehouse_name: "Тула",
      region_name: "Южный + Северо-Кавказский",
      stock_units: 6200,
      in_way_to_client: 244,
      in_way_from_client: 51,
      orders_qty: 610,
      sales_qty: 496,
      revenue: 2220000,
      for_pay: 1430000,
      revenue_source: "finance",
      finance_rows: 310,
      logistics_cost: 172000,
      storage_cost: 31000,
      acceptance_cost: 12000,
      return_logistics_cost: 28000,
      cancelled_orders_qty: 36,
      cancelled_revenue: 92000,
      missed_orders_qty: 118,
      missed_revenue: 396000,
      buyout_percent: 81.3,
      logistics_share_percent: 9.6,
      margin_percent: 34.1,
      turnover_days: 18.4,
      acceptance_coefficient: "1.0",
      acceptance_status: "available",
      allow_unload: true,
      acceptance_next_available_at: "2026-07-19T09:30:00Z",
      acceptance_box_type_id: 2,
      box_type_ids: [2],
      delivery_base: 42,
      delivery_liter: 9,
      storage_base: 0.11,
      region_sales_qty: 640,
      region_sales_amount: 2350000,
      region_sales_share_percent: 39.4,
      supply_count: 4,
      open_supply_count: 1,
      risk_level: "watch",
      recommendation:
        "Держать плановую поставку: слот доступен, экономика нормальная.",
    },
    {
      warehouse_id: 2737,
      warehouse_name: "Казань",
      region_name: "Поволжский",
      stock_units: 1450,
      in_way_to_client: 86,
      in_way_from_client: 21,
      orders_qty: 310,
      sales_qty: 226,
      revenue: 940000,
      for_pay: 562000,
      revenue_source: "finance",
      finance_rows: 128,
      logistics_cost: 92000,
      storage_cost: 21000,
      acceptance_cost: 7000,
      return_logistics_cost: 15000,
      cancelled_orders_qty: 32,
      cancelled_revenue: 74000,
      missed_orders_qty: 95,
      missed_revenue: 301000,
      buyout_percent: 72.9,
      logistics_share_percent: 14.4,
      margin_percent: 24.8,
      turnover_days: 6.4,
      acceptance_coefficient: "—",
      acceptance_status: "closed",
      allow_unload: false,
      acceptance_next_available_at: null,
      acceptance_box_type_id: null,
      box_type_ids: [2],
      delivery_base: 58,
      delivery_liter: 13,
      storage_base: 0.18,
      region_sales_qty: 360,
      region_sales_amount: 1180000,
      region_sales_share_percent: 21.6,
      supply_count: 2,
      open_supply_count: 0,
      risk_level: "warning",
      recommendation:
        "Не везти без проверки транзита: приёмка закрыта, логистика дорогая.",
    },
  ],
  tasks: [
    {
      id: "log-task-1",
      task_type: "stockout",
      severity: "danger",
      title: "Коледино: дефицит по быстрым артикулам",
      warehouse_name: "Коледино",
      region_name: "Центральный",
      detail:
        "Остатка хватит меньше чем на 9 дней, упущенный спрос уже выше 480 тыс.",
      action: "Отгрузить 1 280 шт. в ближайший доступный слот.",
      forecast_days: 14,
      stockout_in_days: 8,
      recommended_supply_qty: 1280,
      potential_orders_qty: 142,
      potential_revenue: 482000,
      expected_net_effect: 138000,
      logistics_share_percent: 12.1,
      buyout_percent: 76.5,
      confidence: "high",
      tags: ["дефицит", "центральный регион", "быстрый довоз"],
    },
    {
      id: "log-task-2",
      task_type: "logistics_cost",
      severity: "warning",
      title: "Казань: логистика съедает маржу",
      warehouse_name: "Казань",
      region_name: "Поволжский",
      detail:
        "Доля логистики 14,4%, приёмка закрыта, нужен транзитный маршрут.",
      action: "Сравнить транзитные тарифы и отложить прямую поставку.",
      forecast_days: 30,
      stockout_in_days: 6,
      recommended_supply_qty: 540,
      potential_orders_qty: 95,
      potential_revenue: 301000,
      expected_net_effect: 61000,
      logistics_share_percent: 14.4,
      buyout_percent: 72.9,
      confidence: "medium",
      tags: ["дорогая логистика", "транзит", "закрытая приёмка"],
    },
  ],
  products: [
    {
      id: "p-1",
      nm_id: 1001001,
      vendor_code: "E2E-001",
      barcode: "460000000001",
      title: "Брюки базовые",
      brand: "E2E",
      subject_name: "Брюки",
      warehouse_name: "Коледино",
      region_name: "Центральный",
      stock_units: 140,
      in_way_to_client: 18,
      in_way_from_client: 3,
      orders_qty: 120,
      sales_qty: 96,
      cancelled_orders_qty: 12,
      cancelled_revenue: 28000,
      revenue: 394000,
      for_pay: 250000,
      revenue_source: "finance",
      finance_rows: 44,
      logistics_cost: 32000,
      storage_cost: 4200,
      acceptance_cost: 1100,
      return_logistics_cost: 5100,
      buyout_percent: 80,
      logistics_share_percent: 10.8,
      margin_percent: 33.2,
      avg_daily_sales: 13.7,
      turnover_days: 10.2,
      recommended_supply_14: 52,
      recommended_supply_30: 271,
      potential_orders_qty: 58,
      potential_revenue: 218000,
      expected_net_effect: 68400,
      risk_level: "danger",
      reason: "быстро заканчивается",
      tags: ["хит", "дефицит"],
    },
    {
      id: "p-2",
      nm_id: 1001002,
      vendor_code: "E2E-002",
      barcode: "460000000002",
      title: "Рубашка хлопок",
      brand: "E2E",
      subject_name: "Рубашки",
      warehouse_name: "Коледино",
      region_name: "Центральный",
      stock_units: 80,
      in_way_to_client: 11,
      in_way_from_client: 2,
      orders_qty: 92,
      sales_qty: 72,
      cancelled_orders_qty: 8,
      cancelled_revenue: 19000,
      revenue: 296000,
      for_pay: 184000,
      revenue_source: "finance",
      finance_rows: 38,
      logistics_cost: 26000,
      storage_cost: 3600,
      acceptance_cost: 900,
      return_logistics_cost: 4200,
      buyout_percent: 78.2,
      logistics_share_percent: 11.7,
      margin_percent: 31.6,
      avg_daily_sales: 10.3,
      turnover_days: 7.8,
      recommended_supply_14: 65,
      recommended_supply_30: 229,
      potential_orders_qty: 42,
      potential_revenue: 166000,
      expected_net_effect: 50200,
      risk_level: "warning",
      reason: "низкое покрытие",
      tags: ["низкий остаток"],
    },
    {
      id: "p-3",
      nm_id: 1001003,
      vendor_code: "E2E-003",
      barcode: "460000000003",
      title: "Платье миди",
      brand: "E2E",
      subject_name: "Платья",
      warehouse_name: "Тула",
      region_name: "Южный + Северо-Кавказский",
      stock_units: 620,
      in_way_to_client: 21,
      in_way_from_client: 4,
      orders_qty: 140,
      sales_qty: 120,
      cancelled_orders_qty: 5,
      cancelled_revenue: 17000,
      revenue: 620000,
      for_pay: 410000,
      revenue_source: "finance",
      finance_rows: 62,
      logistics_cost: 39000,
      storage_cost: 5200,
      acceptance_cost: 1600,
      return_logistics_cost: 6400,
      buyout_percent: 85.7,
      logistics_share_percent: 8.4,
      margin_percent: 36.1,
      avg_daily_sales: 17.1,
      turnover_days: 36.2,
      recommended_supply_14: 0,
      recommended_supply_30: 0,
      potential_orders_qty: 0,
      potential_revenue: 0,
      expected_net_effect: 0,
      risk_level: "ok",
      reason: "запас достаточный",
      tags: ["норма"],
    },
    {
      id: "p-4",
      nm_id: 1001004,
      vendor_code: "E2E-004",
      barcode: "460000000004",
      title: "Кроссовки городские",
      brand: "E2E",
      subject_name: "Обувь",
      warehouse_name: "Казань",
      region_name: "Поволжский",
      stock_units: 65,
      in_way_to_client: 9,
      in_way_from_client: 2,
      orders_qty: 74,
      sales_qty: 51,
      cancelled_orders_qty: 9,
      cancelled_revenue: 33000,
      revenue: 244000,
      for_pay: 142000,
      revenue_source: "finance",
      finance_rows: 29,
      logistics_cost: 26000,
      storage_cost: 4800,
      acceptance_cost: 900,
      return_logistics_cost: 4200,
      buyout_percent: 68.9,
      logistics_share_percent: 14.7,
      margin_percent: 24.1,
      avg_daily_sales: 7.3,
      turnover_days: 8.9,
      recommended_supply_14: 38,
      recommended_supply_30: 154,
      potential_orders_qty: 30,
      potential_revenue: 119000,
      expected_net_effect: 21500,
      risk_level: "warning",
      reason: "дорогая логистика",
      tags: ["транзит"],
    },
  ],
  regional_shipments: [
    {
      id: "r-1",
      warehouse_name: "Коледино",
      region_name: "Центральный",
      recommended_supply_qty: 1280,
      potential_orders_qty: 142,
      potential_revenue: 482000,
      region_sales_qty: 780,
      region_sales_amount: 2980000,
      region_sales_share_percent: 48.2,
      expected_logistics_cost: 71000,
      expected_net_effect: 138000,
      current_stock_units: 3200,
      turnover_days: 8.1,
      acceptance_status: "expensive",
      acceptance_coefficient: "1.4",
      priority: "recommended",
      reason: "Самый большой риск потерянных заказов.",
      tags: ["центральный регион"],
    },
  ],
  warehouse_controls: [
    {
      warehouse_name: "Коледино",
      region_name: "Центральный",
      mode: "active",
      recommended_mode: "active",
      task_count: 1,
      potential_revenue: 482000,
      stock_units: 3200,
      turnover_days: 8.1,
      acceptance_status: "expensive",
      logistics_share_percent: 12.1,
      reason: "Оставить активным: склад нужен для выручки.",
    },
    {
      warehouse_name: "Казань",
      region_name: "Поволжский",
      mode: "active",
      recommended_mode: "review_economics",
      task_count: 1,
      potential_revenue: 301000,
      stock_units: 1450,
      turnover_days: 6.4,
      acceptance_status: "closed",
      logistics_share_percent: 14.4,
      reason: "Проверить транзит и экономику до прямой поставки.",
    },
  ],
  supplies: [
    {
      supply_id: 91001,
      preorder_id: 7001,
      warehouse_name: "Коледино",
      actual_warehouse_name: "Коледино",
      status_id: 2,
      status_label: "В работе",
      supply_date: "2026-07-19T08:00:00Z",
      fact_date: null,
      planned_qty: 640,
      accepted_qty: 0,
      gap_qty: 640,
      box_type_id: 2,
      last_enriched_at: "2026-07-18T12:00:00Z",
    },
  ],
  paid_storage_details: [
    {
      id: 1,
      report_date: "2026-07-18",
      warehouse_name: "Коледино",
      nm_id: 1001001,
      vendor_code: "E2E-001",
      barcode: "460000000001",
      title: "Брюки базовые",
      brand: "E2E",
      subject_name: "Брюки",
      quantity: 140,
      amount: 18400,
      amount_per_unit: 131.4,
      share_percent: 21.4,
      task_id: "paid-1",
      source_row_key: "paid-1",
    },
  ],
  acceptance_details: [
    {
      id: 1,
      operation_date: "2026-07-17",
      warehouse_name: "Коледино",
      operation_name: "Приёмка коробов",
      nm_id: 1001001,
      vendor_code: "E2E-001",
      barcode: "460000000001",
      title: "Брюки базовые",
      brand: "E2E",
      subject_name: "Брюки",
      quantity: 240,
      amount: 9600,
      amount_per_unit: 40,
      share_percent: 30,
      task_id: "acc-1",
      source_row_key: "acc-1",
    },
  ],
  transit_tariffs: [
    {
      id: 1,
      collected_at: "2026-07-18T12:00:00Z",
      route_label: "Тула → Коледино → Казань",
      source_warehouse_id: 120762,
      source_warehouse_name: "Тула",
      transit_warehouse_id: 507,
      transit_warehouse_name: "Коледино",
      destination_warehouse_id: 2737,
      destination_warehouse_name: "Казань",
      box_type_id: 2,
      coefficient: "1.2",
      delivery_base: 38,
      delivery_liter: 8,
      amount: 7600,
      currency: "RUB",
      transit_time_days: 3,
      score: 84,
    },
  ],
  seller_warehouses: [
    {
      id: 1,
      warehouse_id: 501001,
      name: "FBS Москва",
      office_id: 77,
      delivery_type: "fbs",
      delivery_type_label: "FBS",
      cargo_type: "box",
      address: "Москва",
      is_active: true,
      stock_rows: 42,
      stock_units: 520,
      latest_stock_at: "2026-07-18T11:00:00Z",
    },
  ],
  shipment_planning: {
    status: "stock_control",
    formula: {
      source: "stock_control",
      title: "Формула контроля остатков",
      detail:
        "Цель = общий остаток SKU × доля спроса региона; дельта = цель - текущий остаток.",
      latest_run_id: 44,
      latest_run_type: "return_excess",
      latest_run_finished_at: "2026-07-18T12:15:00Z",
    },
    regions: [
      {
        key: "region:центральный",
        label: "Центральный",
        scope_type: "region",
        region_name: "Центральный",
        warehouse_id: null,
        warehouse_name: null,
        enabled_by_default: true,
        selectable: true,
        reason: "контроль остатков: дефицит 410 шт. для ближайшей поставки.",
        risk_level: "danger",
        acceptance_status: null,
        stock_units: 3200,
        current_stock_qty: 530,
        target_stock_qty: 940,
        delta_qty: 410,
        shortage_qty: 410,
        excess_qty: 0,
        inbound_qty: 180,
        outbound_qty: 0,
        sales_qty: 398,
        revenue: 1780000,
        product_count: 2,
      },
      {
        key: "region:поволжский",
        label: "Поволжский",
        scope_type: "region",
        region_name: "Поволжский",
        warehouse_id: null,
        warehouse_name: null,
        enabled_by_default: false,
        selectable: true,
        reason: "Регион исключён в настройках контроля остатков.",
        risk_level: "warning",
        acceptance_status: null,
        stock_units: 1450,
        current_stock_qty: 210,
        target_stock_qty: 360,
        delta_qty: 150,
        shortage_qty: 150,
        excess_qty: 0,
        inbound_qty: 0,
        outbound_qty: 0,
        sales_qty: 226,
        revenue: 940000,
        product_count: 1,
      },
    ],
    warehouses: [
      {
        key: "warehouse:коледино",
        label: "Коледино",
        scope_type: "warehouse",
        region_name: "Центральный",
        warehouse_id: 507,
        warehouse_name: "Коледино",
        enabled_by_default: true,
        selectable: true,
        reason: "контроль остатков: дефицит 410 шт. для ближайшей поставки.",
        risk_level: "danger",
        acceptance_status: "expensive",
        stock_units: 3200,
        current_stock_qty: 530,
        target_stock_qty: 940,
        delta_qty: 410,
        shortage_qty: 410,
        excess_qty: 0,
        inbound_qty: 180,
        outbound_qty: 0,
        sales_qty: 398,
        revenue: 1780000,
        product_count: 2,
      },
      {
        key: "warehouse:казань",
        label: "Казань",
        scope_type: "warehouse",
        region_name: "Поволжский",
        warehouse_id: 2737,
        warehouse_name: "Казань",
        enabled_by_default: false,
        selectable: true,
        reason: "Приёмка закрыта: склад лучше включать только вручную.",
        risk_level: "warning",
        acceptance_status: "closed",
        stock_units: 1450,
        current_stock_qty: 210,
        target_stock_qty: 360,
        delta_qty: 150,
        shortage_qty: 150,
        excess_qty: 0,
        inbound_qty: 0,
        outbound_qty: 0,
        sales_qty: 226,
        revenue: 940000,
        product_count: 1,
      },
    ],
    movements: [
      {
        id: 501,
        movement_type: "regional_redistribution",
        nm_id: 1001001,
        vendor_code: "E2E-001",
        barcode: "460000000001",
        size_name: "M",
        donor_region: "Южный + Северо-Кавказский",
        donor_warehouse: "Тула",
        recipient_region: "Центральный",
        recipient_warehouse: "Коледино",
        quantity: 180,
        priority: "P1",
        reason_code: "regional_shortage",
        business_explanation: "Коледино закрывает дефицит по быстрому SKU.",
        confidence: "high",
        status: "new",
      },
    ],
    excluded_regions: ["Поволжский"],
    source_run_id: 44,
    source_run_type: "return_excess",
    source_run_finished_at: "2026-07-18T12:15:00Z",
    summary: { products: 3, regions: 2, movements: 1 },
  },
  data_sources: [
    {
      key: "stocks",
      label: "Остатки WB",
      status: "ok",
      rows: 21460,
      latest_at: "2026-07-18T11:30:00Z",
    },
    {
      key: "paid_storage",
      label: "Платное хранение",
      status: "ok",
      rows: 4,
      latest_at: "2026-07-18T12:00:00Z",
    },
    {
      key: "transit",
      label: "Транзитные тарифы",
      status: "ok",
      rows: 3,
      latest_at: "2026-07-18T12:00:00Z",
    },
  ],
  api_capabilities: [
    {
      key: "paid_storage",
      label: "Детальный отчёт платного хранения",
      endpoint: "GET seller-analytics-api /api/v1/paid_storage",
      token_category: "analytics",
      status: "active",
    },
    {
      key: "acceptance_report",
      label: "Детальный отчёт расходов приёмки",
      endpoint: "GET seller-analytics-api /api/v1/acceptance_report",
      token_category: "analytics",
      status: "active",
    },
    {
      key: "transit_tariffs",
      label: "Транзитные направления и тарифы",
      endpoint: "GET supplies-api /api/v1/transit-tariffs",
      token_category: "supplies",
      status: "active",
    },
    {
      key: "seller_warehouses",
      label: "Склады продавца FBS/DBW и остатки",
      endpoint: "GET marketplace-api /api/v3/warehouses",
      token_category: "marketplace",
      status: "active",
    },
  ],
  recommendations: [
    {
      severity: "danger",
      title: "Сначала Коледино",
      detail: "Самая большая потеря заказов и короткое покрытие остатка.",
      action: "Отгрузить 1 280 шт.",
      source: "logistics",
    },
    {
      severity: "warning",
      title: "Казань через транзит",
      detail: "Приёмка закрыта, прямой маршрут дорогой.",
      action: "Сравнить тарифы",
      source: "logistics",
    },
  ],
};

const product360 = {
  nm_id: 1001001,
  identity: {
    status: "ok",
    data: {
      nm_id: 1001001,
      sku_id: 7007001,
      vendor_code: "E2E-001",
      title: "Product 360 deep link",
      brand: "E2E",
      subject_name: "Брюки",
    },
  },
  money: {
    status: "ok",
    data: {
      revenue: 125000,
      profit: null,
      margin_percent: null,
    },
  },
  costs: {
    status: "blocked",
    data: {
      cogs: { unit_cost: null },
    },
    message: "Себестоимость не заполнена.",
  },
  business_issues: {
    status: "blocked",
    data: {
      open: [portalAction],
      resolved: [],
      summary: {
        open_count: 1,
        resolved_count: 0,
      },
    },
  },
  actions: [portalAction],
  result_history: {
    status: "ok",
    data: resultEventsPage,
  },
  next_best_action: portalAction,
  module_health: {},
};

const agentResponse = {
  status: "ok",
  mode: "ai",
  intent: "product_search",
  message: "Товары найдены. Выберите нужный товар.",
  actions: [
    {
      type: "open_product_picker",
      title: "Выбрать товар",
      payload: { intent: "product_details", search_query: "брюки" },
    },
  ],
  products: products.items,
  suggestions: [],
  warnings: [],
  audit: { planner: "ai" },
};

function agentResponseFor(body: Record<string, unknown>) {
  const message = String(body.message || "").toLowerCase();
  if (
    (message.includes("отзывы") || message.includes("репутац")) &&
    !message.includes("сценар")
  ) {
    return {
      status: "ok",
      mode: "ai",
      intent: "reputation_agent",
      message:
        "Открыл раздел репутации: там можно работать с отзывами, вопросами и задачами по ответам покупателям.",
      actions: [
        { type: "navigate", title: "Репутация", href: "/reputation" },
        { type: "navigate", title: "История задач", href: "/action-center" },
      ],
      products: [],
      suggestions: ["Создай сценарий ответов"],
      warnings: [],
      audit: { planner: "ai", direct_marketplace_writes: false },
    };
  }
  if (message.includes("умные цены") || message.includes("марж")) {
    return {
      status: "ok",
      mode: "ai",
      intent: "pricing_agent",
      message:
        "Открыл контур цен. Изменения цен готовятся только через безопасную проверку маржи и ручное подтверждение.",
      actions: [
        { type: "navigate", title: "Цены", href: "/pricing" },
        { type: "navigate", title: "Центр действий", href: "/action-center" },
      ],
      products: [],
      suggestions: ["Создай сценарий умных цен"],
      warnings: [],
      audit: { planner: "ai", direct_marketplace_writes: false },
    };
  }
  if (message.includes("реклам")) {
    return {
      status: "ok",
      mode: "ai",
      intent: "module_navigate",
      message:
        "Открыл раздел «Реклама»: там можно смотреть кампании, статистику и эффективность.",
      actions: [{ type: "navigate", title: "Реклама", href: "/ads" }],
      products: [],
      suggestions: ["Открой аналитику"],
      warnings: [],
      audit: {
        planner: "ai",
        direct_marketplace_writes: false,
        module_key: "ads",
      },
    };
  }
  if (message.includes("качеств") || message.includes("dq")) {
    return {
      status: "ok",
      mode: "ai",
      intent: "api_action",
      message:
        "Готов запустить проверку качества данных. Перед выполнением потребуется подтверждение.",
      actions: [
        {
          type: "api_request",
          title: "Запустить проверку данных",
          description:
            "Запустить проверку качества данных по выбранному аккаунту.",
          href: "/dq/run",
          method: "POST",
          confirm_required: true,
          payload: {
            api_action_key: "data_quality.run",
            body: { account_id: 1 },
            success_message: "Проверка качества данных запущена.",
          },
        },
        { type: "navigate", title: "Качество данных", href: "/data-fix" },
      ],
      products: [],
      suggestions: ["Открой качество данных"],
      warnings: [
        "Прямые записи в Wildberries не выполняются без отдельного подтверждения, аудита и прав пользователя.",
      ],
      audit: {
        planner: "ai",
        direct_marketplace_writes: false,
        api_action_key: "data_quality.run",
      },
    };
  }
  if (message.includes("сценар")) {
    if (body.selected_nm_id) {
      return {
        status: "ok",
        mode: "ai",
        intent: "scenario_create",
        message:
          "Создал draft AI-сценария «Создай сценарий ответов на негативные отзывы». Прямых записей в Wildberries нет.",
        actions: [
          {
            type: "api_request",
            title: "Тестовый запуск",
            href: "/portal/agent/scenarios/77/run?account_id=1",
            method: "POST",
            confirm_required: true,
            description: "Запустить сценарий в безопасном dry-run режиме.",
            payload: {
              body: { trigger: "chat", dry_run: true },
              success_message: "AI-сценарий запущен в dry-run режиме.",
            },
          },
          {
            type: "api_request",
            title: "История запусков",
            href: "/portal/agent/scenario-runs?account_id=1&scenario_id=77",
            method: "GET",
            payload: { success_message: "История запусков получена." },
          },
        ],
        products: products.items,
        suggestions: ["Запусти тестовый запуск"],
        warnings: [],
        audit: {
          planner: "ai",
          direct_marketplace_writes: false,
          scenario_id: 77,
        },
      };
    }
    return {
      status: "needs_input",
      mode: "ai",
      intent: "scenario_create",
      message:
        "С каким товаром работаем? Выберите товар из списка или уточните поисковый запрос.",
      actions: [
        {
          type: "open_product_picker",
          title: "Выбрать товар",
          payload: {
            intent: "scenario_create",
            search_query: "",
            draft_message: body.message,
          },
        },
      ],
      products: products.items,
      suggestions: [],
      warnings: [],
      audit: { planner: "ai", direct_marketplace_writes: false },
    };
  }
  return agentResponse;
}

export async function installMockApi(page: Page) {
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const apiPrefix = "/api/v1";
    const path = url.pathname.startsWith(apiPrefix)
      ? url.pathname.slice(apiPrefix.length)
      : url.pathname;

    if (path === "/auth/login" || path === "/auth/refresh") {
      await route.fulfill(json(tokenPair));
      return;
    }
    if (path === "/auth/me") {
      await route.fulfill(json(user));
      return;
    }
    if (path === "/accounts") {
      await route.fulfill(json(user.accounts));
      return;
    }
    if (path === "/dashboard/owner") {
      await route.fulfill(
        json({
          account_id: 1,
          account_name: "E2E WB",
          date_from: "2026-07-13",
          date_to: "2026-07-19",
          revenue: 125000,
          profit: 32000,
          owner_message: {
            title: "Магазин готов к управлению",
            reason: "Корреляция, а не гарантия: данные демонстрационные.",
            today_focus: "Проверьте блокеры данных и прибыльность.",
          },
          next_actions_preview: [portalAction],
          trust: {
            trust_state: "provisional",
            financial_final: false,
            blocking_open_issues_total: 1,
          },
        }),
      );
      return;
    }
    if (path === "/dashboard/data-health") {
      await route.fulfill(
        json({
          account_id: 1,
          financial_final: false,
          open_issues_total: 1,
          revenue_cost_coverage_percent: 75,
          sync_status: {},
          domains: {},
        }),
      );
      return;
    }
    if (path === "/dashboard/owner-ai-summary") {
      await route.fulfill(
        json({
          title: "Сводка",
          summary: "Проверьте себестоимость по тестовому товару.",
          bullets: [],
        }),
      );
      return;
    }
    if (path === "/portal/dashboard/overview" || path === "/portal/overview") {
      await route.fulfill(json(overview));
      return;
    }
    if (path === "/products" || path === "/portal/products") {
      await route.fulfill(json(products));
      return;
    }
    if (path === "/portal/products/1001001") {
      await route.fulfill(json(product360));
      return;
    }
    if (path === "/portal/agent/message") {
      let body: Record<string, unknown> = {};
      try {
        const parsed = request.postDataJSON();
        body = parsed && typeof parsed === "object" ? parsed : {};
      } catch {
        body = {};
      }
      await route.fulfill(json(agentResponseFor(body)));
      return;
    }
    if (path === "/dq/run") {
      await route.fulfill(
        json({
          checked_accounts: 1,
          opened_count: 2,
          updated_count: 1,
          resolved_count: 0,
          active_count: 2,
        }),
      );
      return;
    }
    if (path === "/portal/agent/scenarios/77/run") {
      await route.fulfill(
        json({
          id: 501,
          account_id: 1,
          scenario_id: 77,
          trigger: "chat",
          status: "completed",
          dry_run: true,
          actions_preview_json: [
            { title: "Отзывы", api_action_key: "reputation.summary" },
            { title: "Черновики", api_action_key: "reputation.drafts" },
          ],
          actions_executed: 0,
          actions_blocked: 0,
          output_json: {
            summary:
              "Сценарий подготовил 2 preview-действия. Прямых записей в Wildberries не было.",
          },
          estimated_cost_usd: "0",
          created_at: "2026-07-21T09:00:00Z",
          updated_at: "2026-07-21T09:00:00Z",
        }),
      );
      return;
    }
    if (path === "/portal/agent/scenario-runs") {
      await route.fulfill(
        json({
          status: "ok",
          total: 1,
          limit: 50,
          offset: 0,
          items: [
            {
              id: 501,
              account_id: 1,
              scenario_id: 77,
              trigger: "chat",
              status: "completed",
              dry_run: true,
              actions_preview_json: [],
              actions_executed: 0,
              actions_blocked: 0,
              output_json: {},
              estimated_cost_usd: "0",
              created_at: "2026-07-21T09:00:00Z",
              updated_at: "2026-07-21T09:00:00Z",
            },
          ],
        }),
      );
      return;
    }
    if (path === "/portal/agent/finance") {
      await route.fulfill(
        json({
          status: "ok",
          account_id: 1,
          scenarios_total: 1,
          active_scenarios: 0,
          runs_total: 1,
          runs_last_30d: 1,
          failed_runs_last_30d: 0,
          prompt_tokens: 0,
          completion_tokens: 0,
          total_tokens: 0,
          estimated_cost_usd: "0",
          ledger_items: [],
        }),
      );
      return;
    }
    if (path === "/portal/assignable-users") {
      await route.fulfill(json(assignableUsers));
      return;
    }
    if (path === "/portal/actions" || path === "/portal/action-center") {
      await route.fulfill(json(portalActionsPage));
      return;
    }
    if (path === "/portal/results" || path === "/portal/problems/42/results") {
      await route.fulfill(json(resultEventsPage));
      return;
    }
    if (path === "/portal/logistics/overview") {
      await route.fulfill(json(logisticsOverview));
      return;
    }
    if (path === "/analytics/overview") {
      await route.fulfill(
        json({
          ...overview,
          summary: {},
          products: [],
          regions: [],
          trend: [],
        }),
      );
      return;
    }

    await route.fulfill(json({ items: [], total: 0, limit: 10, offset: 0 }));
  });
}
