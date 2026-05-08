from __future__ import annotations

import json
from pathlib import Path

DEFAULT_KEYTERMS_PATH = Path(__file__).with_name("keyterms.json")


def load_session_keyterms(*, provider: str, model: str = "") -> list[str]:
    """Load IT_Curves domain keyterms with provider-specific caps."""
    try:
        with open(DEFAULT_KEYTERMS_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    common_terms = data.get("common_keyterms", [])
    if not isinstance(common_terms, list):
        return []

    normalized_provider = _normalize_provider(provider)
    cleaned = _dedupe([term for term in common_terms if isinstance(term, str) and term.strip()])
    max_terms = _max_keyterms(data, provider=normalized_provider, model=model)
    return cleaned[:max_terms]


def _max_keyterms(data: dict, *, provider: str, model: str) -> int:
    provider = _normalize_provider(provider)

    if provider == "speechmatics":
        return _positive_int(data.get("speechmatics_max_keyterms"), 200)

    model = model.strip().lower()
    if "flux" in model:
        return _positive_int(data.get("flux_max_keyterms"), 100)
    if "nova" in model:
        return _positive_int(data.get("nova_max_keyterms"), 169)
    return _positive_int(data.get("max_keyterms"), 100)


def _normalize_provider(provider: str) -> str:
    provider = provider.strip().lower()
    if provider == "speechmatic":
        return "speechmatics"
    return provider


def _positive_int(value: object, fallback: int) -> int:
    return value if isinstance(value, int) and value > 0 else fallback


def _dedupe(terms: list[str]) -> list[str]:
    seen = set()
    unique = []
    for term in terms:
        normalized = term.strip()
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique
