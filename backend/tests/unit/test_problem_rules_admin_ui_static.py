from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend" / "src"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_admin_problem_rules_ui_is_wired_into_admin_page() -> None:
    admin_route = _read(FRONTEND / "routes" / "_authenticated" / "admin.tsx")

    assert "ProblemRulesAdminPanel" in admin_route
    assert 'value="problem-rules"' in admin_route
    assert "Правила проблем" in admin_route


def test_problem_rules_admin_ui_covers_required_flow() -> None:
    component = _read(FRONTEND / "components" / "problem-rules" / "ProblemRulesAdminPanel.tsx")
    api_client = _read(FRONTEND / "lib" / "problem-rules.ts")

    for endpoint in (
        "/admin/problem-rules/metrics",
        "/admin/problem-rules/definitions",
        "/validate",
        "/backtest",
        "/publish",
        "/pause",
        "/archive",
    ):
        assert endpoint in api_client

    for template_label in (
        "Нет себестоимости, прибыль не считается",
        "Товар продаётся в минус",
        "Много остатка, продажи медленные",
        "Риск дефицита",
        "Реклама без прибыли",
        "Промо без прибыли",
        "Цена ниже безопасной маржи",
        "Мёртвый остаток",
        "Быстро заканчивается остаток",
    ):
        assert template_label in component

    for step_label in (
        "Выберите сценарий",
        "Выберите бизнес-область",
        "Выберите метрики",
        "Соберите условие",
        "Соберите формулу влияния",
        "Настройте доказательства",
        "Запустите тестовый прогон",
        "Проверьте карточки продавца",
        "Опубликуйте",
    ):
        assert step_label in component

    for ui_marker in (
        "Расширенный режим",
        "JSON только для технических администраторов",
        "Оценка влияния по типу и доверию",
        "Карточки продавца",
        "data-admin-rule-seller-card-preview",
        "no_backtest",
        "no_evidence",
        "price_safety",
        "too_many_matches",
        "test_only",
    ):
        assert ui_marker in component
