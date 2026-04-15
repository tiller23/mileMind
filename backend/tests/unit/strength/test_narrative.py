"""Unit tests for narrative generation (transport mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.models.athlete import AthleteProfile, InjuryTag
from src.strength import build_playbook
from src.strength.narrative import clear_cache, generate_narrative


class _StubTransport:
    """Minimal MessageTransport stub returning canned content."""

    def __init__(self, text: str, *, should_raise: bool = False) -> None:
        self.text = text
        self.should_raise = should_raise
        self.calls = 0

    async def create_message(self, **_kwargs: Any) -> Any:
        self.calls += 1
        if self.should_raise:
            raise RuntimeError("boom")
        return SimpleNamespace(content=[SimpleNamespace(text=self.text)])


def _profile() -> AthleteProfile:
    return AthleteProfile(
        name="Narrator",
        age=30,
        weekly_mileage_base=35.0,
        goal_distance="marathon",
        injury_tags=(InjuryTag.IT_BAND,),
    )


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.mark.asyncio
async def test_narrative_from_parseable_response() -> None:
    profile = _profile()
    pb = build_playbook(profile)
    valid_json = (
        '{"posterior_chain": "Your glutes drive miles.", '
        '"single_leg_stability": "One-leg work = one-leg sport.", '
        '"hip_glute": "IT band loves hip strength.", '
        '"calf_achilles": "Resilient calves = durable runner.", '
        '"core_anti_rotation": "Keep your energy going forward."}'
    )
    transport = _StubTransport(valid_json)
    result = await generate_narrative(pb, profile, transport=transport)
    assert result["posterior_chain"].startswith("Your glutes")
    assert transport.calls == 1


@pytest.mark.asyncio
async def test_fallback_on_transport_error() -> None:
    profile = _profile()
    pb = build_playbook(profile)
    transport = _StubTransport("", should_raise=True)
    result = await generate_narrative(pb, profile, transport=transport)
    # Must contain a fallback for every block in the playbook.
    for block in pb.blocks:
        assert result[block.block_id] == block.rationale_fallback


@pytest.mark.asyncio
async def test_fallback_on_unparseable_response() -> None:
    profile = _profile()
    pb = build_playbook(profile)
    transport = _StubTransport("this is not json at all")
    result = await generate_narrative(pb, profile, transport=transport)
    for block in pb.blocks:
        assert result[block.block_id] == block.rationale_fallback


@pytest.mark.asyncio
async def test_cache_hit_avoids_transport() -> None:
    profile = _profile()
    pb = build_playbook(profile)
    valid_json = '{"posterior_chain": "cached blurb"}'
    transport = _StubTransport(valid_json)
    first = await generate_narrative(pb, profile, transport=transport)
    second = await generate_narrative(pb, profile, transport=transport)
    assert first == second
    assert transport.calls == 1


@pytest.mark.asyncio
async def test_fallback_used_for_missing_block_ids() -> None:
    profile = _profile()
    pb = build_playbook(profile)
    # Only one block returned — others must fall back.
    transport = _StubTransport('{"posterior_chain": "just this one"}')
    result = await generate_narrative(pb, profile, transport=transport)
    assert result["posterior_chain"] == "just this one"
    for block in pb.blocks:
        if block.block_id != "posterior_chain":
            assert result[block.block_id] == block.rationale_fallback


@pytest.mark.asyncio
async def test_no_api_key_no_transport_returns_fallback() -> None:
    profile = _profile()
    pb = build_playbook(profile)
    result = await generate_narrative(pb, profile, transport=None, api_key=None)
    for block in pb.blocks:
        assert result[block.block_id] == block.rationale_fallback


@pytest.mark.asyncio
async def test_concurrent_calls_coalesce_to_one_transport_call() -> None:
    """Thundering herd: N parallel callers must hit the API once."""
    import asyncio

    profile = _profile()
    pb = build_playbook(profile)

    class _SlowStub:
        def __init__(self) -> None:
            self.calls = 0

        async def create_message(self, **_kwargs: Any) -> Any:
            self.calls += 1
            await asyncio.sleep(0.05)
            return SimpleNamespace(content=[SimpleNamespace(text='{"posterior_chain": "ok"}')])

    transport = _SlowStub()
    results = await asyncio.gather(
        *(generate_narrative(pb, profile, transport=transport) for _ in range(5))
    )
    assert transport.calls == 1
    # All callers got the same dict.
    for r in results:
        assert r == results[0]


@pytest.mark.asyncio
async def test_prescriptive_blurb_falls_back() -> None:
    """A blurb that drifts into reps/sets must be replaced by fallback."""
    profile = _profile()
    pb = build_playbook(profile)
    bad = '{"posterior_chain": "Do 3 sets of 10 reps at 70% 1RM."}'
    transport = _StubTransport(bad)
    result = await generate_narrative(pb, profile, transport=transport)
    assert (
        result["posterior_chain"]
        == next(b for b in pb.blocks if b.block_id == "posterior_chain").rationale_fallback
    )


@pytest.mark.asyncio
async def test_catalog_version_change_invalidates_cache() -> None:
    """Changing catalog_version must produce a new cache key."""
    from dataclasses import replace

    profile = _profile()
    pb = build_playbook(profile)
    transport = _StubTransport('{"posterior_chain": "first"}')
    first = await generate_narrative(pb, profile, transport=transport)
    assert transport.calls == 1

    # Forge a different catalog_version on a fresh playbook copy.
    pb_v2 = replace(pb, catalog_version="other-version")
    transport2 = _StubTransport('{"posterior_chain": "second"}')
    second = await generate_narrative(pb_v2, profile, transport=transport2)
    assert transport2.calls == 1
    assert first["posterior_chain"] != second["posterior_chain"]
