from __future__ import annotations

from scripts.run_full_runtime_endpoint_audit import (
    REDACTED,
    build_logical_table_counts,
    contains_unredacted_secret,
    path_exists,
    sanitize,
    strip_api_prefix,
)


def test_sanitize_redacts_sensitive_keys_and_secret_like_strings() -> None:
    payload = {
        "access_token": "raw-token-value",
        "nested": {
            "note": "contact me at seller@example.com",
            "safe": "ok",
        },
        "items": ["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payloadpayload.signaturevalue"],
    }

    sanitized, redactions = sanitize(payload)

    assert redactions >= 3
    assert sanitized["access_token"] == REDACTED
    assert sanitized["nested"]["note"] == f"contact me at {REDACTED}"
    assert sanitized["items"] == [REDACTED]
    assert contains_unredacted_secret(sanitized) == []


def test_route_matching_accepts_openapi_api_prefix() -> None:
    catalog = [{"method": "GET", "path": "/api/v1/portal/doctor"}]

    assert strip_api_prefix("/api/v1/portal/doctor") == "/portal/doctor"
    assert path_exists(catalog, "GET", "/portal/doctor")
    assert not path_exists(catalog, "POST", "/portal/doctor")


def test_db_logical_table_counts_resolve_auth_and_account_aliases() -> None:
    logical_counts = build_logical_table_counts(
        {
            "auth_users": 9,
            "wb_accounts": 4,
            "operator_signals": 0,
        }
    )

    assert logical_counts["users"] == {
        "logical_table": "users",
        "physical_table": "auth_users",
        "status": "ok",
        "count": 9,
    }
    assert logical_counts["accounts"] == {
        "logical_table": "accounts",
        "physical_table": "wb_accounts",
        "status": "ok",
        "count": 4,
    }
    assert logical_counts["operator_signals"]["physical_table"] == "operator_signals"
    assert logical_counts["operator_signals"]["status"] == "ok"


def test_db_logical_table_counts_report_missing_when_physical_alias_missing() -> None:
    logical_counts = build_logical_table_counts({"operator_signals": 0})

    assert logical_counts["users"]["status"] == "missing"
    assert logical_counts["users"]["physical_table"] == "auth_users"
    assert logical_counts["accounts"]["status"] == "missing"
    assert logical_counts["accounts"]["physical_table"] == "wb_accounts"
