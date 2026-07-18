from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def main() -> None:
    engine = create_engine(get_settings().sync_database_url)
    metrics = [
        ("raw_wb_api_responses", "select count(*) from raw_wb_api_responses"),
        ("core_sku", "select count(*) from core_sku"),
        ("core_sku_nm", "select count(distinct nm_id) from core_sku where account_id=1 and nm_id is not null"),
        ("wb_product_cards", "select count(*) from wb_product_cards"),
        ("wb_prices", "select count(*) from wb_prices"),
        ("wb_price_sizes", "select count(*) from wb_price_sizes"),
        ("wb_price_snapshots", "select count(*) from wb_price_snapshots"),
        ("wb_price_upload_tasks", "select count(*) from wb_price_upload_tasks"),
        ("wb_price_upload_task_rows", "select count(*) from wb_price_upload_task_rows"),
        ("wb_price_quarantine", "select count(*) from wb_price_quarantine"),
        ("wb_orders", "select count(*) from wb_orders"),
        ("wb_sales", "select count(*) from wb_sales"),
        ("wb_stock_snapshot_rows", "select count(*) from wb_stock_snapshot_rows"),
        ("wb_realization_report_rows", "select count(*) from wb_realization_report_rows"),
        ("wb_supplies", "select count(*) from wb_supplies"),
        ("wb_supply_goods", "select count(*) from wb_supply_goods"),
        ("wb_supply_packages", "select count(*) from wb_supply_packages"),
        ("wb_supply_goods_supplies", "select count(distinct supply_fk_id) from wb_supply_goods"),
        ("wb_supply_packages_supplies", "select count(distinct supply_fk_id) from wb_supply_packages"),
        ("wb_supply_acceptance_options", "select count(*) from wb_supply_acceptance_options"),
        ("wb_ad_campaigns", "select count(*) from wb_ad_campaigns"),
        ("wb_ad_campaign_items", "select count(*) from wb_ad_campaign_items"),
        ("wb_ad_stats_daily", "select count(*) from wb_ad_stats_daily"),
        ("wb_ad_cluster_stats", "select count(*) from wb_ad_cluster_stats"),
        ("wb_card_funnel_daily", "select count(*) from wb_card_funnel_daily"),
        ("wb_region_sales_daily", "select count(*) from wb_region_sales_daily"),
        ("wb_hidden_products", "select count(*) from wb_hidden_products"),
        ("wb_documents", "select count(*) from wb_documents"),
        ("wb_balance_snapshots", "select count(*) from wb_balance_snapshots"),
        ("wb_tariff_commissions", "select count(*) from wb_tariff_commissions"),
        ("manual_cost_uploads", "select count(*) from manual_cost_uploads"),
        ("manual_costs", "select count(*) from manual_costs"),
        ("mart_sku_daily", "select count(*) from mart_sku_daily"),
        ("mart_stock_daily", "select count(*) from mart_stock_daily"),
        ("mart_finance_reconciliation", "select count(*) from mart_finance_reconciliation"),
        ("open_dq", "select count(*) from data_quality_issues where resolved_at is null"),
    ]
    with engine.connect() as conn:
        for name, query in metrics:
            print(f"{name}: {conn.execute(text(query)).scalar()}")
        print("\nsync cursors:")
        rows = conn.execute(
            text(
                "select domain, cursor_key, status, cursor_value "
                "from wb_sync_cursors where account_id=1 order by domain, cursor_key"
            )
        ).fetchall()
        for row in rows:
            print(row)
        print("\nopen dq by code:")
        issue_rows = conn.execute(
            text(
                "select code, count(*) "
                "from data_quality_issues "
                "where resolved_at is null "
                "group by code order by code"
            )
        ).fetchall()
        for row in issue_rows:
            print(row)


if __name__ == "__main__":
    main()
