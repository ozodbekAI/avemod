from __future__ import annotations

import re
from typing import Any


_SPACE_RE = re.compile(r"\s+")
_REGION_ALIASES = {
    "центральный федеральный округ": "Центральный",
    "центральный": "Центральный",
    "приволжский федеральный округ": "Приволжский",
    "приволжский": "Приволжский",
    "северо-западный федеральный округ": "Северо-Западный",
    "северо западный федеральный округ": "Северо-Западный",
    "северо-западный": "Северо-Западный",
    "северо западный": "Северо-Западный",
    "южный федеральный округ": "Южный",
    "южный": "Южный",
    "северо-кавказский федеральный округ": "Северо-Кавказский",
    "северо кавказский федеральный округ": "Северо-Кавказский",
    "северо-кавказский": "Северо-Кавказский",
    "сибирский федеральный округ": "Сибирский",
    "сибирский": "Сибирский",
    "уральский федеральный округ": "Уральский",
    "уральский": "Уральский",
    "дальневосточный федеральный округ": "Дальневосточный",
    "дальневосточный": "Дальневосточный",
}


def normalize_region(value: Any) -> str:
    text = _SPACE_RE.sub(" ", str(value or "").strip())
    if not text:
        return "Неизвестный регион"
    lowered = text.casefold().replace("ё", "е")
    lowered = lowered.replace("—", "-").replace("–", "-")
    lowered = _SPACE_RE.sub(" ", lowered)
    return _REGION_ALIASES.get(lowered, text)


def normalize_excluded_regions(
    values: list[str] | set[str] | tuple[str, ...] | None,
) -> set[str]:
    return {normalize_region(value) for value in values or []}
