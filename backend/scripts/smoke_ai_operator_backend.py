from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TIMEOUT_SECONDS = 20
DEFAULT_API_PREFIX = "/api/v1"
MAX_DETAIL_CHARS = 240
DEFAULT_PERF_WARNING_MS = 1500.0
DEFAULT_PERF_FAIL_MS = 3000.0
OVERVIEW_PERF_LABELS = {"overview", "dashboard_overview"}
OPTIONAL_DEGRADED_STATUSES = {"disabled", "not_configured", "unavailable", "degraded", "empty"}
DANGEROUS_FEATURE_FLAGS = (
    "ENABLE_REPUTATION_PUBLISH",
    "ENABLE_REPUTATION_WRITE_ACTIONS",
    "ENABLE_CLAIMS_SUBMIT",
    "ENABLE_GROUPING_MERGE",
    "ENABLE_CARD_AUTO_APPLY",
)
TRUTHY = {"1", "true", "yes", "on", "enabled"}


@dataclass
class EndpointSpec:
    label: str
    method: str
    path: str
    required_fields: set[str]
    query: dict[str, str] = field(default_factory=dict)


@dataclass
class SmokeResult:
    label: str
    method: str
    path: str
    ok: bool
    status_code: int | None
    detail: str
    elapsed_ms: float | None = None
    missing_fields: list[str] = field(default_factory=list)
    unavailable_sources: list[str] = field(default_factory=list)
    performance_status: str = "ok"
    performance_detail: str | None = None
    data: dict[str, Any] | None = None


@dataclass(frozen=True)
class PerformanceThresholds:
    warning_ms: float = DEFAULT_PERF_WARNING_MS
    fail_ms: float = DEFAULT_PERF_FAIL_MS
    environment: str = "development"
    allow_slow_overview: bool = False

    @property
    def enforce_overview_failure(self) -> bool:
        return self.environment.strip().lower() == "staging" and not self.allow_slow_overview


@dataclass
class FlagStatus:
    name: str
    value: str | None
    safe: bool


