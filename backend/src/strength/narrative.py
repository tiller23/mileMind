"""Narrative generation for the strength playbook.

Single Haiku call per (profile_shape + catalog_version). Output is a
short blurb per block explaining WHY these exercises matter for this
runner. The LLM NEVER picks exercises and is forbidden from prescribing
sets/reps.

Resilience: if the transport raises or returns unparseable JSON, we
fall back to each block's static ``rationale_fallback``. The playbook
page must render even when the API is unavailable.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from typing import Any

from src.agents.shared import sanitize_prompt_text
from src.agents.transport import AnthropicTransport, MessageTransport
from src.models.athlete import AthleteProfile
from src.strength.models import Playbook

logger = logging.getLogger(__name__)

NARRATIVE_MODEL = "claude-haiku-4-5-20251001"
NARRATIVE_MAX_TOKENS = 600

# Module-level in-memory cache. Bounded to avoid unbounded growth in
# long-running workers; we only need it to dedupe repeated loads of the
# same profile shape in a single process.
_CACHE: dict[str, dict[str, str]] = {}
_CACHE_LIMIT = 512

_SYSTEM_PROMPT = (
    "You are a running-specific strength coach writing short block intros "
    "for a runner's playbook. For each block the runner will see, return a "
    "1-2 sentence rationale in second person ('you/your'). Be specific to "
    "their context (goal race, injury history tags) when relevant. "
    "DO NOT prescribe sets, reps, weights, or frequency. "
    "DO NOT invent physiology, VO2max changes, or heart-rate effects. "
    "Keep each blurb under 280 characters. "
    "Return ONLY valid JSON mapping block_id to rationale string, no prose."
)


def _cache_key(playbook: Playbook) -> str:
    """Derive a stable cache key from playbook-shaping inputs.

    Includes catalog_version so a catalog edit automatically invalidates
    prior narratives.
    """
    payload = {
        "v": playbook.catalog_version,
        "summary": playbook.profile_summary,
        "block_ids": [b.block_id for b in playbook.blocks],
    }
    serialized = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _fallback_narrative(playbook: Playbook) -> dict[str, str]:
    """Return the per-block static fallback rationale map."""
    return {b.block_id: b.rationale_fallback for b in playbook.blocks}


def _build_user_message(playbook: Playbook, profile: AthleteProfile) -> str:
    """Build the single user-turn prompt for the Haiku call."""
    block_summary = [
        {
            "block_id": b.block_id,
            "title": b.title,
            "matched_injury_tags": list(b.matched_injury_tags),
            "example_exercises": [e.name for e in b.exercises[:3]],
        }
        for b in playbook.blocks
    ]
    athlete_context = {
        "goal_distance": sanitize_prompt_text(profile.goal_distance),
        "injury_tags": [t.value for t in profile.injury_tags],
        "experience_tier": playbook.profile_summary.get("experience_tier"),
        "current_acute_injury": profile.current_acute_injury,
        "current_injury_description": sanitize_prompt_text(
            profile.current_injury_description
        )[:200],
        "injury_history_text": sanitize_prompt_text(profile.injury_history)[:300],
    }
    return (
        "Runner context:\n"
        f"{json.dumps(athlete_context, indent=2)}\n\n"
        "Blocks to write rationales for:\n"
        f"{json.dumps(block_summary, indent=2)}\n\n"
        "Return JSON like: {\"posterior_chain\": \"...\", \"calf_achilles\": \"...\"}"
    )


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

# Blurbs should be motivational prose, not prescriptions. If the LLM drifts
# into prescribing loads/reps/frequencies (including via prompt injection),
# force that block back to its static fallback rationale.
_PRESCRIPTION_RE = re.compile(
    r"\b(\d+\s*(?:sets?|reps?|lbs?|kg|kilos?|pounds?|%\s?1?rm|minutes?|mins?)"
    r"|sets?\s*of\s*\d|reps?\s*of\s*\d"
    r"|\d+\s*x\s*\d+"
    r"|rpe\s*\d)\b",
    re.IGNORECASE,
)


def _looks_prescriptive(text: str) -> bool:
    """Return True when a blurb reads like a workout prescription."""
    return bool(_PRESCRIPTION_RE.search(text))


def _extract_json_map(text: str) -> dict[str, str] | None:
    """Extract the first JSON object from text and validate string values.

    Returns None if no valid object is found.
    """
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    clean: dict[str, str] = {}
    for key, value in parsed.items():
        if isinstance(key, str) and isinstance(value, str):
            clean[key] = value.strip()
    return clean or None


async def generate_narrative(
    playbook: Playbook,
    profile: AthleteProfile,
    *,
    transport: MessageTransport | None = None,
    api_key: str | None = None,
) -> dict[str, str]:
    """Produce a per-block rationale map for the playbook.

    Returns ``{block_id: "1-2 sentence rationale"}`` covering every block
    in the playbook. Missing block_ids are filled from static fallbacks.

    Args:
        playbook: The built playbook. ``catalog_version`` + ``profile_summary``
            are folded into the cache key.
        profile: The full athlete profile (for sanitized text context).
        transport: Optional MessageTransport override (for tests). Default
            is a fresh AnthropicTransport built from ``api_key``.
        api_key: Anthropic API key. Required when ``transport`` is None.

    Returns:
        Mapping of block_id to rationale string. Always contains an entry
        for every block in the playbook.
    """
    key = _cache_key(playbook)
    if key in _CACHE:
        return _CACHE[key]

    fallback = _fallback_narrative(playbook)

    if transport is None:
        if not api_key:
            logger.warning("generate_narrative: no transport and no api_key, using fallback")
            return fallback
        transport = AnthropicTransport(api_key=api_key)

    user_message = _build_user_message(playbook, profile)

    try:
        response: Any = await transport.create_message(
            model=NARRATIVE_MODEL,
            max_tokens=NARRATIVE_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            tools=[],
            messages=[{"role": "user", "content": user_message}],
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — resilience is the whole point
        logger.warning("generate_narrative: transport error %s, using fallback", exc)
        return fallback

    text_chunks: list[str] = []
    for block in getattr(response, "content", []) or []:
        block_text = getattr(block, "text", None)
        if block_text:
            text_chunks.append(block_text)
    text = "".join(text_chunks)

    parsed = _extract_json_map(text)
    if parsed is None:
        logger.warning("generate_narrative: unparseable response, using fallback")
        return fallback

    result = dict(fallback)
    for block_id, rationale in parsed.items():
        if block_id not in fallback or not rationale:
            continue
        trimmed = rationale[:400]
        if _looks_prescriptive(trimmed):
            # Drop prescriptive output; leave static fallback in place.
            logger.warning(
                "generate_narrative: prescriptive blurb rejected for %s", block_id
            )
            continue
        result[block_id] = trimmed

    if len(_CACHE) >= _CACHE_LIMIT:
        _CACHE.clear()
    _CACHE[key] = result
    return result


def clear_cache() -> None:
    """Clear the narrative cache (test hook)."""
    _CACHE.clear()
