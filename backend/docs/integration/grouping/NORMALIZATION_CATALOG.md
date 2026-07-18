# Grouping Normalization Catalog

## Text

- Unicode is normalized with NFKC.
- Whitespace is collapsed.
- Empty strings become `null`.
- Matching keys use lowercase normalized brand/subject text.

## Article

- `article_core` is the cleaned upper-case vendor code.
- `article_base_core` strips color suffix when available.
- Regex extracts a model-like prefix such as `AV 100` or `БП 3718-1`.
- Fallback uses the first two article tokens.

## Color

- Color is read only from characteristics named `Цвет`, `color`, or `colors`.
- Missing color stays `null`; it is not fabricated.

## Sizes And Barcodes

- Sizes come from `wb_product_card_sizes`.
- Barcodes are collected from size `skus`.
- Missing sizes/barcodes stay empty lists.

## Source Revision

- Each product snapshot receives a stable SHA-256 over normalized source fields and source payload fragments.
- Grouping run source revision hashes product revisions.
