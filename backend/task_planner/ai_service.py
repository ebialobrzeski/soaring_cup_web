"""AI service — LLM integration via OpenRouter (unified gateway).

Provides:
  generate_task_narrative()     — final LLM-based scoring/narrative for top candidates
  analyze_weather_for_task()    — summarize weather grid for the LLM
  safe_json_parse()             — robust JSON extraction from LLM output
  _call_openrouter()            — single wrapper with automatic model fallback

OpenRouter handles provider failover, rate limits, and load balancing.
Fallback chain: Gemini Flash → Llama 3.3 70B → DeepSeek Chat.
Legacy direct-call wrappers kept as dead-code backup.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from backend.config import (
    DEEPSEEK_API_KEY,
    GEMINI_API_KEY,
    GROQ_API_KEY,
    OPENROUTER_API_KEY,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON parsing (robust, handles LLM artifacts)
# ---------------------------------------------------------------------------

def safe_json_parse(text: str) -> Optional[dict]:
    """Multi-step JSON repair for LLM responses."""
    # Step 1: try as-is
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    if not text:
        return None

    # Step 2: extract first JSON block
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        candidate = match.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        # Step 3: fix common LLM artifacts
        candidate = re.sub(r',\s*([}\]])', r'\1', candidate)  # trailing commas
        candidate = re.sub(r'[\x00-\x1F\x7F](?=[^"]*")', ' ', candidate)  # control chars
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# OpenRouter: unified AI gateway with automatic model fallback
# ---------------------------------------------------------------------------

# Models tried in order; OpenRouter handles provider failover within each model.
_OPENROUTER_MODELS = [
    "google/gemini-2.0-flash-001",
    "meta-llama/llama-3.3-70b-instruct",
    "deepseek/deepseek-chat",
]

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _call_openrouter(prompt: str, system: str = "") -> tuple[str, str, dict]:
    """Call OpenRouter with model fallback chain.

    Returns (response_text, model_used, call_stats).
    """
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not configured")

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    logger.info("OpenRouter request: models=%s, system_prompt=%d chars, user_prompt=%d chars",
                _OPENROUTER_MODELS, len(system), len(prompt))
    logger.debug("OpenRouter system prompt (first 500 chars): %.500s", system)
    logger.debug("OpenRouter user prompt (first 1000 chars): %.1000s", prompt)

    body: dict[str, Any] = {
        "model": _OPENROUTER_MODELS[0],
        "models": _OPENROUTER_MODELS,
        "route": "fallback",
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }

    t0 = time.perf_counter()
    stats: dict[str, Any] = {"attempts": [], "success": None, "total_time_ms": 0}

    try:
        resp = requests.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://soaring-cup.com",
                "X-OpenRouter-Title": "Soaring Cup AI Planner",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=90,
        )
        elapsed = int((time.perf_counter() - t0) * 1000)

        if resp.status_code != 200:
            logger.error("OpenRouter HTTP %d: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        data = resp.json()

        model_used = data.get("model", _OPENROUTER_MODELS[0])
        # Normalise model slug to short name  e.g. "google/gemini-2.0-flash-001" → "gemini-2.0-flash"
        short_model = model_used.split("/")[-1] if "/" in model_used else model_used
        text = data["choices"][0]["message"]["content"]

        usage = data.get("usage", {})
        cost = usage.get("cost")

        stats["attempts"].append({
            "provider": "openrouter",
            "model": model_used,
            "status": "ok",
            "time_ms": elapsed,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "cost": cost,
        })
        stats["success"] = short_model
        stats["total_time_ms"] = elapsed

        logger.info(
            "OpenRouter OK: model=%s, %dms, tokens=%s (prompt=%s, completion=%s), cost=$%s",
            model_used, elapsed,
            usage.get("total_tokens", "?"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
            f"{cost:.6f}" if cost is not None else "?",
        )
        logger.debug("OpenRouter response (first 1000 chars): %.1000s", text)
        return text, short_model, stats

    except Exception:
        elapsed = int((time.perf_counter() - t0) * 1000)
        logger.error("OpenRouter call FAILED after %dms", elapsed, exc_info=True)
        stats["attempts"].append({"provider": "openrouter", "status": "error", "time_ms": elapsed})
        stats["total_time_ms"] = elapsed

    return "", "none", stats


def _call_ai_with_fallback(prompt: str, system: str = "") -> tuple[str, str, dict]:
    """Primary: OpenRouter (handles Gemini → Llama → DeepSeek fallback).

    If OPENROUTER_API_KEY is not set, falls back to direct provider calls.
    Returns (response_text, model_name, call_stats).
    """
    if OPENROUTER_API_KEY:
        logger.info("Using OpenRouter (key present)")
        return _call_openrouter(prompt, system)

    # Legacy direct-call fallback (only if OpenRouter key missing)
    logger.warning("OPENROUTER_API_KEY not set — falling back to legacy direct calls")
    return _call_direct_fallback(prompt, system)


# ---------------------------------------------------------------------------
# Legacy direct-call wrappers (backup when OpenRouter key is absent)
# ---------------------------------------------------------------------------

def _call_direct_fallback(prompt: str, system: str = "") -> tuple[str, str, dict]:
    """Direct Gemini → Groq → DeepSeek fallback (legacy)."""
    providers: list[tuple[str, Any]] = []
    if GEMINI_API_KEY:
        providers.append(("gemini", _call_gemini_direct))
    if GROQ_API_KEY:
        providers.append(("groq", _call_groq_direct))
    if DEEPSEEK_API_KEY:
        providers.append(("deepseek", _call_deepseek_direct))

    stats: dict = {"attempts": [], "success": None, "total_time_ms": 0}

    for name, fn in providers:
        t0 = time.perf_counter()
        try:
            text = fn(prompt, system)
            elapsed = int((time.perf_counter() - t0) * 1000)
            logger.info("Direct AI call OK: %s (%dms)", name, elapsed)
            stats["attempts"].append({"provider": name, "status": "ok", "time_ms": elapsed})
            stats["success"] = name
            stats["total_time_ms"] = elapsed
            return text, name, stats
        except Exception:
            elapsed = int((time.perf_counter() - t0) * 1000)
            logger.warning("Direct AI %s failed (%dms)", name, elapsed, exc_info=True)
            stats["attempts"].append({"provider": name, "status": "error", "time_ms": elapsed})
            stats["total_time_ms"] += elapsed

    return "", "none", stats


def _call_gemini_direct(prompt: str, system: str = "") -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    body: dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096, "responseMimeType": "application/json"},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    resp = requests.post(url, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError("Gemini returned no candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    return parts[0].get("text", "") if parts else ""


def _call_groq_direct(prompt: str, system: str = "") -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={"model": "llama-3.3-70b-versatile", "messages": messages, "temperature": 0.3, "max_tokens": 4096, "response_format": {"type": "json_object"}},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_deepseek_direct(prompt: str, system: str = "") -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
        json={"model": "deepseek-chat", "messages": messages, "temperature": 0.3, "max_tokens": 4096, "response_format": {"type": "json_object"}},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Task narrative generation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are an expert gliding meteorologist and cross-country flight planner \
with 20+ years soaring experience in Central Europe (Poland).

SCORING CRITERIA (total 100 pts):
- Thermal Strength: 40 pts
- Cloud Base: 30 pts
- Wind: 20 pts
- Thermal Index: 10 pts

CAPE interpretation:
- >2000 J/kg = excellent thermals
- 1500-2000 = strong
- 1000-1500 = good
- 700-1000 = moderate
- 400-700 = weak
- <400 = very weak

Lapse rate thresholds:
- >3°C/1000ft = very unstable, excellent thermals
- 2-3 = unstable, good thermals
- 1-2 = neutral, weak thermals
- <1 = stable, no thermals

Cloud base scoring:
- >6000ft = excellent (+30)
- 4000-6000ft = very good (+25)
- 2500-4000ft = moderate (+20)
- 1500-2500ft = marginal (+10)
- <1500ft = poor (+0)

Wind scoring:
- 0-8 kts = ideal (+20)
- 8-12 kts = very good (+16)
- 12-18 kts = acceptable (+10)
- 18-25 kts = challenging (+5)
- >25 kts = dangerous (+0); gusts >15 kts = -20 pts

Return ONLY valid JSON. No commentary outside the JSON."""

