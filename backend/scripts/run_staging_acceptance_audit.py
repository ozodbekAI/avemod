#!/usr/bin/env python3
"""Run the final staging runtime, RBAC, performance, and scrub audit."""

from __future__ import annotations

import json
import os
import re
import shutil
import statistics
import sys
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_full_runtime_endpoint_audit import REDACTED, sanitize  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "audit_staging_final"
REQUIRED_ENV = (
    "BASE_URL",
    "ADMIN_ACCESS_TOKEN",
    "SELLER_ACCESS_TOKEN",
    "SELLER_OWN_ACCOUNT_ID",
    "FORBIDDEN_ACCOUNT_ID",
)
OPTIONAL_ENV = ("SELLER_TEST_NM_ID", "AUDIT_DATE_FROM", "AUDIT_DATE_TO")
FOLDERS = (
    "00_manifest",
    "01_env",
    "02_runtime",
    "03_rbac",
    "04_performance",
    "05_contracts",
    "06_security",
    "07_scorecard",
)
CORE_THRESHOLDS_MS = {
    "/api/v1/portal/doctor": 3000,
    "/api/v1/portal/actions": 3000,
    "/api/v1/portal/products": 3000,
    "/api/v1/portal/products/{nm_id}": 3000,
    "/api/v1/portal/modules/health": 1000,
}
BLOCKED_TERMS = (
    "Bearer eyJ",
    "access_token",
    "refresh_token",
    "password",
    "api_key",
    "WB token",
    "private key",
    "buyer phone",
    "buyer email",
    "full address",
)
TOKEN_LIKE_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")


@dataclass(frozen=True)
class Config:
    base_url: str
    admin_token: str
    seller_token: str
    seller_account_id: str
    forbidden_account_id: str
    nm_id: str | None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def prepare_output() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for folder in FOLDERS:
        (OUTPUT_DIR / folder).mkdir(parents=True, exist_ok=True)


def missing_required_env(env: dict[str, str] | None = None) -> list[str]:
    source = env or os.environ
    return [name for name in REQUIRED_ENV if not (source.get(name) or "").strip()]


def load_config() -> Config | None:
    missing = missing_required_env()
    if missing:
        return None
    return Config(
        base_url=os.environ["BASE_URL"].strip().rstrip("/"),
        admin_token=os.environ["ADMIN_ACCESS_TOKEN"].strip(),
        seller_token=os.environ["SELLER_ACCESS_TOKEN"].strip(),
        seller_account_id=os.environ["SELLER_OWN_ACCOUNT_ID"].strip(),
        forbidden_account_id=os.environ["FORBIDDEN_ACCOUNT_ID"].strip(),
        nm_id=(os.getenv("SELLER_TEST_NM_ID") or "").strip() or None,
    )


def env_manifest(config: Config | None, missing: list[str]) -> dict[str, Any]:
    return {
        "generated_at": utc_now(),
        "base_url_present": bool(config and config.base_url),
        "admin_token_present": bool(config and config.admin_token),
        "seller_token_present": bool(config and config.seller_token),
        "seller_own_account_id": REDACTED if config else None,
        "forbidden_account_id": REDACTED if config else None,
        "optional_env_present": {name: bool((os.getenv(name) or "").strip()) for name in OPTIONAL_ENV},
        "missing_required_env": missing,
        "token_values_saved": False,
    }


def path_url(base_url: str, path: str, query: dict[str, Any] | None = None) -> str:
    clean_path = "/" + path.strip("/")
    if base_url.rstrip("/").endswith("/api/v1") and clean_path.startswith("/api/v1/"):
        clean_path = clean_path[len("/api/v1") :]
    url = f"{base_url.rstrip('/')}{clean_path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    return url


