"""Unit tests for the project_taper tool wrapper.

Tests input validation, handler logic for both project and optimize modes,
and registration with the ToolRegistry.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.tools.project_taper import (
    ProjectTaperInput,
    project_taper_handler,
    register,
)
from src.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

# 42 days of training (enough for meaningful CTL)
SAMPLE_LOADS = [50.0] * 42


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestProjectTaperInput:
    """Test ProjectTaperInput Pydantic validation."""

    def test_valid_project_mode(self) -> None:
        inp = ProjectTaperInput(
            mode="project",
            daily_loads=SAMPLE_LOADS,
            taper_days=14,
        )
        assert inp.mode == "project"
        assert inp.taper_days == 14
        assert inp.taper_load_fraction == 0.0

    def test_valid_optimize_mode(self) -> None:
        inp = ProjectTaperInput(
            mode="optimize",
            daily_loads=SAMPLE_LOADS,
        )
        assert inp.mode == "optimize"
        assert inp.min_days == 7
        assert inp.max_days == 28

    def test_project_mode_requires_taper_days(self) -> None:
        with pytest.raises(ValidationError, match="taper_days"):
            ProjectTaperInput(mode="project", daily_loads=SAMPLE_LOADS)

    def test_optimize_mode_max_lt_min_rejected(self) -> None:
        with pytest.raises(ValidationError, match="max_days"):
            ProjectTaperInput(
                mode="optimize",
                daily_loads=SAMPLE_LOADS,
                min_days=20,
                max_days=10,
            )

    def test_empty_daily_loads_rejected(self) -> None:
        with pytest.raises(ValidationError, match="daily_loads"):
            ProjectTaperInput(mode="project", daily_loads=[], taper_days=7)

    def test_negative_taper_days_rejected(self) -> None:
        with pytest.raises(ValidationError, match="taper_days"):
            ProjectTaperInput(
                mode="project",
                daily_loads=SAMPLE_LOADS,
                taper_days=-1,
            )

    def test_taper_load_fraction_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            ProjectTaperInput(
                mode="project",
                daily_loads=SAMPLE_LOADS,
                taper_days=7,
                taper_load_fraction=1.5,
            )

    def test_invalid_mode_rejected(self) -> None:
        with pytest.raises(ValidationError, match="mode"):
            ProjectTaperInput(
                mode="invalid",
                daily_loads=SAMPLE_LOADS,
                taper_days=7,
            )

    def test_taper_days_zero_rejected(self) -> None:
        with pytest.raises(ValidationError, match="taper_days"):
            ProjectTaperInput(
                mode="project",
                daily_loads=SAMPLE_LOADS,
                taper_days=0,
            )

    def test_custom_load_fraction(self) -> None:
        inp = ProjectTaperInput(
            mode="project",
            daily_loads=SAMPLE_LOADS,
            taper_days=14,
            taper_load_fraction=0.3,
        )
        assert inp.taper_load_fraction == pytest.approx(0.3)

    def test_optimize_custom_range(self) -> None:
        inp = ProjectTaperInput(
            mode="optimize",
            daily_loads=SAMPLE_LOADS,
            min_days=10,
            max_days=21,
        )
        assert inp.min_days == 10
        assert inp.max_days == 21


# ---------------------------------------------------------------------------
# Handler: project mode
# ---------------------------------------------------------------------------


class TestProjectMode:
    """Test project_taper_handler in project mode."""

    def test_returns_ctl_atl_tsb_lists(self) -> None:
        result = project_taper_handler(
            ProjectTaperInput(
                mode="project",
                daily_loads=SAMPLE_LOADS,
                taper_days=14,
            ).model_dump()
        )
        assert result["mode"] == "project"
        assert len(result["ctl"]) == 14
        assert len(result["atl"]) == 14
        assert len(result["tsb"]) == 14

    def test_tsb_increases_during_taper(self) -> None:
        result = project_taper_handler(
            ProjectTaperInput(
                mode="project",
                daily_loads=SAMPLE_LOADS,
                taper_days=14,
            ).model_dump()
        )
        # TSB should generally increase as fatigue dissipates faster than fitness
        assert result["tsb"][-1] > result["tsb"][0]

    def test_fitness_retention_is_fraction(self) -> None:
        result = project_taper_handler(
            ProjectTaperInput(
                mode="project",
                daily_loads=SAMPLE_LOADS,
                taper_days=14,
            ).model_dump()
        )
        assert 0.0 < result["fitness_retention"] <= 1.0

    def test_short_taper_retains_more_fitness(self) -> None:
        short = project_taper_handler(
            ProjectTaperInput(
                mode="project",
                daily_loads=SAMPLE_LOADS,
                taper_days=7,
            ).model_dump()
        )
        long = project_taper_handler(
            ProjectTaperInput(
                mode="project",
                daily_loads=SAMPLE_LOADS,
                taper_days=21,
            ).model_dump()
        )
        assert short["fitness_retention"] > long["fitness_retention"]

    def test_partial_load_retains_more_fitness(self) -> None:
        rest = project_taper_handler(
            ProjectTaperInput(
                mode="project",
                daily_loads=SAMPLE_LOADS,
                taper_days=14,
                taper_load_fraction=0.0,
            ).model_dump()
        )
        partial = project_taper_handler(
            ProjectTaperInput(
                mode="project",
                daily_loads=SAMPLE_LOADS,
                taper_days=14,
                taper_load_fraction=0.3,
            ).model_dump()
        )
        # With partial training, CTL should be higher at end of taper
        assert partial["ctl"][-1] > rest["ctl"][-1]

    def test_retention_reflects_taper_load_fraction(self) -> None:
        """C1 regression: fitness_retention must account for taper_load_fraction."""
        rest = project_taper_handler(
            ProjectTaperInput(
                mode="project",
                daily_loads=SAMPLE_LOADS,
                taper_days=14,
                taper_load_fraction=0.0,
            ).model_dump()
        )
        partial = project_taper_handler(
            ProjectTaperInput(
                mode="project",
                daily_loads=SAMPLE_LOADS,
                taper_days=14,
                taper_load_fraction=0.5,
            ).model_dump()
        )
        # With 50% load maintained, retention must be higher than complete rest
        assert partial["fitness_retention"] > rest["fitness_retention"]


# ---------------------------------------------------------------------------
# Handler: optimize mode
# ---------------------------------------------------------------------------


class TestOptimizeMode:
    """Test project_taper_handler in optimize mode."""

    def test_returns_optimal_days(self) -> None:
        result = project_taper_handler(
            ProjectTaperInput(
                mode="optimize",
                daily_loads=SAMPLE_LOADS,
            ).model_dump()
        )
        assert result["mode"] == "optimize"
        assert isinstance(result["optimal_days"], int)
        assert 7 <= result["optimal_days"] <= 28

    def test_peak_tsb_is_positive(self) -> None:
        result = project_taper_handler(
            ProjectTaperInput(
                mode="optimize",
                daily_loads=SAMPLE_LOADS,
            ).model_dump()
        )
        assert result["peak_tsb"] > 0

    def test_ctl_and_atl_at_peak(self) -> None:
        result = project_taper_handler(
            ProjectTaperInput(
                mode="optimize",
                daily_loads=SAMPLE_LOADS,
            ).model_dump()
        )
        assert result["ctl_at_peak"] > 0
        assert result["atl_at_peak"] >= 0
        # TSB = CTL - ATL, so peak_tsb ~ ctl_at_peak - atl_at_peak
        assert result["peak_tsb"] == pytest.approx(
            result["ctl_at_peak"] - result["atl_at_peak"],
            abs=0.1,
        )

    def test_fitness_retention_included(self) -> None:
        result = project_taper_handler(
            ProjectTaperInput(
                mode="optimize",
                daily_loads=SAMPLE_LOADS,
            ).model_dump()
        )
        assert 0.0 < result["fitness_retention"] <= 1.0

    def test_custom_search_range(self) -> None:
        result = project_taper_handler(
            ProjectTaperInput(
                mode="optimize",
                daily_loads=SAMPLE_LOADS,
                min_days=10,
                max_days=14,
            ).model_dump()
        )
        assert 10 <= result["optimal_days"] <= 14


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Test tool registration with ToolRegistry."""

    def test_register_adds_tool(self) -> None:
        registry = ToolRegistry()
        register(registry)
        assert "project_taper" in registry.tool_names

    def test_anthropic_schema_generated(self) -> None:
        registry = ToolRegistry()
        register(registry)
        tools = registry.get_anthropic_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "project_taper"
        assert "input_schema" in tools[0]

    def test_execute_via_registry(self) -> None:
        registry = ToolRegistry()
        register(registry)
        result = registry.execute(
            "project_taper",
            {
                "mode": "project",
                "daily_loads": SAMPLE_LOADS,
                "taper_days": 7,
            },
        )
        assert result.success is True
        assert len(result.output["ctl"]) == 7

    def test_execute_invalid_input(self) -> None:
        registry = ToolRegistry()
        register(registry)
        result = registry.execute(
            "project_taper",
            {
                "mode": "project",
                "daily_loads": [],
            },
        )
        assert result.success is False
