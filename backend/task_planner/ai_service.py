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
)
from backend.task_planner.debug_logger import save_ai_exchange

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
        candidate = re.sub(r'[\x00-\x1F\x7F](?=[^"]*")', ' ', candidate)  # control chars near quotes
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        # Step 4: escape unescaped control chars inside JSON string values
        # This handles literal newlines/tabs inside "explanation" etc.
        def _escape_control_in_strings(s: str) -> str:
            """Walk through JSON text and escape control chars inside string literals."""
            out = []
            in_string = False
            escaped = False
            for ch in s:
                if escaped:
                    out.append(ch)
                    escaped = False
                    continue
                if ch == '\\' and in_string:
                    out.append(ch)
                    escaped = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    out.append(ch)
                    continue
                if in_string and ch in ('\n', '\r', '\t'):
                    out.append({'\n': '\\n', '\r': '\\r', '\t': '\\t'}[ch])
                    continue
                out.append(ch)
            return ''.join(out)

        candidate = _escape_control_in_strings(candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# OpenRouter: unified AI gateway with automatic model fallback
# ---------------------------------------------------------------------------

# Models tried in order; OpenRouter handles provider failover within each model.
# Gemini 2.5 Flash: excellent structured JSON output and reasoning at low cost
# Llama 3.3 70B: strong fallback with good instruction following
# DeepSeek-V3: capable and cost-effective last resort
_OPENROUTER_MODELS = [
    "google/gemini-2.5-flash",
    "meta-llama/llama-3.3-70b-instruct",
    "deepseek/deepseek-chat-v3-0324",
]

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _call_openrouter(prompt: str, system: str = "", api_key_override: str = "") -> tuple[str, str, dict]:
    """Call OpenRouter with model fallback chain.

    Returns (response_text, model_used, call_stats).
    """
    api_key = api_key_override
    if not api_key:
        raise ValueError("No OpenRouter API key provided")

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
        "max_tokens": 12288,
        "response_format": {"type": "json_object"},
    }

    t0 = time.perf_counter()
    stats: dict[str, Any] = {"attempts": [], "success": None, "total_time_ms": 0}

    try:
        resp = requests.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
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


def _call_ai_with_fallback(prompt: str, system: str = "", api_key_override: str = "") -> tuple[str, str, dict]:
    """Primary: OpenRouter with user-provided key (BYOK).

    If no user key is provided, falls back to direct provider calls
    using server-side legacy keys (if configured).
    Returns (response_text, model_name, call_stats).
    """
    if api_key_override:
        logger.info("Using OpenRouter (user-provided key)")
        return _call_openrouter(prompt, system, api_key_override=api_key_override)

    # Legacy direct-call fallback (only if no user key)
    logger.warning("No user OpenRouter key — falling back to legacy direct calls")
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
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 12288, "responseMimeType": "application/json"},
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
        json={"model": "llama-3.3-70b-versatile", "messages": messages, "temperature": 0.3, "max_tokens": 12288, "response_format": {"type": "json_object"}},
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
        json={"model": "deepseek-chat", "messages": messages, "temperature": 0.3, "max_tokens": 12288, "response_format": {"type": "json_object"}},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Task narrative generation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are an expert gliding meteorologist and cross-country flight planner \
with 20+ years soaring experience in Central Europe (Poland).

ROLE: You are the ROUTE DESIGNER. Given weather data, available waypoints, \
airspace restrictions, and pilot preferences, you must DESIGN optimal \
soaring routes and write an actionable pilot briefing. You propose the \
turnpoints, choose the route geometry, and explain why.

YOU MUST PROPOSE 1 OPTIMAL ROUTE using the provided waypoints. The route must \
use real waypoint coordinates from the AVAILABLE WAYPOINTS list. Do not \
invent coordinates — only use waypoints provided to you.

TEMPORAL AWARENESS: Weather data is labeled by time window:
- [morning] = 09:00-12:00 — thermal development, cumulus forming
- [midday] = 12:00-15:00 — peak thermal strength
- [afternoon] = 15:00-18:00 — thermal decay, overdevelopment risk
Your narrative MUST describe how conditions evolve through the day and \
advise the pilot accordingly (e.g., "complete the furthest leg by 14:00 \
before afternoon overdevelopment").

AIRSPACE SAFETY (CRITICAL):
- You are given a list of AIRSPACE ZONES with their types and altitude limits.
- NEVER route through RESTRICTED, PROHIBITED, or DANGER zones.
- Give a wide berth (2+ km) to CTR and TMA zones unless the pilot can \
  reasonably transit them (class D/E with radio).
