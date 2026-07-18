from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.problem_engine.formula_evaluator import FormulaEvaluator


def evaluator() -> FormulaEvaluator:
    return FormulaEvaluator()


def test_formula_evaluator_supports_boolean_and_comparison_operators() -> None:
    expr = {
        "and": [
            {">": [{"metric": "days_of_stock"}, 60]},
            {">=": [{"metric": "stock_qty"}, 50]},
            {"<": [{"metric": "return_rate"}, 20]},
            {"<=": [{"metric": "drr"}, 10]},
            {"==": [{"metric": "status"}, "ok"]},
            {"!=": [{"metric": "category"}, "blocked"]},
            {"not": {"==": [{"metric": "is_archived"}, True]}},
        ]
    }

    result = evaluator().evaluate_condition(
        expr,
        metrics={
            "days_of_stock": 90,
            "stock_qty": 50,
            "return_rate": 12,
            "drr": 10,
            "status": "ok",
            "category": "watch",
            "is_archived": False,
        },
        evaluation_context={
            "allowed_metrics": {
                "days_of_stock",
                "stock_qty",
                "return_rate",
                "drr",
                "status",
                "category",
                "is_archived",
            }
        },
    )

    assert result.error is None
    assert result.value is True
    assert result.missing_metrics == []


def test_formula_evaluator_supports_or_and_reports_missing_in_all_branches() -> None:
    result = evaluator().evaluate_condition(
        {"and": [False, {">": [{"metric": "missing_metric"}, 1]}]},
        metrics={},
        evaluation_context={"allowed_metrics": {"missing_metric"}},
    )

    assert result.error is None
    assert result.value is False
    assert result.missing_metrics == ["missing_metric"]
    assert any("missing" in warning for warning in result.warnings)

    result_or = evaluator().evaluate_condition({"or": [False, {"==": [1, 1]}]}, metrics={})
    assert result_or.error is None
    assert result_or.value is True


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ({"+": [1, 2, {"metric": "x"}]}, Decimal("6")),
        ({"-": [10, {"metric": "x"}, 2]}, Decimal("5")),
        ({"-": [{"metric": "x"}]}, Decimal("-3")),
        ({"*": [2, {"metric": "x"}, 4]}, Decimal("24")),
        ({"/": [12, {"metric": "x"}]}, Decimal("4")),
        ({"max": [1, {"metric": "x"}, 10]}, Decimal("10")),
        ({"min": [1, {"metric": "x"}, 10]}, Decimal("1")),
        ({"abs": {"-": [1, 4]}}, Decimal("3")),
        ({"round": [{"/": [10, 3]}, 2]}, Decimal("3.33")),
        ({"coalesce": [{"metric": "missing"}, {"metric": "x"}, 0]}, Decimal("3")),
        ({"percent_change": [125, 100]}, Decimal("25.00")),
    ],
)
def test_formula_evaluator_supports_numeric_operators(expr: dict, expected: Decimal) -> None:
    result = evaluator().evaluate_numeric(
        expr,
        metrics={"x": 3},
        evaluation_context={"allowed_metrics": {"x", "missing"}},
    )

    assert result.error is None
    assert result.value == expected


def test_formula_evaluator_handles_division_by_zero_safely() -> None:
    result = evaluator().evaluate({"/": [10, 0]}, metrics={})

    assert result.error is None
    assert result.value is None
    assert "division by zero" in result.warnings

    pct = evaluator().evaluate({"percent_change": [10, 0]}, metrics={})
    assert pct.error is None
    assert pct.value is None
    assert "percent_change division by zero" in pct.warnings


def test_formula_evaluator_supports_missing_operator() -> None:
    result = evaluator().evaluate(
        {"missing": ["cost", {"metric": "price"}, "stock"]},
        metrics={"price": 100, "stock": None},
        evaluation_context={"allowed_metrics": {"cost", "price", "stock"}},
    )

    assert result.error is None
    assert result.value == ["cost", "stock"]
    assert result.missing_metrics == ["cost", "stock"]


