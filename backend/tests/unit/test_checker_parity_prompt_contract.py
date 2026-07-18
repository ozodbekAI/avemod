from __future__ import annotations

from app.core.config import Settings
from app.services.checker_core.ai_fixer import CheckerAIFixer
from app.services.checker_core.wb_logic_prompt import build_wb_logic_block


def test_source_prompt_contract_requires_human_check_and_suggestion_kind() -> None:
    block = build_wb_logic_block()

    assert "requires_human_check" in block
    assert "suggestion_kind" in block


def test_openai_checker_prompt_contract_requests_review_ready_separation() -> None:
    service = CheckerAIFixer(Settings(checker_ai_enabled=True, openai_api_key="test-key"))

    prompt = service._build_prompt(
        card={"subjectName": "Костюмы", "characteristics": []},
        issues=[{"id": 1, "name": "Тип верха", "allowed_values": ["жакет"]}],
    )

    assert '"requires_human_check"' in prompt
    assert '"suggestion_kind"' in prompt
    assert '"candidate_values"' in prompt
    assert '"recommended_value": null' in prompt
    assert "exact_fix" in prompt
    assert "no_safe_fix" in prompt
    assert "Не подставляй случайное allowed value" in prompt
    assert 'recommended_value заполняй только когда это безопасный `suggestion_kind="exact_fix"`' in prompt
    assert "⚠️ СВОБОДНЫЕ ПОЛЯ" in prompt
    assert "Если allowed_values НЕТ — это СВОБОДНОЕ ПОЛЕ" in prompt
    assert "Для title → 40-60 символов" in prompt
    assert "Для description → 1000-1800 символов" in prompt
    assert "Используй Product DNA" in prompt
