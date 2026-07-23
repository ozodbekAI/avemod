from __future__ import annotations

import asyncio
import math
import mimetypes
import os
import re
from pathlib import Path
from datetime import date, timedelta
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.http import WBHTTPClient
from app.core.config import get_settings
from app.core.time import utcnow
from app.models.ab_tests import ABTestCompany, ABTestPhoto
from app.models.accounts import WBAPICategory
from app.models.photo_studio import PhotoAsset
from app.models.product_cards import WBProductCard
from app.repositories.ab_tests import ABTestRepository
from app.services.accounts import AccountService
from app.services.photo_studio import PhotoStorageService


class ABTestWBAdvertClient:
    BASE_URL = "https://advert-api.wildberries.ru"

    def __init__(self, token: str) -> None:
        self.token = token
        self.http = WBHTTPClient(token)

    async def request_json(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> Any:
        return (
            await self.http.request_json(
                method,
                f"{self.BASE_URL}{endpoint}",
                params=params,
                json_body=json_body,
            )
        ).payload

    async def get_balance(self) -> Any:
        return await self.request_json("GET", "/adv/v1/balance")

    async def create_seacat_campaign(self, *, name: str, nm_id: int) -> tuple[int, Any]:
        payload = {
            "name": name[:255],
            "nms": [int(nm_id)],
            "bid_type": "unified",
            "payment_type": "cpm",
        }
        data = await self.request_json(
            "POST", "/adv/v2/seacat/save-ad", json_body=payload
        )
        advert_id = self._extract_advert_id(data)
        if advert_id is None:
            raise HTTPException(
                status_code=502,
                detail=f"WB campaign response did not contain advert id: {data}",
            )
        return advert_id, data

    async def set_bid(self, *, advert_id: int, nm_id: int, cpm_rub: int) -> Any:
        bid_kopecks = int(cpm_rub) * 100
        payload = {
            "bids": [
                {
                    "advert_id": int(advert_id),
                    "nm_bids": [
                        {
                            "nm_id": int(nm_id),
                            "bid_kopecks": int(bid_kopecks),
                            "placement": "combined",
                        }
                    ],
                }
            ]
        }
        try:
            return await self.request_json(
                "PATCH", "/api/advert/v1/bids", json_body=payload
            )
        except Exception:
            payload_no_placement = {
                "bids": [
                    {
                        "advert_id": int(advert_id),
                        "nm_bids": [
                            {"nm_id": int(nm_id), "bid_kopecks": int(bid_kopecks)}
                        ],
                    }
                ]
            }
            try:
                return await self.request_json(
                    "PATCH", "/api/advert/v1/bids", json_body=payload_no_placement
                )
            except Exception:
                fallback = {
                    "bids": [
                        {
                            "advert_id": int(advert_id),
                            "nm_bids": [{"nm": int(nm_id), "bid": int(cpm_rub)}],
                        }
                    ]
                }
                return await self.request_json(
                    "PATCH", "/adv/v0/bids", json_body=fallback
                )

    async def get_min_bids(
        self, *, advert_id: int, nm_id: int, payment_type: str = "cpm"
    ) -> dict[str, Any]:
        base_payloads = [
            {
                "advert_id": int(advert_id),
                "nm_ids": [int(nm_id)],
                "payment_type": payment_type,
                "placement_types": ["combined"],
            },
            {
                "advertId": int(advert_id),
                "nmIds": [int(nm_id)],
                "paymentType": payment_type,
                "placementTypes": ["combined"],
            },
            {
                "AdvertId": int(advert_id),
                "NmIds": [int(nm_id)],
                "PaymentType": payment_type,
                "PlacementTypes": ["combined"],
            },
        ]
        raw: Any = None
        values_in_kopecks = True
        last_error: Exception | None = None
        for payload in base_payloads:
            try:
                raw = await self.request_json(
                    "POST", "/api/advert/v1/bids/min", json_body=payload
                )
                values_in_kopecks = True
                break
            except Exception as exc:
                last_error = exc
        if raw is None:
            try:
                raw = await self.request_json(
                    "POST",
                    "/adv/v0/bids/min",
                    json_body={
                        "advert_id": int(advert_id),
                        "nm_ids": [int(nm_id)],
                        "payment_type": payment_type,
                        "placement_types": ["combined"],
                    },
                )
                values_in_kopecks = False
            except Exception:
                if last_error is not None:
                    raise last_error
                raise
        return self._parse_min_bids(raw, values_in_kopecks=values_in_kopecks)

    async def deposit_budget(
        self,
        *,
        advert_id: int,
        amount_rub: int,
        source_type: int = 0,
        cashback_sum: int | None = None,
        cashback_percent: int | None = None,
    ) -> Any:
        body: dict[str, Any] = {"sum": int(amount_rub), "type": int(source_type)}
        if cashback_sum is not None:
            body["cashback_sum"] = int(cashback_sum)
            if cashback_percent is None:
                raise HTTPException(
                    status_code=400,
                    detail="cashback_percent is required when cashback_sum is provided",
                )
            body["cashback_percent"] = int(cashback_percent)
        return await self.request_json(
            "POST",
            "/adv/v1/budget/deposit",
            params={"id": int(advert_id)},
            json_body=body,
        )

    async def get_campaign_budget(self, *, advert_id: int) -> int:
        data = await self.request_json(
            "GET", "/adv/v1/budget", params={"id": int(advert_id)}
        )
        try:
            return int((data or {}).get("total") or 0)
        except Exception:
            return 0

    async def start_campaign(self, *, advert_id: int) -> Any:
        return await self.request_json(
            "GET", "/adv/v0/start", params={"id": int(advert_id)}
        )

    async def stop_campaign(self, *, advert_id: int) -> Any:
        return await self.request_json(
            "GET", "/adv/v0/stop", params={"id": int(advert_id)}
        )

    async def fullstats(
        self, *, advert_ids: list[int], begin_date: str, end_date: str
    ) -> Any:
        if not advert_ids:
            return []
        return await self.request_json(
            "GET",
            "/adv/v3/fullstats",
            params={
                "ids": ",".join(str(int(item)) for item in advert_ids[:50]),
                "beginDate": begin_date,
                "endDate": end_date,
            },
        )

    @staticmethod
    def _extract_advert_id(data: Any) -> int | None:
        if isinstance(data, int):
            return int(data)
        if isinstance(data, str) and data.isdigit():
            return int(data)
        if isinstance(data, dict):
            for key in ("advertId", "advert_id", "id", "campaignId", "campaign_id"):
                if data.get(key) is not None:
                    return int(data[key])
            result = data.get("result")
            if isinstance(result, dict):
                return ABTestWBAdvertClient._extract_advert_id(result)
        return None

    @staticmethod
    def _parse_min_bids(raw: Any, *, values_in_kopecks: bool) -> dict[str, Any]:
        values: dict[str, int] = {
            "min_combined_rub": 0,
            "min_search_rub": 0,
            "min_recommendation_rub": 0,
        }

        def normalize(value: Any) -> int:
            try:
                amount = float(value or 0)
            except Exception:
                return 0
            if values_in_kopecks:
                return int(math.ceil(amount / 100.0))
            return int(math.ceil(amount))

        def visit(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    visit(item)
                return
            if not isinstance(node, dict):
                return
            placement = str(
                node.get("placement")
                or node.get("placement_type")
                or node.get("placementType")
                or node.get("type")
                or node.get("name")
                or ""
            ).lower()
            amount = (
                node.get("bid")
                or node.get("min_bid")
                or node.get("minBid")
                or node.get("cpm")
                or node.get("value")
                or node.get("price")
            )
            key = None
            if "combined" in placement or placement in {"0", "all", "unified"}:
                key = "min_combined_rub"
            elif "search" in placement:
                key = "min_search_rub"
            elif "recommend" in placement:
                key = "min_recommendation_rub"
            if key and amount is not None:
                values[key] = max(values[key], normalize(amount))
            for nested_key in ("bids", "data", "result", "items"):
                if nested_key in node:
                    visit(node[nested_key])

        visit(raw)
        return {**values, "raw": raw}


class ABTestContentClient:
    BASE_URL = "https://content-api.wildberries.ru"

    def __init__(self, token: str) -> None:
        self.token = token
        self.http = WBHTTPClient(token)

    async def request_json(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> Any:
        return (
            await self.http.request_json(
                method,
                f"{self.BASE_URL}{endpoint}",
                params=params,
                json_body=json_body,
            )
        ).payload

    async def get_card_photo_urls(self, *, nm_id: int) -> list[str]:
        body = {
            "settings": {
                "sort": {"ascending": False},
                "cursor": {"limit": 20},
                "filter": {"withPhoto": -1, "textSearch": str(int(nm_id))},
            }
        }
        data = await self.request_json(
            "POST", "/content/v2/get/cards/list", json_body=body
        )
        for card in data.get("cards") or []:
            if int(card.get("nmID") or 0) != int(nm_id):
                continue
            return self._extract_photo_urls(card.get("photos"))
        return []

    async def upload_media_file(
        self,
        *,
        nm_id: int,
        photo_number: int,
        content: bytes,
        filename: str,
        content_type: str,
    ) -> Any:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.BASE_URL}/content/v3/media/file",
                headers={
                    "Authorization": self.token,
                    "Accept": "application/json",
                    "X-Nm-Id": str(int(nm_id)),
                    "X-Photo-Number": str(int(photo_number)),
                },
                files={
                    "uploadfile": (
                        filename,
                        content,
                        content_type or "application/octet-stream",
                    )
                },
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=502, detail=f"WB media upload failed: {response.text[:500]}"
            )
        try:
            payload = response.json() if response.text else {}
        except Exception:
            payload = {}
        if isinstance(payload, dict) and payload.get("error"):
            raise HTTPException(
                status_code=502,
                detail=payload.get("errorText") or "WB media upload failed",
            )
        return payload

    async def save_media_state(self, *, nm_id: int, photos: list[str]) -> Any:
        return await self.request_json(
            "POST",
            "/content/v3/media/save",
            json_body={
                "nmId": int(nm_id),
                "data": [str(item) for item in photos if str(item).strip()],
            },
        )

    @staticmethod
    def _extract_photo_urls(value: Any) -> list[str]:
        out: list[str] = []
        for item in value or []:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                for key in ("big", "url", "full", "c516x688", "c246x328"):
                    if item.get(key):
                        out.append(str(item[key]))
                        break
        return out


class ABTestService:
    STATUS_MAP = {
        "running": {"running"},
        "pending": {"created"},
        "finished": {"finished"},
        "failed": {"failed", "stopped"},
    }
    MIN_VARIANTS = 2
    MIN_IMPRESSIONS = 300
    MIN_CTR_DELTA = 0.35
    MIN_SCORE_DELTA = 0.06

    def __init__(self) -> None:
        self.accounts = AccountService()
        self.repo = ABTestRepository()
        self.storage = PhotoStorageService()

    async def balance(
        self, session: AsyncSession, *, account_id: int
    ) -> dict[str, Any]:
        advert = await self._advert_client(session, account_id=account_id)
        raw = await advert.get_balance()
        if isinstance(raw, dict):
            available_balance = raw.get("balance")
            if available_balance is None:
                available_balance = raw.get("net")
            return {
                "balance": int(available_balance or 0),
                "promo_bonus_rub": int(
                    raw.get("bonus") or raw.get("promo_bonus_rub") or 0
                ),
                "raw": raw,
            }
        return {"balance": int(raw or 0), "promo_bonus_rub": 0, "raw": raw}

    async def list_companies(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        status: str,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        statuses = self.STATUS_MAP.get(status)
        if statuses is None:
            raise HTTPException(status_code=404, detail="Unknown A/B test status")
        rows, total = await self.repo.list_by_status(
            session,
            account_id=account_id,
            statuses=statuses,
            limit=limit,
            offset=offset,
        )
        return {
            "items": [self.serialize_company(row) for row in rows],
            "pagination": {
                "page": (offset // limit) + 1 if limit else 1,
                "page_size": limit,
                "total": total,
                "total_pages": math.ceil(total / limit) if limit else 1,
            },
        }

    async def create_company(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        user_id: int | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        photos = self._normalize_photos(
            payload.get("photos") or [], main_photo_url=payload.get("main_photo_url")
        )
        product_card = await self._resolve_product_card(
            session,
            account_id=account_id,
            nm_id=int(payload["nm_id"]),
            product_card_id=payload.get("product_card_id") or payload.get("card_id"),
        )
        if not self._payload_confirmed(payload):
            return self._write_preview_response(
                action="create_company",
                account_id=account_id,
                payload=payload,
                photos=photos,
                product_card_id=int(product_card.id)
                if product_card is not None
                else None,
            )
        advert = await self._advert_client(session, account_id=account_id)
        wb_advert_id, wb_response = await advert.create_seacat_campaign(
            name=str(payload.get("title") or f"A/B {payload['nm_id']}"),
            nm_id=int(payload["nm_id"]),
        )
        min_bids = await advert.get_min_bids(
            advert_id=int(wb_advert_id), nm_id=int(payload["nm_id"])
        )
        min_cpm = self._min_cpm_from_bids(min_bids)
        company = ABTestCompany(
            account_id=int(account_id),
            created_by_user_id=user_id,
            wb_advert_id=int(wb_advert_id),
            nm_id=int(payload["nm_id"]),
            product_card_id=int(product_card.id) if product_card is not None else None,
            title=str(payload.get("title") or f"A/B {payload['nm_id']}"),
            status="created",
            from_main=bool(payload.get("from_main")),
            max_slots=int(payload.get("max_slots") or 5),
            keep_winner_as_main=bool(payload.get("keep_winner_as_main", True)),
            delete_test_photos=bool(payload.get("delete_test_photos", True)),
            photos_count=len(photos),
        )
        session.add(company)
        await session.flush()
        await self.repo.replace_photos(session, company, photos)
        await session.refresh(company, attribute_names=["photos"])
        return {
            "id_company": int(company.id),
            "local_company_id": int(company.id),
            "company_id": int(wb_advert_id),
            "wb_company_id": int(wb_advert_id),
            "wb_advert_id": int(wb_advert_id),
            "wb_save_ad_response": wb_response,
            "wb_min_bids_response": min_bids.get("raw"),
            "min_bids": {
                "min_combined_rub": int(min_bids.get("min_combined_rub") or 0),
                "min_search_rub": int(min_bids.get("min_search_rub") or 0),
                "min_recommendation_rub": int(
                    min_bids.get("min_recommendation_rub") or 0
                ),
            },
            "min_cpm": int(min_cpm),
            "status": company.status,
        }

    async def update_company_and_start(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        company_id = int(payload.get("id_company") or payload.get("company_id") or 0)
        company = await self.repo.get_company_any_id(
            session, account_id=account_id, company_id=company_id
        )
        if company is None:
            raise HTTPException(status_code=404, detail="A/B test company not found")
        photos = self._normalize_photos(payload.get("photos") or [])
        if not self._payload_confirmed(payload):
            return self._write_preview_response(
                action="update_and_start",
                account_id=account_id,
                payload=payload,
                photos=photos,
                company=company,
                product_card_id=int(company.product_card_id)
                if company.product_card_id
                else None,
            )
        if photos:
            await self.repo.replace_photos(session, company, photos)
        company.title = str(payload.get("title") or company.title)
        company.from_main = bool(payload.get("from_main"))
        company.max_slots = int(payload.get("max_slots") or company.max_slots or 5)
        company.keep_winner_as_main = bool(payload.get("keep_winner_as_main", True))
        company.delete_test_photos = bool(payload.get("delete_test_photos", True))
        company.views_per_photo = int(payload.get("views_per_photo") or 0)
        if company.views_per_photo < 1000:
            raise HTTPException(
                status_code=400, detail="views_per_photo must be at least 1000"
            )
        requested_cpm = int(payload.get("cpm") or 0)
        if requested_cpm <= 0:
            raise HTTPException(status_code=400, detail="cpm must be positive")
        advert = await self._advert_client(session, account_id=account_id)
        min_bids = await advert.get_min_bids(
            advert_id=int(company.wb_advert_id), nm_id=int(company.nm_id)
        )
        min_cpm = self._min_cpm_from_bids(min_bids)
        company.cpm = max(requested_cpm, min_cpm)
        company.photos_count = len(photos or company.photos or [])
        company.spend_rub = self._calc_spend_rub(
            photos_count=int(company.photos_count or len(company.photos or [])),
            views_per_photo=int(company.views_per_photo),
            cpm_rub=int(company.cpm),
        )
        await session.flush()
        result = await self.start_company(
            session,
            account_id=account_id,
            company_id=int(company.id),
            confirm=True,
            auto_deposit=bool(payload.get("auto_deposit", True)),
            deposit_rub=payload.get("deposit_rub"),
            payment_source=payload.get("payment_source"),
            use_promo_bonus=bool(payload.get("use_promo_bonus", False)),
        )
        return {
            **result,
            "id_company": int(company.id),
            "local_company_id": int(company.id),
            "company_id": int(company.wb_advert_id) if company.wb_advert_id else None,
            "wb_company_id": int(company.wb_advert_id)
            if company.wb_advert_id
            else None,
            "wb_advert_id": int(company.wb_advert_id) if company.wb_advert_id else None,
            "nm_id": int(company.nm_id),
            "card_id": int(company.product_card_id)
            if company.product_card_id
            else None,
            "product_card_id": int(company.product_card_id)
            if company.product_card_id
            else None,
            "title": company.title,
            "cpm": int(company.cpm),
            "min_cpm": int(min_cpm),
            "views_per_photo": int(company.views_per_photo),
            "photos_count": int(company.photos_count),
            "spend_rub": int(company.spend_rub),
            "estimated_spend_rub": int(company.spend_rub),
        }

    async def start_company(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        company_id: int,
        confirm: bool = False,
        auto_deposit: bool = True,
        deposit_rub: int | None = None,
        payment_source: str | None = None,
        use_promo_bonus: bool = False,
    ) -> dict[str, Any]:
        company = await self.repo.get_company_any_id(
            session, account_id=account_id, company_id=company_id
        )
        if company is None:
            raise HTTPException(status_code=404, detail="A/B test company not found")
        if not confirm:
            return self._write_preview_response(
                action="start_company",
                account_id=account_id,
                payload={"company_id": company_id},
                photos=[
                    {
                        "order": int(photo.order),
                        "file_url": photo.file_url,
                        "preview_url": photo.preview_url,
                    }
                    for photo in sorted(
                        company.photos or [], key=lambda item: int(item.order or 0)
                    )
                ],
                company=company,
                product_card_id=int(company.product_card_id)
                if company.product_card_id
                else None,
            )
        if len(company.photos or []) < 2:
            raise HTTPException(
                status_code=400, detail="At least two photo variants are required"
            )
        if not company.wb_advert_id:
            advert = await self._advert_client(session, account_id=account_id)
            company.wb_advert_id, _ = await advert.create_seacat_campaign(
                name=company.title, nm_id=company.nm_id
            )
            await session.flush()
        advert = await self._advert_client(session, account_id=account_id)
        advert_id = int(company.wb_advert_id)
        spend_total = max(int(company.spend_rub or 0), 0)
        deposit_amount = 0
        current_budget = 0
        deposit_error = ""

        await self._apply_current_photo(session, company)
        if company.cpm > 0:
            await advert.set_bid(
                advert_id=advert_id, nm_id=int(company.nm_id), cpm_rub=int(company.cpm)
            )

        if spend_total > 0:
            try:
                current_budget = await advert.get_campaign_budget(advert_id=advert_id)
            except Exception:
                current_budget = 0

            if current_budget < spend_total and auto_deposit:
                deposit_amount = int(deposit_rub or (spend_total - current_budget))
                wb_balance: dict[str, Any] = {}
                try:
                    raw_balance = await advert.get_balance()
                    wb_balance = raw_balance if isinstance(raw_balance, dict) else {}
                except Exception:
                    wb_balance = {}

                cashback_sum = None
                cashback_percent = None
                cashback = (
                    self._pick_cashback_for_deposit(wb_balance, deposit_amount)
                    if use_promo_bonus
                    else None
                )
                if cashback is not None:
                    cashback_sum, cashback_percent = cashback

                required_source_amount = max(
                    int(deposit_amount) - int(cashback_sum or 0), 0
                )
                source_type = self._resolve_deposit_source_type(
                    payment_source, wb_balance, required_source_amount
                )
                try:
                    await advert.deposit_budget(
                        advert_id=advert_id,
                        amount_rub=deposit_amount,
                        source_type=source_type,
                        cashback_sum=cashback_sum,
                        cashback_percent=cashback_percent,
                    )
                except Exception as exc:
                    deposit_error = str(exc)
                    if self._is_insufficient_funds_error(deposit_error):
                        fallback = self._fallback_deposit_source_type(
                            source_type, wb_balance, required_source_amount
                        )
                        if fallback is not None:
                            try:
                                await advert.deposit_budget(
                                    advert_id=advert_id,
                                    amount_rub=deposit_amount,
                                    source_type=fallback,
                                    cashback_sum=cashback_sum,
                                    cashback_percent=cashback_percent,
                                )
                                deposit_error = ""
                            except Exception as retry_exc:
                                deposit_error = str(retry_exc)

            current_budget = await self._wait_for_campaign_budget(
                advert,
                advert_id=advert_id,
                required_budget=spend_total,
                timeout_sec=90 if deposit_amount > 0 else 30,
            )

        last_error = ""
        retryable = False
        for attempt in range(4):
            try:
                await advert.start_campaign(advert_id=advert_id)
                begin = date.today().isoformat()
                end = (date.today() + timedelta(days=1)).isoformat()
                stats = await advert.fullstats(
                    advert_ids=[advert_id], begin_date=begin, end_date=end
                )
                shows, clicks = self.parse_stats_totals(stats, advert_id=advert_id)
                company.last_total_shows = int(shows)
                company.last_total_clicks = int(clicks)
                company.status = "running"
                company.error_message = None
                company.started_at = company.started_at or utcnow()
                company.finished_at = None
                await session.flush()
                return {
                    "status": "running",
                    "started": True,
                    "id_company": int(company.id),
                    "company_id": advert_id,
                    "deposit_amount": int(deposit_amount),
                    "campaign_budget": int(current_budget),
                }
            except Exception as exc:
                last_error = str(exc)
                retryable = self._is_retryable_start_error(last_error)
                if not retryable or attempt >= 3:
                    break
                current_budget = await self._wait_for_campaign_budget(
                    advert,
                    advert_id=advert_id,
                    required_budget=spend_total,
                    timeout_sec=25,
                )

        await self._restore_media(session, company)
        if retryable:
            if self._is_insufficient_funds_error(deposit_error):
                wait_error = (
                    "На счёте кабинета продвижения WB недостаточно средств для пополнения бюджета кампании. "
                    "Тест оставлен в ожидании: после пополнения система попробует запустить его автоматически."
                )
            else:
                wait_error = (
                    "WB еще не видит пополнение бюджета кампании. Мы оставили тест в ожидании и попробуем запустить его автоматически."
                    if spend_total > 0
                    else last_error
                )
            company.status = "created"
            company.error_message = wait_error
            company.last_polled_at = utcnow() + timedelta(seconds=60)
            await session.flush()
            return {
                "status": "waiting_balance",
                "started": False,
                "error": wait_error,
                "deposit_amount": int(deposit_amount),
                "campaign_budget": int(current_budget),
            }
        company.status = "failed"
        company.error_message = last_error
        company.last_polled_at = utcnow()
        await session.flush()
        return {
            "status": "failed",
            "started": False,
            "error": last_error,
            "deposit_amount": int(deposit_amount),
            "campaign_budget": int(current_budget),
        }

    async def stop_company(
        self, session: AsyncSession, *, account_id: int, company_id: int
    ) -> dict[str, Any]:
        company = await self.repo.get_company_any_id(
            session, account_id=account_id, company_id=company_id
        )
        if company is None:
            raise HTTPException(status_code=404, detail="A/B test company not found")
        return await self.stop_company_confirmed(
            session, account_id=account_id, company_id=company_id, confirm=False
        )

    async def stop_company_confirmed(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        company_id: int,
        confirm: bool,
    ) -> dict[str, Any]:
        company = await self.repo.get_company_any_id(
            session, account_id=account_id, company_id=company_id
        )
        if company is None:
            raise HTTPException(status_code=404, detail="A/B test company not found")
        if not confirm:
            return self._write_preview_response(
                action="stop_company",
                account_id=account_id,
                payload={"company_id": company_id},
                photos=[
                    {
                        "order": int(photo.order),
                        "file_url": photo.file_url,
                        "preview_url": photo.preview_url,
                    }
                    for photo in sorted(
                        company.photos or [], key=lambda item: int(item.order or 0)
                    )
                ],
                company=company,
                product_card_id=int(company.product_card_id)
                if company.product_card_id
                else None,
            )
        advert = await self._advert_client(session, account_id=account_id)
        stop_error = None
        if company.wb_advert_id:
            try:
                await advert.stop_campaign(advert_id=int(company.wb_advert_id))
            except Exception as exc:
                stop_error = str(exc)
        try:
            await self._restore_media(session, company)
        except Exception as exc:
            stop_error = (
                f"{stop_error}; restore failed: {exc}"
                if stop_error
                else f"restore failed: {exc}"
            )
        company.status = "stopped"
        company.finished_at = utcnow()
        company.error_message = stop_error
        await session.flush()
        return {"status": "stopped", "stopped": True, "error": stop_error}

    async def company_stats(
        self, session: AsyncSession, *, account_id: int, company_id: int
    ) -> dict[str, Any]:
        company = await self.repo.get_company_any_id(
            session, account_id=account_id, company_id=company_id
        )
        if company is None:
            raise HTTPException(status_code=404, detail="A/B test company not found")
        return self.serialize_company(company)

    async def product_block(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        limit: int = 5,
    ) -> dict[str, Any]:
        rows = list(
            (
                await session.execute(
                    select(ABTestCompany)
                    .options(selectinload(ABTestCompany.photos))
                    .where(
                        ABTestCompany.account_id == int(account_id),
                        ABTestCompany.nm_id == int(nm_id),
                    )
                    .order_by(ABTestCompany.updated_at.desc(), ABTestCompany.id.desc())
                    .limit(max(1, min(int(limit or 5), 20)))
                )
            ).scalars()
        )
        items = [self.serialize_company(row) for row in rows]
        active_statuses = {"created", "running"}
        finished_statuses = {"finished", "stopped"}
        failed_statuses = {"failed"}
        active = [
            item
            for item in items
            if str(item.get("status") or "").lower() in active_statuses
        ]
        finished = [
            item
            for item in items
            if str(item.get("status") or "").lower() in finished_statuses
        ]
        failed = [
            item
            for item in items
            if str(item.get("status") or "").lower() in failed_statuses
        ]
        latest_finished = next(
            (
                item
                for item in items
                if item.get("winner_decision") or item.get("winner_photo_order")
            ),
            None,
        )
        status = "empty"
        if active:
            status = "running"
        elif failed:
            status = "warning"
        elif items:
            status = "ok"
        latest_result = None
        if latest_finished:
            latest_result = {
                "outcome": latest_finished.get("winner_decision") or "finished",
                "confidence": "medium"
                if latest_finished.get("winner_photo_order")
                else "low",
                "seller_summary": self._photo_test_summary(latest_finished),
                "evaluated_at": latest_finished.get("finished_at"),
            }
        next_evaluation_at = next(
            (
                item.get("started_at")
                for item in active
                if str(item.get("status") or "").lower() == "running"
            ),
            None,
        )
        return {
            "status": status,
            "items": items,
            "running": active,
            "latest_result": latest_result,
            "next_evaluation_at": next_evaluation_at,
            "summary": {
                "active_count": len(active),
                "running_count": sum(
                    1
                    for item in active
                    if str(item.get("status") or "").lower() == "running"
                ),
                "planned_count": sum(
                    1
                    for item in active
                    if str(item.get("status") or "").lower() == "created"
                ),
                "pending_count": sum(
                    1
                    for item in active
                    if str(item.get("status") or "").lower() == "created"
                ),
                "finished_count": len(finished),
                "completed_count": len(finished),
                "failed_count": len(failed),
                "total_count": len(items),
            },
            "source": "photo_ab_tests",
        }

    async def process_due(self, session: AsyncSession, *, limit: int = 100) -> None:
        companies = await self.repo.list_active_for_scheduler(session, limit=limit)
        if not companies:
            return
        for company in companies:
            if company.status == "created" and self._can_autostart(company):
                try:
                    await self.start_company(
                        session,
                        account_id=int(company.account_id),
                        company_id=int(company.id),
                        confirm=True,
                    )
                except Exception as exc:
                    company.error_message = f"autostart failed: {exc}"
                    company.last_polled_at = utcnow() + timedelta(minutes=2)
                continue
            if company.status != "running" or not company.wb_advert_id:
                continue
            if company.last_polled_at and company.last_polled_at > utcnow():
                continue
            try:
                await self._poll_running_company(session, company)
            except Exception as exc:
                company.status = "running"
                company.error_message = f"tick error: {exc}"
                company.last_polled_at = utcnow() + timedelta(seconds=45)
                await session.flush()

    @staticmethod
    def _photo_test_summary(item: dict[str, Any]) -> str:
        winner = item.get("winner_photo_order")
        decision = str(item.get("winner_decision") or "").strip()
        if winner:
            return f"Лучший вариант главного фото: #{winner}. Решение: {decision or 'winner_found'}."
        if decision == "no_clear_winner":
            return "Тест завершён, но явного победителя по CTR нет."
        if decision == "insufficient_data":
            return "Тест завершён без достаточного объёма данных."
        return "Фото-тест завершён."

    async def _poll_running_company(
        self, session: AsyncSession, company: ABTestCompany
    ) -> None:
        advert = await self._advert_client(session, account_id=int(company.account_id))
        begin = date.today().isoformat()
        end = (date.today() + timedelta(days=1)).isoformat()
        stats = await advert.fullstats(
            advert_ids=[int(company.wb_advert_id)], begin_date=begin, end_date=end
        )
        shows, clicks = self.parse_stats_totals(
            stats, advert_id=int(company.wb_advert_id)
        )
        delta_shows = max(shows - int(company.last_total_shows or 0), 0)
        delta_clicks = max(clicks - int(company.last_total_clicks or 0), 0)
        current = self._current_photo(company)
        if current is not None and (delta_shows or delta_clicks):
            current.shows += delta_shows
            current.clicks += delta_clicks
            current.ctr = (
                round((current.clicks / current.shows) * 100.0, 4)
                if current.shows
                else 0.0
            )
        company.last_total_shows = shows
        company.last_total_clicks = clicks
        company.last_polled_at = utcnow()
        company.error_message = None
        threshold = int(company.views_per_photo or 0)
        if current is None or threshold <= 0 or int(current.shows or 0) < threshold:
            await session.flush()
            return
        if int(company.current_photo_order or 1) < int(
            company.photos_count or len(company.photos or [])
        ):
            company.current_photo_order = int(company.current_photo_order or 1) + 1
            await self._apply_current_photo(session, company)
        else:
            await self.finalize_winner(session, company)
        await session.flush()

    async def finalize_winner(
        self, session: AsyncSession, company: ABTestCompany
    ) -> int | None:
        photos = sorted(company.photos or [], key=lambda item: int(item.order or 0))
        winner, reason = self._pick_winner(photos)
        advert = await self._advert_client(session, account_id=int(company.account_id))
        if company.wb_advert_id:
            try:
                await advert.stop_campaign(advert_id=int(company.wb_advert_id))
            except Exception:
                pass
        if winner is None:
            company.status = "finished"
            company.winner_photo_order = None
            company.error_message = reason
            company.finished_at = utcnow()
            await self._restore_media(session, company)
            return None
        for photo in photos:
            photo.is_winner = int(photo.order) == int(winner.order)
        company.winner_photo_order = int(winner.order)
        company.status = "finished"
        company.error_message = None
        company.finished_at = utcnow()
        if company.keep_winner_as_main:
            company.current_photo_order = int(winner.order)
            await self._apply_current_photo(session, company)
        else:
            await self._restore_media(session, company)
        return int(winner.order)

    def serialize_company(self, company: ABTestCompany) -> dict[str, Any]:
        scores = self._variant_scores(company.photos or [])
        photos = []
        for photo in sorted(
            company.photos or [], key=lambda item: int(item.order or 0)
        ):
            score = scores.get(int(photo.order)) or {}
            photos.append(
                {
                    "order": int(photo.order),
                    "file_url": photo.file_url,
                    "wb_url": photo.wb_url,
                    "preview_url": self._preview_url_for_photo(company, photo),
                    "shows": int(photo.shows or 0),
                    "clicks": int(photo.clicks or 0),
                    "ctr": float(photo.ctr or 0.0),
                    "is_winner": bool(photo.is_winner),
                    "winner_score": score.get("score"),
                    "winner_score_confidence": score.get("confidence"),
                    "winner_score_conversion_source": score.get("conversion_source"),
                    "winner_score_reason": score.get("reason"),
                }
            )
        return {
            "id_company": int(company.id),
            "company_id": int(company.id),
            "wb_advert_id": int(company.wb_advert_id) if company.wb_advert_id else None,
            "account_id": int(company.account_id),
            "nm_id": int(company.nm_id),
            "product_card_id": int(company.product_card_id)
            if company.product_card_id
            else None,
            "card_id": int(company.product_card_id)
            if company.product_card_id
            else None,
            "title": company.title,
            "status": company.status,
            "spend_rub": int(company.spend_rub or 0),
            "estimated_spend_rub": int(company.spend_rub or 0),
            "winner_decision": self._winner_decision(company),
            "views_per_photo": int(company.views_per_photo or 0),
            "photos_count": int(company.photos_count or len(company.photos or [])),
            "current_photo_order": int(company.current_photo_order or 1),
            "winner_photo_order": company.winner_photo_order,
            "last_error": company.error_message,
            "can_start": company.status in {"created", "failed", "stopped"},
            "can_stop": company.status == "running",
            "started_at": company.started_at,
            "finished_at": company.finished_at,
            "photos": photos,
        }

    async def _advert_client(
        self, session: AsyncSession, *, account_id: int
    ) -> ABTestWBAdvertClient:
        token = await self.accounts.get_decrypted_token(
            session, account_id, WBAPICategory.PROMOTION.value
        )
        return ABTestWBAdvertClient(token)

    async def _content_client(
        self, session: AsyncSession, *, account_id: int
    ) -> ABTestContentClient:
        token = await self.accounts.get_decrypted_token(
            session, account_id, WBAPICategory.CONTENT.value
        )
        return ABTestContentClient(token)

    async def _resolve_product_card(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        product_card_id: int | None,
    ) -> WBProductCard | None:
        if product_card_id:
            row = await session.get(WBProductCard, int(product_card_id))
            if (
                row
                and int(row.account_id) == int(account_id)
                and int(row.nm_id) == int(nm_id)
            ):
                return row
            if row and int(row.account_id) == int(account_id):
                raise HTTPException(
                    status_code=400, detail="product_card_id/nm_id mismatch"
                )
        return (
            await session.execute(
                select(WBProductCard).where(
                    WBProductCard.account_id == int(account_id),
                    WBProductCard.nm_id == int(nm_id),
                )
            )
        ).scalar_one_or_none()

    async def _apply_current_photo(
        self, session: AsyncSession, company: ABTestCompany
    ) -> None:
        current = self._current_photo(company)
        if current is None:
            raise HTTPException(status_code=400, detail="Current A/B photo not found")
        content = await self._content_client(
            session, account_id=int(company.account_id)
        )
        original = await content.get_card_photo_urls(nm_id=int(company.nm_id))
        state = dict(company.original_media_json or {})
        if not state.get("original_urls"):
            state["original_urls"] = original
        if self._same_media_url(current.file_url, original[0] if original else None):
            company.original_media_json = state
            company.current_uploaded_wb_url = None
            current.wb_url = current.file_url
            await self._update_local_card_photos(session, company, original)
            return
        payload, content_type, filename = await self._read_photo_bytes(
            session, current.file_url
        )
        await content.upload_media_file(
            nm_id=int(company.nm_id),
            photo_number=1,
            content=payload,
            filename=filename,
            content_type=content_type,
        )
        company.original_media_json = state
        company.current_uploaded_wb_url = current.file_url
        current.wb_url = current.file_url
        await self._update_local_card_main(session, company, current.file_url, original)

    async def _restore_media(
        self, session: AsyncSession, company: ABTestCompany
    ) -> None:
        state = company.original_media_json or {}
        original = [
            str(item) for item in state.get("original_urls") or [] if str(item).strip()
        ]
        if not original:
            return
        content = await self._content_client(
            session, account_id=int(company.account_id)
        )
        await content.save_media_state(nm_id=int(company.nm_id), photos=original)
        await self._update_local_card_photos(session, company, original)
        company.current_uploaded_wb_url = None

    async def _update_local_card_main(
        self,
        session: AsyncSession,
        company: ABTestCompany,
        main_url: str,
        original: list[str],
    ) -> None:
        photos = [main_url]
        for item in original:
            if item and item not in photos:
                photos.append(item)
        await self._update_local_card_photos(session, company, photos)

    async def _update_local_card_photos(
        self, session: AsyncSession, company: ABTestCompany, photos: list[str]
    ) -> None:
        row = None
        if company.product_card_id:
            row = await session.get(WBProductCard, int(company.product_card_id))
        if row is None:
            row = (
                await session.execute(
                    select(WBProductCard).where(
                        WBProductCard.account_id == int(company.account_id),
                        WBProductCard.nm_id == int(company.nm_id),
                    )
                )
            ).scalar_one_or_none()
        if row is not None:
            row.photos = [str(item) for item in photos if str(item).strip()]

    async def _read_photo_bytes(
        self, session: AsyncSession, url: str
    ) -> tuple[bytes, str, str]:
        raw = str(url or "").strip()
        asset_id = self._asset_id_from_url(raw)
        if asset_id is not None:
            asset = await session.get(PhotoAsset, int(asset_id))
            if asset and asset.storage_key:
                path = self.storage.path_for_key(asset.storage_key)
                return (
                    path.read_bytes(),
                    asset.mime_type or "image/png",
                    asset.original_file_name or f"asset_{asset.id}.png",
                )
        local_candidate = self._resolve_local_media_candidate(raw)
        if local_candidate is not None:
            if not local_candidate.exists() or not local_candidate.is_file():
                raise HTTPException(
                    status_code=400,
                    detail="Cannot download photo variant: local file not found",
                )
            return (
                local_candidate.read_bytes(),
                self._guess_content_type_from_path(local_candidate),
                local_candidate.name,
            )
        if raw.startswith("/"):
            raw = f"http://127.0.0.1:8000{raw}"
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            response = await client.get(raw)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot download photo variant: {response.status_code}",
            )
        content_type = response.headers.get("content-type", "image/png").split(";")[0]
        filename = os.path.basename(urlparse(raw).path) or "variant.png"
        return response.content, content_type, filename

    @staticmethod
    def _payload_confirmed(payload: dict[str, Any]) -> bool:
        return bool(
            payload.get("confirm")
            or payload.get("confirmed")
            or payload.get("preview_confirmed")
            or payload.get("apply_confirmed")
        )

    def _write_preview_response(
        self,
        *,
        action: str,
        account_id: int,
        payload: dict[str, Any],
        photos: list[dict[str, Any]],
        company: ABTestCompany | None = None,
        product_card_id: int | None = None,
    ) -> dict[str, Any]:
        nm_id = int(payload.get("nm_id") or getattr(company, "nm_id", 0) or 0)
        current = (
            [
                photo.file_url
                for photo in sorted(
                    company.photos or [], key=lambda item: int(item.order or 0)
                )
            ]
            if company
            else []
        )
        proposed = [
            str(item.get("file_url") or "").strip()
            for item in photos
            if str(item.get("file_url") or "").strip()
        ]
        return {
            "status": "preview_required",
            "requires_confirmation": True,
            "wb_write_performed": False,
            "action": action,
            "account_id": int(account_id),
            "id_company": int(company.id)
            if company is not None and company.id
            else None,
            "company_id": int(company.id)
            if company is not None and company.id
            else None,
            "wb_advert_id": int(company.wb_advert_id)
            if company is not None and company.wb_advert_id
            else None,
            "nm_id": nm_id,
            "product_card_id": product_card_id,
            "card_id": product_card_id,
            "title": str(
                payload.get("title") or getattr(company, "title", "") or f"A/B {nm_id}"
            ),
            "photos_count": len(proposed),
            "photos": [
                {
                    "order": int(item.get("order") or idx),
                    "file_url": str(item.get("file_url") or ""),
                    "preview_url": str(
                        item.get("preview_url") or item.get("file_url") or ""
                    ),
                }
                for idx, item in enumerate(photos, start=1)
            ],
            "diff": {
                "current_media": current,
                "proposed_media": proposed,
                "will_create_or_update_wb_campaign": action
                in {"create_company", "update_and_start", "start_company"},
                "will_start_or_stop_campaign": action
                in {"update_and_start", "start_company", "stop_company"},
                "will_upload_or_restore_media": action
                in {"update_and_start", "start_company", "stop_company"},
            },
            "confirm_fields": ["confirm=true"],
        }

    @staticmethod
    def _asset_id_from_url(url: str) -> int | None:
        match = re.search(r"/photo/assets/(\d+)/download", url)
        if match:
            return int(match.group(1))
        match = re.search(r"/portal/photo/assets/(\d+)/download", url)
        if match:
            return int(match.group(1))
        qs = parse_qs(urlparse(url).query)
        for key in ("asset_id", "id"):
            if qs.get(key):
                try:
                    return int(qs[key][0])
                except Exception:
                    return None
        return None

    @staticmethod
    def _guess_content_type_from_path(path: Path) -> str:
        content_type, _ = mimetypes.guess_type(path.name)
        if content_type:
            return content_type
        suffix = path.suffix.lower()
        if suffix == ".webp":
            return "image/webp"
        if suffix in {".jpg", ".jpeg"}:
            return "image/jpeg"
        if suffix == ".png":
            return "image/png"
        return "application/octet-stream"

    @staticmethod
    def _media_root() -> Path:
        configured = (
            getattr(get_settings(), "MEDIA_ROOT", None)
            or getattr(get_settings(), "MEDIA_DIR", None)
            or getattr(get_settings(), "media_root", None)
        )
        if configured:
            return Path(str(configured))
        storage_root = Path(
            str(getattr(get_settings(), "photo_storage_root", ".local/photo_studio"))
        )
        if storage_root.name == "photo_studio":
            return storage_root.parent / "media"
        return Path.cwd() / "media"

    @classmethod
    def _resolve_local_media_candidate(cls, url: str) -> Path | None:
        raw = str(url or "").strip()
        if not raw:
            return None
        media_rel = ""
        if raw.startswith("/media/"):
            media_rel = raw[len("/media/") :]
        elif raw.startswith("media/"):
            media_rel = raw[len("media/") :]
        else:
            parsed = urlparse(raw)
            if (
                parsed.scheme in {"http", "https"}
                and parsed.hostname in {"localhost", "127.0.0.1"}
                and (parsed.path or "").startswith("/media/")
            ):
                media_rel = (parsed.path or "")[len("/media/") :]
        if not media_rel:
            return None
        media_root = cls._media_root().resolve()
        candidate = (media_root / unquote(media_rel).lstrip("/")).resolve()
        try:
            candidate.relative_to(media_root)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Unsafe media path") from exc
        return candidate

    @staticmethod
    def _is_wb_url(url: str | None) -> bool:
        raw = str(url or "").strip().lower()
        return "wbbasket" in raw or "basket" in raw and "/images/" in raw

    @staticmethod
    def _extract_photo_number(url: str | None) -> int | None:
        match = re.search(
            r"/(?:big|tm|c\d+x\d+)/(\d+)\.[a-z0-9]+(?:$|\?)",
            str(url or ""),
            re.IGNORECASE,
        )
        if not match:
            return None
        try:
            return int(match.group(1))
        except Exception:
            return None

    @staticmethod
    def _public_media_url(relative_path: str) -> str:
        rel = str(relative_path or "").strip().lstrip("/")
        if rel.startswith("media/"):
            rel = rel[len("media/") :]
        base = str(
            getattr(get_settings(), "MEDIA_PUBLIC_BASE_URL", None)
            or getattr(get_settings(), "media_public_base_url", None)
            or getattr(get_settings(), "PUBLIC_BASE_URL", None)
            or getattr(get_settings(), "public_base_url", None)
            or ""
        ).strip()
        if base:
            return f"{base.rstrip('/')}/media/{rel}"
        return f"/media/{rel}"

    @classmethod
    def _preview_url_for_photo(
        cls,
        company: ABTestCompany,
        photo: ABTestPhoto,
        *,
        media_state: dict[str, Any] | None = None,
    ) -> str:
        file_url = str(getattr(photo, "file_url", "") or "").strip()
        wb_url = str(getattr(photo, "wb_url", "") or "").strip()
        if not file_url:
            return wb_url
        if not cls._is_wb_url(file_url):
            return file_url
        state = (
            media_state
            if isinstance(media_state, dict)
            else dict(getattr(company, "original_media_json", None) or {})
        )
        slot = cls._extract_photo_number(file_url)
        if slot:
            rel_backup = str(
                ((state.get("backups") or {}).get(str(int(slot))) or "")
            ).strip()
            if rel_backup:
                return cls._public_media_url(rel_backup)
        return file_url or wb_url

    @staticmethod
    def _calc_spend_rub(
        *, photos_count: int, views_per_photo: int, cpm_rub: int
    ) -> int:
        raw = (int(photos_count) * int(views_per_photo) * int(cpm_rub)) / 1000.0
        return int(math.ceil(max(raw * 1.1, 1000.0) / 100.0) * 100)

    @staticmethod
    def _min_cpm_from_bids(min_bids: dict[str, Any]) -> int:
        return max(
            int(min_bids.get("min_combined_rub") or 0),
            int(min_bids.get("min_search_rub") or 0),
            int(min_bids.get("min_recommendation_rub") or 0),
        )

    @staticmethod
    def _is_retryable_start_error(error: str) -> bool:
        raw = str(error or "").strip().lower()
        if not raw:
            return False
        markers = (
            "low budget",
            "budget",
            "баланс",
            "бюджет",
            "недостаточно",
            "insufficient",
            "not enough",
            "funds",
            "money",
        )
        return any(marker in raw for marker in markers)

    @staticmethod
    def _is_insufficient_funds_error(error: str) -> bool:
        raw = str(error or "").strip().lower()
        if not raw:
            return False
        markers = (
            "insufficient funds",
            "insufficient funds in the account",
            "недостаточно средств",
            "недостаточно денег",
            "insufficient balance",
        )
        return any(marker in raw for marker in markers)

    @staticmethod
    def _pick_cashback_for_deposit(
        balance_payload: Any, amount_rub: int
    ) -> tuple[int, int] | None:
        if not isinstance(balance_payload, dict):
            return None
        amount = max(int(amount_rub or 0), 0)
        if amount <= 0:
            return None
        best: tuple[int, int] | None = None
        for item in balance_payload.get("cashbacks") or []:
            if not isinstance(item, dict):
                continue
            try:
                available_sum = max(int(item.get("sum") or 0), 0)
                percent = max(int(item.get("percent") or 0), 0)
            except Exception:
                continue
            if available_sum <= 0 or percent <= 0:
                continue
            usable_sum = min(available_sum, max((amount * percent) // 100, 0))
            if usable_sum <= 0:
                continue
            candidate = (usable_sum, percent)
            if best is None or candidate[0] > best[0]:
                best = candidate
        return best

    @staticmethod
    def _extract_deposit_source_balances(balance_payload: Any) -> tuple[int, int]:
        if not isinstance(balance_payload, dict):
            return 0, 0
        try:
            account_balance = max(int(balance_payload.get("balance") or 0), 0)
        except Exception:
            account_balance = 0
        try:
            net_balance = max(int(balance_payload.get("net") or 0), 0)
        except Exception:
            net_balance = 0
        return account_balance, net_balance

    @classmethod
    def _resolve_deposit_source_type(
        cls, payment_source: str | None, balance_payload: Any, amount_rub: int
    ) -> int:
        raw = str(payment_source or "").strip().lower()
        if raw in {"balance", "topup", "top-up", "account", "cash", "счет", "счёт"}:
            return 0
        if raw in {"net", "netting", "balance_sheet", "balance-sheet", "mutual"}:
            return 1
        account_balance, net_balance = cls._extract_deposit_source_balances(
            balance_payload
        )
        required_amount = max(int(amount_rub or 0), 0)
        if required_amount > 0:
            if account_balance >= required_amount:
                return 0
            if net_balance >= required_amount:
                return 1
        if account_balance > 0 and net_balance <= 0:
            return 0
        if net_balance > 0 and account_balance <= 0:
            return 1
        return 0

    @classmethod
    def _fallback_deposit_source_type(
        cls, source_type: int, balance_payload: Any, amount_rub: int
    ) -> int | None:
        required_amount = max(int(amount_rub or 0), 0)
        account_balance, net_balance = cls._extract_deposit_source_balances(
            balance_payload
        )
        if int(source_type) != 0:
            if account_balance >= required_amount or (
                account_balance > 0 and net_balance <= 0
            ):
                return 0
        if int(source_type) != 1:
            if net_balance >= required_amount or (
                net_balance > 0 and account_balance <= 0
            ):
                return 1
        return None

    @staticmethod
    async def _wait_for_campaign_budget(
        advert: ABTestWBAdvertClient,
        *,
        advert_id: int,
        required_budget: int,
        timeout_sec: int = 75,
        poll_sec: float = 5.0,
    ) -> int:
        target = max(int(required_budget or 0), 0)
        if target <= 0:
            return 0
        deadline = utcnow() + timedelta(seconds=max(int(timeout_sec or 0), 0))
        last_total = 0
        while True:
            try:
                last_total = max(
                    int(
                        await advert.get_campaign_budget(advert_id=int(advert_id)) or 0
                    ),
                    0,
                )
            except Exception:
                pass
            if last_total >= target:
                return last_total
            if utcnow() >= deadline:
                return last_total
            await asyncio.sleep(max(float(poll_sec or 0), 1.0))

    @staticmethod
    def _same_media_url(left: str | None, right: str | None) -> bool:
        def clean(value: str | None) -> str:
            raw = str(value or "").strip()
            if not raw:
                return ""
            parsed = urlparse(raw)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path}".rstrip(
                    "/"
                )
            return raw.rstrip("/")

        return bool(clean(left) and clean(left) == clean(right))

    @staticmethod
    def _normalize_photos(
        raw_photos: list[Any], *, main_photo_url: str | None = None
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for idx, item in enumerate(raw_photos, start=1):
            if not isinstance(item, dict):
                continue
            file_url = str(item.get("file_url") or item.get("url") or "").strip()
            if not file_url:
                continue
            out.append(
                {
                    "order": int(item.get("order") or idx),
                    "file_url": file_url,
                    "preview_url": item.get("preview_url") or file_url,
                }
            )
        if len(out) < 2 and main_photo_url:
            out.insert(
                0,
                {"order": 1, "file_url": main_photo_url, "preview_url": main_photo_url},
            )
            for idx, item in enumerate(out, start=1):
                item["order"] = idx
        if len(out) < 2:
            raise HTTPException(
                status_code=400, detail="At least two photo variants are required"
            )
        return sorted(out, key=lambda item: int(item["order"]))

    @staticmethod
    def _current_photo(company: ABTestCompany) -> ABTestPhoto | None:
        order = int(company.current_photo_order or 1)
        return next(
            (photo for photo in (company.photos or []) if int(photo.order) == order),
            None,
        )

    @staticmethod
    def _can_autostart(company: ABTestCompany) -> bool:
        return (
            len(company.photos or []) >= 2
            and int(company.views_per_photo or 0) >= 1000
            and int(company.cpm or 0) > 0
            and (company.last_polled_at is None or company.last_polled_at <= utcnow())
        )

    @classmethod
    def _variant_scores(cls, photos: list[ABTestPhoto]) -> dict[int, dict[str, Any]]:
        max_ctr = max((float(photo.ctr or 0.0) for photo in photos), default=0.0)
        out: dict[int, dict[str, Any]] = {}
        for photo in photos:
            shows = max(int(photo.shows or 0), 0)
            ctr = float(photo.ctr or 0.0)
            confidence = min(shows / float(cls.MIN_IMPRESSIONS), 1.0)
            ctr_norm = ctr / max_ctr if max_ctr > 0 else 0.0
            score = 0.7 * ctr_norm + 0.3 * confidence
            out[int(photo.order)] = {
                "score": round(score, 6),
                "confidence": round(confidence, 6),
                "conversion_source": "clicks_proxy",
                "reason": f"score={score:.4f}; ctr_norm={ctr_norm:.4f}; confidence={confidence:.4f}",
            }
        return out

    @classmethod
    def _pick_winner(
        cls, photos: list[ABTestPhoto]
    ) -> tuple[ABTestPhoto | None, str | None]:
        if len(photos) < cls.MIN_VARIANTS:
            return None, "insufficient_data: not enough variants"
        min_shows = min(int(photo.shows or 0) for photo in photos)
        if min_shows < cls.MIN_IMPRESSIONS:
            return (
                None,
                f"insufficient_data: min_shows={min_shows}, min_required={cls.MIN_IMPRESSIONS}",
            )
        scores = cls._variant_scores(photos)
        ranked = sorted(
            photos,
            key=lambda photo: (
                scores.get(int(photo.order), {}).get("score") or 0.0,
                float(photo.ctr or 0.0),
            ),
            reverse=True,
        )
        if len(ranked) < 2:
            return ranked[0] if ranked else None, None
        top, second = ranked[0], ranked[1]
        ctr_delta = float(top.ctr or 0.0) - float(second.ctr or 0.0)
        score_delta = (scores.get(int(top.order), {}).get("score") or 0.0) - (
            scores.get(int(second.order), {}).get("score") or 0.0
        )
        if ctr_delta < cls.MIN_CTR_DELTA or score_delta < cls.MIN_SCORE_DELTA:
            return (
                None,
                f"no_clear_winner: ctr_delta={ctr_delta:.4f}, score_delta={score_delta:.4f}",
            )
        return top, None

    @staticmethod
    def _winner_decision(company: ABTestCompany) -> str | None:
        if company.winner_photo_order:
            return "winner_found"
        if company.status == "stopped":
            return "test_interrupted"
        if company.error_message and "insufficient_data" in company.error_message:
            return "insufficient_data"
        if company.error_message and "no_clear_winner" in company.error_message:
            return "no_clear_winner"
        if company.status == "finished":
            return "no_clear_winner"
        return None

    @staticmethod
    def parse_stats_totals(stats_resp: Any, advert_id: int) -> tuple[int, int]:
        if isinstance(stats_resp, dict):
            for key in ("adverts", "data", "items"):
                if isinstance(stats_resp.get(key), list):
                    return ABTestService.parse_stats_totals(stats_resp[key], advert_id)
            return int(stats_resp.get("views") or stats_resp.get("shows") or 0), int(
                stats_resp.get("clicks") or 0
            )
        total_shows = 0
        total_clicks = 0
        for item in stats_resp or []:
            if not isinstance(item, dict):
                continue
            item_id = item.get("advertId") or item.get("advert_id") or item.get("id")
            if item_id is not None and int(item_id) != int(advert_id):
                continue
            total_shows += int(item.get("views") or item.get("shows") or 0)
            total_clicks += int(item.get("clicks") or 0)
            for day in item.get("days") or []:
                total_shows += int(day.get("views") or day.get("shows") or 0)
                total_clicks += int(day.get("clicks") or 0)
        return total_shows, total_clicks
