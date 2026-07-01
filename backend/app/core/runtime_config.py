"""Runtime configuration overrides for LLM settings.

Provides a thread-safe, in-memory override dictionary that takes precedence
over environment-variable-based Settings. Used by the frontend to let users
change LLM provider/model/key at runtime without restarting the container.
"""
from __future__ import annotations

from typing import Any

_RUNTIME_OVERRIDES: dict[str, str] = {}


def get_llm_config() -> dict[str, str]:
    """Return the current runtime LLM config overrides (keys only)."""
    return {
        k: v
        for k, v in _RUNTIME_OVERRIDES.items()
        if k in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")
    }


def set_llm_config(**kwargs: Any) -> dict[str, str]:
    """Set runtime LLM overrides.

    Accepted keys: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL.
    Empty string clears the override (fall back to env).
    """
    for key in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        if key in kwargs:
            val = kwargs[key]
            if val:
                _RUNTIME_OVERRIDES[key] = str(val)
            else:
                _RUNTIME_OVERRIDES.pop(key, None)
    return get_llm_config()


def resolve(key: str, fallback: str = "") -> str:
    """Resolve a setting key: runtime override > env/fallback."""
    return _RUNTIME_OVERRIDES.get(key) or fallback