def test_formula_evaluator_supports_case_operator_structured_and_flat_forms() -> None:
    structured = evaluator().evaluate(
        {
            "case": [
                {"if": {">": [{"metric": "profit"}, 0]}, "then": "profitable"},
                {"if": {"<": [{"metric": "profit"}, 0]}, "then": "loss"},
                {"else": "watch"},
            ]
        },
        metrics={"profit": -1},
        evaluation_context={"allowed_metrics": {"profit"}},
    )
    assert structured.error is None
    assert structured.value == "loss"

    flat = evaluator().evaluate({"case": [{">": [1, 2]}, "bad", {"==": [2, 2]}, "ok", "fallback"]}, metrics={})
    assert flat.error is None
    assert flat.value == "ok"


def test_formula_evaluator_supports_in_and_between() -> None:
    in_result = evaluator().evaluate_condition({"in": [{"metric": "status"}, ["new", "blocked"]]}, metrics={"status": "new"}, evaluation_context={"allowed_metrics": {"status"}})
    assert in_result.error is None
    assert in_result.value is True

    between_result = evaluator().evaluate_condition({"between": [{"metric": "drr"}, 5, 15]}, metrics={"drr": 9}, evaluation_context={"allowed_metrics": {"drr"}})
    assert between_result.error is None
    assert between_result.value is True


def test_formula_evaluator_reports_missing_metrics_without_crashing() -> None:
    result = evaluator().evaluate_condition(
        {">": [{"metric": "net_profit"}, 0]},
        metrics={},
        evaluation_context={"allowed_metrics": {"net_profit"}},
    )

    assert result.error is None
    assert result.value is False
    assert result.missing_metrics == ["net_profit"]


@pytest.mark.parametrize(
    "expr",
    [
        {"eval": ["1 + 1"]},
        {"exec": ["print(1)"]},
        {"__import__": ["os"]},
        {"unknown": [1, 2]},
    ],
)
def test_formula_evaluator_rejects_unknown_or_code_like_operators(expr: dict) -> None:
    result = evaluator().evaluate(expr, metrics={})

    assert result.error is not None
    assert "unknown operator" in result.error
    assert result.value is None


def test_formula_evaluator_rejects_unknown_metrics_when_allowed_metrics_are_supplied() -> None:
    result = evaluator().evaluate({"metric": "not_in_catalog"}, metrics={}, evaluation_context={"allowed_metrics": {"known_metric"}})

    assert result.error == "unknown metric: not_in_catalog"
    assert result.value is None


@pytest.mark.parametrize(
    "expr",
    [
        {"abs": "not-a-number"},
        {"max": ["not-a-number", 1]},
        {">": ["not-a-number", 1]},
        {"in": [1, 123]},
    ],
)
def test_formula_evaluator_rejects_unsafe_or_invalid_types(expr: dict) -> None:
    result = evaluator().evaluate(expr, metrics={})

    assert result.error is not None
    assert result.value is None


def test_formula_evaluator_rejects_malformed_expression_objects() -> None:
    result = evaluator().evaluate({"and": [True], "or": [False]}, metrics={})
    assert result.error == "expression objects must contain exactly one operator"

    missing = evaluator().evaluate({"missing": [{"bad": "shape"}]}, metrics={})
    assert missing.error == "operator missing accepts only metric names or metric refs"


def test_formula_evaluator_numeric_helper_reports_non_numeric_result() -> None:
    result = evaluator().evaluate_numeric({"coalesce": ["text", 1]}, metrics={})

    assert result.error == "operator requires numeric argument, got str"
    assert result.value is None


def test_formula_evaluator_rejects_non_finite_numbers() -> None:
    result = evaluator().evaluate_numeric({"+": [float("inf"), 1]}, metrics={})

    assert result.error is not None
    assert "invalid numeric value" in result.error