def main() -> int:
    base_url = os.environ.get("BASE_URL", "").strip().rstrip("/")
    api_prefix = normalize_api_prefix(os.environ.get("API_PREFIX", DEFAULT_API_PREFIX))
    access_token = os.environ.get("ACCESS_TOKEN", "").strip()
    account_id = os.environ.get("ACCOUNT_ID", "").strip()
    explicit_nm_id = os.environ.get("NM_ID", "").strip()
    performance_thresholds = performance_thresholds_from_env(os.environ)

    missing = [name for name, value in (("BASE_URL", base_url), ("ACCESS_TOKEN", access_token), ("ACCOUNT_ID", account_id)) if not value]
    if missing:
        print(f"FAIL config: missing env {', '.join(missing)}")
        return 2

    results: list[SmokeResult] = []
    common_query = {"account_id": account_id}

    base_specs = [
        endpoint(api_prefix, "modules_health", "/portal/modules/health", {"computed_at", "modules", "unavailable_sources"}, common_query),
        endpoint(api_prefix, "doctor", "/portal/doctor", {"status", "trust_state", "headline", "unavailable_sources"}, common_query),
        endpoint(api_prefix, "overview", "/portal/overview", {"module_health", "unavailable_sources", "top_actions"}, common_query),
        endpoint(api_prefix, "actions", "/portal/actions", {"total", "items", "unavailable_sources"}, common_query),
        endpoint(api_prefix, "products", "/portal/products", {"total", "items", "unavailable_sources"}, common_query),
        endpoint(api_prefix, "reputation_summary", "/portal/reputation/summary", {"status", "unavailable_sources", "trust_state"}, common_query),
        endpoint(api_prefix, "reputation_inbox", "/portal/reputation/inbox", {"status", "total", "items", "unavailable_sources"}, common_query),
        endpoint(api_prefix, "cases", "/portal/cases", {"status", "total", "items", "unavailable_sources"}, common_query),
        endpoint(api_prefix, "results", "/portal/results", {"status", "total", "items", "unavailable_sources"}, common_query),
    ]

    products: SmokeResult | None = None
    modules_health: SmokeResult | None = None
    for spec in base_specs:
        result = call(base_url, access_token, spec)
        results.append(result)
        if spec.label == "modules_health":
            modules_health = result
        if spec.label == "products":
            products = result

    nm_id = parse_nm_id(explicit_nm_id) or first_nm_id(products.data if products else None)
    quality_result: SmokeResult | None = None
    if nm_id is None:
        results.append(
            SmokeResult(
                label="product_360",
                method="GET",
                path=f"{api_prefix}/portal/products/{{nm_id}}",
                ok=False,
                status_code=None,
                detail="missing NM_ID and products response did not contain an nm_id",
                missing_fields=["nm_id"],
            )
        )
    else:
        results.append(
            call(
                base_url,
                access_token,
                endpoint(
                    api_prefix,
                    "product_360",
                    f"/portal/products/{nm_id}",
                    {
                        "nm_id",
                        "identity",
                        "money",
                        "costs",
                        "quality",
                        "reputation",
                        "claims",
                        "grouping",
                        "actions",
                        "history",
                        "result_history",
                        "next_best_action",
                        "unavailable_sources",
                    },
                    common_query,
                ),
            )
        )
        quality_result = call(
            base_url,
            access_token,
            endpoint(
                api_prefix,
                "product_quality",
                f"/portal/products/{nm_id}/quality",
                {"status", "module", "issues"},
                common_query,
            ),
        )
        results.append(quality_result)

    flag_statuses = dangerous_feature_flag_statuses()
    results = [apply_performance_thresholds(result, performance_thresholds) for result in results]

    for result in results:
        status = "PASS" if result.ok else "FAIL"
        code = result.status_code if result.status_code is not None else "n/a"
        elapsed = f"{result.elapsed_ms:.1f}ms" if result.elapsed_ms is not None else "n/a"
        print(f"{status} {result.label}: {result.method} {result.path} -> {code} {elapsed} {result.detail}")
        if result.performance_status == "warn":
            print(f"  performance_warning={result.performance_detail}")
        elif result.performance_status == "fail":
            print(f"  performance_failure={result.performance_detail}")
        if result.missing_fields:
            print(f"  missing_fields={result.missing_fields}")
        if result.unavailable_sources:
            print(f"  unavailable_sources={result.unavailable_sources}")
        if result.label == "modules_health" and result.data:
            for line in module_state_lines(result.data):
                print(f"  {line}")

    print(f"Checker audit: {json.dumps(checker_audit(modules_health, quality_result), ensure_ascii=False, sort_keys=True)}")

    print("Dangerous feature flags:")
    for flag in flag_statuses:
        rendered = flag.value if flag.value not in {None, ""} else "unset/false"
        status = "PASS" if flag.safe else "FAIL"
        print(f"  {status} {flag.name}={rendered}")

    return 0 if all(result.ok for result in results) and all(flag.safe for flag in flag_statuses) else 1


def normalize_api_prefix(value: str | None) -> str:
    raw = (value or "").strip()
    if raw in {"", "/"}:
        return ""
    return f"/{raw.strip('/')}"


def endpoint(
    api_prefix: str,
    label: str,
    portal_path: str,
    required_fields: set[str],
    query: dict[str, str],
    method: str = "GET",
) -> EndpointSpec:
    return EndpointSpec(label, method, f"{api_prefix}{portal_path}", required_fields, query)


