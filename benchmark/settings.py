from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=False)

SETTINGS_PATH = Path(os.getenv("BENCHMARK_SETTINGS_PATH", "benchmark_settings.json"))

DEFAULT_SETTINGS: dict[str, Any] = {
    "stt_benchmark_mode": "production",
    "stt_primary_provider": "deepgram",
    "stt_shadow_provider": "speechmatics",
    "deepgram_stt_model": "nova-2",
    "deepgram_interim_results": None,
    "speechmatics_operating_point": "enhanced",
    "speechmatics_max_delay": 1.5,
    "soniox_stt_model": "stt-rt-v4",
    "soniox_max_endpoint_delay_ms": 500,
    "benchmark_publish_events": True,
    "benchmark_api_url": "http://127.0.0.1:8090",
    "benchmark_storage_root": "calls",
}

ENV_KEYS = {
    "stt_benchmark_mode": "STT_BENCHMARK_MODE",
    "stt_primary_provider": "STT_PRIMARY_PROVIDER",
    "stt_shadow_provider": "STT_SHADOW_PROVIDER",
    "deepgram_stt_model": "DEEPGRAM_STT_MODEL",
    "deepgram_interim_results": "DEEPGRAM_INTERIM_RESULTS",
    "speechmatics_operating_point": "SPEECHMATICS_OPERATING_POINT",
    "speechmatics_max_delay": "SPEECHMATICS_MAX_DELAY",
    "soniox_stt_model": "SONIOX_STT_MODEL",
    "soniox_max_endpoint_delay_ms": "SONIOX_MAX_ENDPOINT_DELAY_MS",
    "benchmark_publish_events": "BENCHMARK_PUBLISH_EVENTS",
    "benchmark_api_url": "BENCHMARK_API_URL",
    "benchmark_storage_root": "BENCHMARK_STORAGE_ROOT",
}

BOOL_KEYS = {"benchmark_publish_events"}
OPTIONAL_BOOL_KEYS = {"deepgram_interim_results"}
FLOAT_KEYS = {"speechmatics_max_delay"}
INT_KEYS = {"soniox_max_endpoint_delay_ms"}
PROVIDERS = {"deepgram", "speechmatics", "soniox", "seniox"}
MODES = {"production", "shadow", "comparison"}


def load_settings() -> dict[str, Any]:
    file_settings = _file_settings()
    settings = DEFAULT_SETTINGS | file_settings
    for key, env_key in ENV_KEYS.items():
        env_value = os.getenv(env_key)
        if key == "stt_primary_provider":
            env_value = os.getenv("STT_PRIMARY_PROVIDER", os.getenv("STT_PROVIDER"))
        if env_value is not None and key not in file_settings:
            settings[key] = _coerce_value(key, env_value)
    return sanitize_settings(settings)


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_settings()
    next_settings = sanitize_settings(current | {key: value for key, value in payload.items() if key in DEFAULT_SETTINGS})
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(next_settings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return next_settings


def setting(key: str, fallback: Any = None) -> Any:
    return load_settings().get(key, fallback)


def sanitize_settings(settings: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(DEFAULT_SETTINGS)
    sanitized.update({key: settings.get(key) for key in DEFAULT_SETTINGS})

    sanitized["stt_benchmark_mode"] = _choice(sanitized["stt_benchmark_mode"], MODES, DEFAULT_SETTINGS["stt_benchmark_mode"])
    sanitized["stt_primary_provider"] = _provider(sanitized["stt_primary_provider"], DEFAULT_SETTINGS["stt_primary_provider"])
    sanitized["stt_shadow_provider"] = _provider(sanitized["stt_shadow_provider"], DEFAULT_SETTINGS["stt_shadow_provider"])
    if sanitized["stt_shadow_provider"] == sanitized["stt_primary_provider"]:
        sanitized["stt_shadow_provider"] = "speechmatics" if sanitized["stt_primary_provider"] == "deepgram" else "deepgram"

    sanitized["deepgram_stt_model"] = _non_empty_string(sanitized["deepgram_stt_model"], DEFAULT_SETTINGS["deepgram_stt_model"])
    sanitized["deepgram_interim_results"] = _optional_bool(sanitized["deepgram_interim_results"])
    sanitized["speechmatics_operating_point"] = _choice(
        sanitized["speechmatics_operating_point"],
        {"enhanced", "standard"},
        DEFAULT_SETTINGS["speechmatics_operating_point"],
    )
    sanitized["speechmatics_max_delay"] = max(0.0, _float(sanitized["speechmatics_max_delay"], DEFAULT_SETTINGS["speechmatics_max_delay"]))
    sanitized["soniox_stt_model"] = _non_empty_string(sanitized["soniox_stt_model"], DEFAULT_SETTINGS["soniox_stt_model"])
    sanitized["soniox_max_endpoint_delay_ms"] = min(
        3000,
        max(500, _int(sanitized["soniox_max_endpoint_delay_ms"], DEFAULT_SETTINGS["soniox_max_endpoint_delay_ms"])),
    )
    sanitized["benchmark_publish_events"] = _bool(sanitized["benchmark_publish_events"], DEFAULT_SETTINGS["benchmark_publish_events"])
    sanitized["benchmark_api_url"] = _non_empty_string(sanitized["benchmark_api_url"], DEFAULT_SETTINGS["benchmark_api_url"])
    sanitized["benchmark_storage_root"] = _non_empty_string(sanitized["benchmark_storage_root"], DEFAULT_SETTINGS["benchmark_storage_root"])
    return sanitized


def _file_settings() -> dict[str, Any]:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _coerce_value(key: str, value: str) -> Any:
    if key in BOOL_KEYS:
        return _bool(value, DEFAULT_SETTINGS[key])
    if key in OPTIONAL_BOOL_KEYS:
        return _optional_bool(value)
    if key in FLOAT_KEYS:
        return _float(value, DEFAULT_SETTINGS[key])
    if key in INT_KEYS:
        return _int(value, DEFAULT_SETTINGS[key])
    return value


def _provider(value: Any, fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "seniox":
        normalized = "soniox"
    return normalized if normalized in PROVIDERS else fallback


def _choice(value: Any, choices: set[str], fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in choices else fallback


def _non_empty_string(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.strip().lower() in {"1", "true", "yes", "on"}:
            return True
        if value.strip().lower() in {"0", "false", "no", "off"}:
            return False
    return fallback


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    return _bool(value, False)


def _float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