- If you cannot avoid all restricted airspace, say so explicitly and \
  recommend the pilot consult with ATC.

ROUTE DESIGN PRINCIPLES:
- All routes must be CLOSED CIRCUITS returning to the takeoff airport.
- For conservative/standard safety: STRONGLY prefer triangles (2 TPs) or \
  quadrilaterals (3 TPs). These keep the pilot within glide range of home.
- Out-and-return (1 TP) is acceptable ONLY for aggressive safety or if no \
  multi-TP route is viable.
- Legs should NOT all be the same length. Use asymmetric routes: \
  short first leg into the wind, long second leg with tailwind, medium return. \
  This keeps the pilot close to home during the hardest (upwind) portion.
- The furthest-from-home leg should be flown during peak thermal hours (12:00-15:00).
- Prefer turnpoints that are near landable airports when possible.
- For the target distance: routes should total within ±15% of the requested distance.

WAYPOINT SELECTION:
- Choose turnpoints from the AVAILABLE WAYPOINTS list provided.
- Prefer cities/towns that are easy to identify from the air.
- Airports make excellent turnpoints — they provide emergency landing options.
- Consider weather at each waypoint (thermal strength, cloud base, wind).
- Reference turnpoints by their name in the narrative. Also mention \
  recognisable landmarks along each leg (rivers, lakes, motorways, forests).

RESPONSE LANGUAGE: Write ALL narrative text (explanation, weather_summary, \
safety_notes) in the language specified by the RESPONSE LANGUAGE field. \
Return only ONE version — do not duplicate in multiple languages.

WEATHER INTERPRETATION:
CAPE: >2000 J/kg = excellent thermals, 1000-2000 = good, 400-1000 = moderate, <400 = weak
Lapse rate: >3°C/1000ft = excellent, 2-3 = good, 1-2 = weak, <1 = stable
Cloud base: >6000ft = excellent, 4000-6000ft = very good, 2500-4000ft = moderate, \
1500-2500ft = marginal, <1500ft = poor
Wind: 0-8kt = ideal, 8-12kt = good, 12-18kt = acceptable, 18-25kt = challenging, >25kt = dangerous

SCORING: Rate the proposed route 0-100 based on:
- Thermal conditions along route: 40 pts
- Cloud base adequacy: 20 pts
- Wind favourability (tailwind on long legs): 20 pts
- Safety (airspace clearance, landable options): 20 pts

PILOT CUSTOM INSTRUCTIONS: If the prompt contains a "PILOT CUSTOM INSTRUCTIONS" \
section, those preferences have HIGHEST PRIORITY. Design the route to satisfy them. \
If the route cannot fully satisfy the instructions, explain why.

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


# Language code → full name for the LLM instruction
_LANG_NAMES = {"en": "English", "pl": "Polish", "de": "German", "cs": "Czech"}


