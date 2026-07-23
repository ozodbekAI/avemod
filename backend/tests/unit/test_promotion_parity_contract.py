from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.core.time import utcnow
from app.models.ab_tests import ABTestCompany, ABTestPhoto
from app.models.accounts import WBAPICategory
from app.services.ab_tests import ABTestContentClient, ABTestService, ABTestWBAdvertClient


class _AdvertBalanceStub:
    def __init__(self, payload):
        self.payload = payload

    async def get_balance(self):
        return self.payload


@pytest.mark.asyncio
async def test_promotion_balance_prefers_balance_field_when_present(monkeypatch):
    service = ABTestService()

    async def _advert_client(session, *, account_id: int):
        return _AdvertBalanceStub({"net": 1500, "balance": 2000, "bonus": 300})

    monkeypatch.setattr(service, "_advert_client", _advert_client)

    result = await service.balance(session=None, account_id=5)

    assert result["balance"] == 2000
    assert result["promo_bonus_rub"] == 300


@pytest.mark.asyncio
async def test_promotion_balance_falls_back_to_net_field(monkeypatch):
    service = ABTestService()

    async def _advert_client(session, *, account_id: int):
        return _AdvertBalanceStub({"net": 1800, "currency": "RUB"})

    monkeypatch.setattr(service, "_advert_client", _advert_client)

    result = await service.balance(session=None, account_id=5)

    assert result["balance"] == 1800
    assert result["promo_bonus_rub"] == 0


def test_wb_clients_use_explicit_token_for_headers():
    advert = ABTestWBAdvertClient(token="promotion-token")
    content = ABTestContentClient(token="content-token")

    assert advert.token == "promotion-token"
    assert content.token == "content-token"
    assert advert.http._token == "promotion-token"
    assert content.http._token == "content-token"


@pytest.mark.asyncio
async def test_ab_service_token_context_uses_account_categories(monkeypatch):
    service = ABTestService()
    calls: list[tuple[int, str]] = []

    async def _token(session, account_id: int, category: str):
        calls.append((account_id, category))
        return f"{category}-token"

    monkeypatch.setattr(service.accounts, "get_decrypted_token", _token)

    advert = await service._advert_client(session=None, account_id=77)
    content = await service._content_client(session=None, account_id=77)

    assert advert.token == "promotion-token"
    assert content.token == "content-token"
    assert calls == [(77, WBAPICategory.PROMOTION.value), (77, WBAPICategory.CONTENT.value)]


def test_preview_url_prefers_stable_local_file_for_generated_assets():
    service = ABTestService()
    company = ABTestCompany(original_media_json={"v": 2})
    photo = ABTestPhoto(
        order=1,
        file_url="/media/assets/generated-1.jpg",
        wb_url="https://basket.example.ru/vol0/part0/1/images/big/1.webp",
    )

    result = service._preview_url_for_photo(company, photo)

    assert result == "/media/assets/generated-1.jpg"


def test_preview_url_uses_backup_snapshot_for_wb_slot(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "media_public_base_url", "https://media.example.com")
    monkeypatch.setattr(settings, "public_base_url", "https://backend.example.com")

    service = ABTestService()
    company = ABTestCompany(
        original_media_json={
            "v": 2,
            "backups": {
                "3": "promotion_media/nm_119401801/c_1_session/backup_slot3.jpg",
            },
        }
    )
    photo = ABTestPhoto(
        order=2,
        file_url="https://basket-01.wbbasket.ru/vol0/part0/119401801/images/big/3.webp",
        wb_url="https://basket-01.wbbasket.ru/vol0/part0/119401801/images/big/1.webp",
    )

    result = service._preview_url_for_photo(company, photo)

    assert result == "https://media.example.com/media/promotion_media/nm_119401801/c_1_session/backup_slot3.jpg"


@pytest.mark.asyncio
async def test_read_photo_bytes_supports_relative_media_path(monkeypatch, tmp_path):
    media_root = tmp_path / "media"
    asset_path = media_root / "assets" / "sample.jpg"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(b"fake-jpg-bytes")
    monkeypatch.setattr(get_settings(), "media_root", str(media_root))

    service = ABTestService()
    content, content_type, filename = await service._read_photo_bytes(SimpleNamespace(get=None), "/media/assets/sample.jpg")

    assert content == b"fake-jpg-bytes"
    assert content_type == "image/jpeg"
    assert filename == "sample.jpg"


@pytest.mark.asyncio
async def test_read_photo_bytes_supports_relative_media_path_without_leading_slash(monkeypatch, tmp_path):
    media_root = tmp_path / "media"
    asset_path = media_root / "assets" / "sample.webp"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(b"fake-webp-bytes")
    monkeypatch.setattr(get_settings(), "media_root", str(media_root))

    service = ABTestService()
    content, content_type, filename = await service._read_photo_bytes(SimpleNamespace(get=None), "media/assets/sample.webp")

    assert content == b"fake-webp-bytes"
    assert content_type == "image/webp"
    assert filename == "sample.webp"