# Load custom instructions from global file (if present)
_INSTRUCTIONS_PATH = Path(__file__).resolve().parents[2] / "ai_planner_instructions.md"

def _load_custom_instructions() -> str:
    """Read the global AI planner instructions file."""
    logger.debug("Looking for custom instructions at: %s", _INSTRUCTIONS_PATH)
    try:
        if not _INSTRUCTIONS_PATH.is_file():
            logger.warning("Custom instructions file NOT FOUND: %s", _INSTRUCTIONS_PATH)
            return ""
        text = _INSTRUCTIONS_PATH.read_text(encoding="utf-8").strip()
        if not text:
            logger.warning("Custom instructions file is EMPTY: %s", _INSTRUCTIONS_PATH)
            return ""
        logger.info(
            "Loaded custom AI planner instructions (%d chars, %d lines) from %s",
            len(text), text.count('\n') + 1, _INSTRUCTIONS_PATH,
        )
        logger.debug("Custom instructions content:\n%s", text)
        return text
    except Exception:
        logger.error("Failed to read AI planner instructions", exc_info=True)
    return ""

_CUSTOM_INSTRUCTIONS = _load_custom_instructions()
if _CUSTOM_INSTRUCTIONS:
    _SYSTEM_PROMPT = _SYSTEM_PROMPT + "\n\nADDITIONAL INSTRUCTIONS:\n" + _CUSTOM_INSTRUCTIONS
    logger.info("System prompt now includes custom instructions (total %d chars)", len(_SYSTEM_PROMPT))
