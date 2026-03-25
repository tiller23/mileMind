#!/usr/bin/env python3
"""Seed demo data into the MileMind database.

Creates a demo user with 3 pre-generated training plans that can be
browsed without authentication. Idempotent — safe to run multiple times.

Usage:
    cd backend
    python scripts/seed_demo_data.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Add backend to path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings
from src.db.models import Base, DBAthleteProfile, TrainingPlan, User
from src.demo.constants import DEMO_PLAN_IDS, DEMO_USER_ID

PLANS_DIR = Path(__file__).resolve().parent.parent / "src" / "demo" / "plans"

PLAN_FILES = {
    "beginner_5k": PLANS_DIR / "beginner_5k.json",
    "intermediate_half": PLANS_DIR / "intermediate_half.json",
    "advanced_marathon": PLANS_DIR / "advanced_marathon.json",
}


async def seed(session: AsyncSession) -> None:
    """Seed demo user and plans.

    Args:
        session: Async database session.
    """
    # Upsert demo user
    result = await session.execute(select(User).where(User.id == DEMO_USER_ID))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            id=DEMO_USER_ID,
            email="demo@milemind.app",
            name="Demo User",
            auth_provider="demo",
            auth_provider_id="demo",
            role="user",
            invite_code_used="DEMO",
        )
        session.add(user)
        await session.flush()
        print(f"  Created demo user: {DEMO_USER_ID}")
    else:
        print(f"  Demo user already exists: {DEMO_USER_ID}")

    # Seed each plan
    for plan_key, plan_file in PLAN_FILES.items():
        plan_id = DEMO_PLAN_IDS[plan_key]
        data = json.loads(plan_file.read_text())

        # Upsert profile for this plan's athlete
        snapshot = data["athlete_snapshot"]

        # Check if plan already exists
        result = await session.execute(
            select(TrainingPlan).where(TrainingPlan.id == plan_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing plan
            existing.athlete_snapshot = snapshot
            existing.plan_data = data["plan_data"]
            existing.decision_log = data["decision_log"]
            existing.scores = data["scores"]
            existing.approved = data["approved"]
            existing.total_tokens = data["total_tokens"]
            existing.estimated_cost_usd = data["estimated_cost_usd"]
            print(f"  Updated plan: {plan_key} ({plan_id})")
        else:
            plan = TrainingPlan(
                id=plan_id,
                user_id=DEMO_USER_ID,
                athlete_snapshot=snapshot,
                plan_data=data["plan_data"],
                decision_log=data["decision_log"],
                scores=data["scores"],
                approved=data["approved"],
                status="active",
                total_tokens=data["total_tokens"],
                estimated_cost_usd=data["estimated_cost_usd"],
            )
            session.add(plan)
            print(f"  Created plan: {plan_key} ({plan_id})")

    await session.commit()
    print("\nDemo data seeded successfully!")


async def main() -> None:
    """Entry point."""
    settings = get_settings()
    print(f"Database: {settings.database_url}")
    print("Seeding demo data...\n")

    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        await seed(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
