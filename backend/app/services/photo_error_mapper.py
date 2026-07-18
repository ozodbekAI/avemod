from __future__ import annotations

import re
from typing import Any


def _truncate_text(value: Any, max_len: int = 280) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_len:
        return text
    return f"{text[:max_len].rstrip()}...(+{len(text) - max_len} chars)"


def _build_debug_payload(raw_text: str, context: str | None = None) -> dict[str, Any]:
    lowered = raw_text.lower()
    debug: dict[str, Any] = {
        "context": str(context) if context else None,
        "where": str(context or "unknown"),
        "provider": "server",
        "reason": "unknown_error",
        "raw_error_excerpt": _truncate_text(raw_text) if raw_text else "",
    }
    gemini_http = re.search(r"gemini error\s+(\d+)", raw_text, flags=re.IGNORECASE)
    finish_reason = re.search(
        r"finishreason\):\s*([A-Z0-9_:-]+)", raw_text, flags=re.IGNORECASE
    )
    if gemini_http:
        debug.update(
            provider="gemini",
            where=f"{context or 'unknown'}:gemini_http",
            reason="http_error",
            provider_status_code=int(gemini_http.group(1)),
        )
        return debug
    if "gemini error timeout" in lowered or "timeout" in lowered:
        debug.update(
            provider="gemini" if "gemini" in lowered else "upstream",
            where=f"{context or 'unknown'}:timeout",
            reason="timeout",
        )
        return debug
    if finish_reason:
        debug.update(
            provider="gemini",
            where=f"{context or 'unknown'}:gemini_finish_reason",
            reason="blocked",
            finish_reason=finish_reason.group(1),
        )
        return debug
    if "no candidates returned" in lowered:
        debug.update(
            provider="gemini",
            where=f"{context or 'unknown'}:gemini_no_candidates",
            reason="no_candidates",
        )
        return debug
    if "failed to decode image data" in lowered:
        debug.update(
            provider="gemini",
            where=f"{context or 'unknown'}:decode_output",
            reason="decode_failed",
        )
        return debug
    if (
        "no image in result" in lowered
        or "empty result" in lowered
        or "could not generate an image" in lowered
    ):
        debug.update(
            provider="gemini",
            where=f"{context or 'unknown'}:empty_output",
            reason="empty_result",
        )
        return debug
    if (
        lowered.startswith("task failed:")
        or "failed to create task" in lowered
        or "kie" in lowered
    ):
        debug.update(
            provider="kie",
            where=f"{context or 'unknown'}:kie_task",
            reason="task_failed",
        )
        return debug
    if "wb " in lowered or lowered.startswith("wb"):
        debug.update(
            provider="wb",
            where=f"{context or 'unknown'}:wb_apply",
            reason="wb_apply_failed",
        )
        return debug
    return debug


