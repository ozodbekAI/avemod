# Grouping Old-To-New Component Map

| Legacy groupingbackend area | Finance mapping | Status |
| --- | --- | --- |
| Product DB model | `wb_product_cards`, `wb_product_card_characteristics`, `wb_product_card_sizes` | Implemented for local runs |
| `article_core` / `article_base_core` | `GroupingBetaService._normalize_article` and `_article_base` | Implemented |
| `imt_id_core` | `scenario=imt_id_validation` bucket key | Implemented |
| Constraints | brand, subject, article family, identity evidence blockers | Implemented safe subset |
| Scoring | deterministic confidence/risk model | Implemented safe subset |
| Recommendations | `grouping_candidates` + `grouping_recommendations` | Implemented |
| Pipeline runs | `grouping_runs` | Implemented |
| Product snapshots | `grouping_product_snapshots` | Implemented |
| Review status | `grouping_review_history` | Implemented |
| Export artifacts | `grouping_export_artifacts` metadata | Modeled, endpoint pending |
| `merge-wb` | no Finance equivalent | Explicitly blocked |

## Finance Source Fields

- `nm_id`: `WBProductCard.nm_id`
- `imt_id`: `WBProductCard.imt_id`
- seller article/vendor code: `WBProductCard.vendor_code`
- title: `WBProductCard.title`
- brand: `WBProductCard.brand`
- subject/category: `WBProductCard.subject_name`
- characteristics/color: `WBProductCardCharacteristic`
- sizes/barcodes: `WBProductCardSize`
- media summary: `WBProductCard.photos`, `WBProductCard.video`

Finance remains the only source of truth for portal grouping.
