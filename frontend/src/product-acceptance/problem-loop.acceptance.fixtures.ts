export const problemLoopAcceptanceScenarios = {
  actionCenterDynamicProblemDrawer: {
    loop: [
      "Проблема",
      "доказательства",
      "действие",
      "статус",
      "повторная проверка",
      "результат",
    ],
    requiredSurface: "Action Center",
    requiredFixtures: ["confirmedLossProblem", "problemImproved"],
    sellerChecks: [
      "проблема отображается",
      "доказательства открываются",
      "статус меняется",
      "виден результат",
      "видно предупреждение о корреляции",
    ],
  },
  productDoctorGroupedIssue: {
    requiredSurface: "Product360",
    requiredTitle: "Проблемы товара",
    requiredGroups: [
      "Прибыльность",
      "Остатки",
      "Цена",
      "Реклама и промо",
      "Блокеры данных",
    ],
    requiredFixtures: ["estimatedOverstockProblem", "problemWithNoAfterData"],
  },
  dataFixLinkedIssue: {
    requiredSurface: "Data Fix",
    requiredFixtures: [
      "missingCostDataFixFixture",
      "unmatchedSkuDataFixFixture",
      "unclassifiedExpenseDataFixFixture",
      "financeReconciliationMismatchDataFixFixture",
    ],
    requiredStates: [
      "Можно исправить внутри платформы",
      "Проверяет система",
      "Нужна синхронизация или сверка",
    ],
  },
  evidenceDrawerSellerMode: {
    requiredButton: "Как посчитано?",
    rawDataMode: "только админ",
    requiredSections: [
      "Короткий вывод",
      "Формула",
      "Какие числа использовали",
      "Откуда взяли данные",
      "Чего не хватает",
      "Почему можно/нельзя действовать",
      "Как перепроверим",
    ],
  },
  estimatedVsConfirmedMoneyStyling: {
    requiredFixtures: [
      "confirmedLossProblem",
      "estimatedOverstockProblem",
      "blockedMissingCostProblem",
      "opportunityCheckerContentProblem",
    ],
    forbiddenSellerClaim: "сэкономленные деньги",
    savedMoneyRequires: ["after_snapshot", "confidence"],
  },
  adminRuleBuilderNoCode: {
    requiredSurface: "Admin Problem Rules",
    requiredTemplate: "Нет себестоимости, прибыль не считается",
    requiredFlow: [
      "сценарий",
      "предпросмотр формулы",
      "тестовый прогон",
      "блокировка публикации без доказательств",
    ],
  },
} as const;