def test_pick_cashback_for_deposit_uses_doc_constraints():
    meta = ABTestService._pick_cashback_for_deposit(
        {"cashbacks": [{"sum": 700, "percent": 30}, {"sum": 200, "percent": 50}]},
        1000,
    )

    assert meta == (300, 30)


@pytest.mark.asyncio
async def test_waiting_balance_returns_clear_insufficient_funds_message(monkeypatch):
    service = ABTestService()
    company = ABTestCompany(
        id=11,
        account_id=7,
        wb_advert_id=36750360,
        nm_id=119401801,
        title="A/B",
        status="created",
        spend_rub=1000,
        cpm=170,
    )
    company.photos = [
        ABTestPhoto(order=1, file_url="/media/a.jpg"),
        ABTestPhoto(order=2, file_url="/media/b.jpg"),
    ]
    service.repo.get_company_any_id = _async_return(company)  # type: ignore[method-assign]

    class _Advert:
        async def set_bid(self, **kwargs):
            return None

        async def get_campaign_budget(self, **kwargs):
            return 0

        async def get_balance(self):
            return {"cashbacks": [{"sum": 300, "percent": 30}]}

        async def deposit_budget(self, **kwargs):
            raise RuntimeError("WB budget deposit error 400: insufficient funds in the account")

        async def start_campaign(self, **kwargs):
            raise RuntimeError("low budget")

    monkeypatch.setattr(service, "_advert_client", _async_return(_Advert()))
    monkeypatch.setattr(service, "_apply_current_photo", _async_noop)
    monkeypatch.setattr(service, "_restore_media", _async_noop)
    monkeypatch.setattr(service, "_wait_for_campaign_budget", _async_return(0))
    session = SimpleNamespace(flush=_async_noop)

    result = await service.start_company(
        session=session,
        account_id=7,
        company_id=11,
        confirm=True,
        auto_deposit=True,
        payment_source="balance",
        use_promo_bonus=True,
    )

    assert result["status"] == "waiting_balance"
    assert "недостаточно средств" in result["error"].lower()
    assert company.status == "created"
    assert company.error_message == result["error"]


@pytest.mark.asyncio
async def test_start_preview_guard_returns_without_wb_write(monkeypatch):
    service = ABTestService()
    company = ABTestCompany(id=11, account_id=7, wb_advert_id=123, nm_id=119401801, title="A/B test", status="created")
    company.photos = [
        ABTestPhoto(order=1, file_url="/media/a.jpg"),
        ABTestPhoto(order=2, file_url="/media/b.jpg"),
    ]
    service.repo.get_company_any_id = _async_return(company)  # type: ignore[method-assign]

    async def _advert_client(*args, **kwargs):
        raise AssertionError("WB advert client must not be created before confirm")

    monkeypatch.setattr(service, "_advert_client", _advert_client)

    result = await service.start_company(session=SimpleNamespace(flush=_async_noop), account_id=7, company_id=11)

    assert result["status"] == "preview_required"
    assert result["requires_confirmation"] is True
    assert result["wb_write_performed"] is False


@pytest.mark.asyncio
async def test_scheduler_success_clears_runtime_error(monkeypatch):
    service = ABTestService()
    photo = ABTestPhoto(order=1, file_url="/media/a.jpg", shows=0, clicks=0)
    company = ABTestCompany(
        id=1,
        account_id=7,
        wb_advert_id=123,
        nm_id=119401801,
        title="A/B",
        status="running",
        error_message="tick error: temporary",
        last_total_shows=0,
        last_total_clicks=0,
        views_per_photo=1000,
        current_photo_order=1,
        photos_count=1,
    )
    company.photos = [photo]

    class _Advert:
        async def fullstats(self, **kwargs):
            return [{"advertId": 123, "views": 260, "clicks": 9}]

    monkeypatch.setattr(service, "_advert_client", _async_return(_Advert()))
    session = SimpleNamespace(flush=_async_noop)

    await service._poll_running_company(session, company)

    assert company.last_total_shows == 260
    assert company.last_total_clicks == 9
    assert company.error_message is None
    assert company.last_polled_at is not None


@pytest.mark.asyncio
async def test_process_due_running_retry_keeps_company_running(monkeypatch):
    service = ABTestService()
    company = ABTestCompany(
        id=1,
        account_id=7,
        wb_advert_id=123,
        nm_id=119401801,
        title="A/B",
        status="running",
        last_polled_at=utcnow() - timedelta(minutes=1),
    )
    service.repo.list_active_for_scheduler = _async_return([company])  # type: ignore[method-assign]

    async def _poll(session, item):
        raise RuntimeError("temporary")

    monkeypatch.setattr(service, "_poll_running_company", _poll)
    session = SimpleNamespace(flush=_async_noop)

    await service.process_due(session)

    assert company.status == "running"
    assert company.error_message == "tick error: temporary"
    assert company.last_polled_at is not None


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner


async def _async_noop(*args, **kwargs):
    return None
