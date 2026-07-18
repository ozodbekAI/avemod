# Old To New Component Map

| Backend 7 component | Finance component |
| --- | --- |
| `Shop` | `WBAccount` |
| `shop_id` | `account_id` |
| `Feedback` | `ReputationItem(item_type="review")` |
| `Question` | `ReputationItem(item_type="question")` |
| `ChatSession` / `ChatEvent` | Planned `ReputationItem(item_type="chat")` plus source payload |
| `FeedbackDraft` / `QuestionDraft` / `ChatDraft` | `OperatorDraft(source_module="reputation")` |
| old `Job` | `PortalModuleSyncRun(module="reputation")` |
| old `Audit` | `ResultEvent(source_module="reputation")` |
| old shop settings | `ReputationSettings(account_id=...)` |
| legacy WB client | `ReputationService` using Finance decrypted WB content token |
| legacy publish service | Finance portal publish guard plus local WB submit method |