def _build_task_prompt(
    waypoints: list[dict],
    weather_summary: list[str],
    task_inputs: dict,
    airspace_zones: list[dict] | None = None,
    terrain_info: dict | None = None,
    language: str = "en",
    custom_instructions: str = "",
    flyability_warning: list[str] | None = None,
) -> str:
    """Build the prompt for AI route design and narrative.

    The AI receives available waypoints, weather, airspace, and constraints,
    and proposes 3 routes using the provided waypoints.
    """
    safety = task_inputs.get('safety_profile', 'standard')
    lang_name = _LANG_NAMES.get(language, "English")
    takeoff_name = task_inputs.get('takeoff_airport', 'unknown')
    takeoff_lat = task_inputs.get('takeoff_lat', 0)
    takeoff_lon = task_inputs.get('takeoff_lon', 0)

    lines = [
        f"TASK REQUEST: {task_inputs.get('target_distance_km', 100)}km "
        f"{task_inputs.get('soaring_mode', 'thermal')} flight",
        f"TAKEOFF: {takeoff_name} ({takeoff_lat:.4f}N, {takeoff_lon:.4f}E)",
        f"TODAY: {date.today().isoformat()}",
        f"FLIGHT DATE: {task_inputs.get('flight_date', 'N/A')}",
        f"SAFETY PROFILE: {safety}",
        f"RESPONSE LANGUAGE: {lang_name}",
    ]

    if task_inputs.get('max_duration_hours'):
        lines.append(f"MAX DURATION: {task_inputs['max_duration_hours']}h")
    if task_inputs.get('takeoff_time'):
        lines.append(f"PLANNED TAKEOFF TIME: {task_inputs['takeoff_time']}")

    # User custom instructions — placed early so the model weighs them heavily
    if custom_instructions:
        lines.append('')
        lines.append('PILOT CUSTOM INSTRUCTIONS (HIGHEST PRIORITY — design routes that satisfy these):')
        lines.append(custom_instructions)

    # Add safety profile guidance
    if safety == "conservative":
        lines.append("")
        lines.append("SAFETY GUIDANCE: Pilot wants MAXIMUM safety. Design "
                      "triangle/multi-leg routes that keep within glide range of takeoff. "
                      "First leg MUST face into the wind so the return has tailwind. "
                      "Prefer turnpoints near landable airports.")
    elif safety == "standard":
        lines.append("")
        lines.append("SAFETY GUIDANCE: Balanced safety. Prefer triangle routes. "
                      "Starting into wind is recommended but not mandatory.")
    else:
        lines.append("")
        lines.append("SAFETY GUIDANCE: Aggressive — pilot accepts higher risk. "
                      "Out-and-return and longer routes are acceptable.")

    # Flyability warning — injected when conditions are clearly unflyable
    if flyability_warning:
        lines.append("")
        lines.append("⚠⚠⚠ FLYABILITY WARNING ⚠⚠⚠")
        lines.append("Conditions appear UNFLYABLE for thermal soaring. Issues:")
        for w in flyability_warning:
            lines.append(f"  - {w}")
        lines.append("You MUST include a clear recommendation to NOT FLY in your explanation ")
        lines.append("and safety_notes. Set score to 0-15 maximum. Still propose the least-bad ")
        lines.append("route in case the pilot insists, but make the danger abundantly clear.")

    # Weather summary with time-window labels
    lines.append("")
    lines.append("═══ WEATHER CONDITIONS ═══")
    for ws in weather_summary:
        lines.append(f"  {ws}")

    # Airspace zones — describe each zone so the AI can route around them
    if airspace_zones:
        # Always keep critical zones; cap minor ones to limit prompt size
        _CRITICAL_TYPES = {'RESTRICTED', 'PROHIBITED', 'DANGER', 'CTR', 'TMA'}
        critical = [z for z in airspace_zones if z.get('type') in _CRITICAL_TYPES]
        minor = [z for z in airspace_zones if z.get('type') not in _CRITICAL_TYPES]
        MAX_MINOR_ZONES = 20
        if len(minor) > MAX_MINOR_ZONES:
            minor = minor[:MAX_MINOR_ZONES]
        zones_to_show = critical + minor

        lines.append("")
        lines.append(f"═══ AIRSPACE ZONES ({len(zones_to_show)} in task area) ═══")
        # Zone types where the AI needs the actual boundary to plan routes
        _BOUNDARY_TYPES = _CRITICAL_TYPES
        for zone in zones_to_show:
            z_type = zone.get('type', '?')
            z_class = zone.get('airspace_class', '?')
            z_name = zone.get('name', '?')
            z_lower = zone.get('lower_limit_ft', 0)
            z_upper = zone.get('upper_limit_ft', 0)
            poly = zone.get('polygon', [])
            blocking = "⚠ AVOID" if z_type in ('RESTRICTED', 'PROHIBITED', 'DANGER') else ""

            if poly and z_type in _BOUNDARY_TYPES:
                # RDP simplification — preserves shape, caps at 8 vertices, 2dp precision
                simplified = _simplify_polygon(poly, max_points=8)
                boundary = " ".join(f"{p[0]:.2f}N/{p[1]:.2f}E" for p in simplified)
                lines.append(
                    f"  {z_name} | {z_type} class={z_class} | "
                    f"{z_lower}-{z_upper}ft | boundary=[{boundary}] {blocking}"
                )
            else:
                # Minor zones: center + radius is enough
                if poly:
                    center_lat = sum(p[0] for p in poly) / len(poly)
                    center_lon = sum(p[1] for p in poly) / len(poly)
                    max_dist = 0.0
                    for p in poly:
                        dlat = abs(p[0] - center_lat) * 111.0
                        dlon = abs(p[1] - center_lon) * 111.0 * math.cos(math.radians(center_lat))
                        d = math.sqrt(dlat ** 2 + dlon ** 2)
                        if d > max_dist:
                            max_dist = d
                    loc = f"center≈{center_lat:.2f}N {center_lon:.2f}E radius≈{max_dist:.0f}km"
                else:
                    loc = "location unknown"
                lines.append(
                    f"  {z_name} | {z_type} class={z_class} | "
                    f"{z_lower}-{z_upper}ft | {loc} {blocking}"
                )

    if terrain_info:
        lines.append("")
        lines.append(f"TERRAIN: max elevation {terrain_info.get('max_terrain_m', 0)}m ASL")

    # Available waypoints
    lines.append("")
    lines.append(f"═══ AVAILABLE WAYPOINTS ({len(waypoints)} reachable from takeoff) ═══")
    lines.append("Use ONLY these waypoints as turnpoints. Each includes distance/bearing from takeoff and local weather.")
    for wp in waypoints:
        lines.append(f"  {wp['summary_line']}")

    # Response format
    lines.append("")
    lines.append("═══ YOUR TASK ═══")
    lines.append("Design the BEST route using the available waypoints.")
    lines.append("The route is a closed circuit: Takeoff → TP1 → [TP2 → ...] → Takeoff.")
    lines.append("")
    lines.append("Return JSON with this EXACT structure:")
    lines.append('{')
    lines.append('  "route": {')
    lines.append('    "description": "<short label, e.g. Triangle via Rawicz and Leszno>",')
    lines.append('    "score": <0-100>,')
    lines.append('    "turnpoints": [')
    lines.append('      {"name": "<exact waypoint name from list>", "lat": <float>, "lon": <float>},')
    lines.append('      {"name": "<exact waypoint name from list>", "lat": <float>, "lon": <float>}')
    lines.append('    ]')
    lines.append('  },')
    lines.append(f'  "explanation": "<Detailed {lang_name} narrative: weather analysis by time '
                 'window (morning/midday/afternoon), route justification, per-leg tactical '
                 'advice (headwind/tailwind, dolphin flying, thermal strategy), landmarks '
                 'along each leg, safety considerations. Reference turnpoints by name.>",')
    lines.append(f'  "weather_summary": "<Thorough weather overview in {lang_name}: '
                 'how conditions change morning→midday→afternoon, cloud base evolution, '
                 'wind shifts, thermal strength progression, overdevelopment risk>",')
    lines.append('  "recommended_takeoff_time": "<HH:MM>",')
    lines.append('  "estimated_duration_hours": <float>,')
    lines.append('  "estimated_speed_kmh": <float>,')
    lines.append('  "safety_notes": ["<note1>", "<note2>", ...]')
    lines.append('}')

    return "\n".join(lines)


