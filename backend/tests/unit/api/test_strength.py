"""API route tests for /strength/playbook."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DBAthleteProfile, User
from src.strength.narrative import clear_cache


@pytest.fixture(autouse=True)
def _reset_narrative_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture(autouse=True)
def _stub_narrative(monkeypatch) -> None:
    """Short-circuit the Haiku call in all /strength tests."""

    async def _fake_generate_narrative(playbook, profile, **_kwargs: Any):
        return {b.block_id: f"stub {b.block_id}" for b in playbook.blocks}

    monkeypatch.setattr(
        "src.api.routes.strength.generate_narrative", _fake_generate_narrative
    )


async def test_playbook_404_without_profile(client) -> None:
    response = await client.get("/api/v1/strength/playbook")
    assert response.status_code == 404


async def test_playbook_returns_blocks(
    client, db_session: AsyncSession, test_user: User
) -> None:
    profile = DBAthleteProfile(
        user_id=test_user.id,
        name="Runner",
        age=30,
        weekly_mileage_base=40.0,
        goal_distance="marathon",
        injury_tags=["it_band"],
    )
    db_session.add(profile)
    await db_session.commit()

    response = await client.get("/api/v1/strength/playbook")
    assert response.status_code == 200
    body = response.json()
    assert "blocks" in body
    block_ids = [b["block_id"] for b in body["blocks"]]
    assert "posterior_chain" in block_ids
    assert "hip_glute" in block_ids
    assert body["catalog_version"]
    # Narrative stub populated the rationale.
    for block in body["blocks"]:
        assert block["rationale"].startswith("stub ")


async def test_playbook_acute_gate_active(
    client, db_session: AsyncSession, test_user: User
) -> None:
    profile = DBAthleteProfile(
        user_id=test_user.id,
        name="Runner",
        age=30,
        weekly_mileage_base=30.0,
        goal_distance="10K",
        injury_tags=[],
        current_acute_injury=True,
        current_injury_description="Tweaked my knee yesterday",
    )
    db_session.add(profile)
    await db_session.commit()

    response = await client.get("/api/v1/strength/playbook")
    assert response.status_code == 200
    body = response.json()
    assert body["acute_injury_gate"]["active"] is True
    assert "knee" in body["acute_injury_gate"]["description"]
    # Server-side suppression: no exercises are returned while acute.
    assert body["blocks"] == []


async def test_playbook_acute_gate_inactive_by_default(
    client, db_session: AsyncSession, test_user: User
) -> None:
    profile = DBAthleteProfile(
        user_id=test_user.id,
        name="Runner",
        age=30,
        weekly_mileage_base=30.0,
        goal_distance="10K",
    )
    db_session.add(profile)
    await db_session.commit()

    response = await client.get("/api/v1/strength/playbook")
    assert response.status_code == 200
    assert response.json()["acute_injury_gate"]["active"] is False