def call(base_url: str, access_token: str, spec: EndpointSpec) -> SmokeResult:
    url = f"{base_url}{spec.path}"
    if spec.query:
        url = f"{url}?{urlencode(spec.query)}"
    request = Request(
        url,
        method=spec.method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
            elapsed_ms = (time.perf_counter() - started) * 1000
            data = parse_json(body)
            missing = missing_fields(data, spec.required_fields)
            ok = 200 <= int(response.status) < 300 and data is not None and not missing
            detail = contract_detail(data, missing)
            return SmokeResult(
                label=spec.label,
                method=spec.method,
                path=spec.path,
                ok=ok,
                status_code=int(response.status),
                detail=detail,
                elapsed_ms=elapsed_ms,
                missing_fields=missing,
                unavailable_sources=collect_unavailable_sources(data),
                data=data,
            )
    except HTTPError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        body = exc.read().decode("utf-8", errors="replace")
        data = parse_json(body)
        return SmokeResult(
            label=spec.label,
            method=spec.method,
            path=spec.path,
            ok=False,
            status_code=int(exc.code),
            detail=http_failure_detail(int(exc.code), data, exc.reason),
            elapsed_ms=elapsed_ms,
            data=data,
        )
    except URLError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return SmokeResult(label=spec.label, method=spec.method, path=spec.path, ok=False, status_code=None, detail=str(exc.reason), elapsed_ms=elapsed_ms)
    except TimeoutError:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return SmokeResult(label=spec.label, method=spec.method, path=spec.path, ok=False, status_code=None, detail="timeout", elapsed_ms=elapsed_ms)


def parse_json(body: str) -> dict[str, Any] | None:
    if not body.strip():
        return {}
    try:
        value = json.loads(body)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else {"data": value}


def missing_fields(data: dict[str, Any] | None, required_fields: set[str]) -> list[str]:
    if data is None:
        return sorted(required_fields)
    return sorted(field for field in required_fields if field not in data)


def contract_detail(data: dict[str, Any] | None, missing: list[str]) -> str:
    if data is None:
        return "non-json response"
    if missing:
        return "contract fields missing"
    return short_detail(safe_detail(data))


def safe_detail(data: dict[str, Any] | None) -> str:
    if data is None:
        return "non-json response"
    status = data.get("status")
    unavailable = data.get("unavailable_sources")
    total = data.get("total")
    if status is not None and unavailable:
        return f"status={status}; unavailable_sources={unavailable}"
    if status is not None:
        return f"status={status}"
    if unavailable:
        return f"unavailable_sources={unavailable}"
    if total is not None:
        return f"total={total}"
    return "contract=ok"


def http_failure_detail(status_code: int, data: dict[str, Any] | None, reason: str) -> str:
    status_label = {
        401: "authentication failed",
        403: "account forbidden or role denied",
        422: "request validation failed",
        500: "server error",
    }.get(status_code, reason or "http error")
    detail = safe_detail(data)
    if data is not None:
        raw_detail = data.get("detail")
        if isinstance(raw_detail, str):
            detail = raw_detail
        elif isinstance(raw_detail, list):
            detail = f"validation_errors={len(raw_detail)}"
    return short_detail(f"{status_label}; {detail}")


def short_detail(value: str) -> str:
    redacted = scrub_secret_like_text(value.replace("\n", " ").strip())
    if len(redacted) <= MAX_DETAIL_CHARS:
        return redacted
    return f"{redacted[: MAX_DETAIL_CHARS - 3]}..."


def scrub_secret_like_text(value: str) -> str:
    patterns = (
        (r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [redacted]"),
        (r"(?i)(token|jwt|secret|password|api[_-]?key)=([^;&\s]+)", r"\1=[redacted]"),
    )
    scrubbed = value
    for pattern, replacement in patterns:
        scrubbed = re.sub(pattern, replacement, scrubbed)
    return scrubbed


def collect_unavailable_sources(data: dict[str, Any] | None) -> list[str]:
    if not isinstance(data, dict):
        return []
    values: list[str] = []
    raw = data.get("unavailable_sources")
    if isinstance(raw, list):
        values.extend(str(item) for item in raw)
    modules = data.get("modules")
    if isinstance(modules, dict) and "modules" in modules and isinstance(modules.get("modules"), dict):
        modules = modules["modules"]
    if isinstance(modules, dict):
        for name, item in modules.items():
            if isinstance(item, dict) and str(item.get("status") or "") in OPTIONAL_DEGRADED_STATUSES:
                values.append(str(name))
    return sorted(set(values))


def module_state_lines(data: dict[str, Any]) -> list[str]:
    modules = data.get("modules")
    if isinstance(modules, dict) and "modules" in modules and isinstance(modules.get("modules"), dict):
        modules = modules["modules"]
    if not isinstance(modules, dict):
        return []
    lines: list[str] = []
    for name in sorted(modules):
        item = modules.get(name)
        if not isinstance(item, dict):
            continue
        status = item.get("status") or "unknown"
        visible = item.get("visible")
        group = item.get("navigation_group")
        reason = item.get("reason") or item.get("message") or ""
        prefix = "optional" if status in OPTIONAL_DEGRADED_STATUSES else "module"
        lines.append(f"{prefix} {name}: status={status}; visible={visible}; group={group}; reason={reason}")
    return lines


def checker_audit(modules_health: SmokeResult | None, quality_result: SmokeResult | None) -> dict[str, Any]:
    checker_status = module_status(modules_health.data if modules_health else None, "checker")
    quality_status = None
    if isinstance(quality_result, SmokeResult) and isinstance(quality_result.data, dict):
        quality_status = quality_result.data.get("status")
    if checker_status == "ok" and quality_status == "ok":
        checker_state = "configured_readonly"
    elif checker_status == "not_configured" or quality_status == "not_configured":
        checker_state = "not_configured"
    else:
        checker_state = str(checker_status or quality_status or "unavailable")
    return {
        "checker_state": checker_state,
        "quality_endpoint_status": quality_result.status_code if quality_result is not None else None,
        "quality_status": quality_status,
    }


def module_status(data: dict[str, Any] | None, module_name: str) -> str | None:
    if not isinstance(data, dict):
        return None
    modules = data.get("modules")
    if isinstance(modules, dict) and "modules" in modules and isinstance(modules.get("modules"), dict):
        modules = modules["modules"]
    if not isinstance(modules, dict):
        return None
    item = modules.get(module_name)
    return str(item.get("status")) if isinstance(item, dict) and item.get("status") is not None else None


def dangerous_feature_flag_statuses() -> list[FlagStatus]:
    statuses: list[FlagStatus] = []
    for name in DANGEROUS_FEATURE_FLAGS:
        value = os.environ.get(name)
        safe = str(value or "").strip().lower() not in TRUTHY
        statuses.append(FlagStatus(name=name, value=value, safe=safe))
    return statuses


def parse_threshold_ms(value: str | None, default: float) -> float:
    raw = str(value or "").strip()
    if not raw:
        return default
    try:
        parsed = float(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def performance_thresholds_from_env(env: Mapping[str, str]) -> PerformanceThresholds:
    environment = (
        env.get("SMOKE_ENV")
        or env.get("APP_ENV")
        or env.get("ENVIRONMENT")
        or "development"
    )
    return PerformanceThresholds(
        warning_ms=parse_threshold_ms(env.get("SMOKE_PERF_WARNING_MS"), DEFAULT_PERF_WARNING_MS),
        fail_ms=parse_threshold_ms(env.get("SMOKE_PERF_FAIL_MS"), DEFAULT_PERF_FAIL_MS),
        environment=str(environment),
        allow_slow_overview=str(env.get("SMOKE_ALLOW_SLOW_OVERVIEW") or "").strip().lower() in TRUTHY,
    )


def apply_performance_thresholds(result: SmokeResult, thresholds: PerformanceThresholds) -> SmokeResult:
    if result.elapsed_ms is None:
        return result
    elapsed = float(result.elapsed_ms)
    if (
        thresholds.enforce_overview_failure
        and result.label in OVERVIEW_PERF_LABELS
        and elapsed > thresholds.fail_ms
    ):
        result.ok = False
        result.performance_status = "fail"
        result.performance_detail = (
            f"{elapsed:.1f}ms > {thresholds.fail_ms:.0f}ms staging overview limit"
        )
        return result
    if elapsed > thresholds.warning_ms:
        result.performance_status = "warn"
        result.performance_detail = f"{elapsed:.1f}ms > {thresholds.warning_ms:.0f}ms warning threshold"
    return result


def parse_nm_id(value: str) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        print("WARN config: NM_ID is not an integer; falling back to first product nm_id")
        return None


def first_nm_id(data: dict[str, Any] | None) -> int | None:
    if not data:
        return None
    items = data.get("items")
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get("nm_id")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            continue
    return None


if __name__ == "__main__":
    sys.exit(main())