def generate_task_routes(
    waypoints: list[dict],
    weather_summary: list[str],
    task_inputs: dict,
    airspace_zones: list[dict] | None = None,
    terrain_info: dict | None = None,
    language: str = "en",
    api_key_override: str = "",
    custom_instructions: str = "",
) -> dict:
    """Ask the AI to design routes from available waypoints.

    Returns dict with routes[], weather_summary, safety_notes, etc.
    Falls back to error result if all AI providers fail.
    """
    # Assess flyability from raw weather cells passed via task_inputs
    flyability_warning: list[str] | None = None
    raw_weather_cells = task_inputs.get("_weather_cells")
    if raw_weather_cells:
        from backend.task_planner.weather import assess_flyability
        assessment = assess_flyability(raw_weather_cells)
        if not assessment["flyable"]:
            flyability_warning = assessment["reasons"]
            logger.warning("Conditions assessed as UNFLYABLE: %s", flyability_warning)

    prompt = _build_task_prompt(
        waypoints, weather_summary, task_inputs,
        airspace_zones=airspace_zones,
        terrain_info=terrain_info,
        language=language,
        custom_instructions=custom_instructions,
        flyability_warning=flyability_warning,
    )
    logger.info(
        "generate_task_routes: %d waypoints, %d weather cells, target=%skm, safety=%s, prompt=%d chars",
        len(waypoints), len(weather_summary),
        task_inputs.get('target_distance_km', '?'),
        task_inputs.get('safety_profile', '?'),
        len(prompt),
    )
    logger.debug("Full task prompt (%d chars):\n%s", len(prompt), prompt)

    raw_text, model, ai_stats = _call_ai_with_fallback(prompt, _SYSTEM_PROMPT, api_key_override=api_key_override)

    parsed = safe_json_parse(raw_text) if raw_text else None

    # Save full exchange to disk for analysis (dev mode only)
    save_ai_exchange(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=prompt,
        raw_response=raw_text,
        parsed_response=parsed,
        model_used=model,
        ai_stats=ai_stats,
        task_inputs=task_inputs,
    )

    if raw_text:
        if parsed and "route" in parsed and isinstance(parsed["route"], dict):
            logger.info(
                "AI route design OK: model=%s, score=%s",
                model, parsed["route"].get("score", "?"),
            )
            parsed["ai_model"] = model
            parsed["ai_stats"] = ai_stats
            return parsed
        logger.error("AI returned text but parse failed or no route. Raw (first 500 chars): %.500s", raw_text)

    # Fallback — no route available without AI
    logger.warning("All AI providers failed — cannot generate route")
    return {
        "route": None,
        "explanation": "",
        "weather_summary": "AI unavailable — cannot generate route proposal.",
        "safety_notes": ["AI route generation failed. Please try again or check your API key."],
        "ai_model": "none",
        "ai_stats": ai_stats,
    }