def map_photo_error(raw_error: Any, *, context: str | None = None) -> dict[str, Any]:
    raw_text = str(raw_error or "").strip()
    lowered = raw_text.lower()
    debug = _build_debug_payload(raw_text, context)
    payload: dict[str, Any] = {
        "code": "photo_operation_failed",
        "message": "Операция не завершилась. Повторите попытку.",
        "retryable": True,
        "category": "unknown",
        "http_status": 400,
        "where": debug.get("where"),
        "provider": debug.get("provider"),
        "reason": debug.get("reason"),
        "debug": debug,
    }
    if context:
        payload["context"] = str(context)
    if not raw_text:
        return payload
    if lowered.startswith("task failed:"):
        nested_raw = raw_text.split(":", 1)[1].strip()
        nested_clean = (
            nested_raw.rsplit("(", 1)[0].strip() if "(code:" in lowered else nested_raw
        )
        nested = map_photo_error(nested_clean, context=context)
        if nested.get("code") != "photo_operation_failed":
            return nested
    if "unauthorized" in lowered:
        return {
            **payload,
            "code": "photo_unauthorized",
            "message": "Сессия истекла. Обновите страницу и войдите снова.",
            "retryable": False,
            "category": "auth",
            "http_status": 401,
        }
    if (
        "asset not found" in lowered
        or "не нашёл выбранное фото" in lowered
        or "photo not found on wb card" in lowered
    ):
        return {
            **payload,
            "code": "photo_asset_not_found",
            "message": "Не удалось найти выбранное изображение. Выберите фото заново.",
            "retryable": True,
            "category": "asset",
            "http_status": 400,
        }
    if (
        "source_url is required" in lowered
        or "cannot load source image" in lowered
        or "unsupported url" in lowered
        or ("unsupported" in lowered and "host" in lowered)
        or "redirected to an unsupported host" in lowered
        or "url does not point to an image" in lowered
        or "image is too large" in lowered
        or "не найдены загруженные фото" in lowered
        or "пришлите фото" in lowered
    ):
        return {
            **payload,
            "code": "photo_source_image_missing",
            "message": "Не удалось получить исходное фото. Загрузите или выберите другое изображение.",
            "retryable": True,
            "category": "input",
            "http_status": 400,
        }
    if "image_size is not within the range of allowed options" in lowered:
        return {
            **payload,
            "code": "photo_invalid_image_size",
            "message": "Размер изображения не поддерживается для этой задачи KIE. Используйте 1:1 или 3:4 и повторите.",
            "retryable": True,
            "category": "input",
            "http_status": 400,
        }
    if "kie api key is not configured" in lowered or (
        "not configured" in lowered and "kie" in lowered
    ):
        return {
            **payload,
            "code": "photo_service_not_configured",
            "message": "Сервис KIE не настроен. Проверьте KIE_API_KEY в .env и перезапустите сервер.",
            "retryable": False,
            "category": "configuration",
            "http_status": 503,
        }
    if "failed to create task" in lowered and "image_size" in lowered:
        return {
            **payload,
            "code": "photo_invalid_image_size",
            "message": "Не удалось создать задачу из-за размера изображения. Используйте 1:1 или 3:4.",
            "retryable": True,
            "category": "input",
            "http_status": 400,
        }
    if "failed to create task" in lowered:
        return {
            **payload,
            "code": "photo_task_create_failed",
            "message": "Не удалось отправить задачу в KIE. Проверьте параметры изображения и попробуйте позже.",
            "retryable": True,
            "category": "upstream",
            "http_status": 502,
        }
    gemini_http = re.search(r"gemini error\s+(\d+)", raw_text, flags=re.IGNORECASE)
    if gemini_http:
        status_code = int(gemini_http.group(1))
        if status_code == 429:
            return {
                **payload,
                "code": "photo_gemini_rate_limited",
                "message": "Gemini временно ограничил запросы. Повторите попытку чуть позже.",
                "retryable": True,
                "category": "upstream",
                "http_status": 429,
            }
        if status_code == 400:
            return {
                **payload,
                "code": "photo_gemini_bad_request",
                "message": "Gemini отклонил запрос на этапе генерации. Проверьте промпт и входные изображения.",
                "retryable": True,
                "category": "input",
                "http_status": 400,
            }
        if 500 <= status_code <= 599:
            return {
                **payload,
                "code": "photo_gemini_upstream_error",
                "message": "Gemini вернул серверную ошибку во время генерации. Повторите попытку позже.",
                "retryable": True,
                "category": "upstream",
                "http_status": 502,
            }
        return {
            **payload,
            "code": "photo_gemini_http_error",
            "message": f"Gemini вернул HTTP {status_code} во время генерации.",
            "retryable": True,
            "category": "upstream",
            "http_status": 502,
        }
    if (
        "duplicate photo urls are not allowed" in lowered
        or "resolved photo list contains duplicates" in lowered
    ):
        return {
            **payload,
            "code": "photo_duplicate_sources",
            "message": "В списке есть дубли фото. Удалите повторяющиеся изображения и повторите.",
            "retryable": True,
            "category": "input",
            "http_status": 400,
        }
    if "no candidates returned" in lowered:
        return {
            **payload,
            "code": "photo_generation_no_candidates",
            "message": "Gemini не вернул ни одного варианта изображения. Попробуйте упростить запрос.",
            "retryable": True,
            "category": "generation",
            "http_status": 502,
        }
    if "finishreason" in lowered:
        return {
            **payload,
            "code": "photo_generation_blocked",
            "message": "Gemini остановил генерацию из-за внутренних ограничений ответа. Попробуйте изменить запрос.",
            "retryable": True,
            "category": "generation",
            "http_status": 502,
        }
    if "failed to decode image data" in lowered:
        return {
            **payload,
            "code": "photo_generation_decode_failed",
            "message": "Gemini вернул повреждённые данные изображения. Повторите попытку.",
            "retryable": True,
            "category": "generation",
            "http_status": 502,
        }
    if (
        "no image in result" in lowered
        or "пустой результат" in lowered
        or "empty result" in lowered
        or "gemini вернул пустой результат" in lowered
        or "could not generate an image" in lowered
    ):
        return {
            **payload,
            "code": "photo_generation_empty_result",
            "message": "Генерация не завершилась с этим промптом. Сформулируйте задачу проще или измените её и повторите.",
            "retryable": True,
            "category": "generation",
            "http_status": 502,
        }
    if "no video in result" in lowered:
        return {
            **payload,
            "code": "photo_generation_no_video",
            "message": "Видео не сгенерировалось в этой попытке. Попробуйте другой промпт.",
            "retryable": True,
            "category": "generation",
            "http_status": 502,
        }
    if (
        "wb media save failed" in lowered
        or "wb photo upload failed" in lowered
        or "wb photo replace failed" in lowered
        or "wb apply failed" in lowered
        or "wb media/file failed" in lowered
        or "did not return a photo url" in lowered
    ):
        return {
            **payload,
            "code": "photo_wb_apply_failed",
            "message": "Не удалось применить изменения в WB. Повторите попытку позже.",
            "retryable": True,
            "category": "wb_apply",
            "http_status": 502,
        }
    if (
        "timed out" in lowered
        or "timeout" in lowered
        or "readtimeout" in lowered
        or "connecttimeout" in lowered
        or "pooltimeout" in lowered
    ):
        return {
            **payload,
            "code": "photo_upstream_timeout",
            "message": "Внешний сервис не ответил вовремя. Повторите попытку через минуту.",
            "retryable": True,
            "category": "upstream",
            "http_status": 504,
        }
    if "insufficient" in lowered and "credit" in lowered:
        return {
            **payload,
            "code": "photo_insufficient_credits",
            "message": "Недостаточно кредитов для генерации. Пополните баланс и повторите.",
            "retryable": False,
            "category": "billing",
            "http_status": 402,
        }
    if "pose prompt not found" in lowered:
        return {
            **payload,
            "code": "photo_pose_not_found",
            "message": "Выбранная поза недоступна. Выберите другую позу.",
            "retryable": True,
            "category": "input",
            "http_status": 400,
        }
    if "scene item not found" in lowered:
        return {
            **payload,
            "code": "photo_scene_not_found",
            "message": "Выбранная сцена недоступна. Обновите каталог и попробуйте снова.",
            "retryable": True,
            "category": "input",
            "http_status": 400,
        }
    if "quick_action.type is required" in lowered:
        return {
            **payload,
            "code": "photo_action_missing",
            "message": "Не удалось определить действие. Выберите команду заново.",
            "retryable": True,
            "category": "input",
            "http_status": 400,
        }
    if (
        "new_model_prompt or model_item_id is required" in lowered
        or "промпт не указан" in lowered
    ):
        return {
            **payload,
            "code": "photo_prompt_missing",
            "message": "Нужен промпт или выбор модели из каталога.",
            "retryable": True,
            "category": "input",
            "http_status": 400,
        }
    if lowered.startswith("ошибка quick_action"):
        return {
            **payload,
            "code": "photo_quick_action_failed",
            "message": "Команда не выполнилась из-за технической ошибки. Повторите позже.",
            "retryable": True,
            "category": "generation",
            "http_status": 500,
        }
    return payload


def map_photo_error_message(raw_message: str) -> str:
    return str(
        map_photo_error(raw_message).get("message")
        or "Операция не завершилась. Повторите попытку."
    )