else:
    logger.warning("No custom instructions loaded — using built-in system prompt only")
logger.debug("Final system prompt:\n%s", _SYSTEM_PROMPT)


def _build_task_prompt(
    candidates: list[dict],
    weather_summary: list[str],
    task_inputs: dict,
    airspace_info: Optional[dict] = None,
    terrain_info: Optional[dict] = None,
) -> str:
    """Build the prompt for final task selection and narrative."""
    lines = [
        f"TASK REQUEST: {task_inputs.get('target_distance_km', 100)}km "
        f"{task_inputs.get('soaring_mode', 'thermal')} flight from "
        f"{task_inputs.get('takeoff_airport', 'unknown')}",
        f"DATE: {task_inputs.get('flight_date', 'N/A')}",
        f"SAFETY PROFILE: {task_inputs.get('safety_profile', 'standard')}",
        "",
        "WEATHER CONDITIONS (grid cell summaries):",
    ]
    for ws in weather_summary[:30]:  # limit to 30 cells
        lines.append(f"  {ws}")

    if airspace_info:
        lines.append("")
        lines.append(f"AIRSPACE: {airspace_info.get('zones_count', 0)} zones, "
                      f"{airspace_info.get('conflicts', 0)} conflicts")

    if terrain_info:
        lines.append(f"TERRAIN: max elevation {terrain_info.get('max_terrain_m', 0)}m ASL")

    lines.append("")
    lines.append(f"TOP {len(candidates)} CANDIDATE ROUTES:")
    for i, c in enumerate(candidates, 1):
        lines.append(f"  Route {i}: {c.get('description', 'N/A')}")
        lines.append(f"    Distance: {c.get('total_distance_km', 0):.1f}km, "
                      f"Score: {c.get('score', 0):.0f}/100")
        legs = c.get("legs", [])
        for j, leg in enumerate(legs):
            lines.append(f"    Leg {j+1}: {leg.get('from', '?')} → {leg.get('to', '?')} "
                          f"({leg.get('distance_km', 0):.1f}km, {leg.get('bearing', 0):.0f}°)")

    lines.append("")
    lines.append("Analyze these routes. Return JSON with this structure:")
    lines.append('{')
    lines.append('  "selected_route": <1-based index of best route>,')
    lines.append('  "score": <0-100 integer>,')
    lines.append('  "explanation_en": "<Detailed English narrative: weather analysis, '
                 'route justification, safety notes, thermal strategy, estimated XC speed>",')
    lines.append('  "explanation_pl": "<Same in Polish>",')
    lines.append('  "weather_summary_en": "<Brief weather overview in English>",')
    lines.append('  "weather_summary_pl": "<Brief weather overview in Polish>",')
    lines.append('  "recommended_takeoff_time": "<HH:MM>",')
    lines.append('  "estimated_duration_hours": <float>,')
    lines.append('  "estimated_speed_kmh": <float>,')
    lines.append('  "safety_notes": ["<note1>", "<note2>"]')
    lines.append('}')

    return "\n".join(lines)


