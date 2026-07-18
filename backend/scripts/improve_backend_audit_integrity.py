#!/usr/bin/env python3
"""Recompute backend audit score integrity from saved evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


WEIGHTS = {
    "Backend runtime": 15,
    "Auth/login": 5,
    "RBAC/account access": 5,
    "Finance core": 10,
    "Legacy profit diagnostics": 10,
    "Action Center": 10,
    "Products list": 8,
    "Product 360": 7,
    "Results": 4,
    "Claims Factory": 3,
    "Reputation Operator": 3,
    "Security/safety": 10,
    "Tests": 5,
    "DB/migrations": 5,
}

SPECIFIC_REASON_REPLACEMENTS = {
    "Backend runtime": "Runtime evidence is local, not staging; staging BASE_URL audit is required for 100.",
    "Auth/login": "Auth endpoints passed in local/runtime evidence; staging admin and seller token proof is still required for 100.",
    "Finance core": "Finance endpoints passed locally; staging finance runtime and target DB migration proof are still required for 100.",
    "Legacy profit diagnostics": "Doctor endpoint contract passed locally; staging runtime evidence and optional module degradation proof are still required for 100.",
    "Action Center": "Action Center passed local read/update safety checks; staging proof with real seller/admin identities is still required for 100.",
    "Products list": "Products list passed locally; staging performance and real account data proof are still required for 100.",
    "Product 360": "Product 360 passed locally for a discovered nm_id; staging product detail proof is still required for 100.",
    "Data Fix": "Data Fix contracts passed locally; staging seller-scoped data-quality proof is still required for 100.",
    "Costs": "Costs endpoints passed locally; staging manual-cost/account-scope proof is still required for 100.",
    "Results": "Results endpoint passed locally; staging result-event evidence is still required for 100.",
    "Claims Factory": "Claims endpoints passed local safe-mode checks; external submit remains disabled and staging safe proof is still required for 100.",
    "Reputation Operator": "Reputation endpoints passed local disabled/degraded contracts; live reputation integration proof is still required for 100.",
    "Checker integration state": "Checker is read-only/not_configured in MVP evidence; live read-only checker adapter proof is still required for 100.",
    "StockOps integration state": "StockOps remains optional/safe-mode; staging read-only or disabled proof is still required for 100.",
    "Grouping Beta": "Grouping beta endpoint passed local recommendation-only checks; staging beta proof is still required for 100.",
    "Photo Studio state": "Photo Studio is not fully wired in MVP evidence; keep disabled/not_configured until an adapter contract is proven.",
    "Security/safety": "Secret logging scans passed locally; staging response/log scrubbing proof is still required for 100.",
    "Performance": "Local endpoint audit completed; staging latency and load evidence are still required for 100.",
    "Tests": "Full pytest evidence must stay green in the generated bundle; no failing test evidence may be published as ready.",
    "Deploy readiness": "Clean deploy context passed, but staging runtime/RBAC/performance evidence is missing.",
    "Lovable contract readiness": "Frontend contract evidence is local; staging portal contract smoke is still required for 100.",
    "Controlled pilot readiness": "Controlled pilot is local-evidence ready; staging smoke is still needed before external pilot rollout.",
    "Public MVP readiness": "Public launch is blocked until staging runtime, staging RBAC, and staging performance evidence pass.",
    "Full product readiness": "Full product requires optional module integrations and confirmed write-action safety flows beyond MVP.",
}


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def evidence_state(audit_dir: Path) -> dict[str, Any]:
    tests = read_json(audit_dir / "03_tests" / "test_summary.json", {})
    rbac = read_json(audit_dir / "08_rbac_security" / "rbac_summary.json", {})
    secret_scan = read_json(audit_dir / "08_rbac_security" / "secret_leak_scan.json", {})
    risky = read_json(audit_dir / "02_code_static" / "risky_patterns.json", {})
    deploy = read_json(audit_dir / "17_deploy_readiness" / "staging_runtime_index.json", {})
    deploy_scan_rc = (audit_dir / "17_deploy_readiness" / "deploy_safety_scan.rc")
    return {
        "pytest_full_rc": tests.get("pytest_full", {}).get("returncode"),
        "pytest_full_status": tests.get("pytest_full", {}).get("status"),
        "rbac_passed": bool(rbac.get("passed")),
        "rbac_fixture_mode": bool(rbac.get("fixture_mode")),
        "raw_token_logging": bool(risky.get("count")) or secret_scan.get("status") == "FAIL",
        "deploy_safety_pass": deploy_scan_rc.exists() and deploy_scan_rc.read_text(encoding="utf-8").strip() == "0",
        "staging_runtime_status": deploy.get("status", "MISSING"),
        "staging_missing_env": deploy.get("missing_env", []),
    }


def set_score(scores: list[dict[str, Any]], area: str, score: int, reason: str, evidence: list[str], priority: str) -> None:
    for item in scores:
        if item.get("area") == area:
            item["score"] = min(int(item.get("score", 0)), score) if int(item.get("score", 0)) > score else int(item.get("score", 0))
            item["why_not_100"] = [reason]
            item["evidence"] = evidence
            item["required_to_100"] = required_to_100(area)
            item["priority"] = priority
            return


def lift_score(scores: list[dict[str, Any]], area: str, score: int, evidence: list[str], priority: str) -> None:
    for item in scores:
        if item.get("area") == area and int(item.get("score", 0)) < score:
            item["score"] = score
            item["why_not_100"] = [] if score >= 100 else item.get("why_not_100", [])
            item["evidence"] = evidence
            item["required_to_100"] = [] if score >= 100 else required_to_100(area)
            item["priority"] = priority
            return


def required_to_100(area: str) -> list[str]:
    if area == "Tests":
        return ["Keep full pytest green in the generated audit bundle."]
    if area == "Security/safety":
        return ["Keep secret logging scan clean and rerun against staging runtime responses."]
    if area == "RBAC/account access":
        return ["Run seller/admin matrix against staging with real tokens and own/forbidden account ids."]
    if area == "Deploy readiness":
        return ["Run staging runtime endpoint, RBAC, and performance audits with required staging env."]
    if area == "Public MVP readiness":
        return ["Pass staging runtime, staging seller RBAC, staging performance, and deploy context scans."]
    return ["Provide staging evidence for this area and rerun audit integrity scoring."]


def normalize_reasons(scores: list[dict[str, Any]]) -> None:
    generic = "Evidence did not prove every production/live dependency and RBAC negative path at 100%."
    fallback = "This area lacks complete staging evidence for 100."
    for item in scores:
        if int(item.get("score", 0)) >= 100:
            item["why_not_100"] = []
            continue
        reasons = item.get("why_not_100") or []
        if not reasons or reasons == [generic] or generic in reasons or reasons == [fallback] or fallback in reasons:
            item["why_not_100"] = [SPECIFIC_REASON_REPLACEMENTS.get(item.get("area"), "This area lacks complete staging evidence for 100.")]


def apply_integrity_caps(scores: list[dict[str, Any]], state: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if state.get("pytest_full_rc") == 0:
        lift_score(scores, "Tests", 100, ["03_tests/test_summary.json"], "P2")
    else:
        set_score(
            scores,
            "Tests",
            60,
            "Full pytest did not pass in the generated audit evidence.",
            ["03_tests/test_summary.json"],
            "P0",
        )
        blockers.append("Full pytest failed; final verdict cannot exceed CONDITIONAL_GO.")
    if state.get("raw_token_logging"):
        set_score(
            scores,
            "Security/safety",
            80,
            "Raw token/password/secret logging risk was detected in production code or audit scans.",
            ["02_code_static/risky_patterns.json", "08_rbac_security/secret_leak_scan.json"],
            "P0",
        )
        blockers.append("Raw token logging risk detected; public GO is blocked.")
    if not state.get("rbac_passed"):
        set_score(
            scores,
            "RBAC/account access",
            70,
            "Seller forbidden-account negative proof is missing or failed.",
            ["08_rbac_security/rbac_summary.json", "08_rbac_security/rbac_matrix.json"],
            "P1",
        )
        set_score(
            scores,
            "Public MVP readiness",
            75,
            "Public launch cannot exceed 75 without seller forbidden-account RBAC proof.",
            ["08_rbac_security/rbac_summary.json"],
            "P1",
        )
        blockers.append("Seller RBAC negative proof missing or failed.")
    if state.get("staging_runtime_status") != "PASS":
        set_score(
            scores,
            "Public MVP readiness",
            75,
            "Public launch is capped because staging runtime/RBAC/performance evidence is missing.",
            ["17_deploy_readiness/staging_runtime_index.json", "17_deploy_readiness/staging_rbac_matrix.json", "17_deploy_readiness/staging_performance.json"],
            "P1",
        )
        blockers.append("Staging runtime evidence is missing; public launch readiness is capped.")
    deploy_score = next((int(item.get("score", 0)) for item in scores if item.get("area") == "Deploy readiness"), 0)
    if deploy_score < 70:
        set_score(
            scores,
            "Public MVP readiness",
            75,
            "Public launch is capped because deploy readiness is below 70.",
            ["17_deploy_readiness/DEPLOY_CONTEXT_AUDIT.md"],
            "P1",
        )
        blockers.append("Deploy readiness below 70; public launch readiness is capped.")
    return blockers


def weighted_overall(scores: list[dict[str, Any]]) -> float:
    by_area = {item["area"]: int(item.get("score", 0)) for item in scores}
    total_weight = sum(WEIGHTS.values())
    return round(sum(by_area.get(area, 0) * weight for area, weight in WEIGHTS.items()) / total_weight, 1)


def readiness_summary(scores: list[dict[str, Any]], state: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    score = {item["area"]: int(item.get("score", 0)) for item in scores}
    tests_ok = state.get("pytest_full_rc") == 0
    security_ok = not state.get("raw_token_logging")
    rbac_ok = state.get("rbac_passed")
    deploy_ok = score.get("Deploy readiness", 0) >= 70 and state.get("deploy_safety_pass")
    staging_ok = state.get("staging_runtime_status") == "PASS"
    return {
        "demo_readiness": {
            "status": "READY" if tests_ok and security_ok else "BLOCKED",
            "reason": "Local tests, security scan, and contracts are sufficient for demo." if tests_ok and security_ok else "Demo is blocked by failing tests or security scan.",
        },
        "controlled_pilot_readiness": {
            "status": "CONDITIONAL_READY" if tests_ok and security_ok and rbac_ok and deploy_ok else "BLOCKED",
            "reason": "Local RBAC and deploy context pass; staging smoke is still required before external pilot." if tests_ok and security_ok and rbac_ok and deploy_ok else "Controlled pilot lacks required local RBAC/deploy/test evidence.",
        },
        "public_launch_readiness": {
            "status": "BLOCKED" if not staging_ok or blockers else "READY",
            "reason": "Staging runtime/RBAC/performance evidence is missing." if not staging_ok else "No public launch blockers found.",
        },
    }


def write_blocking_summary(audit_dir: Path, summary: dict[str, Any], blockers: list[str], state: dict[str, Any]) -> None:
    lines = [
        "# Blocking Summary",
        "",
        f"- Demo readiness: `{summary['demo_readiness']['status']}` - {summary['demo_readiness']['reason']}",
        f"- Controlled pilot readiness: `{summary['controlled_pilot_readiness']['status']}` - {summary['controlled_pilot_readiness']['reason']}",
        f"- Public launch readiness: `{summary['public_launch_readiness']['status']}` - {summary['public_launch_readiness']['reason']}",
        "",
        "## Integrity Gates",
        "",
        f"- Full pytest return code: `{state.get('pytest_full_rc')}`",
        f"- Raw token logging detected: `{state.get('raw_token_logging')}`",
        f"- Seller RBAC proof passed: `{state.get('rbac_passed')}`",
        f"- Deploy safety passed: `{state.get('deploy_safety_pass')}`",
        f"- Staging runtime status: `{state.get('staging_runtime_status')}`",
    ]
    if state.get("staging_missing_env"):
        lines.append(f"- Missing staging env: `{', '.join(state['staging_missing_env'])}`")
    lines += ["", "## Blockers", ""]
    lines += [f"- {blocker}" for blocker in blockers] if blockers else ["- No integrity blockers found."]
    (audit_dir / "14_scorecards" / "blocking_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=Path("audit_100_backend"))
    args = parser.parse_args()
    audit_dir = args.audit_dir

    scores = read_json(audit_dir / "14_scorecards" / "backend_scorecard.json", [])
    state = evidence_state(audit_dir)
    normalize_reasons(scores)
    blockers = apply_integrity_caps(scores, state)
    normalize_reasons(scores)
    overall = weighted_overall(scores)
    readiness = readiness_summary(scores, state, blockers)
    verdict = "NO_GO" if state.get("pytest_full_rc") != 0 or state.get("raw_token_logging") else "CONDITIONAL_GO"

    write_json(audit_dir / "14_scorecards" / "backend_scorecard.json", scores)
    (audit_dir / "14_scorecards" / "backend_scorecard.md").write_text(
        "# Backend Scorecard\n\n"
        + "\n".join(
            f"- {item['area']}: {item['score']}/100 ({item['priority']}) - "
            f"{'; '.join(item.get('why_not_100') or ['ready'])}"
            for item in scores
        )
        + f"\n\nWeighted overall: {overall}/100\n",
        encoding="utf-8",
    )
    write_json(audit_dir / "14_scorecards" / "weighted_overall_score.json", {"overall_score": overall, "weights": WEIGHTS})
    write_blocking_summary(audit_dir, readiness, blockers, state)

    p0 = sum(1 for item in scores if item.get("priority") == "P0" and int(item.get("score", 100)) < 100)
    p1 = sum(1 for item in scores if item.get("priority") == "P1" and int(item.get("score", 100)) < 100)
    issues = blockers or [readiness["public_launch_readiness"]["reason"]]
    final = {
        "final_verdict": verdict,
        "overall_score": overall,
        "p0_blockers": p0,
        "p1_blockers": p1,
        "main_remaining_issues": issues[:5],
        "integrity_state": state,
        "readiness": readiness,
        "scores": scores,
        "evidence_root": str(audit_dir),
    }
    write_json(audit_dir / "FINAL_BACKEND_100_SCORE_REPORT.json", final)
    md_lines = [
        "# FINAL BACKEND 100 SCORE REPORT",
        "",
        "## Executive Summary",
        f"Overall score: {overall}/100. Final verdict: {verdict}. Public launch remains blocked until staging runtime/RBAC/performance evidence is provided.",
        "",
        "## Final Verdict",
        verdict,
        "",
        "## Overall Score",
        f"{overall}/100",
        "",
        "## Score Table",
        "",
    ]
    md_lines.extend(
        f"- {item['area']}: {item['score']}/100 - {'; '.join(item.get('why_not_100') or ['ready'])}"
        for item in scores
    )
    md_lines += [
        "",
        "## Blocking Summary",
        "",
        f"- Demo readiness: `{readiness['demo_readiness']['status']}`",
        f"- Controlled pilot readiness: `{readiness['controlled_pilot_readiness']['status']}`",
        f"- Public launch readiness: `{readiness['public_launch_readiness']['status']}`",
        "",
        "## Exact Next Actions",
        "",
    ]
    md_lines.extend(f"- {issue}" for issue in issues)
    (audit_dir / "FINAL_BACKEND_100_SCORE_REPORT.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(json.dumps({"overall_score": overall, "final_verdict": verdict, "blockers": blockers, "readiness": readiness}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
