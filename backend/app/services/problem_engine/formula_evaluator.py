from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


class FormulaValidationError(ValueError):
    """Raised only by explicit validation helpers; evaluate() returns diagnostics."""


@dataclass(slots=True)
class FormulaEvaluationResult:
    value: Any = None
    missing_metrics: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class ConditionEvaluationResult:
    value: bool = False
    missing_metrics: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class NumericFormulaEvaluationResult:
    value: Decimal | None = None
    missing_metrics: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class _EvalState:
    missing_metrics: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def missing(self, metric_code: str) -> None:
        self.missing_metrics.add(metric_code)


class FormulaEvaluator:
    """Safe JSONLogic-style evaluator for admin-authored problem formulas.

    The evaluator intentionally uses a closed operator set and recursive AST
    walking. It never calls eval, exec, imports, SQL, or dynamic function lookup.
    """

    ALLOWED_OPERATORS = frozenset(
        {
            "and",
            "or",
            "not",
            ">",
            ">=",
            "<",
            "<=",
            "==",
            "!=",
            "+",
            "-",
            "*",
            "/",
            "max",
            "min",
            "abs",
            "round",
            "coalesce",
            "missing",
            "case",
            "in",
            "between",
            "percent_change",
        }
    )
    METRIC_OPERATOR = "metric"
    DEFAULT_MAX_DEPTH = 32
    DEFAULT_MAX_NODES = 512
    UNSAFE_STRING_RE = re.compile(
        r"(--|/\*|\*/|;|\b(select|insert|update|delete|drop|alter|create|truncate|union|exec|execute)\b|__import__|eval\s*\(|exec\s*\()",
        re.IGNORECASE,
    )

    def evaluate(
        self,
        expression_json: Any,
        metrics: dict[str, Any],
        evaluation_context: dict[str, Any] | None = None,
    ) -> FormulaEvaluationResult:
        context = dict(evaluation_context or {})
        validation_error = self.validate(
            expression_json, metrics=metrics, evaluation_context=context
        )
        if validation_error is not None:
            return FormulaEvaluationResult(error=validation_error)
        state = _EvalState()
        try:
            value = self._eval(
                expression_json, metrics=metrics, context=context, state=state
            )
        except FormulaValidationError as exc:
            return FormulaEvaluationResult(
                value=None,
                missing_metrics=sorted(state.missing_metrics),
                warnings=state.warnings,
                error=str(exc),
            )
        return FormulaEvaluationResult(
            value=value,
            missing_metrics=sorted(state.missing_metrics),
            warnings=state.warnings,
            error=None,
        )

    def evaluate_condition(
        self,
        expression_json: Any,
        metrics: dict[str, Any],
        evaluation_context: dict[str, Any] | None = None,
    ) -> ConditionEvaluationResult:
        result = self.evaluate(
            expression_json, metrics=metrics, evaluation_context=evaluation_context
        )
        return ConditionEvaluationResult(
            value=False if result.error else self._truthy(result.value),
            missing_metrics=result.missing_metrics,
            warnings=result.warnings,
            error=result.error,
        )

    def evaluate_numeric(
        self,
        expression_json: Any,
        metrics: dict[str, Any],
        evaluation_context: dict[str, Any] | None = None,
    ) -> NumericFormulaEvaluationResult:
        result = self.evaluate(
            expression_json, metrics=metrics, evaluation_context=evaluation_context
        )
        value: Decimal | None = None
        error = result.error
        if error is None:
            if result.value is None:
                value = None
            else:
                try:
                    value = self._to_decimal(result.value)
                except FormulaValidationError as exc:
                    error = str(exc)
        return NumericFormulaEvaluationResult(
            value=value,
            missing_metrics=result.missing_metrics,
            warnings=result.warnings,
            error=error,
        )

    def validate(
        self,
        expression_json: Any,
        *,
        metrics: dict[str, Any] | None = None,
        evaluation_context: dict[str, Any] | None = None,
    ) -> str | None:
        context = dict(evaluation_context or {})
        allowed_metrics = self._allowed_metrics(metrics=metrics or {}, context=context)
        state = {"nodes": 0}
        try:
            self._validate_node(
                expression_json,
                allowed_metrics=allowed_metrics,
                depth=0,
                max_depth=int(context.get("max_depth") or self.DEFAULT_MAX_DEPTH),
                max_nodes=int(context.get("max_nodes") or self.DEFAULT_MAX_NODES),
                state=state,
            )
        except FormulaValidationError as exc:
            return str(exc)
        return None

    def _validate_node(
        self,
        node: Any,
        *,
        allowed_metrics: set[str] | None,
        depth: int,
        max_depth: int,
        max_nodes: int,
        state: dict[str, int],
    ) -> None:
        state["nodes"] += 1
        if state["nodes"] > max_nodes:
            raise FormulaValidationError(f"expression exceeds node limit {max_nodes}")
        if depth > max_depth:
            raise FormulaValidationError(f"expression exceeds depth limit {max_depth}")
        if isinstance(node, dict):
            if len(node) != 1:
                raise FormulaValidationError(
                    "expression objects must contain exactly one operator"
                )
            op, raw_args = next(iter(node.items()))
            if op == self.METRIC_OPERATOR:
                if not isinstance(raw_args, str) or not raw_args.strip():
                    raise FormulaValidationError(
                        "metric reference must be a non-empty string"
                    )
                self._validate_metric_code(raw_args, allowed_metrics=allowed_metrics)
                return
            if op not in self.ALLOWED_OPERATORS:
                raise FormulaValidationError(f"unknown operator: {op}")
            self._validate_operator_shape(
                op,
                raw_args,
                allowed_metrics=allowed_metrics,
                depth=depth,
                max_depth=max_depth,
                max_nodes=max_nodes,
                state=state,
            )
            return
        if isinstance(node, list):
            for item in node:
                self._validate_node(
                    item,
                    allowed_metrics=allowed_metrics,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_nodes=max_nodes,
                    state=state,
                )
            return
        if isinstance(node, str):
            if self.UNSAFE_STRING_RE.search(node):
                raise FormulaValidationError("unsafe formula literal")
            return
        if isinstance(node, (int, float, Decimal, bool)) or node is None:
            return
        raise FormulaValidationError(f"unsupported literal type: {type(node).__name__}")

    def _validate_operator_shape(
        self,
        op: str,
        raw_args: Any,
        *,
        allowed_metrics: set[str] | None,
        depth: int,
        max_depth: int,
        max_nodes: int,
        state: dict[str, int],
    ) -> None:
        args = raw_args if isinstance(raw_args, list) else [raw_args]
        if op in {"and", "or", "+", "*", "max", "min", "coalesce"} and len(args) < 1:
            raise FormulaValidationError(
                f"operator {op} requires at least one argument"
            )
        if op in {
            ">",
            ">=",
            "<",
            "<=",
            "==",
            "!=",
            "/",
            "in",
            "between",
            "percent_change",
        }:
            expected = 3 if op == "between" else 2
            if len(args) != expected:
                raise FormulaValidationError(
                    f"operator {op} requires {expected} arguments"
                )
        if op in {"not", "abs"} and len(args) != 1:
            raise FormulaValidationError(f"operator {op} requires one argument")
        if op == "round" and len(args) not in {1, 2}:
            raise FormulaValidationError("operator round requires one or two arguments")
        if op == "-" and len(args) < 1:
            raise FormulaValidationError("operator - requires at least one argument")
        if op == "missing":
            if not isinstance(raw_args, list):
                raise FormulaValidationError(
                    "operator missing requires a list of metric names"
                )
            for item in raw_args:
                metric_code = self._missing_arg_metric_code(item)
                if metric_code is None:
                    raise FormulaValidationError(
                        "operator missing accepts only metric names or metric refs"
                    )
                self._validate_metric_code(metric_code, allowed_metrics=allowed_metrics)
            return
        if op == "case":
            self._validate_case(
                raw_args,
                allowed_metrics=allowed_metrics,
                depth=depth,
                max_depth=max_depth,
                max_nodes=max_nodes,
                state=state,
            )
            return
        for arg in args:
            self._validate_node(
                arg,
                allowed_metrics=allowed_metrics,
                depth=depth + 1,
                max_depth=max_depth,
                max_nodes=max_nodes,
                state=state,
            )

    def _validate_case(
        self,
        raw_args: Any,
        *,
        allowed_metrics: set[str] | None,
        depth: int,
        max_depth: int,
        max_nodes: int,
        state: dict[str, int],
    ) -> None:
        if not isinstance(raw_args, list) or not raw_args:
            raise FormulaValidationError("operator case requires a non-empty list")
        if all(
            isinstance(item, dict) and ("if" in item or "else" in item)
            for item in raw_args
        ):
            for item in raw_args:
                allowed_keys = {"if", "then"} if "if" in item else {"else"}
                if set(item.keys()) != allowed_keys:
                    raise FormulaValidationError(
                        "case entries must be {'if','then'} or {'else'}"
                    )
                if "if" in item:
                    self._validate_node(
                        item["if"],
                        allowed_metrics=allowed_metrics,
                        depth=depth + 1,
                        max_depth=max_depth,
                        max_nodes=max_nodes,
                        state=state,
                    )
                    self._validate_node(
                        item["then"],
                        allowed_metrics=allowed_metrics,
                        depth=depth + 1,
                        max_depth=max_depth,
                        max_nodes=max_nodes,
                        state=state,
                    )
                else:
                    self._validate_node(
                        item["else"],
                        allowed_metrics=allowed_metrics,
                        depth=depth + 1,
                        max_depth=max_depth,
                        max_nodes=max_nodes,
                        state=state,
                    )
            return
        if len(raw_args) < 3 or len(raw_args) % 2 == 0:
            raise FormulaValidationError(
                "flat case form requires condition/value pairs plus a default"
            )
        for arg in raw_args:
            self._validate_node(
                arg,
                allowed_metrics=allowed_metrics,
                depth=depth + 1,
                max_depth=max_depth,
                max_nodes=max_nodes,
                state=state,
            )

    def _eval(
        self,
        node: Any,
        *,
        metrics: dict[str, Any],
        context: dict[str, Any],
        state: _EvalState,
    ) -> Any:
        if isinstance(node, dict):
            op, raw_args = next(iter(node.items()))
            if op == self.METRIC_OPERATOR:
                return self._metric_value(str(raw_args), metrics=metrics, state=state)
            args = raw_args if isinstance(raw_args, list) else [raw_args]
            if op == "and":
                values = [
                    self._eval(arg, metrics=metrics, context=context, state=state)
                    for arg in args
                ]
                return all(self._truthy(value) for value in values)
            if op == "or":
                values = [
                    self._eval(arg, metrics=metrics, context=context, state=state)
                    for arg in args
                ]
                return any(self._truthy(value) for value in values)
            if op == "not":
                return not self._truthy(
                    self._eval(args[0], metrics=metrics, context=context, state=state)
                )
            if op in {">", ">=", "<", "<=", "==", "!="}:
                return self._compare(
                    op, args, metrics=metrics, context=context, state=state
                )
            if op in {"+", "-", "*", "/", "max", "min"}:
                return self._numeric_op(
                    op, args, metrics=metrics, context=context, state=state
                )
            if op == "abs":
                value = self._eval(
                    args[0], metrics=metrics, context=context, state=state
                )
                return None if value is None else abs(self._to_decimal(value))
            if op == "round":
                return self._round(args, metrics=metrics, context=context, state=state)
            if op == "coalesce":
                for arg in args:
                    value = self._eval(
                        arg, metrics=metrics, context=context, state=state
                    )
                    if value is not None:
                        return value
                return None
            if op == "missing":
                return self._missing(raw_args, metrics=metrics, state=state)
            if op == "case":
                return self._case(
                    raw_args, metrics=metrics, context=context, state=state
                )
            if op == "in":
                return self._in(args, metrics=metrics, context=context, state=state)
            if op == "between":
                return self._between(
                    args, metrics=metrics, context=context, state=state
                )
            if op == "percent_change":
                return self._percent_change(
                    args, metrics=metrics, context=context, state=state
                )
            raise FormulaValidationError(f"unknown operator: {op}")
        if isinstance(node, list):
            return [
                self._eval(item, metrics=metrics, context=context, state=state)
                for item in node
            ]
        return node

    def _metric_value(
        self, metric_code: str, *, metrics: dict[str, Any], state: _EvalState
    ) -> Any:
        if metric_code not in metrics:
            state.missing(metric_code)
            return None
        raw_value = metrics.get(metric_code)
        value = (
            raw_value.get("value")
            if isinstance(raw_value, dict) and "value" in raw_value
            else raw_value
        )
        if value is None:
            state.missing(metric_code)
        return value

    def _compare(
        self,
        op: str,
        args: list[Any],
        *,
        metrics: dict[str, Any],
        context: dict[str, Any],
        state: _EvalState,
    ) -> bool:
        left = self._eval(args[0], metrics=metrics, context=context, state=state)
        right = self._eval(args[1], metrics=metrics, context=context, state=state)
        if left is None or right is None:
            state.warn(f"operator {op} evaluated false because an argument is missing")
            return False
        if op in {"==", "!="}:
            result = left == right
            return result if op == "==" else not result
        left_num = self._to_decimal(left)
        right_num = self._to_decimal(right)
        if op == ">":
            return left_num > right_num
        if op == ">=":
            return left_num >= right_num
        if op == "<":
            return left_num < right_num
        if op == "<=":
            return left_num <= right_num
        raise FormulaValidationError(f"unknown comparison operator: {op}")

    def _numeric_op(
        self,
        op: str,
        args: list[Any],
        *,
        metrics: dict[str, Any],
        context: dict[str, Any],
        state: _EvalState,
    ) -> Decimal | None:
        values = [
            self._eval(arg, metrics=metrics, context=context, state=state)
            for arg in args
        ]
        if any(value is None for value in values):
            state.warn(f"operator {op} returned null because an argument is missing")
            return None
        numbers = [self._to_decimal(value) for value in values]
        if op == "+":
            return sum(numbers, start=Decimal("0"))
        if op == "-":
            if len(numbers) == 1:
                return -numbers[0]
            result = numbers[0]
            for number in numbers[1:]:
                result -= number
            return result
        if op == "*":
            result = Decimal("1")
            for number in numbers:
                result *= number
            return result
        if op == "/":
            result = numbers[0]
            for divisor in numbers[1:]:
                if divisor == 0:
                    state.warn("division by zero")
                    return None
                result /= divisor
            return result
        if op == "max":
            return max(numbers)
        if op == "min":
            return min(numbers)
        raise FormulaValidationError(f"unknown numeric operator: {op}")

    def _round(
        self,
        args: list[Any],
        *,
        metrics: dict[str, Any],
        context: dict[str, Any],
        state: _EvalState,
    ) -> Decimal | None:
        value = self._eval(args[0], metrics=metrics, context=context, state=state)
        if value is None:
            state.warn("operator round returned null because an argument is missing")
            return None
        number = self._to_decimal(value)
        digits = 0
        if len(args) == 2:
            raw_digits = self._eval(
                args[1], metrics=metrics, context=context, state=state
            )
            if raw_digits is None:
                state.warn("operator round returned null because precision is missing")
                return None
            digits_decimal = self._to_decimal(raw_digits)
            if digits_decimal != digits_decimal.to_integral_value():
                raise FormulaValidationError(
                    "operator round precision must be an integer"
                )
            digits = int(digits_decimal)
            if digits < 0 or digits > 12:
                raise FormulaValidationError(
                    "operator round precision must be between 0 and 12"
                )
        quant = Decimal("1") if digits == 0 else Decimal("1").scaleb(-digits)
        return number.quantize(quant, rounding=ROUND_HALF_UP)

    def _missing(
        self, raw_args: list[Any], *, metrics: dict[str, Any], state: _EvalState
    ) -> list[str]:
        missing: list[str] = []
        for item in raw_args:
            metric_code = self._missing_arg_metric_code(item)
            if metric_code is None:
                raise FormulaValidationError(
                    "operator missing accepts only metric names or metric refs"
                )
            raw_value = metrics.get(metric_code)
            value = (
                raw_value.get("value")
                if isinstance(raw_value, dict) and "value" in raw_value
                else raw_value
            )
            if metric_code not in metrics or value is None:
                state.missing(metric_code)
                missing.append(metric_code)
        return missing

    def _case(
        self,
        raw_args: list[Any],
        *,
        metrics: dict[str, Any],
        context: dict[str, Any],
        state: _EvalState,
    ) -> Any:
        if all(
            isinstance(item, dict) and ("if" in item or "else" in item)
            for item in raw_args
        ):
            for item in raw_args:
                if "if" in item and self._truthy(
                    self._eval(
                        item["if"], metrics=metrics, context=context, state=state
                    )
                ):
                    return self._eval(
                        item["then"], metrics=metrics, context=context, state=state
                    )
                if "else" in item:
                    return self._eval(
                        item["else"], metrics=metrics, context=context, state=state
                    )
            return None
        for idx in range(0, len(raw_args) - 1, 2):
            if self._truthy(
                self._eval(raw_args[idx], metrics=metrics, context=context, state=state)
            ):
                return self._eval(
                    raw_args[idx + 1], metrics=metrics, context=context, state=state
                )
        return self._eval(raw_args[-1], metrics=metrics, context=context, state=state)

    def _in(
        self,
        args: list[Any],
        *,
        metrics: dict[str, Any],
        context: dict[str, Any],
        state: _EvalState,
    ) -> bool:
        needle = self._eval(args[0], metrics=metrics, context=context, state=state)
        haystack = self._eval(args[1], metrics=metrics, context=context, state=state)
        if needle is None or haystack is None:
            state.warn("operator in evaluated false because an argument is missing")
            return False
        if not isinstance(haystack, (list, tuple, set, str)):
            raise FormulaValidationError(
                "operator in requires a list or string as the second argument"
            )
        if isinstance(haystack, str) and not isinstance(needle, str):
            raise FormulaValidationError(
                "operator in requires a string needle for string haystack"
            )
        return needle in haystack

    def _between(
        self,
        args: list[Any],
        *,
        metrics: dict[str, Any],
        context: dict[str, Any],
        state: _EvalState,
    ) -> bool:
        values = [
            self._eval(arg, metrics=metrics, context=context, state=state)
            for arg in args
        ]
        if any(value is None for value in values):
            state.warn(
                "operator between evaluated false because an argument is missing"
            )
            return False
        value, lower, upper = (self._to_decimal(item) for item in values)
        return lower <= value <= upper

    def _percent_change(
        self,
        args: list[Any],
        *,
        metrics: dict[str, Any],
        context: dict[str, Any],
        state: _EvalState,
    ) -> Decimal | None:
        current_raw = self._eval(args[0], metrics=metrics, context=context, state=state)
        previous_raw = self._eval(
            args[1], metrics=metrics, context=context, state=state
        )
        if current_raw is None or previous_raw is None:
            state.warn(
                "operator percent_change returned null because an argument is missing"
            )
            return None
        current = self._to_decimal(current_raw)
        previous = self._to_decimal(previous_raw)
        if previous == 0:
            state.warn("percent_change division by zero")
            return None
        return ((current - previous) / abs(previous)) * Decimal("100")

    @staticmethod
    def _truthy(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, Decimal):
            return value != 0
        return bool(value)

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        if isinstance(value, bool):
            raise FormulaValidationError("boolean value is not numeric")
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise FormulaValidationError(f"invalid numeric value: {value!r}")
            return value
        if isinstance(value, (int, float)):
            try:
                number = Decimal(str(value))
            except (InvalidOperation, ValueError) as exc:
                raise FormulaValidationError(
                    f"invalid numeric value: {value!r}"
                ) from exc
            if not number.is_finite():
                raise FormulaValidationError(f"invalid numeric value: {value!r}")
            return number
        raise FormulaValidationError(
            f"operator requires numeric argument, got {type(value).__name__}"
        )

    @staticmethod
    def _missing_arg_metric_code(item: Any) -> str | None:
        if isinstance(item, str) and item.strip():
            return item
        if (
            isinstance(item, dict)
            and set(item.keys()) == {"metric"}
            and isinstance(item.get("metric"), str)
        ):
            return str(item["metric"])
        return None

    @staticmethod
    def _allowed_metrics(
        *, metrics: dict[str, Any], context: dict[str, Any]
    ) -> set[str] | None:
        for key in ("allowed_metrics", "metric_codes", "known_metrics"):
            raw = context.get(key)
            if raw is not None:
                return {str(item) for item in raw}
        catalog = context.get("metric_catalog")
        if isinstance(catalog, dict):
            return {str(item) for item in catalog.keys()}
        return None

    @staticmethod
    def _validate_metric_code(
        metric_code: str, *, allowed_metrics: set[str] | None
    ) -> None:
        if allowed_metrics is not None and metric_code not in allowed_metrics:
            raise FormulaValidationError(f"unknown metric: {metric_code}")