def generate_task_narrative(
    candidates: list[dict],
    weather_summary: list[str],
    task_inputs: dict,
    airspace_info: Optional[dict] = None,
    terrain_info: Optional[dict] = None,
) -> dict:
    """Send top candidates to LLM for final selection and narrative.

    Returns dict with selected_route, score, explanation, etc.
    Falls back to rule-based scoring if all AI providers fail.
    """
    prompt = _build_task_prompt(
        candidates, weather_summary, task_inputs, airspace_info, terrain_info,
    )
    logger.info(
        "generate_task_narrative: %d candidates, %d weather cells, target=%skm, safety=%s",
        len(candidates), len(weather_summary),
        task_inputs.get('target_distance_km', '?'),
        task_inputs.get('safety_profile', '?'),
    )
    logger.debug("Full task prompt (%d chars):\n%s", len(prompt), prompt)

    raw_text, model, ai_stats = _call_ai_with_fallback(prompt, _SYSTEM_PROMPT)

    if raw_text:
        parsed = safe_json_parse(raw_text)
        if parsed:
            logger.info(
                "AI narrative OK: model=%s, score=%s, selected_route=%s",
                model, parsed.get('score', '?'), parsed.get('selected_route', '?'),
            )
            parsed["ai_model"] = model
            parsed["ai_stats"] = ai_stats
            return parsed
        logger.error("AI returned text but JSON parse failed. Raw (first 500 chars): %.500s", raw_text)

    # Rule-based fallback
    logger.warning("All AI providers failed — using rule-based scoring")
    result = _rule_based_fallback(candidates, task_inputs)
    result["ai_stats"] = ai_stats
    return result


def _rule_based_fallback(candidates: list[dict], task_inputs: dict) -> dict:
    """Simple rule-based scoring when AI is unavailable."""
    if not candidates:
        return {
            "selected_route": 0,
            "score": 0,
            "explanation_en": "No candidate routes could be generated.",
            "explanation_pl": "Nie udało się wygenerować tras.",
            "ai_model": "rule_based",
        }

    best = candidates[0]
    return {
        "selected_route": 1,
        "score": int(best.get("score", 50)),
        "explanation_en": (
            f"Route selected based on numeric scoring. "
            f"Total distance: {best.get('total_distance_km', 0):.1f}km. "
            f"AI narrative unavailable — review weather conditions manually."
        ),
        "explanation_pl": (
            f"Trasa wybrana na podstawie punktacji numerycznej. "
            f"Dystans: {best.get('total_distance_km', 0):.1f}km. "
            f"Opis AI niedostępny — sprawdź warunki pogodowe ręcznie."
        ),
        "weather_summary_en": "AI weather summary unavailable.",
        "weather_summary_pl": "Podsumowanie pogody AI niedostępne.",
        "ai_model": "rule_based",
    }


# ---------------------------------------------------------------------------
# Weather analysis for forecast feature (batch)
# ---------------------------------------------------------------------------