def safe_name(label: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", label).strip("_").lower() or "request"


def auth_header(token: str) -> dict[str, str]:
    return {"Accept": "application/json", "Authorization": f"Bearer {token}"}


def redacted_headers(token_present: bool) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if token_present:
        headers["Authorization"] = "Bearer <REDACTED>"
    return headers


def parse_response(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"text": response.text[:2000]}


def request_json(
    client: httpx.Client,
    config: Config,
    *,
    actor: str,
    token: str,
    method: str,
    path: str,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    status_code = 0
    parsed: Any = None
    error: str | None = None
    try:
        response = client.request(method, path_url(config.base_url, path, query), headers=auth_header(token), json=body)
        status_code = response.status_code
        parsed = parse_response(response)
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        error = exc.__class__.__name__
        parsed = {"error": error}
    duration_ms = int((time.perf_counter() - started) * 1000)
    safe_response, redactions = sanitize(parsed)
    safe_body, body_redactions = sanitize(body or {})
    record = {
        "ts": utc_now(),
        "actor": actor,
        "method": method,
        "path": path,
        "query": query or {},
        "status_code": status_code,
        "duration_ms": duration_ms,
        "request": {
            "headers": redacted_headers(True),
            "json": safe_body,
        },
        "response": safe_response,
        "redactions": redactions + body_redactions,
        "error": error,
    }
    folder = OUTPUT_DIR / ("03_rbac" if label and label.startswith("rbac_") else "02_runtime")
    write_json(folder / f"{safe_name(label or f'{actor}_{method}_{path}')}.json", record)
    return record


def first_nm_id(payload: Any) -> str | None:
    stack = [payload]
    while stack:
        node = stack.pop(0)
        if isinstance(node, dict):
            value = node.get("nm_id") or node.get("nmId")
            if value not in (None, ""):
                return str(value)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None


def first_updatable_action(payload: Any) -> dict[str, Any] | None:
    stack = [payload]
    while stack:
        node = stack.pop(0)
        if isinstance(node, dict):
            if node.get("can_update") is True and node.get("source_module") and node.get("source_id"):
                return node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None


def status_pass(record: dict[str, Any]) -> bool:
    return int(record.get("status_code") or 0) < 500 and int(record.get("status_code") or 0) != 0


def run_runtime(client: httpx.Client, config: Config) -> tuple[list[dict[str, Any]], str | None]:
    account = config.seller_account_id
    endpoints = [
        ("GET", "/api/v1/health", {}),
        ("GET", "/api/v1/auth/me", {}),
        ("GET", "/api/v1/accounts", {}),
        ("GET", "/api/v1/portal/modules/health", {"account_id": account}),
        ("GET", "/api/v1/portal/doctor", {"account_id": account}),
        ("GET", "/api/v1/portal/overview", {"account_id": account}),
        ("GET", "/api/v1/portal/actions", {"account_id": account}),
        ("GET", "/api/v1/portal/products", {"account_id": account, "limit": 20}),
        ("GET", "/api/v1/portal/results", {"account_id": account}),
        ("GET", "/api/v1/portal/cases", {"account_id": account}),
        ("GET", "/api/v1/portal/reputation/summary", {"account_id": account}),
        ("GET", "/api/v1/portal/reputation/inbox", {"account_id": account}),
    ]
    records = [
        request_json(
            client,
            config,
            actor="seller",
            token=config.seller_token,
            method=method,
            path=path,
            query=query,
            label=f"runtime_{index:02d}_{method}_{path}",
        )
        for index, (method, path, query) in enumerate(endpoints, start=1)
    ]
    products = next((item for item in records if item["path"] == "/api/v1/portal/products"), None)
    nm_id = config.nm_id or (first_nm_id(products.get("response")) if products else None)
    if nm_id:
        for suffix in ("", "/quality", "/grouping", "/events"):
            records.append(
                request_json(
                    client,
                    config,
                    actor="seller",
                    token=config.seller_token,
                    method="GET",
                    path=f"/api/v1/portal/products/{nm_id}{suffix}",
                    query={"account_id": account},
                    label=f"runtime_product_{nm_id}{suffix or '_detail'}",
                )
            )
    write_json(OUTPUT_DIR / "02_runtime" / "runtime_index.json", {"status": "DONE", "nm_id": nm_id, "records": records})
    return records, nm_id


def run_rbac(client: httpx.Client, config: Config, nm_id: str | None) -> tuple[list[dict[str, Any]], bool]:
    own = config.seller_account_id
    forbidden = config.forbidden_account_id
    own_paths = [
        "/api/v1/portal/doctor",
        "/api/v1/portal/actions",
        "/api/v1/portal/products",
        "/api/v1/portal/results",
        "/api/v1/portal/cases",
    ]
    if nm_id:
        own_paths.append(f"/api/v1/portal/products/{nm_id}")
    forbidden_paths = [
        "/api/v1/portal/doctor",
        "/api/v1/portal/actions",
        "/api/v1/portal/products",
        "/api/v1/portal/results",
        "/api/v1/portal/cases",
    ]
    records: list[dict[str, Any]] = []
    for path in own_paths:
        records.append(
            request_json(client, config, actor="seller", token=config.seller_token, method="GET", path=path, query={"account_id": own}, label=f"rbac_seller_own_{path}")
        )
    for path in forbidden_paths:
        records.append(
            request_json(
                client,
                config,
                actor="seller",
                token=config.seller_token,
                method="GET",
                path=path,
                query={"account_id": forbidden},
                label=f"rbac_seller_forbidden_{path}",
            )
        )
    for path in forbidden_paths:
        records.append(
            request_json(
                client,
                config,
                actor="admin",
                token=config.admin_token,
                method="GET",
                path=path,
                query={"account_id": forbidden},
                label=f"rbac_admin_forbidden_{path}",
            )
        )
    seller_own_pass = all(record["status_code"] == 200 for record in records if record["actor"] == "seller" and record["query"].get("account_id") == own)
    seller_forbidden_pass = all(record["status_code"] in {403, 404} for record in records if record["actor"] == "seller" and record["query"].get("account_id") == forbidden)
    matrix = {
        "seller_own_pass": seller_own_pass,
        "seller_forbidden_pass": seller_forbidden_pass,
        "admin_forbidden_observed": [
            {"path": record["path"], "status_code": record["status_code"]}
            for record in records
            if record["actor"] == "admin"
        ],
        "passed": seller_own_pass and seller_forbidden_pass,
        "records": records,
    }
    write_json(OUTPUT_DIR / "03_rbac" / "rbac_matrix.json", matrix)
    write_text(
        OUTPUT_DIR / "03_rbac" / "rbac_summary.md",
        "\n".join(
            [
                "# Staging RBAC Summary",
                "",
                f"- Seller own account 200 proof: `{seller_own_pass}`",
                f"- Seller forbidden account 403/404 proof: `{seller_forbidden_pass}`",
                f"- Overall RBAC pass: `{seller_own_pass and seller_forbidden_pass}`",
            ]
        ),
    )
    return records, seller_own_pass and seller_forbidden_pass


def run_action_patch(client: httpx.Client, config: Config, action_source: Any | None = None) -> dict[str, Any]:
    actions = action_source or request_json(
        client,
        config,
        actor="seller",
        token=config.seller_token,
        method="GET",
        path="/api/v1/portal/actions",
        query={"account_id": config.seller_account_id},
        label="runtime_action_patch_preload",
    )
    action = first_updatable_action(actions.get("response"))
    if not action:
        result = {
            "status": "NO_UPDATABLE_ACTION_AVAILABLE",
            "passed": False,
            "marketplace_external_writes": [],
        }
        write_json(OUTPUT_DIR / "05_contracts" / "action_patch_proof.json", result)
        return result
    payload = {
        "account_id": config.seller_account_id,
        "source_module": action["source_module"],
        "source_id": action["source_id"],
        "status": "in_progress",
    }
    patch = request_json(
        client,
        config,
        actor="seller",
        token=config.seller_token,
        method="PATCH",
        path="/api/v1/portal/actions/by-source",
        body=payload,
        label="runtime_action_patch_by_source",
    )
    reload_record = request_json(
        client,
        config,
        actor="seller",
        token=config.seller_token,
        method="GET",
        path="/api/v1/portal/actions",
        query={"account_id": config.seller_account_id},
        label="runtime_action_patch_reload",
    )
    result = {
        "status": "PASS" if patch["status_code"] == 200 else "FAIL",
        "passed": patch["status_code"] == 200,
        "patch_status_code": patch["status_code"],
        "reload_status_code": reload_record["status_code"],
        "marketplace_external_writes": [],
        "source_module": action["source_module"],
        "source_id": action["source_id"],
    }
    write_json(OUTPUT_DIR / "05_contracts" / "action_patch_proof.json", result)
    return result


def run_performance(client: httpx.Client, config: Config, nm_id: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    endpoint_map = {
        "/api/v1/portal/doctor": ("/api/v1/portal/doctor", {"account_id": config.seller_account_id}),
        "/api/v1/portal/actions": ("/api/v1/portal/actions", {"account_id": config.seller_account_id}),
        "/api/v1/portal/products": ("/api/v1/portal/products", {"account_id": config.seller_account_id, "limit": 20}),
        "/api/v1/portal/modules/health": ("/api/v1/portal/modules/health", {"account_id": config.seller_account_id}),
    }
    if nm_id:
        endpoint_map["/api/v1/portal/products/{nm_id}"] = (f"/api/v1/portal/products/{nm_id}", {"account_id": config.seller_account_id})
    results: dict[str, Any] = {}
    slow: list[dict[str, Any]] = []
    for key, (path, query) in endpoint_map.items():
        durations: list[int] = []
        statuses: list[int] = []
        for index in range(3):
            record = request_json(
                client,
                config,
                actor="seller",
                token=config.seller_token,
                method="GET",
                path=path,
                query=query,
                label=f"performance_{safe_name(key)}_{index + 1}",
            )
            durations.append(record["duration_ms"])
            statuses.append(record["status_code"])
        p50 = int(statistics.median(durations))
        p95 = int(max(durations))
        threshold = CORE_THRESHOLDS_MS[key]
        item = {"path": key, "status_codes": statuses, "durations_ms": durations, "p50_ms": p50, "p95_ms": p95, "threshold_ms": threshold, "passed": p95 <= threshold}
        results[key] = item
        if not item["passed"]:
            slow.append(item)
    write_json(OUTPUT_DIR / "04_performance" / "performance.json", results)
    write_json(OUTPUT_DIR / "04_performance" / "slow_endpoints.json", slow)
    return results, slow


def scrub_artifacts() -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in OUTPUT_DIR.rglob("*"):
        if not path.is_file() or path.suffix not in {".json", ".md", ".txt", ".jsonl"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for term in BLOCKED_TERMS:
            if term in text:
                findings.append({"path": str(path.relative_to(OUTPUT_DIR)), "pattern": term})
        if TOKEN_LIKE_RE.search(text):
            findings.append({"path": str(path.relative_to(OUTPUT_DIR)), "pattern": "jwt_like_token"})
    write_json(OUTPUT_DIR / "06_security" / "artifact_secret_scan.json", {"passed": not findings, "findings": findings})
    return findings


def scorecard(*, missing: list[str], runtime: list[dict[str, Any]], rbac_pass: bool, nm_id: str | None, action_patch: dict[str, Any], slow: list[dict[str, Any]], security_findings: list[dict[str, Any]]) -> dict[str, Any]:
    any_5xx = any(int(record.get("status_code") or 0) >= 500 for record in runtime)
    runtime_pass = bool(runtime) and all(status_pass(record) for record in runtime)
    product_360_pass = bool(nm_id) and any("/portal/products/" in record["path"] and record["status_code"] == 200 for record in runtime)
    performance_pass = not slow
    security_pass = not security_findings
    scores = {
        "Backend runtime": 0 if missing else (0 if any_5xx else (100 if runtime_pass else 70)),
        "Auth/login": 0 if missing else (100 if any(record["path"] == "/api/v1/auth/me" and record["status_code"] == 200 for record in runtime) else 70),
        "Seller RBAC": 0 if missing else (100 if rbac_pass else 70),
        "Product 360": 0 if missing else (100 if product_360_pass else 70),
        "Action PATCH": 0 if missing else (100 if action_patch.get("passed") else 70),
        "Performance": 0 if missing else (100 if performance_pass else 80),
        "Security": 100 if security_pass else 0,
    }
    controlled = min(scores.values()) if not missing else 0
    public = controlled
    if missing:
        public = min(public, 70)
    if not rbac_pass:
        public = min(public, 75)
    if not action_patch.get("passed"):
        controlled = min(controlled, 85)
    if not product_360_pass:
        controlled = min(controlled, 80)
    if any_5xx:
        verdict = "NO_GO"
    elif missing:
        verdict = "NO_GO_MISSING_ENV"
    elif public >= 100:
        verdict = "GO"
    elif controlled >= 85 and security_pass and rbac_pass:
        verdict = "CONDITIONAL_GO"
    else:
        verdict = "NO_GO"
    scores["Controlled pilot readiness"] = controlled
    scores["Public launch readiness"] = public
    report = {
        "generated_at": utc_now(),
        "final_verdict": verdict,
        "scores": scores,
        "missing_required_env": missing,
        "remaining_blockers": blockers_for_report(missing, rbac_pass, bool(action_patch.get("passed")), product_360_pass, performance_pass, security_pass, any_5xx),
        "controlled_pilot_allowed": controlled >= 85 and not any_5xx and security_pass and not missing,
    }
    write_json(OUTPUT_DIR / "07_scorecard" / "STAGING_BACKEND_ACCEPTANCE_REPORT.json", report)
    lines = ["# Staging Backend Acceptance Report", "", f"- Final verdict: `{verdict}`", f"- Controlled pilot allowed: `{report['controlled_pilot_allowed']}`", "", "## Scores", ""]
    lines.extend(f"- {area}: `{score}/100`" for area, score in scores.items())
    lines += ["", "## Remaining Blockers", ""]
    lines.extend(f"- {blocker}" for blocker in report["remaining_blockers"] or ["None"])
    write_text(OUTPUT_DIR / "07_scorecard" / "STAGING_BACKEND_ACCEPTANCE_REPORT.md", "\n".join(lines))
    return report


def blockers_for_report(missing: list[str], rbac_pass: bool, action_patch_pass: bool, product_360_pass: bool, performance_pass: bool, security_pass: bool, any_5xx: bool) -> list[str]:
    blockers: list[str] = []
    if missing:
        blockers.append("Required staging environment variables are missing: " + ", ".join(missing))
    if any_5xx:
        blockers.append("At least one core endpoint returned 5xx.")
    if not rbac_pass:
        blockers.append("Seller forbidden-account RBAC proof is missing or failed.")
    if not action_patch_pass:
        blockers.append("Action PATCH proof is missing or failed.")
    if not product_360_pass:
        blockers.append("Product 360 proof is missing or failed.")
    if not performance_pass:
        blockers.append("One or more core endpoints exceeded latency threshold.")
    if not security_pass:
        blockers.append("Artifact secret scrub found blocked patterns.")
    return blockers


def write_missing_env_report(missing: list[str]) -> dict[str, Any]:
    write_json(OUTPUT_DIR / "00_manifest" / "manifest.json", env_manifest(None, missing))
    write_json(OUTPUT_DIR / "01_env" / "env_manifest.json", env_manifest(None, missing))
    write_text(
        OUTPUT_DIR / "NO_GO_MISSING_ENV.md",
        "\n".join(
            [
                "# NO GO: Missing Staging Environment",
                "",
                "Real staging runtime/RBAC/performance audit was not executed because required env variables are missing.",
                "",
                "## Missing Variables",
                "",
                *[f"- `{name}`" for name in missing],
                "",
                "No fixture-mode users, DB-generated tokens, or local backend fallback were used.",
            ]
        ),
    )
    findings = scrub_artifacts()
    return scorecard(missing=missing, runtime=[], rbac_pass=False, nm_id=None, action_patch={"passed": False}, slow=[], security_findings=findings)


def zip_output() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = REPO_ROOT / f"CODEX_STAGING_BACKEND_ACCEPTANCE_AUDIT_{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in OUTPUT_DIR.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(REPO_ROOT))
    write_text(OUTPUT_DIR / "00_manifest" / "zip_path.txt", str(zip_path))
    return zip_path


def main() -> int:
    prepare_output()
    missing = missing_required_env()
    config = load_config()
    if missing or config is None:
        report = write_missing_env_report(missing)
        final_findings = scrub_artifacts()
        if final_findings:
            report = scorecard(missing=missing, runtime=[], rbac_pass=False, nm_id=None, action_patch={"passed": False}, slow=[], security_findings=final_findings)
        zip_path = zip_output()
        print(json.dumps({"final_verdict": report["final_verdict"], "zip_path": str(zip_path), "missing_required_env": missing}, indent=2))
        return 2

    write_json(OUTPUT_DIR / "00_manifest" / "manifest.json", env_manifest(config, []))
    write_json(OUTPUT_DIR / "01_env" / "env_manifest.json", env_manifest(config, []))
    with httpx.Client(timeout=httpx.Timeout(45.0, connect=10.0), follow_redirects=True) as client:
        runtime_records, nm_id = run_runtime(client, config)
        _, rbac_pass = run_rbac(client, config, nm_id)
        action_record = next((record for record in runtime_records if record["path"] == "/api/v1/portal/actions"), None)
        action_patch = run_action_patch(client, config, action_record)
        _, slow = run_performance(client, config, nm_id)
    security_findings = scrub_artifacts()
    report = scorecard(missing=[], runtime=runtime_records, rbac_pass=rbac_pass, nm_id=nm_id, action_patch=action_patch, slow=slow, security_findings=security_findings)
    final_findings = scrub_artifacts()
    if final_findings != security_findings:
        report = scorecard(missing=[], runtime=runtime_records, rbac_pass=rbac_pass, nm_id=nm_id, action_patch=action_patch, slow=slow, security_findings=final_findings)
    zip_path = zip_output()
    print(json.dumps({"final_verdict": report["final_verdict"], "zip_path": str(zip_path), "controlled_pilot_allowed": report["controlled_pilot_allowed"]}, indent=2))
    return 0 if report["final_verdict"] in {"GO", "CONDITIONAL_GO"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
