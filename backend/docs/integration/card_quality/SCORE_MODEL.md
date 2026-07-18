# Card Quality Score Model

The local Card Quality score is deterministic and does not require an LLM.

## Base Formula

```text
score = 100 - min(sum(category_penalties), 100)
```

Each issue has a severity penalty:

| Severity | Penalty |
|---|---:|
| `critical` | 25 |
| `high` | 15 |
| `medium` | 7 |
| `low` | 3 |
| `info` | 0 |

Category caps prevent one family from double-punishing the product:

| Category | Max penalty |
|---|---:|
| `title` | 35 |
| `description` | 30 |
| `characteristics` | 30 |
| `media` | 30 |
| `identity` | 20 |
| `completeness` | 15 |

## Category Scores

```text
category_score = 100 - category_penalty
```

Categories without issues return `100`.

## Status

- `critical`: any critical issue or score below 50.
- `warning`: high/medium/low issue exists or score below 90.
- `clean`: no non-informational issue and score is at least 90.

Informational video absence has zero score penalty and cannot make a clean card warning by itself.
