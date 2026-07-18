const drawerSections = [
  "Header",
  "Что произошло?",
  "Почему платформа так решила?",
  "На что влияет?",
  "Что сделать сейчас?",
  "Назначение и срок",
  "Статус и комментарий",
  "История",
  "Повторная проверка",
  "Результат после действия",
] as const;

const correlationDisclaimer =
  "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе.";

const baseProblemAction = {
  id: "problem-engine:101",
  source_module: "problem_engine",
  source_kind: "problem_engine",
  source_id: "problem_instance:101",
  problem_instance_id: 101,
  problem_code: "negative_unit_profit",
  title: "Товар продаётся в минус",
  short_explanation: "Маржа ниже безопасного порога по данным продаж и себестоимости.",
  status: "new",
  status_label: "Новая",
  priority: "P1",
  severity: "high",
  trust_state: "confirmed",
  impact_type: "confirmed_loss",
  money_impact_amount: 12500,
  money_impact_currency: "RUB",
  data_freshness: {
    required_sources: ["sales", "finance", "costs"],
    source_status: "fresh",
    last_synced_at: "2026-07-07T08:00:00Z",
    blocking_sources: [],
    freshness_notes: [],
  },
  can_update: true,
  can_recheck: true,
  can_assign: true,
  can_set_deadline: true,
  is_beta: false,
  is_test_only: false,
  is_read_only: false,
  allowed_actions: ["open_price_review", "assign", "recheck"],
  evidence_ledger: {
    formula_human: "Цена продажи - комиссия - логистика - себестоимость < 0",
    facts: [],
    sources: [],
  },
  history_summary: { total: 0, latest_label: null, latest_at: null, items: [] },
} as const;

const emptyResultPage = {
  total: 0,
  limit: 50,
  offset: 0,
  items: [],
  recent_events: [],
  summary: {},
  disclaimer: correlationDisclaimer,
} as const;

const improvedResultPage = {
  total: 4,
  limit: 50,
  offset: 0,
  items: [
    {
      id: "before-101",
      account_id: 1,
      problem_instance_id: 101,
      problem_code: "negative_unit_profit",
      source_module: "problem_engine",
      event_type: "before_snapshot",
      before_snapshot: { status: "new", profit: -12500 },
      created_at: "2026-07-01T09:00:00Z",
    },
    {
      id: "started-101",
      account_id: 1,
      problem_instance_id: 101,
      problem_code: "negative_unit_profit",
      source_module: "problem_engine",
      event_type: "action_started",
      message: "Цена отправлена на пересмотр",
      created_at: "2026-07-01T10:00:00Z",
    },
    {
      id: "after-101",
      account_id: 1,
      problem_instance_id: 101,
      problem_code: "negative_unit_profit",
      source_module: "problem_engine",
      event_type: "after_snapshot",
      outcome: "improved",
      after_snapshot: { status: "done", profit: 3200 },
      created_at: "2026-07-08T10:00:00Z",
    },
    {
      id: "comparison-101",
      account_id: 1,
      problem_instance_id: 101,
      problem_code: "negative_unit_profit",
      source_module: "problem_engine",
      event_type: "measured_comparison",
      outcome: "improved",
      comparison: { profit: { before: -12500, after: 3200, delta: 15700, direction: "improved" } },
      confidence: "medium",
      calculation_note: correlationDisclaimer,
      created_at: "2026-07-08T10:05:00Z",
    },
  ],
  recent_events: [],
  summary: {
    result_status: "improved",
    finance_windows: {
      "7d": {
        metrics: {
          profit: { before: -12500, after: 3200, delta: 15700, direction: "improved" },
        },
      },
    },
  },
  disclaimer: correlationDisclaimer,
} as const;

const worseResultPage = {
  ...improvedResultPage,
  items: improvedResultPage.items.map((event) =>
    event.id === "comparison-101"
      ? {
          ...event,
          outcome: "worse",
          comparison: { profit: { before: -12500, after: -18000, delta: -5500, direction: "worse" } },
        }
      : event.id === "after-101"
        ? { ...event, outcome: "worse", after_snapshot: { status: "done", profit: -18000 } }
        : event,
  ),
  summary: {
    result_status: "worse",
    finance_windows: {
      "7d": {
        metrics: {
          profit: { before: -12500, after: -18000, delta: -5500, direction: "worse" },
        },
      },
    },
  },
} as const;

export const newProblemNoResultDrawerFixture = {
  state: "new problem no result",
  sections: drawerSections,
  action: baseProblemAction,
  resultPage: emptyResultPage,
  expectedEmptyState: "Канонический журнал результата пока пуст",
} as const;

export const inProgressProblemDrawerFixture = {
  state: "in_progress problem",
  sections: drawerSections,
  action: {
    ...baseProblemAction,
    status: "in_progress",
    status_label: "В работе",
    assigned_to_user_name: "Оператор",
    deadline_at: "2026-07-09T12:00:00Z",
    history_summary: {
      total: 1,
      latest_label: "В работе",
      latest_at: "2026-07-07T09:00:00Z",
      items: [{ event_type: "status_changed", old_status: "new", new_status: "in_progress", created_at: "2026-07-07T09:00:00Z" }],
    },
  },
  resultPage: emptyResultPage,
} as const;

export const doneWaitingDataDrawerFixture = {
  state: "done waiting data",
  sections: drawerSections,
  action: {
    ...baseProblemAction,
    status: "done",
    status_label: "Выполнено",
    result_status: "pending_data",
  },
  resultPage: emptyResultPage,
  expectedRecheckState: "Ждёт свежих данных после перепроверки",
} as const;

export const improvedResultDrawerFixture = {
  state: "improved result",
  sections: drawerSections,
  action: { ...baseProblemAction, status: "done", status_label: "Выполнено" },
  resultPage: improvedResultPage,
  expectedBadge: "Есть улучшение",
} as const;

export const worseResultDrawerFixture = {
  state: "worse result",
  sections: drawerSections,
  action: { ...baseProblemAction, status: "done", status_label: "Выполнено" },
  resultPage: worseResultPage,
  expectedBadge: "Стало хуже",
} as const;

export const readOnlyBetaSignalDrawerFixture = {
  state: "read-only beta signal",
  sections: drawerSections,
  action: {
    ...baseProblemAction,
    id: "beta:stockops:1",
    source_module: "stockops",
    source_kind: "beta",
    title: "Тестовый сигнал по остаткам",
    trust_state: "test_only",
    impact_type: "system_warning",
    can_update: false,
    can_recheck: false,
    can_assign: false,
    can_set_deadline: false,
    is_beta: true,
    is_test_only: true,
    is_read_only: true,
    can_update_reason: "Бета-сигнал доступен только для чтения.",
    allowed_actions: [],
  },
  resultPage: emptyResultPage,
  expectedReadOnlyReason: "Бета-сигнал доступен только для чтения.",
} as const;

export const actionCenterDrawerFixtures = [
  newProblemNoResultDrawerFixture,
  inProgressProblemDrawerFixture,
  doneWaitingDataDrawerFixture,
  improvedResultDrawerFixture,
  worseResultDrawerFixture,
  readOnlyBetaSignalDrawerFixture,
] as const;
