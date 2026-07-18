from __future__ import annotations

import json
from pathlib import Path

from app.modules.photo_chat.router import _sse, router
from app.schemas.photo_chat import PhotoChatStreamRequest
from app.services.photo_error_mapper import map_photo_error

ROOT = Path(__file__).resolve().parents[3]


def _parse_sse_chunk(chunk: str) -> dict:
    lines = [line for line in chunk.strip().splitlines() if line]
    assert lines[0] == "event: message"
    assert sum(1 for line in lines if line.startswith("event:")) == 1
    data_line = next(line for line in lines if line.startswith("data: "))
    return json.loads(data_line[len("data: ") :])


def test_emit_uses_message_event_with_thread_and_request_ids():
    chunk = _sse({"type": "chat", "request_id": "req-123", "thread_id": 42, "content": "hello"})

    assert chunk.startswith("event: message\n")
    assert "\nevent: generation_start\n" not in f"\n{chunk}"
    assert _parse_sse_chunk(chunk) == {
        "type": "chat",
        "request_id": "req-123",
        "thread_id": 42,
        "content": "hello",
    }


def test_only_message_event_is_used_for_supported_sse_payload_types():
    supported_types = [
        "ack",
        "chat",
        "question",
        "generation_start",
        "images_start",
        "image_started",
        "generation_complete",
        "error",
        "context_state",
    ]

    for payload_type in supported_types:
        payload = _parse_sse_chunk(_sse({"type": payload_type, "request_id": "req-contract", "thread_id": 77, "marker": payload_type}))
        assert payload["type"] == payload_type
        assert payload["request_id"] == "req-contract"
        assert payload["thread_id"] == 77


def test_photo_chat_stream_request_accepts_and_normalizes_model_fields():
    payload = PhotoChatStreamRequest(
        message="  hello  ",
        planner_model="  gemini-3.1-pro-preview  ",
        generation_model="  gemini-3-pro-image-preview  ",
        model_profile="  quality  ",
        allow_quality_fallback=False,
    )

    assert payload.message == "hello"
    assert payload.planner_model == "gemini-3.1-pro-preview"
    assert payload.generation_model == "gemini-3-pro-image-preview"
    assert payload.model_profile == "quality"
    assert payload.allow_quality_fallback is False


def test_photo_chat_stream_request_remains_backward_compatible_without_new_fields():
    payload = PhotoChatStreamRequest(message="hello", asset_ids=[1, "2", "bad"])

    assert payload.message == "hello"
    assert payload.asset_ids == [1, 2]
    assert payload.planner_model is None
    assert payload.generation_model is None
    assert payload.model_profile is None
    assert payload.allow_quality_fallback is None


def test_map_photo_error_recovers_from_task_failed_wrapper():
    mapped = map_photo_error(
        "Task failed: Gemini could not generate an image with the given prompt. Please try again with a different prompt. (code: 500)",
        context="chat_stream:generation",
    )
    assert mapped["code"] == "photo_generation_empty_result"
    assert "Сформулируйте задачу проще" in str(mapped["message"])


def test_map_photo_error_handles_image_size_task_error():
    mapped = map_photo_error(
        "Task failed: Failed to create task: image_size is not within the range of allowed options (code: 500)",
        context="chat_stream",
    )
    assert mapped["code"] == "photo_invalid_image_size"
    assert "1:1" in str(mapped["message"])


def test_map_photo_error_exposes_gemini_http_details():
    mapped = map_photo_error(
        'Gemini error 500: {"error":{"message":"backend exploded"}}',
        context="chat_stream:generation",
    )
    assert mapped["code"] == "photo_gemini_upstream_error"
    assert mapped["provider"] == "gemini"
    assert mapped["where"] == "chat_stream:generation:gemini_http"
    assert mapped["debug"]["provider_status_code"] == 500
    assert mapped["debug"]["reason"] == "http_error"


def test_map_photo_error_exposes_block_reason_details():
    mapped = map_photo_error(
        "Gemini API javobni blokladi! Sabab (finishReason): SAFETY",
        context="chat_stream:generation",
    )
    assert mapped["code"] == "photo_generation_blocked"
    assert mapped["provider"] == "gemini"
    assert mapped["debug"]["finish_reason"] == "SAFETY"
    assert mapped["debug"]["where"] == "chat_stream:generation:gemini_finish_reason"


def test_photo_compatibility_routes_cover_source_frontend_surface():
    routes = {
        (method, route.path)
        for route in router.routes
        if getattr(route, "methods", None)
        for method in route.methods
    }

    for method, path in [
        ("GET", "/stores"),
        ("GET", "/stores/{account_id}/cards/wb/live"),
        ("GET", "/stores/{account_id}/cards"),
        ("GET", "/stores/{account_id}/cards/{card_id}"),
        ("POST", "/stores/{account_id}/cards/{card_id}/photos/sync"),
        ("GET", "/photo/chat/models"),
        ("GET", "/photo/threads"),
        ("POST", "/photo/threads/new"),
        ("DELETE", "/photo/threads/{thread_id}"),
        ("GET", "/photo/chat/history"),
        ("POST", "/photo/assets/upload"),
        ("POST", "/photo/assets/import"),
        ("POST", "/photo/chat/stream"),
        ("POST", "/photo/generator/run"),
        ("POST", "/photo/chat/clear"),
        ("POST", "/photo/chat/messages/delete"),
        ("POST", "/photo/chat/assets/delete"),
    ]:
        assert (method, path) in routes


def test_photo_studio_ui_remains_beta_hidden_for_non_superuser():
    sidebar = (ROOT / "frontend/src/components/AppSidebar.tsx").read_text(encoding="utf-8")
    assert "const betaNav" in sidebar
    assert '{ to: "/photo-studio", label: "Фотостудия", icon: Camera, module: "photo" }' in sidebar
    assert "VITE_ENABLE_BETA_MODULES" in sidebar
    assert "betaModulesEnabled" in sidebar
    assert "BetaNav" in sidebar
