"""Tests for workout domain models."""

import pytest
from pydantic import ValidationError

from src.models.workout import PaceZone, Workout, WorkoutLog, WorkoutType


class TestWorkoutType:
    """Tests for WorkoutType enum."""

    def test_all_11_values(self) -> None:
        assert len(WorkoutType) == 11

    @pytest.mark.parametrize(
        "value",
        [
            "easy", "long_run", "tempo", "interval", "repetition",
            "recovery", "marathon_pace", "fartlek", "hill", "rest", "cross_train",
        ],
    )
    def test_valid_values(self, value: str) -> None:
        assert WorkoutType(value).value == value


class TestPaceZone:
    """Tests for PaceZone enum."""

    def test_all_5_values(self) -> None:
        assert len(PaceZone) == 5

    @pytest.mark.parametrize(
        "value", ["easy", "marathon", "threshold", "interval", "repetition"],
    )
    def test_valid_values(self, value: str) -> None:
        assert PaceZone(value).value == value


class TestWorkout:
    """Tests for Workout model validation."""

    def _valid_workout(self, **overrides) -> Workout:
        defaults = {
            "day": 1,
            "workout_type": WorkoutType.EASY,
            "distance_km": 8.0,
            "duration_minutes": 45.0,
            "intensity": 0.5,
        }
        defaults.update(overrides)
        return Workout(**defaults)

    def test_valid_workout(self) -> None:
        w = self._valid_workout()
        assert w.day == 1
        assert w.workout_type == WorkoutType.EASY
        assert w.distance_km == 8.0

    @pytest.mark.parametrize("day", [1, 4, 7])
    def test_valid_day_values(self, day: int) -> None:
        w = self._valid_workout(day=day)
        assert w.day == day

    def test_day_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._valid_workout(day=0)

    def test_day_eight_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._valid_workout(day=8)

    def test_negative_distance_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._valid_workout(distance_km=-1.0)

    def test_zero_distance_allowed(self) -> None:
        w = self._valid_workout(distance_km=0.0)
        assert w.distance_km == 0.0

    def test_negative_duration_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._valid_workout(duration_minutes=-1.0)

    def test_intensity_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._valid_workout(intensity=1.1)

    def test_intensity_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._valid_workout(intensity=-0.1)

    def test_intensity_boundaries(self) -> None:
        assert self._valid_workout(intensity=0.0).intensity == 0.0
        assert self._valid_workout(intensity=1.0).intensity == 1.0

    def test_pace_zone_optional(self) -> None:
        w = self._valid_workout(pace_zone=None)
        assert w.pace_zone is None

    def test_tss_optional(self) -> None:
        w = self._valid_workout(tss=None)
        assert w.tss is None

    def test_description_default_empty(self) -> None:
        w = self._valid_workout()
        assert w.description == ""


class TestWorkoutLog:
    """Tests for WorkoutLog model validation."""

    def _valid_log(self, **overrides) -> WorkoutLog:
        defaults = {
            "workout_day": 1,
            "actual_distance_km": 5.0,
            "actual_duration_minutes": 30.0,
        }
        defaults.update(overrides)
        return WorkoutLog(**defaults)

    def test_valid_log(self) -> None:
        log = self._valid_log()
        assert log.workout_day == 1

    def test_day_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._valid_log(workout_day=0)

    def test_day_eight_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._valid_log(workout_day=8)

    def test_heart_rate_boundaries(self) -> None:
        assert self._valid_log(avg_heart_rate=30).avg_heart_rate == 30
        assert self._valid_log(avg_heart_rate=250).avg_heart_rate == 250

    def test_heart_rate_below_30_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._valid_log(avg_heart_rate=29)

    def test_heart_rate_above_250_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._valid_log(avg_heart_rate=251)

    def test_rpe_boundaries(self) -> None:
        assert self._valid_log(rpe=1).rpe == 1
        assert self._valid_log(rpe=10).rpe == 10

    def test_rpe_below_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._valid_log(rpe=0)

    def test_rpe_above_ten_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._valid_log(rpe=11)

    def test_negative_distance_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._valid_log(actual_distance_km=-1.0)

    def test_optional_fields_default_none(self) -> None:
        log = self._valid_log()
        assert log.avg_heart_rate is None
        assert log.rpe is None
        assert log.actual_tss is None
        assert log.actual_pace_sec_per_km is None
