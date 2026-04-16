"""Deterministic strength playbook builder.

Pure Python, no AI. Given an AthleteProfile, returns a Playbook composed
of 3–5 exercise blocks with 3–5 exercises each. Exercise selection is
driven by injury tags, goal distance, and experience tier.

Blocks:
    - posterior_chain (always included)
    - single_leg_stability (always included)
    - hip_glute (included when IT band / hip / knee in tags, else still included as baseline)
    - core_anti_rotation (always included for half-marathon+, optional for shorter)
    - calf_achilles (always included; heavier bias when achilles/plantar/shin tags present)

Contraindication filtering: any exercise whose ``contraindicated_for``
intersects the athlete's ``injury_tags`` is dropped entirely.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.models.athlete import AthleteProfile
from src.strength.models import Exercise, ExerciseBlock, Playbook

_CATALOG_PATH = Path(__file__).parent / "exercise_catalog.json"

# Goal distance keywords that imply half-marathon or longer.
_LONG_GOAL_KEYWORDS = ("half", "marathon", "50k", "50 k", "ultra", "100k", "100 k")

# Max exercises returned per block.
_BLOCK_LIMIT = 5
_BLOCK_MIN = 3


@lru_cache(maxsize=1)
def _load_catalog_raw() -> tuple[dict[str, Any], str]:
    """Load and cache the catalog JSON along with its SHA-256 hash.

    Returns:
        Tuple of (parsed catalog dict, 16-char SHA-256 prefix string).
    """
    raw_bytes = _CATALOG_PATH.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
    return json.loads(raw_bytes), digest


@lru_cache(maxsize=1)
def _all_exercises() -> tuple[Exercise, ...]:
    """Return all catalog exercises as immutable Exercise dataclasses."""
    catalog, _ = _load_catalog_raw()
    return tuple(
        Exercise(
            id=item["id"],
            name=item["name"],
            block_id=item["block_id"],
            equipment=tuple(item["equipment"]),
            difficulty=item["difficulty"],
            beneficial_for=tuple(item.get("beneficial_for", ())),
            contraindicated_for=tuple(item.get("contraindicated_for", ())),
            search_query=item["search_query"],
            why_runners=item.get("why_runners", ""),
        )
        for item in catalog["exercises"]
    )


def catalog_version() -> str:
    """Return the current catalog content hash (short SHA-256 prefix)."""
    _, digest = _load_catalog_raw()
    return digest


def _block_metadata(block_id: str) -> tuple[str, str]:
    """Return (title, rationale_fallback) for a block id."""
    catalog, _ = _load_catalog_raw()
    block = catalog["blocks"][block_id]
    return block["title"], block["rationale_fallback"]


def _is_long_goal(goal_distance: str) -> bool:
    """Return True when the goal is half-marathon or longer."""
    lowered = goal_distance.lower()
    return any(kw in lowered for kw in _LONG_GOAL_KEYWORDS)


def _experience_tier(profile: AthleteProfile) -> str:
    """Map weekly mileage baseline to a coarse experience tier.

    Returns:
        ``"beginner"`` (<25 km/wk), ``"intermediate"`` (25–60), ``"advanced"`` (>60).
    """
    wm = profile.weekly_mileage_base
    if wm < 25:
        return "beginner"
    if wm < 60:
        return "intermediate"
    return "advanced"


_DIFFICULTY_RANK = {"beginner": 0, "intermediate": 1, "advanced": 2}


def _difficulty_penalty(exercise_difficulty: str, experience_tier: str) -> int:
    """Lower is better. Penalizes exercises that mismatch the athlete's tier.

    Beginners get a hard penalty on advanced; advanced athletes get a mild
    penalty on beginner (not harmful, just less interesting).
    """
    ex_rank = _DIFFICULTY_RANK[exercise_difficulty]
    tier_rank = _DIFFICULTY_RANK[experience_tier]
    if ex_rank > tier_rank:
        # Too hard: strong negative signal.
        return (ex_rank - tier_rank) * 10
    # Too easy (or matched): mild penalty only.
    return tier_rank - ex_rank


def _select_block(
    block_id: str,
    profile: AthleteProfile,
    injury_tag_values: set[str],
) -> ExerciseBlock:
    """Filter + rank exercises for one block."""
    tier = _experience_tier(profile)
    candidates = [ex for ex in _all_exercises() if ex.block_id == block_id]

    # Drop contraindicated exercises outright.
    candidates = [ex for ex in candidates if not (set(ex.contraindicated_for) & injury_tag_values)]

    def sort_key(ex: Exercise) -> tuple[int, int, str]:
        # Negative count so higher overlap sorts first under ascending sort.
        beneficial_overlap = -len(set(ex.beneficial_for) & injury_tag_values)
        difficulty_score = _difficulty_penalty(ex.difficulty, tier)
        return (beneficial_overlap, difficulty_score, ex.id)

    candidates.sort(key=sort_key)
    selected = tuple(candidates[:_BLOCK_LIMIT])
    if len(selected) < _BLOCK_MIN and len(candidates) >= _BLOCK_MIN:
        # Should not happen with current catalog; defensive fallback.
        selected = tuple(candidates[:_BLOCK_MIN])

    matched = tuple(
        tag
        for tag in sorted(injury_tag_values)
        if any(tag in ex.beneficial_for for ex in selected)
    )

    title, rationale_fallback = _block_metadata(block_id)
    return ExerciseBlock(
        block_id=block_id,
        title=title,
        rationale_fallback=rationale_fallback,
        exercises=selected,
        matched_injury_tags=matched,
    )


def build_playbook(profile: AthleteProfile) -> Playbook:
    """Build a deterministic strength playbook for the given athlete.

    Args:
        profile: Frozen athlete profile (injury_tags, goal, mileage baseline).

    Returns:
        Playbook with 4–5 blocks depending on goal distance; all exercises
        deterministically selected and ranked.
    """
    injury_tag_values = {tag.value for tag in profile.injury_tags}

    block_order: list[str] = [
        "posterior_chain",
        "single_leg_stability",
        "hip_glute",
        "calf_achilles",
    ]
    if _is_long_goal(profile.goal_distance) or injury_tag_values & {
        "lower_back",
        "hip",
    }:
        # Core anti-rotation for longer races or specific injury history.
        block_order.append("core_anti_rotation")

    blocks = tuple(_select_block(bid, profile, injury_tag_values) for bid in block_order)

    summary = {
        "injury_tags": sorted(injury_tag_values),
        "goal_distance": profile.goal_distance,
        "experience_tier": _experience_tier(profile),
        "current_acute_injury": profile.current_acute_injury,
    }
    return Playbook(
        blocks=blocks,
        catalog_version=catalog_version(),
        profile_summary=summary,
    )
