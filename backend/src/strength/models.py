"""Dataclasses for the strength playbook.

All frozen for safe sharing across async boundaries and cache keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Exercise:
    """A single strength exercise drawn from the curated catalog.

    Attributes:
        id: Stable catalog identifier (e.g., ``single_leg_rdl``).
        name: Human-readable display name.
        block_id: Block this exercise belongs to.
        equipment: Tuple of equipment options (e.g., ``("bodyweight", "dumbbells")``).
        difficulty: ``beginner`` | ``intermediate`` | ``advanced``.
        beneficial_for: Injury tags that this exercise tends to help.
        contraindicated_for: Injury tags that exclude this exercise.
        search_query: Suggested phrase for a form/video search link.
        why_runners: One-sentence runner-facing justification (catalog copy).
    """

    id: str
    name: str
    block_id: str
    equipment: tuple[str, ...]
    difficulty: str
    beneficial_for: tuple[str, ...]
    contraindicated_for: tuple[str, ...]
    search_query: str
    why_runners: str = ""


@dataclass(frozen=True)
class ExerciseBlock:
    """A themed group of exercises (e.g., posterior chain).

    Attributes:
        block_id: Stable block key (e.g., ``posterior_chain``).
        title: Human-readable block title.
        rationale_fallback: Static blurb used when LLM narrative is unavailable.
        exercises: Ordered tuple of selected exercises (best match first).
        matched_injury_tags: Injury tags from the athlete that boosted this block.
    """

    block_id: str
    title: str
    rationale_fallback: str
    exercises: tuple[Exercise, ...]
    matched_injury_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Playbook:
    """A complete strength playbook for one athlete at one point in time.

    Attributes:
        blocks: Ordered tuple of exercise blocks.
        catalog_version: SHA-256 of the catalog bytes at build time.
        profile_summary: Shallow dict of inputs that drove selection
            (used as part of the narrative cache key).
    """

    blocks: tuple[ExerciseBlock, ...]
    catalog_version: str
    profile_summary: dict[str, Any] = field(default_factory=dict)
