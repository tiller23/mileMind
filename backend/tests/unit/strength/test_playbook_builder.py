"""Unit tests for the deterministic strength playbook builder."""

from __future__ import annotations

import json
from pathlib import Path

from src.models.athlete import AthleteProfile, InjuryTag
from src.strength.playbook_builder import (
    _CATALOG_PATH,
    build_playbook,
    catalog_version,
)


def _profile(**overrides) -> AthleteProfile:
    base = dict(
        name="Test Runner",
        age=32,
        weekly_mileage_base=40.0,
        goal_distance="marathon",
    )
    base.update(overrides)
    return AthleteProfile(**base)


def test_baseline_blocks_always_present() -> None:
    pb = build_playbook(_profile(goal_distance="5K", weekly_mileage_base=20.0))
    ids = [b.block_id for b in pb.blocks]
    assert "posterior_chain" in ids
    assert "single_leg_stability" in ids
    assert "hip_glute" in ids
    assert "calf_achilles" in ids


def test_long_goal_adds_core_block() -> None:
    pb = build_playbook(_profile(goal_distance="half marathon"))
    ids = [b.block_id for b in pb.blocks]
    assert "core_anti_rotation" in ids


def test_short_goal_no_core_block() -> None:
    pb = build_playbook(_profile(goal_distance="5K", injury_tags=()))
    ids = [b.block_id for b in pb.blocks]
    assert "core_anti_rotation" not in ids


def test_lower_back_tag_forces_core_block_even_for_5k() -> None:
    pb = build_playbook(_profile(goal_distance="5K", injury_tags=(InjuryTag.LOWER_BACK,)))
    ids = [b.block_id for b in pb.blocks]
    assert "core_anti_rotation" in ids


def test_contraindication_filtering_removes_exercise() -> None:
    # Good morning is contraindicated for lower_back.
    pb = build_playbook(_profile(injury_tags=(InjuryTag.LOWER_BACK,)))
    posterior = next(b for b in pb.blocks if b.block_id == "posterior_chain")
    ex_ids = {e.id for e in posterior.exercises}
    assert "good_morning" not in ex_ids
    assert "kettlebell_swing" not in ex_ids


def test_beneficial_exercise_ranks_first() -> None:
    pb = build_playbook(_profile(injury_tags=(InjuryTag.ACHILLES,)))
    calf = next(b for b in pb.blocks if b.block_id == "calf_achilles")
    # single_leg_calf_raise is beneficial for achilles + plantar + shin (3 tags),
    # so it must outrank plain standing_calf_raise which only hits achilles.
    ids = [e.id for e in calf.exercises]
    assert ids.index("single_leg_calf_raise") < ids.index("standing_calf_raise")


def test_matched_injury_tags_populated() -> None:
    pb = build_playbook(_profile(injury_tags=(InjuryTag.IT_BAND,)))
    hip_glute = next(b for b in pb.blocks if b.block_id == "hip_glute")
    assert "it_band" in hip_glute.matched_injury_tags


def test_empty_injury_tags_returns_baseline() -> None:
    # No injury tags should produce baseline blocks (no special filters).
    pb = build_playbook(_profile(injury_tags=()))
    block_ids = [b.block_id for b in pb.blocks]
    assert "posterior_chain" in block_ids
    assert "single_leg_stability" in block_ids
    # No matched_injury_tags anywhere when there are no tags.
    for block in pb.blocks:
        assert block.matched_injury_tags == ()


def test_block_exercise_counts_within_range() -> None:
    pb = build_playbook(_profile())
    for block in pb.blocks:
        assert 3 <= len(block.exercises) <= 5, block.block_id


def test_experience_tier_beginner_avoids_advanced() -> None:
    pb = build_playbook(_profile(weekly_mileage_base=15.0, injury_tags=(), goal_distance="5K"))
    # Beginners should not have pistol_squat_progression (advanced) ranked
    # above easier options.
    sl = next(b for b in pb.blocks if b.block_id == "single_leg_stability")
    ids = [e.id for e in sl.exercises]
    if "pistol_squat_progression" in ids:
        # Should be last if present at all.
        assert ids[-1] == "pistol_squat_progression"


def test_deterministic_output() -> None:
    p = _profile(injury_tags=(InjuryTag.IT_BAND, InjuryTag.ACHILLES))
    a = build_playbook(p)
    b = build_playbook(p)
    assert [blk.block_id for blk in a.blocks] == [blk.block_id for blk in b.blocks]
    for blk_a, blk_b in zip(a.blocks, b.blocks):
        assert [e.id for e in blk_a.exercises] == [e.id for e in blk_b.exercises]


def test_catalog_version_is_short_hex() -> None:
    v = catalog_version()
    assert len(v) == 16
    int(v, 16)  # parses as hex


def test_catalog_integrity_all_tags_valid() -> None:
    """Every beneficial_for/contraindicated_for must be a valid InjuryTag value."""
    catalog = json.loads(Path(_CATALOG_PATH).read_bytes())
    valid_tags = {tag.value for tag in InjuryTag}
    block_ids = set(catalog["blocks"].keys())
    for exercise in catalog["exercises"]:
        assert exercise["block_id"] in block_ids, exercise["id"]
        for tag in exercise.get("beneficial_for", []):
            assert tag in valid_tags, f"{exercise['id']}: unknown tag {tag}"
        for tag in exercise.get("contraindicated_for", []):
            assert tag in valid_tags, f"{exercise['id']}: unknown tag {tag}"
        assert exercise["difficulty"] in {"beginner", "intermediate", "advanced"}


def test_every_block_has_at_least_three_exercises_in_catalog() -> None:
    catalog = json.loads(Path(_CATALOG_PATH).read_bytes())
    counts: dict[str, int] = {}
    for exercise in catalog["exercises"]:
        counts[exercise["block_id"]] = counts.get(exercise["block_id"], 0) + 1
    for block_id in catalog["blocks"]:
        assert counts.get(block_id, 0) >= 3, block_id


def test_profile_summary_includes_acute_flag() -> None:
    pb = build_playbook(_profile(current_acute_injury=True))
    assert pb.profile_summary["current_acute_injury"] is True