# ---------------------------------------------------------------------------
# Route validation helpers
# ---------------------------------------------------------------------------

def _thermal_label(index: float | None) -> str:
    """Human-readable thermal quality from numeric index."""
    if index is None:
        return "—"
    if index >= 7:
        return f"strong ({index:.1f})"
    if index >= 4:
        return f"moderate ({index:.1f})"
    return f"weak ({index:.1f})"


def _wind_label(wind_dir: int | None, wind_kts: float | None) -> str:
    """Human-readable wind string from direction and speed."""
    if wind_dir is None or wind_kts is None:
        return "—"
    return f"{wind_dir}°/{wind_kts:.0f}kt"


def _rdp_simplify(
    points: list[tuple[float, float]], epsilon: float
) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker polyline simplification (recursive)."""
    if len(points) <= 2:
        return points
    start, end = points[0], points[-1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    max_dist, max_idx = 0.0, 0
    for i in range(1, len(points) - 1):
        if dx == 0 and dy == 0:
            dist = math.hypot(points[i][0] - start[0], points[i][1] - start[1])
        else:
            t = max(0.0, min(1.0, (
                (points[i][0] - start[0]) * dx + (points[i][1] - start[1]) * dy
            ) / (dx * dx + dy * dy)))
            dist = math.hypot(
                points[i][0] - (start[0] + t * dx),
                points[i][1] - (start[1] + t * dy),
            )
        if dist > max_dist:
            max_dist, max_idx = dist, i
    if max_dist > epsilon:
        left = _rdp_simplify(points[: max_idx + 1], epsilon)
        right = _rdp_simplify(points[max_idx:], epsilon)
        return left[:-1] + right
    return [start, end]


def _simplify_polygon(
    poly: list[tuple[float, float]], max_points: int = 8
) -> list[tuple[float, float]]:
    """Simplify an airspace boundary polygon for inclusion in the AI prompt.

    Uses Ramer-Douglas-Peucker with ~2km tolerance (0.02°) to discard
    redundant collinear vertices while preserving the actual shape of narrow
    or irregular zones.  Falls back to uniform sampling if the result still
    exceeds *max_points*.
    """
    if len(poly) <= 4:
        return poly
    # RDP pass — 0.02° ≈ 2 km, acceptable for AI route planning
    simplified = _rdp_simplify(poly, epsilon=0.02)
    if len(simplified) <= max_points:
        return simplified
    # Uniform fallback to hard cap
    step = len(simplified) / max_points
    return [simplified[int(i * step) % len(simplified)] for i in range(max_points)]


def validate_ai_route(
    route: dict,
    takeoff_lat: float,
    takeoff_lon: float,
    available_waypoints: list[dict],
    max_waypoint_snap_km: float = 5.0,
) -> dict | None:
    """Validate and snap an AI-proposed route to real waypoint coordinates.

    Returns a validated route dict or None if invalid.
    Snaps each proposed turnpoint to the closest available waypoint within
    max_waypoint_snap_km to handle minor coordinate imprecision from the LLM.
    """
    turnpoints = route.get("turnpoints", [])
    if not turnpoints:
        logger.warning("AI route has no turnpoints: %s", route.get("description", "?"))
        return None

    from backend.task_planner.waypoints import _haversine, _bearing

    snapped_tps: list[dict] = []
    for tp in turnpoints:
        tp_lat = tp.get("lat", 0)
        tp_lon = tp.get("lon", 0)
        tp_name = tp.get("name", "?")

        # Find closest available waypoint
        best_wp = None
        best_dist = float("inf")
        for wp in available_waypoints:
            d = _haversine(tp_lat, tp_lon, wp["lat"], wp["lon"])
            if d < best_dist:
                best_dist = d
                best_wp = wp

        if best_wp and best_dist <= max_waypoint_snap_km:
            snapped_tps.append({
                "name": best_wp["name"],
                "lat": best_wp["lat"],
                "lon": best_wp["lon"],
                "type": best_wp.get("type", "town"),
                "icao": best_wp.get("icao"),
                "thermal_index": best_wp.get("thermal_index"),
                "wind_speed_kts": best_wp.get("wind_speed_kts"),
                "wind_dir": best_wp.get("wind_dir"),
                "cloud_base_ft": best_wp.get("cloud_base_ft"),
            })
            if best_dist > 0.5:
                logger.info("Snapped AI turnpoint '%s' → '%s' (%.1fkm offset)",
                            tp_name, best_wp["name"], best_dist)
        else:
            logger.warning(
                "AI turnpoint '%s' (%.4f, %.4f) not near any available waypoint "
                "(closest: %.1fkm > %.1fkm limit)",
                tp_name, tp_lat, tp_lon, best_dist, max_waypoint_snap_km,
            )
            return None

    # Build legs: takeoff → TP1 → TP2 → ... → takeoff
    legs = []
    points = [(takeoff_lat, takeoff_lon)] + [(tp["lat"], tp["lon"]) for tp in snapped_tps] + [(takeoff_lat, takeoff_lon)]
    names = ["Takeoff"] + [tp["name"] for tp in snapped_tps] + ["Takeoff"]

    # Build weather lookup from snapped turnpoints (keyed by name)
    wp_weather: dict[str, dict] = {}
    for tp in snapped_tps:
        label = _thermal_label(tp.get("thermal_index"))
        wind = _wind_label(tp.get("wind_dir"), tp.get("wind_speed_kts"))
        wp_weather[tp["name"]] = {
            "thermal_index": tp.get("thermal_index"),
            "thermal_quality": label,
            "wind_speed_kts": tp.get("wind_speed_kts"),
            "wind_dir": tp.get("wind_dir"),
            "wind_exposure": wind,
            "cloud_base_ft": tp.get("cloud_base_ft"),
        }

    # Add weather for the takeoff point from the nearest available waypoint
    best_to_dist = float("inf")
    best_to_wp = None
    for wp in available_waypoints:
        d = _haversine(takeoff_lat, takeoff_lon, wp["lat"], wp["lon"])
        if d < best_to_dist:
            best_to_dist = d
            best_to_wp = wp
    if best_to_wp:
        wp_weather["Takeoff"] = {
            "thermal_index": best_to_wp.get("thermal_index"),
            "thermal_quality": _thermal_label(best_to_wp.get("thermal_index")),
            "wind_speed_kts": best_to_wp.get("wind_speed_kts"),
            "wind_dir": best_to_wp.get("wind_dir"),
            "wind_exposure": _wind_label(best_to_wp.get("wind_dir"), best_to_wp.get("wind_speed_kts")),
            "cloud_base_ft": best_to_wp.get("cloud_base_ft"),
        }

    total_distance = 0.0
    for i in range(len(points) - 1):
        dist = _haversine(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
        brg = _bearing(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
        total_distance += dist
        # Attach weather from the destination waypoint of this leg
        dest_wx = wp_weather.get(names[i + 1], {})
        legs.append({
            "from": names[i],
            "to": names[i + 1],
            "from_lat": points[i][0],
            "from_lon": points[i][1],
            "to_lat": points[i + 1][0],
            "to_lon": points[i + 1][1],
            "distance_km": round(dist, 1),
            "bearing": round(brg, 0),
            "thermal_quality": dest_wx.get("thermal_quality", "—"),
            "wind_exposure": dest_wx.get("wind_exposure", "—"),
            "cloud_base_ft": dest_wx.get("cloud_base_ft"),
        })

    return {
        "description": route.get("description", "AI-proposed route"),
        "score": route.get("score", 50),
        "explanation": route.get("explanation", ""),
        "total_distance_km": round(total_distance, 1),
        # Full route: takeoff + intermediate TPs + destination (=takeoff for closed circuits)
        "turnpoints": (
            [{"lat": takeoff_lat, "lon": takeoff_lon}]
            + [{"lat": tp["lat"], "lon": tp["lon"]} for tp in snapped_tps]
            + [{"lat": takeoff_lat, "lon": takeoff_lon}]
        ),
        "turnpoint_names": (
            ["Takeoff"]
            + [tp["name"] for tp in snapped_tps]
            + ["Takeoff"]
        ),
        "legs": legs,
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
