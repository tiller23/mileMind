"""Tests for the Orchestrator on_progress callback integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.orchestrator import Orchestrator
from src.models.athlete import AthleteProfile
from src.models.decision_log import ReviewerScores
from src.models.plan_change import PlanChangeType
from src.models.progress import ProgressEvent, ProgressEventType

pytestmark = pytest.mark.asyncio


def _make_athlete() -> AthleteProfile:
    """Create a test athlete."""
    return AthleteProfile(
        name="Test Runner",
        age=30,
        weekly_mileage_base=30.0,
        goal_distance="5K",
    )


def _make_planner_result(plan_text: str = "Week 1: run") -> MagicMock:
    """Create a mock PlannerResult."""
    result = MagicMock()
    result.plan_text = plan_text
    result.tool_calls = []
    result.iterations = 3
    result.total_input_tokens = 500
    result.total_output_tokens = 300
    result.error = None
    result.validation = MagicMock()
    result.validation.passed = True
    return result


def _make_reviewer_result(approved: bool = True) -> MagicMock:
    """Create a mock ReviewerResult."""
    scores = ReviewerScores(safety=90, progression=85, specificity=80, feasibility=85)
    result = MagicMock()
    result.approved = approved
    result.scores = scores
    result.critique = "Looks good" if approved else "Needs more zone 2"
    result.issues = [] if approved else ["Insufficient easy running"]
    result.tool_calls = []
    result.iterations = 2
    result.total_input_tokens = 200
    result.total_output_tokens = 100
    result.error = None
    return result


class TestOnProgressCallback:
    """Tests for the on_progress callback in Orchestrator."""

    async def test_callback_receives_events_on_approval(self):
        """on_progress fires for planner_started, planner_complete, reviewer_started, reviewer_complete."""
        events: list[ProgressEvent] = []

        def on_progress(event: ProgressEvent) -> None:
            events.append(event)

        planner = AsyncMock()
        planner.model = "claude-sonnet-4-20250514"
        planner.generate_plan = AsyncMock(return_value=_make_planner_result())

        reviewer = AsyncMock()
        reviewer.model = "claude-opus-4-20250514"
        reviewer.review_plan = AsyncMock(return_value=_make_reviewer_result(approved=True))

        orchestrator = Orchestrator(
            planner=planner,
            reviewer=reviewer,
            on_progress=on_progress,
        )

        result = await orchestrator.generate_plan(_make_athlete())
        assert result.approved is True

        event_types = [e.event_type for e in events]
        assert ProgressEventType.PLANNER_STARTED in event_types
        assert ProgressEventType.PLANNER_COMPLETE in event_types
        assert ProgressEventType.REVIEWER_STARTED in event_types
        assert ProgressEventType.REVIEWER_COMPLETE in event_types

    async def test_callback_receives_retry_events(self):
        """on_progress fires retry events when plan is rejected then approved."""
        events: list[ProgressEvent] = []

        def on_progress(event: ProgressEvent) -> None:
            events.append(event)

        planner = AsyncMock()
        planner.model = "claude-sonnet-4-20250514"
        planner.generate_plan = AsyncMock(return_value=_make_planner_result())
        planner.revise_plan = AsyncMock(return_value=_make_planner_result("Revised plan"))

        reviewer = AsyncMock()
        reviewer.model = "claude-opus-4-20250514"
        reviewer.review_plan = AsyncMock(
            side_effect=[
                _make_reviewer_result(approved=False),
                _make_reviewer_result(approved=True),
            ]
        )

        orchestrator = Orchestrator(
            planner=planner,
            reviewer=reviewer,
            max_retries=2,
            on_progress=on_progress,
        )

        result = await orchestrator.generate_plan(_make_athlete())
        assert result.approved is True

        event_types = [e.event_type for e in events]
        assert ProgressEventType.RETRY in event_types
        # Should have 2 planner_started events (one per attempt)
        assert event_types.count(ProgressEventType.PLANNER_STARTED) == 2

    async def test_no_callback_does_not_error(self):
        """Orchestrator works fine without on_progress callback."""
        planner = AsyncMock()
        planner.model = "claude-sonnet-4-20250514"
        planner.generate_plan = AsyncMock(return_value=_make_planner_result())

        reviewer = AsyncMock()
        reviewer.model = "claude-opus-4-20250514"
        reviewer.review_plan = AsyncMock(return_value=_make_reviewer_result(approved=True))

        orchestrator = Orchestrator(
            planner=planner,
            reviewer=reviewer,
            on_progress=None,
        )

        result = await orchestrator.generate_plan(_make_athlete())
        assert result.approved is True

    async def test_tweak_skips_reviewer_events(self):
        """TWEAK change_type does not emit reviewer events."""
        events: list[ProgressEvent] = []

        def on_progress(event: ProgressEvent) -> None:
            events.append(event)

        planner = AsyncMock()
        planner.model = "claude-sonnet-4-20250514"
        planner.generate_plan = AsyncMock(return_value=_make_planner_result())

        reviewer = AsyncMock()
        reviewer.model = "claude-opus-4-20250514"

        orchestrator = Orchestrator(
            planner=planner,
            reviewer=reviewer,
            on_progress=on_progress,
        )

        result = await orchestrator.generate_plan(
            _make_athlete(),
            change_type=PlanChangeType.TWEAK,
        )
        assert result.approved is True

        event_types = [e.event_type for e in events]
        assert ProgressEventType.REVIEWER_STARTED not in event_types
        assert ProgressEventType.REVIEWER_COMPLETE not in event_types
