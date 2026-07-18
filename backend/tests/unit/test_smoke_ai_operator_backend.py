from scripts.smoke_ai_operator_backend import (
    PerformanceThresholds,
    SmokeResult,
    apply_performance_thresholds,
    checker_audit,
    collect_unavailable_sources,
    dangerous_feature_flag_statuses,
    endpoint,
    http_failure_detail,
    missing_fields,
    normalize_api_prefix,
    module_state_lines,
    parse_threshold_ms,
    parse_nm_id,
    performance_thresholds_from_env,
    short_detail,
)


def test_smoke_module_state_lines_print_optional_degradation() -> None:
    lines = module_state_lines(
        {
            "modules": {
                "finance": {"status": "ok", "visible": True, "navigation_group": "core", "reason": "ready"},
                "reputation": {
                    "status": "not_configured",
                    "visible": False,
                    "navigation_group": "hidden",
                    "reason": "REPUTATION_BASE_URL is missing",
                },
            }
        }
    )

    assert "module finance: status=ok; visible=True; group=core; reason=ready" in lines
    assert (
        "optional reputation: status=not_configured; visible=False; "
        "group=hidden; reason=REPUTATION_BASE_URL is missing"
    ) in lines


def test_smoke_contract_field_and_unavailable_detection() -> None:
    payload = {
        "status": "ok",
        "items": [],
        "unavailable_sources": ["reputation"],
        "modules": {
            "claims": {"status": "disabled"},
            "finance": {"status": "ok"},
        },
    }

    assert missing_fields(payload, {"status", "items"}) == []
    assert missing_fields(payload, {"status", "total"}) == ["total"]
    assert collect_unavailable_sources(payload) == ["claims", "reputation"]


def test_smoke_checker_audit_records_unambiguous_state() -> None:
    modules = SmokeResult(
        label="modules_health",
        method="GET",
        path="/api/v1/portal/modules/health",
        ok=True,
        status_code=200,
        detail="ok",
        data={"modules": {"checker": {"status": "not_configured"}}},
    )
    quality = SmokeResult(
        label="product_quality",
        method="GET",
        path="/api/v1/portal/products/1001/quality",
        ok=True,
        status_code=200,
        detail="ok",
        data={"status": "not_configured", "module": "checker", "issues": []},
    )

    assert checker_audit(modules, quality) == {
        "checker_state": "not_configured",
        "quality_endpoint_status": 200,
        "quality_status": "not_configured",
    }

    modules.data = {"modules": {"checker": {"status": "ok"}}}
    quality.data = {"status": "ok", "module": "checker", "issues": []}
    assert checker_audit(modules, quality)["checker_state"] == "configured_readonly"


def test_smoke_dangerous_feature_flags_are_safe_by_default(monkeypatch) -> None:
    for name in (
        "ENABLE_REPUTATION_PUBLISH",
        "ENABLE_REPUTATION_WRITE_ACTIONS",
        "ENABLE_CLAIMS_SUBMIT",
        "ENABLE_GROUPING_MERGE",
        "ENABLE_CARD_AUTO_APPLY",
    ):
        monkeypatch.delenv(name, raising=False)

    assert all(flag.safe for flag in dangerous_feature_flag_statuses())

    monkeypatch.setenv("ENABLE_CLAIMS_SUBMIT", "true")
    statuses = {flag.name: flag.safe for flag in dangerous_feature_flag_statuses()}
    assert statuses["ENABLE_CLAIMS_SUBMIT"] is False


def test_smoke_http_failure_detail_is_clear() -> None:
    assert http_failure_detail(401, {"detail": "Not authenticated"}, "Unauthorized") == (
        "authentication failed; Not authenticated"
    )
    assert http_failure_detail(403, {"detail": "Forbidden"}, "Forbidden") == "account forbidden or role denied; Forbidden"
    assert http_failure_detail(422, {"detail": [{"loc": ["query", "account_id"]}]}, "Unprocessable Entity") == (
        "request validation failed; validation_errors=1"
    )
    assert http_failure_detail(500, None, "Internal Server Error") == "server error; non-json response"
    assert "Bearer [redacted]" in http_failure_detail(
        500,
        {"detail": "upstream leaked Bearer abc.def.ghi"},
        "Internal Server Error",
    )


def test_smoke_api_prefix_and_endpoint_paths_are_configurable() -> None:
    assert normalize_api_prefix(None) == ""
    assert normalize_api_prefix("/") == ""
    assert normalize_api_prefix("api/v1") == "/api/v1"

    spec = endpoint("/api/v1", "doctor", "/portal/doctor", {"status"}, {"account_id": "1"})
    assert spec.method == "GET"
    assert spec.path == "/api/v1/portal/doctor"
    assert spec.query == {"account_id": "1"}


def test_smoke_short_detail_is_single_line_and_bounded() -> None:
    detail = short_detail("first line\n" + ("x" * 400))
    assert "\n" not in detail
    assert len(detail) <= 240


def test_smoke_parse_nm_id() -> None:
    assert parse_nm_id("123") == 123
    assert parse_nm_id("") is None
    assert parse_nm_id("not-a-number") is None


def test_smoke_performance_threshold_parsing_uses_safe_defaults() -> None:
    assert parse_threshold_ms("2500", 1500.0) == 2500.0
    assert parse_threshold_ms("0", 1500.0) == 1500.0
    assert parse_threshold_ms("not-a-number", 1500.0) == 1500.0

    thresholds = performance_thresholds_from_env(
        {
            "SMOKE_ENV": "staging",
            "SMOKE_PERF_WARNING_MS": "1200",
            "SMOKE_PERF_FAIL_MS": "2800",
        }
    )

    assert thresholds.warning_ms == 1200.0
    assert thresholds.fail_ms == 2800.0
    assert thresholds.enforce_overview_failure is True


def test_smoke_performance_warning_does_not_fail_regular_endpoint() -> None:
    result = SmokeResult(
        label="actions",
        method="GET",
        path="/api/v1/portal/actions",
        ok=True,
        status_code=200,
        detail="contract=ok",
        elapsed_ms=1600.0,
    )

    evaluated = apply_performance_thresholds(result, PerformanceThresholds(warning_ms=1500.0))

    assert evaluated.ok is True
    assert evaluated.performance_status == "warn"
    assert "1500ms" in str(evaluated.performance_detail)


def test_smoke_staging_overview_over_fail_threshold_fails_unless_overridden() -> None:
    slow_overview = SmokeResult(
        label="overview",
        method="GET",
        path="/api/v1/portal/overview",
        ok=True,
        status_code=200,
        detail="contract=ok",
        elapsed_ms=3100.0,
    )

    failed = apply_performance_thresholds(
        slow_overview,
        PerformanceThresholds(environment="staging", fail_ms=3000.0),
    )

    assert failed.ok is False
    assert failed.performance_status == "fail"

    overridden = apply_performance_thresholds(
        SmokeResult(
            label="overview",
            method="GET",
            path="/api/v1/portal/overview",
            ok=True,
            status_code=200,
            detail="contract=ok",
            elapsed_ms=3100.0,
        ),
        PerformanceThresholds(environment="staging", fail_ms=3000.0, allow_slow_overview=True),
    )

    assert overridden.ok is True
    assert overridden.performance_status == "warn"