def analyze_batch_gliding_conditions(
    forecasts: list[dict],
    airport_info: dict,
) -> dict:
    """Analyze multiple days of forecasts in ONE AI call.

    Returns:
        analyses_en: {date_str: {score, explanation}}
        analyses_pl: {date_str: {score, explanation}}
        model: provider name
    """
    if not forecasts:
        return {"analyses_en": {}, "analyses_pl": {}, "model": "none"}

    # Group by date
    by_date: dict[str, list[dict]] = {}
    for f in forecasts:
        d = f.get("date", f.get("time", ""))[:10]
        by_date.setdefault(d, []).append(f)

    # Build compact prompt
    airport_name = airport_info.get("name", "Unknown")
    runway = airport_info.get("runwayDirection", "N/A")

    lines = [
        f"You are an expert gliding meteorologist analyzing weather for {airport_name}.",
        f"RUNWAY: {runway}",
        "",
        "You MUST provide analysis in BOTH English AND Polish.",
        f"ANALYZE THE FOLLOWING {len(by_date)} DAYS:",
        "",
    ]

    for date_str, day_forecasts in sorted(by_date.items()):
        lines.append(f"━━━━ DAY: {date_str} ━━━━")
        for f in day_forecasts[:5]:  # max 5 time slots per day
            t = f.get("time", f.get("hour", "??:??"))
            ws = f.get("wind_speed", 0)
            wd = f.get("wind_direction", 0)
            cb = f.get("cloud_base", 0)
            cc = f.get("cloud_cover", 0)
            temp = f.get("temperature", 0)
            dp = f.get("dew_point", 0)
            ti = f.get("thermal_index", 0)
            cape = f.get("cape", 0)
            solar = f.get("solar_radiation", 0)
            lines.append(
                f"{t} | Wind: {ws:.0f}kts from {wd}° | CB: {cb}ft | CC: {cc}% | "
                f"Temp: {temp:.0f}°C | DP: {dp:.0f}°C | Thermal: {ti:.1f}/10 | "
                f"CAPE: {cape:.0f} J/kg | Solar: {solar:.0f} W/m²"
            )
        lines.append("")

    lines.append('Return JSON: {"days": {"YYYY-MM-DD": {"score": 0-100, '
                  '"explanation_en": "...", "explanation_pl": "..."}}}')
    lines.append("Keep brief. Return ONLY JSON.")

    prompt = "\n".join(lines)
    raw_text, model, _ai_stats = _call_ai_with_fallback(prompt, _SYSTEM_PROMPT)

    result: dict[str, Any] = {"analyses_en": {}, "analyses_pl": {}, "model": model}

    if raw_text:
        parsed = safe_json_parse(raw_text)
        if parsed and "days" in parsed:
            for d, info in parsed["days"].items():
                result["analyses_en"][d] = {
                    "score": info.get("score", 0),
                    "explanation": info.get("explanation_en", ""),
                }
                result["analyses_pl"][d] = {
                    "score": info.get("score", 0),
                    "explanation": info.get("explanation_pl", ""),
                }
            return result

    # Rule-based fallback for batch
    for date_str, day_forecasts in by_date.items():
        score = _rule_based_score(day_forecasts)
        result["analyses_en"][date_str] = {"score": score, "explanation": "Rule-based score (AI unavailable)"}
        result["analyses_pl"][date_str] = {"score": score, "explanation": "Punktacja automatyczna (AI niedostępne)"}
    result["model"] = "rule_based"
    return result


def _rule_based_score(forecasts: list[dict]) -> int:
    """Simple rule-based scoring for a day's forecasts."""
    if not forecasts:
        return 0

    # Average of key metrics
    thermal_scores = []
    cb_scores = []
    wind_scores = []

    for f in forecasts:
        ti = f.get("thermal_index", 0) or 0
        thermal_scores.append(min(40, ti * 4))

        cb = f.get("cloud_base", 0) or 0
        if cb > 6000:
            cb_scores.append(30)
        elif cb > 4000:
            cb_scores.append(25)
        elif cb > 2500:
            cb_scores.append(20)
        elif cb > 1500:
            cb_scores.append(10)
        else:
            cb_scores.append(0)

        ws = f.get("wind_speed", 0) or 0
        if ws <= 8:
            wind_scores.append(20)
        elif ws <= 12:
            wind_scores.append(16)
        elif ws <= 18:
            wind_scores.append(10)
        elif ws <= 25:
            wind_scores.append(5)
        else:
            wind_scores.append(0)

    avg = lambda lst: sum(lst) / len(lst) if lst else 0
    total = avg(thermal_scores) + avg(cb_scores) + avg(wind_scores)
    return min(100, max(0, int(total)))
