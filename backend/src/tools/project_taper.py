"""Tool wrapper: project_taper.

Exposes the taper decay modeling engine as a Claude-callable tool.
The LLM provides training history and taper parameters; all physiological
math is performed by taper.py — the LLM never generates CTL/ATL/TSB
values itself.

Two modes:

1. **Project**: Given training history and taper duration, project
   CTL/ATL/TSB curves forward during the taper period.
2. **Optimize**: Search for the taper length (within a range) that
   maximizes TSB (peak freshness).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.deterministic import taper
from src.deterministic.banister import compute_ctl
from src.tools.registry import ToolDefinition, ToolRegistry


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------


class ProjectTaperInput(BaseModel):
    """Validated input for the project_taper tool.

    Attributes:
        mode: Operation mode — "project" for forward projection,
            "optimize" to find the best taper length.
        daily_loads: Training history as daily TSS values. Index 0 is
            oldest, index -1 is most recent. Must be non-empty.
        taper_days: Number of days to project forward. Required for
            "project" mode, ignored for "optimize" mode.
        taper_load_fraction: Fraction of recent average load maintained
            during the taper. 0.0 = complete rest, 0.3 = 30% of recent
            average. Must be in [0.0, 1.0]. Default 0.0.
        min_days: Minimum taper length to search. Only used in "optimize"
            mode. Default 7.
        max_days: Maximum taper length to search. Only used in "optimize"
            mode. Default 28.
    """

    mode: Literal["project", "optimize"] = Field(
        description=(
            'Operation mode: "project" to forward-project CTL/ATL/TSB '
            'curves, "optimize" to find the taper length that maximizes TSB.'
        ),
    )
    daily_loads: list[float] = Field(
        min_length=1,
        description=(
            "Training history as daily TSS values. Index 0 is oldest. "
            "Must contain at least one value."
        ),
    )
    taper_days: int | None = Field(
        default=None,
        gt=0,
        description=(
            'Number of taper days to project. Required for "project" mode, '
            'ignored for "optimize" mode.'
        ),
    )
    taper_load_fraction: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of recent average load maintained during taper. "
            "0.0 = complete rest, 1.0 = full training. Default 0.0."
        ),
    )
    min_days: int = Field(
        default=7,
        ge=1,
        description=(
            'Minimum taper length to search (only used in "optimize" mode). '
            "Default 7."
        ),
    )
    max_days: int = Field(
        default=28,
        ge=1,
        description=(
            'Maximum taper length to search (only used in "optimize" mode). '
            "Default 28."
        ),
    )

    @model_validator(mode="after")
    def _validate_mode_fields(self) -> "ProjectTaperInput":
        """Ensure required fields are present for the chosen mode.

        Raises:
            ValueError: If taper_days is missing in project mode,
                or max_days < min_days in optimize mode.
        """
        if self.mode == "project" and self.taper_days is None:
            raise ValueError(
                'taper_days is required when mode is "project".'
            )
        if self.mode == "optimize" and self.max_days < self.min_days:
            raise ValueError(
                f"max_days ({self.max_days}) must be >= min_days ({self.min_days})."
            )
        return self


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def project_taper_handler(input_data: dict[str, Any]) -> dict[str, Any]:
    """Execute taper projection or optimization.

    Routes to the appropriate deterministic function based on mode.

    Args:
        input_data: Validated input dict from ProjectTaperInput.model_dump().

    Returns:
        For "project" mode: dict with "ctl", "atl", "tsb" lists and
            "fitness_retention" float.
        For "optimize" mode: dict with "optimal_days", "peak_tsb",
            "ctl_at_peak", "atl_at_peak", and "fitness_retention".
    """
    mode = input_data["mode"]
    daily_loads = input_data["daily_loads"]
    taper_load_fraction = input_data["taper_load_fraction"]

    # Pre-taper CTL for retention calculation
    pre_taper_ctl = compute_ctl(daily_loads)

    if mode == "project":
        taper_days = input_data["taper_days"]

        projection = taper.project_taper(
            daily_loads=daily_loads,
            taper_days=taper_days,
            taper_load_fraction=taper_load_fraction,
        )

        # Compute retention from the projected CTL (which respects taper_load_fraction)
        post_taper_ctl = projection["ctl"][-1] if projection["ctl"] else 0.0
        retention = post_taper_ctl / pre_taper_ctl if pre_taper_ctl > 0 else 0.0

        return {
            "mode": "project",
            "taper_days": taper_days,
            "ctl": projection["ctl"],
            "atl": projection["atl"],
            "tsb": projection["tsb"],
            "fitness_retention": round(retention, 4),
        }

    else:  # optimize
        result = taper.find_optimal_taper_length(
            daily_loads=daily_loads,
            min_days=input_data["min_days"],
            max_days=input_data["max_days"],
            taper_load_fraction=taper_load_fraction,
        )

        # Compute retention from the CTL at optimal day (respects taper_load_fraction)
        post_taper_ctl = result["ctl_at_peak"]
        retention = post_taper_ctl / pre_taper_ctl if pre_taper_ctl > 0 else 0.0

        return {
            "mode": "optimize",
            "optimal_days": result["optimal_days"],
            "peak_tsb": round(result["peak_tsb"], 2),
            "ctl_at_peak": round(result["ctl_at_peak"], 2),
            "atl_at_peak": round(result["atl_at_peak"], 2),
            "fitness_retention": round(retention, 4),
        }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_DESCRIPTION = (
    "Project CTL/ATL/TSB curves during a pre-race taper, or find the optimal "
    "taper length that maximizes Training Stress Balance (freshness). Uses the "
    "Banister impulse-response model to simulate fitness retention vs. fatigue "
    "dissipation during reduced training load."
)


def register(registry: ToolRegistry) -> None:
    """Register the project_taper tool with the given ToolRegistry.

    Args:
        registry: The ToolRegistry instance to register into.
    """
    registry.register(
        ToolDefinition(
            name="project_taper",
            description=_DESCRIPTION,
            input_model=ProjectTaperInput,
            handler=project_taper_handler,
        )
    )
