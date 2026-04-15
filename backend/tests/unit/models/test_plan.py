"""Tests for training plan domain models."""

import pytest
from pydantic import ValidationError

from src.models.plan import PlanWeek, TrainingPhase, TrainingPlan
from src.models.workout import Workout, WorkoutType


class TestTrainingPhase:
    """Tests for TrainingPhase enum."""

    def test_all_5_values(self) -> None:
        assert len(TrainingPhase) == 5

    @pytest.mark.parametrize(
        "value",
        ["base", "build", "peak", "taper", "recovery"],
    )
    def test_valid_values(self, value: str) -> None:
        assert TrainingPhase(value).value == value


class TestPlanWeek:
    """Tests for PlanWeek model and computed properties."""

    def _make_workout(
        self,
        day: int = 1,
        wtype: WorkoutType = WorkoutType.EASY,
        distance: float = 8.0,
        duration: float = 45.0,
        intensity: float = 0.5,
    ) -> Workout:
        return Workout(
            day=day,
            workout_type=wtype,
            distance_km=distance,
            duration_minutes=duration,
            intensity=intensity,
        )

    def test_week_number_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            PlanWeek(week_number=0, phase=TrainingPhase.BASE)

    def test_valid_week(self) -> None:
        w = PlanWeek(week_number=1, phase=TrainingPhase.BASE)
        assert w.week_number == 1
        assert w.phase == TrainingPhase.BASE

    def test_total_distance_km_sums_workouts(self) -> None:
        workouts = [
            self._make_workout(day=1, distance=8.0),
            self._make_workout(day=2, distance=10.0),
            self._make_workout(day=3, distance=5.0),
        ]
        week = PlanWeek(week_number=1, phase=TrainingPhase.BASE, workouts=workouts)
        assert week.total_distance_km == pytest.approx(23.0)

    def test_total_distance_km_empty(self) -> None:
        week = PlanWeek(week_number=1, phase=TrainingPhase.BASE)
        assert week.total_distance_km == 0.0

    def test_total_duration_minutes_sums_workouts(self) -> None:
        workouts = [
            self._make_workout(day=1, duration=30.0),
            self._make_workout(day=2, duration=60.0),
        ]
        week = PlanWeek(week_number=1, phase=TrainingPhase.BUILD, workouts=workouts)
        assert week.total_duration_minutes == pytest.approx(90.0)

    def test_training_days_excludes_rest(self) -> None:
        workouts = [
            self._make_workout(day=1, wtype=WorkoutType.EASY),
            self._make_workout(day=2, wtype=WorkoutType.REST, distance=0, duration=0, intensity=0),
            self._make_workout(day=3, wtype=WorkoutType.LONG_RUN),
        ]
        week = PlanWeek(week_number=1, phase=TrainingPhase.BASE, workouts=workouts)
        assert week.training_days == 2

    def test_training_days_all_rest(self) -> None:
        workouts = [
            self._make_workout(day=d, wtype=WorkoutType.REST, distance=0, duration=0, intensity=0)
            for d in range(1, 4)
        ]
        week = PlanWeek(week_number=1, phase=TrainingPhase.RECOVERY, workouts=workouts)
        assert week.training_days == 0


class TestTrainingPlan:
    """Tests for TrainingPlan model and computed properties."""

    def _make_week(self, num: int, phase: TrainingPhase) -> PlanWeek:
        return PlanWeek(week_number=num, phase=phase)

    def test_total_weeks(self) -> None:
        plan = TrainingPlan(
            athlete_name="Test",
            goal_event="5K",
            weeks=[self._make_week(i, TrainingPhase.BASE) for i in range(1, 5)],
        )
        assert plan.total_weeks == 4

    def test_total_weeks_empty(self) -> None:
        plan = TrainingPlan(athlete_name="Test", goal_event="5K")
        assert plan.total_weeks == 0

    def test_phase_distribution(self) -> None:
        weeks = [
            self._make_week(1, TrainingPhase.BASE),
            self._make_week(2, TrainingPhase.BASE),
            self._make_week(3, TrainingPhase.BUILD),
            self._make_week(4, TrainingPhase.TAPER),
        ]
        plan = TrainingPlan(athlete_name="Test", goal_event="marathon", weeks=weeks)
        dist = plan.phase_distribution
        assert dist[TrainingPhase.BASE] == 2
        assert dist[TrainingPhase.BUILD] == 1
        assert dist[TrainingPhase.TAPER] == 1

    def test_phase_distribution_empty(self) -> None:
        plan = TrainingPlan(athlete_name="Test", goal_event="5K")
        assert plan.phase_distribution == {}

    def test_optional_fields(self) -> None:
        plan = TrainingPlan(athlete_name="Test", goal_event="5K")
        assert plan.goal_date is None
        assert plan.predicted_finish_time_minutes is None
        assert plan.notes == ""
