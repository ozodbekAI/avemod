from __future__ import annotations

from scripts.seed_ai_operator_demo import DEMO_PRODUCT_NM_ID, demo_payload, demo_source_id, demo_source_ids, dry_run_payload


def test_demo_source_id_is_deterministic() -> None:
    assert demo_source_id("claims:draft_claim", nm_id=DEMO_PRODUCT_NM_ID, suffix="defect") == "demo:claims:draft_claim:1001001:defect"
    assert demo_source_id("claims:draft_claim", nm_id=DEMO_PRODUCT_NM_ID, suffix="defect") == demo_source_id(
        "claims:draft_claim",
        nm_id=DEMO_PRODUCT_NM_ID,
        suffix="defect",
    )


def test_demo_source_ids_are_unique_and_stable() -> None:
    first = demo_source_ids()
    second = demo_source_ids()
    flattened = [source_id for values in first.values() for source_id in values]

    assert first == second
    assert len(flattened) == len(set(flattened))
    assert all(source_id.startswith("demo:") for source_id in flattened)


def test_demo_payload_marks_records_safe() -> None:
    payload = demo_payload(example=True)

    assert payload["demo"] is True
    assert payload["safe_demo"] is True
    assert payload["external_operation"] is False
    assert payload["marketplace_change"] is False
    assert payload["example"] is True


def test_dry_run_payload_contains_no_private_or_token_fields() -> None:
    payload = dry_run_payload()
    dumped = str(payload).lower()

    assert payload["safety"]["no_real_wb_tokens"] is True
    assert payload["safety"]["no_private_buyer_data"] is True
    assert "token" not in dumped.replace("no_real_wb_tokens", "")
    assert "phone" not in dumped
    assert "passport" not in dumped
