from __future__ import annotations

import re
from typing import Any


SENSITIVE_FIELD_TOKENS = (
    "api_key",
    "authorization",
    "credential",
    "encrypted_token",
    "encryption_key",
    "headers",
    "jwt",
    "password",
    "refresh_token",
    "secret",
    "token",
    "wb_payload",
    "raw_wb",
)

_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b("
    r"access[_-]?token|refresh[_-]?token|wb[_-]?token|api[_-]?key|"
    r"authorization|password|secret|jwt|credential"
    r")\b\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")


def has_sensitive_key(key: Any) -> bool:
    lowered = str(key).lower()
    return any(token in lowered for token in SENSITIVE_FIELD_TOKENS)


def redact_sensitive_text(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    redacted = _BEARER_RE.sub("Bearer <redacted>", value)
    return _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}=<redacted>", redacted
    )


def scrub_sensitive_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: scrub_sensitive_payload(item)
            for key, item in value.items()
            if not has_sensitive_key(key)
        }
    if isinstance(value, list):
        return [scrub_sensitive_payload(item) for item in value]
    if isinstance(value, tuple):
        return [scrub_sensitive_payload(item) for item in value]
    return redact_sensitive_text(value)
