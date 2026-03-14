"""Dev-only AI planner debug logger.

When FLASK_DEBUG is enabled, saves the full LLM input (system prompt + user
prompt) and output (raw response + parsed result) to timestamped JSON files
in the ``ai_debug_logs/`` directory for offline analysis.

In production (FLASK_DEBUG=0) the functions are no-ops.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import FLASK_DEBUG

logger = logging.getLogger(__name__)

_LOG_DIR = Path(__file__).resolve().parents[2] / "ai_debug_logs"


def save_ai_exchange(
    *,
    system_prompt: str,
    user_prompt: str,
    raw_response: str,
    parsed_response: dict[str, Any] | None,
    model_used: str,
    ai_stats: dict[str, Any],
    task_inputs: dict[str, Any],
) -> None:
    """Persist a full AI planner exchange to disk (dev mode only)."""
    if not FLASK_DEBUG:
        return

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"ai_exchange_{ts}.json"

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model_used": model_used,
            "ai_stats": ai_stats,
            "task_inputs": _sanitize(task_inputs),
            "input": {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            },
            "output": {
                "raw_response": raw_response,
                "parsed_response": parsed_response,
            },
        }

        path = _LOG_DIR / filename
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        logger.info("AI debug log saved: %s", path)
    except Exception:
        logger.warning("Failed to save AI debug log", exc_info=True)


def _sanitize(obj: Any) -> Any:
    """Remove sensitive fields (API keys) and internal objects from task_inputs before logging."""
    if not isinstance(obj, dict):
        return obj
    return {
        k: ("***" if "key" in k.lower() or "secret" in k.lower() or "password" in k.lower() else v)
        for k, v in obj.items()
        if not k.startswith("_")  # strip internal keys like _weather_cells
    }
