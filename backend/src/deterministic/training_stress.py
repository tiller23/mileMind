"""Training Stress Score (TSS) Computation.

Implements the Coggan/Allen Training Stress Score formula and load
classification thresholds. TSS quantifies the physiological cost of a
workout based on its duration and intensity.

The canonical formula:
    TSS = (duration_seconds * IF^2) / 3600 * 100

Where IF (Intensity Factor) is the ratio of actual intensity to threshold
intensity. One hour at IF=1.0 yields exactly TSS=100 by definition.

TSS values can be used as the daily load input to the Banister
impulse-response model (CTL/ATL/TSB).

References:
    - Coggan & Allen: "Training and Racing with a Power Meter"
    - TrainingPeaks: "Normalized Power, Intensity Factor and TSS"
"""

import math
from typing import Literal

# TSS classification thresholds (TrainingPeaks standard)
_TSS_EASY_UPPER = 50.0
_TSS_MODERATE_UPPER = 100.0
_TSS_HARD_UPPER = 200.0

LoadClassification = Literal["easy", "moderate", "hard", "very_hard"]

# Default lactate threshold HR estimate for recreational/competitive runners.
# Used when deriving Intensity Factor from heart rate data in the absence of
# an athlete-specific lactate threshold HR test.
DEFAULT_THRESHOLD_HR: int = 175

# Canonical intensity factor defaults per workout type. These encode exercise
# science knowledge about typical effort levels for each workout category.
DEFAULT_WORKOUT_INTENSITY: dict[str, float] = {
    "easy": 0.60,
    "long_run": 0.65,
    "tempo": 0.80,
    "interval": 0.90,
    "repetition": 0.95,
    "recovery": 0.45,
    "marathon_pace": 0.75,
    "fartlek": 0.72,
    "hill": 0.82,
    "rest": 0.0,
    "cross_train": 0.55,
}


def compute_tss(duration_minutes: float, intensity_factor: float) -> float:
    """Compute Training Stress Score for a workout.

    Args:
        duration_minutes: Workout duration in minutes. Must be non-negative.
        intensity_factor: Intensity Factor in [0, 1]. Represents the fraction
            of threshold intensity sustained during the workout.

    Returns:
        TSS value. One hour at IF=1.0 yields exactly 100.

    Raises:
        ValueError: If duration_minutes is negative or intensity_factor
            is outside [0, 1].
    """
    if duration_minutes < 0:
        raise ValueError(f"duration_minutes must be non-negative, got {duration_minutes}")
    if not 0.0 <= intensity_factor <= 1.0:
        raise ValueError(f"intensity_factor must be in [0, 1], got {intensity_factor}")

    duration_seconds = duration_minutes * 60.0
    return (duration_seconds * intensity_factor ** 2) / 3600.0 * 100.0


def classify_load(tss: float) -> LoadClassification:
    """Classify a TSS value into a load category.

    Thresholds follow the TrainingPeaks standard:
        - easy:      TSS < 50
        - moderate:  50 <= TSS < 100
        - hard:      100 <= TSS < 200
        - very_hard: TSS >= 200

    Args:
        tss: Training Stress Score value.

    Returns:
        One of "easy", "moderate", "hard", or "very_hard".
    """
    if tss < _TSS_EASY_UPPER:
        return "easy"
    if tss < _TSS_MODERATE_UPPER:
        return "moderate"
    if tss < _TSS_HARD_UPPER:
        return "hard"
    return "very_hard"


def hr_to_intensity_factor(
    avg_heart_rate: int,
    threshold_hr: int = DEFAULT_THRESHOLD_HR,
) -> float:
    """Derive Intensity Factor from average heart rate.

    Estimates IF as the ratio of observed HR to lactate threshold HR,
    clamped to [0, 1]. This is the standard Coggan/Allen approach for
    HR-based training stress estimation.

    Args:
        avg_heart_rate: Average heart rate in bpm during the workout.
        threshold_hr: Lactate threshold heart rate in bpm. Defaults to
            DEFAULT_THRESHOLD_HR (175 bpm).

    Returns:
        Intensity factor in [0, 1].

    Raises:
        ValueError: If threshold_hr is not positive.
    """
    if threshold_hr <= 0:
        raise ValueError(f"threshold_hr must be positive, got {threshold_hr}")
    ratio = avg_heart_rate / threshold_hr
    return min(max(ratio, 0.0), 1.0)


def scale_intensity_for_target_tss(
    current_intensity: float,
    scale_factor: float,
) -> float:
    """Back-calculate a new intensity to scale TSS by a given factor.

    Since TSS is proportional to IF^2 (for constant duration), scaling TSS
    by factor k requires: IF_new = IF_old * sqrt(k). The result is clamped
    to [0, 1].

    This function co-locates the derived formula with the TSS computation
    it depends on, so changes to the TSS formula are reflected here.

    Args:
        current_intensity: Current intensity factor in [0, 1].
        scale_factor: Desired TSS multiplier. E.g., 2.0 to double TSS.
            Must be non-negative.

    Returns:
        New intensity factor in [0, 1].

    Raises:
        ValueError: If scale_factor is negative.
    """
    if scale_factor < 0:
        raise ValueError(f"scale_factor must be non-negative, got {scale_factor}")
    new_intensity = current_intensity * math.sqrt(scale_factor)
    return min(1.0, max(0.0, new_intensity))
