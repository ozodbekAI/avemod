# Experiments Metric Catalog

| Code | Seller label | Formula/source | Grain | Nullable | Notes |
| --- | --- | --- | --- | --- | --- |
| `revenue` | Выручка | sum `mart_sku_daily.final_revenue` | product/day | yes | Primary finance metric. |
| `for_pay` | К перечислению | sum `mart_sku_daily.final_for_pay` | product/day | yes | Finance payout proxy. |
| `estimated_profit` | Оценочная прибыль | sum `mart_sku_daily.net_profit_after_all_expenses` | product/day | yes | Depends on cost coverage. |
| `margin_revenue_percent` | Маржинальность | avg `mart_sku_daily.margin_percent` | product/day | yes | Percent average, not weighted yet. |
| `cogs` | Себестоимость | sum `mart_sku_daily.estimated_cogs` | product/day | yes | Guardrail, lower is better. |
| `wb_expenses` | Расходы WB | sum `mart_sku_daily.total_wb_expenses` | product/day | yes | Guardrail, lower is better. |
| `orders_count` | Заказы | sum `mart_sku_daily.ordered_units` | product/day | yes | Used for sufficiency. |
| `units_sold` | Продано штук | sum `mart_sku_daily.final_sales_qty` | product/day | yes | Sales quantity. |
| `sales_count` | Продажи | sum `mart_sku_daily.sale_rows` | product/day | yes | Row count, not units. |
| `return_count` | Возвраты | sum `mart_sku_daily.final_return_qty` | product/day | yes | Lower is better. |
| `return_rate` | Доля возвратов | returns / sales | product/day | yes | Null when sales are zero. |
| `average_order_value` | Средний чек | revenue / ordered units | product/day | yes | Null when orders are zero. |
| `ads_spend` | Расходы на рекламу | sum `mart_sku_daily.ad_spend` | product/day | yes | Confounder for non-ads experiments. |
| `roas` | ROAS | revenue / ads spend | product/day | yes | Null when spend is zero. |
| `acos` | ACOS | ads spend / revenue | product/day | yes | Lower is better. |
| `clicks` | Клики | sum `mart_sku_daily.ad_clicks` | product/day | yes | Ads support metric. |
| `ctr` | CTR | clicks / ad views | product/day | yes | Null when views are zero. |
| `cpc` | CPC | ads spend / clicks | product/day | yes | Lower is better. |
| `views` | Просмотры | sum `wb_card_funnel_daily.open_count` | product/day | yes | Only when analytics sync has data. |
| `add_to_cart` | Добавления в корзину | sum `wb_card_funnel_daily.cart_count` | product/day | yes | Only when analytics sync has data. |
| `conversion_rate` | Конверсия в заказ | orders / opens | product/day | yes | Null when opens are zero. |
| `in_stock_days` | Дней в наличии | stock quantity > 0 | product/day | yes | From `mart_stock_daily`. |
| `stockout_days` | Дней без остатка | stock quantity <= 0 | product/day | yes | Guardrail and confounder. |
| `average_stock` | Средний остаток | avg `mart_stock_daily.quantity` | product/day | yes | Stock guardrail. |
| `days_of_stock` | Дней запаса | avg `mart_stock_daily.days_of_stock` | product/day | yes | Stock guardrail. |

Unsupported metrics must return explicit `unsupported`/empty states rather than fake values.

