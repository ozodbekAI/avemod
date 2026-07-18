from __future__ import annotations

from app.services.checker_core.vision_service import (
    build_product_dna_audit,
    has_meaningful_product_dna,
    normalize_product_dna_json,
    product_dna_to_text,
)


def test_product_dna_audit_empty_payload_is_not_grounded() -> None:
    audit = build_product_dna_audit({}, subject_name="Костюмы", photo_count=0)

    assert audit["grounded"] is False
    assert audit["trust_state"] == "empty"


def test_product_dna_audit_low_confidence_is_weak() -> None:
    audit = build_product_dna_audit(
        {"confidence": 0.21, "items": [{"type": "jacket", "visible": True}]},
        subject_name="Костюмы",
        photo_count=3,
    )

    assert audit["grounded"] is False
    assert audit["trust_state"] == "weak"


def test_product_dna_audit_accessory_contamination_is_rejected() -> None:
    audit = build_product_dna_audit(
        {
            "confidence": 0.88,
            "items": [{"type": "jacket", "visible": True}],
            "per_photo_notes": [{"observation": "Visible jacket, shirt and handbag."}],
        },
        subject_name="Костюмы",
        photo_count=3,
    )

    assert audit["grounded"] is False
    assert audit["trust_state"] == "contaminated"


def test_product_dna_audit_subject_mismatch_for_suit_is_rejected() -> None:
    audit = build_product_dna_audit(
        {
            "confidence": 0.9,
            "items": [{"type": "dress", "visible": True}],
            "summary": "Visible dress silhouette.",
        },
        subject_name="Костюмы",
        photo_count=3,
    )

    assert audit["grounded"] is False
    assert audit["trust_state"] == "subject_mismatch"


def test_product_dna_audit_grounded_clean_set_is_accepted() -> None:
    audit = build_product_dna_audit(
        {
            "confidence": 0.92,
            "items": [{"type": "jacket", "visible": True}, {"type": "pants", "visible": True}],
            "summary": "Visible suit set with jacket and pants.",
        },
        subject_name="Костюмы",
        photo_count=3,
    )

    assert audit["grounded"] is True
    assert audit["trust_state"] == "grounded"


def test_product_dna_audit_suit_jacket_alias_is_grounded_for_suit_subject() -> None:
    audit = build_product_dna_audit(
        {
            "confidence": 0.92,
            "items": [{"type": "suit jacket", "visible": True}, {"type": "pants", "visible": True}],
            "summary": "Visible tailored suit jacket with matching pants.",
        },
        subject_name="Костюмы",
        photo_count=3,
    )

    assert audit["grounded"] is True
    assert audit["trust_state"] == "grounded"
    assert audit["visible_types"] == ["jacket", "pants"]


def test_product_dna_ignores_accessory_hits_when_product_is_visible() -> None:
    audit = build_product_dna_audit(
        {
            "confidence": 0.8,
            "items": [{"type": "jacket", "visible": True, "confidence": 0.85}],
            "summary": "Visible jacket with handbag accessory in the frame.",
        },
        subject_name="Костюмы",
        photo_count=3,
    )

    assert audit["grounded"] is True
    assert audit["accessory_hits_ignored"]


def test_empty_shell_product_dna_is_dropped() -> None:
    dna = normalize_product_dna_json(
        {"version": "product_dna_v2", "confidence": 0.0, "items": [], "summary": "", "per_photo_notes": []},
        subject_name="Костюмы",
    )

    assert dna == {}
    assert has_meaningful_product_dna(dna) is False
    assert product_dna_to_text(dna) == ""


def test_meaningful_product_dna_is_preserved() -> None:
    dna = normalize_product_dna_json(
        {
            "confidence": 0.83,
            "items": [{"type": "жакет", "confidence": 0.94, "visible": True}],
            "summary": "Костюм с жакетом и темной фактурой.",
        },
        subject_name="Костюмы",
    )

    assert has_meaningful_product_dna(dna) is True
    assert "жакет" in product_dna_to_text(dna).lower()


def test_product_dna_derives_confidence_from_item_evidence_when_model_omits_it() -> None:
    dna = normalize_product_dna_json(
        {
            "confidence": 0.0,
            "items": [{"type": "suit", "confidence": 0.9, "visible": True}],
            "observed_texture": "smooth",
            "color": ["burgundy"],
            "per_photo_notes": [{"photo_index": 1, "visible_parts": ["jacket", "pants"], "observation": "Both parts are visible."}],
        },
        subject_name="Костюмы",
    )

    assert has_meaningful_product_dna(dna) is True
    assert float(dna["confidence"]) >= 0.45


def test_product_dna_with_only_color_signal_is_dropped() -> None:
    dna = normalize_product_dna_json(
        {"confidence": 0.0, "summary": "black", "color": ["black"], "items": [{"type": "unknown", "confidence": 0.0, "visible": True}]},
        subject_name="Костюмы",
    )

    assert dna == {}


def test_nested_product_dna_payload_is_normalized() -> None:
    dna = normalize_product_dna_json(
        {"product_dna": {"confidence": 0.77, "items": [{"type": "жакет", "confidence": 0.9}], "summary": "Виден жакет."}},
        subject_name="Костюмы",
    )

    assert has_meaningful_product_dna(dna) is True
    assert dna["items"][0]["type"] == "jacket"

