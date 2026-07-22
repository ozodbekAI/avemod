from __future__ import annotations


def load_all_models() -> None:
    from app.models import ab_tests as _ab_tests_models  # noqa: F401
    from app.models import accounts as _accounts_models  # noqa: F401
    from app.models import agent as _agent_models  # noqa: F401
    from app.models import ads as _ads_models  # noqa: F401
    from app.models import analytics as _analytics_models  # noqa: F401
    from app.models import auth as _auth_models  # noqa: F401
    from app.models import card_quality as _card_quality_models  # noqa: F401
    from app.models import claims as _claims_models  # noqa: F401
    from app.models import control_tower as _control_tower_models  # noqa: F401
    from app.models import data_quality as _dq_models  # noqa: F401
    from app.models import documents as _documents_models  # noqa: F401
    from app.models import experiments as _experiments_models  # noqa: F401
    from app.models import finance as _finance_models  # noqa: F401
    from app.models import grouping as _grouping_models  # noqa: F401
    from app.models import logistics as _logistics_models  # noqa: F401
    from app.models import manual_costs as _manual_costs_models  # noqa: F401
    from app.models import marts as _marts_models  # noqa: F401
    from app.models import orders as _orders_models  # noqa: F401
    from app.models import operator as _operator_models  # noqa: F401
    from app.models import photo_studio as _photo_studio_models  # noqa: F401
    from app.models import problem_engine as _problem_engine_models  # noqa: F401
    from app.models import prices as _prices_models  # noqa: F401
    from app.models import product_cards as _product_cards_models  # noqa: F401
    from app.models import promotions as _promotions_models  # noqa: F401
    from app.models import raw as _raw_models  # noqa: F401
    from app.models import reputation as _reputation_models  # noqa: F401
    from app.models import response_snapshots as _response_snapshot_models  # noqa: F401
    from app.models import sales as _sales_models  # noqa: F401
    from app.models import stocks as _stocks_models  # noqa: F401
    from app.models import stock_control as _stock_control_models  # noqa: F401
    from app.models import supplies as _supplies_models  # noqa: F401
    from app.models import sync as _sync_models  # noqa: F401
    from app.models import tariffs as _tariffs_models  # noqa: F401
