"""Tests for the evaluate_fatigue_state tool wrapper.

Validates:
- Input schema compliance (Pydantic model)
- Output schema compliance (Pydantic model)
- Handler correctness against known banister values
- Recovery status classification thresholds
- Error paths: empty loads, negative loads, tau constraints
- ToolRegistry round-trip (schema generation + execute dispatch)
- Optional time-series output
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from src.deterministic.banister import classify_recovery_status as _classify_recovery_status
from src.deterministic.banister import (
    compute_atl,
    compute_ctl,
    compute_tsb,
    compute_tsb_series,
)
from src.tools.evaluate_fatigue_state import (
    EvaluateFatigueStateInput,
    EvaluateFatigueStateOutput,
    evaluate_fatigue_state_handler,
    register,
)
from src.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def steady_loads_30() -> list[float]:
    """30 days of 50 TSS/day — a well-known reference scenario."""
    return [50.0] * 30


@pytest.fixture()
def minimal_loads() -> list[float]:
    """Single-day load — smallest valid input."""
    return [80.0]


@pytest.fixture()
def mixed_loads() -> list[float]:
    """Two weeks of varied load including rest days."""
    return [60, 0, 70, 80, 0, 90, 50, 55, 0, 65, 75, 0, 85, 40]


@pytest.fixture()
def registry_with_tool() -> ToolRegistry:
    """ToolRegistry with evaluate_fatigue_state registered."""
    reg = ToolRegistry()
    register(reg)
    return reg


# ---------------------------------------------------------------------------
# Input model: valid inputs
# ---------------------------------------------------------------------------


class TestEvaluateFatigueStateInputValid:
    """EvaluateFatigueStateInput accepts well-formed data."""

    def test_defaults(self, steady_loads_30: list[float]) -> None:
        """Model fields take correct defaults."""
        m = EvaluateFatigueStateInput(daily_loads=steady_loads_30)
        assert m.fitness_tau == 42
        assert m.fatigue_tau == 7
        assert m.include_series is False

    def test_explicit_all_fields(self, mixed_loads: list[float]) -> None:
        """All fields can be supplied explicitly."""
        m = EvaluateFatigueStateInput(
            daily_loads=mixed_loads,
            fitness_tau=28,
            fatigue_tau=5,
            include_series=True,
        )
        assert m.fitness_tau == 28
        assert m.fatigue_tau == 5
        assert m.include_series is True

    def test_zero_loads_allowed(self) -> None:
        """A list of all-zero TSS values is valid (rest period)."""
        m = EvaluateFatigueStateInput(daily_loads=[0.0, 0.0, 0.0])
        assert m.daily_loads == [0.0, 0.0, 0.0]

    def test_single_day_load(self, minimal_loads: list[float]) -> None:
        """A single-element list is the minimum valid daily_loads."""
        m = EvaluateFatigueStateInput(daily_loads=minimal_loads)
        assert len(m.daily_loads) == 1

    def test_large_loads_accepted(self) -> None:
        """Very large TSS values (ultra events) are accepted."""
        m = EvaluateFatigueStateInput(daily_loads=[500.0, 400.0])
        assert m.daily_loads[0] == 500.0

    def test_float_and_int_loads_accepted(self) -> None:
        """Integer load values are coerced to float by Pydantic."""
        m = EvaluateFatigueStateInput(daily_loads=[50, 60, 70])  # type: ignore[list-item]
        assert all(isinstance(v, float) for v in m.daily_loads)

    def test_custom_tau_values(self, steady_loads_30: list[float]) -> None:
        """Non-default tau values are stored as-is."""
        m = EvaluateFatigueStateInput(daily_loads=steady_loads_30, fitness_tau=56, fatigue_tau=10)
        assert m.fitness_tau == 56
        assert m.fatigue_tau == 10


# ---------------------------------------------------------------------------
# Input model: invalid inputs
# ---------------------------------------------------------------------------


class TestEvaluateFatigueStateInputInvalid:
    """EvaluateFatigueStateInput raises ValidationError on bad data."""

    def test_empty_daily_loads_rejected(self) -> None:
        """Empty daily_loads violates min_length=1."""
        with pytest.raises(ValidationError) as exc_info:
            EvaluateFatigueStateInput(daily_loads=[])
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("daily_loads",) for e in errors)

    def test_negative_load_rejected(self) -> None:
        """Any negative TSS value must be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EvaluateFatigueStateInput(daily_loads=[50.0, -1.0, 60.0])
        errors = exc_info.value.errors()
        assert any("daily_loads" in str(e["loc"]) for e in errors)

    def test_negative_load_at_index_zero(self) -> None:
        """Negative value at index 0 is caught."""
        with pytest.raises(ValidationError):
            EvaluateFatigueStateInput(daily_loads=[-0.1])

    def test_zero_fitness_tau_rejected(self, minimal_loads: list[float]) -> None:
        """fitness_tau=0 violates gt=0."""
        with pytest.raises(ValidationError):
            EvaluateFatigueStateInput(daily_loads=minimal_loads, fitness_tau=0)

    def test_negative_fitness_tau_rejected(self, minimal_loads: list[float]) -> None:
        """Negative fitness_tau is rejected."""
        with pytest.raises(ValidationError):
            EvaluateFatigueStateInput(daily_loads=minimal_loads, fitness_tau=-5)

    def test_zero_fatigue_tau_rejected(self, minimal_loads: list[float]) -> None:
        """fatigue_tau=0 violates gt=0."""
        with pytest.raises(ValidationError):
            EvaluateFatigueStateInput(daily_loads=minimal_loads, fatigue_tau=0)

    def test_negative_fatigue_tau_rejected(self, minimal_loads: list[float]) -> None:
        """Negative fatigue_tau is rejected."""
        with pytest.raises(ValidationError):
            EvaluateFatigueStateInput(daily_loads=minimal_loads, fatigue_tau=-3)

    def test_missing_daily_loads_rejected(self) -> None:
        """Omitting daily_loads is a required-field error."""
        with pytest.raises(ValidationError):
            EvaluateFatigueStateInput()  # type: ignore[call-arg]

    def test_non_list_daily_loads_rejected(self) -> None:
        """A scalar instead of a list is rejected."""
        with pytest.raises((ValidationError, TypeError)):
            EvaluateFatigueStateInput(daily_loads=50.0)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class TestEvaluateFatigueStateOutput:
    """EvaluateFatigueStateOutput stores values correctly."""

    def test_without_series(self) -> None:
        """Series fields default to None."""
        out = EvaluateFatigueStateOutput(ctl=30.0, atl=45.0, tsb=-15.0, recovery_status="fatigued")
        assert out.ctl_series is None
        assert out.atl_series is None
        assert out.tsb_series is None

    def test_with_series(self) -> None:
        """Series fields are stored when provided."""
        out = EvaluateFatigueStateOutput(
            ctl=30.0,
            atl=45.0,
            tsb=-15.0,
            recovery_status="fatigued",
            ctl_series=[10.0, 20.0, 30.0],
            atl_series=[20.0, 35.0, 45.0],
            tsb_series=[-10.0, -15.0, -15.0],
        )
        assert len(out.ctl_series) == 3  # type: ignore[arg-type]
        assert len(out.tsb_series) == 3  # type: ignore[arg-type]

    def test_model_dump_keys(self) -> None:
        """model_dump() contains all expected keys."""
        out = EvaluateFatigueStateOutput(ctl=1.0, atl=2.0, tsb=-1.0, recovery_status="neutral")
        d = out.model_dump()
        assert set(d.keys()) == {
            "ctl",
            "atl",
            "tsb",
            "recovery_status",
            "ctl_series",
            "atl_series",
            "tsb_series",
        }


# ---------------------------------------------------------------------------
# Recovery status classifier
# ---------------------------------------------------------------------------


class TestClassifyRecoveryStatus:
    """_classify_recovery_status covers all four bands."""

    @pytest.mark.parametrize(
        "tsb,expected",
        [
            (11.0, "fresh"),
            (10.1, "fresh"),
            (100.0, "fresh"),
        ],
    )
    def test_fresh(self, tsb: float, expected: str) -> None:
        """TSB > 10 is classified as fresh."""
        assert _classify_recovery_status(tsb) == expected

    @pytest.mark.parametrize(
        "tsb,expected",
        [
            (10.0, "neutral"),
            (0.0, "neutral"),
            (-10.0, "neutral"),
            (5.5, "neutral"),
        ],
    )
    def test_neutral(self, tsb: float, expected: str) -> None:
        """TSB in [-10, 10] is classified as neutral."""
        assert _classify_recovery_status(tsb) == expected

    @pytest.mark.parametrize(
        "tsb,expected",
        [
            (-10.1, "fatigued"),
            (-15.0, "fatigued"),
            (-20.0, "fatigued"),
        ],
    )
    def test_fatigued(self, tsb: float, expected: str) -> None:
        """TSB in [-20, -10) is classified as fatigued."""
        assert _classify_recovery_status(tsb) == expected

    @pytest.mark.parametrize(
        "tsb,expected",
        [
            (-20.1, "very_fatigued"),
            (-50.0, "very_fatigued"),
            (-100.0, "very_fatigued"),
        ],
    )
    def test_very_fatigued(self, tsb: float, expected: str) -> None:
        """TSB < -20 is classified as very_fatigued."""
        assert _classify_recovery_status(tsb) == expected

    def test_boundary_tsb_10(self) -> None:
        """Exact boundary TSB=10 falls in neutral, not fresh."""
        assert _classify_recovery_status(10.0) == "neutral"

    def test_boundary_tsb_minus10(self) -> None:
        """Exact boundary TSB=-10 falls in neutral, not fatigued."""
        assert _classify_recovery_status(-10.0) == "neutral"

    def test_boundary_tsb_minus20(self) -> None:
        """Exact boundary TSB=-20 falls in fatigued, not very_fatigued."""
        assert _classify_recovery_status(-20.0) == "fatigued"


# ---------------------------------------------------------------------------
# Handler: correctness
# ---------------------------------------------------------------------------


class TestEvaluateFatigueStateHandlerCorrectness:
    """Handler produces values that match direct banister calls."""

    def test_ctl_matches_banister(self, steady_loads_30: list[float]) -> None:
        """Returned CTL equals direct banister.compute_ctl() call."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": steady_loads_30,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": False,
            }
        )
        expected = compute_ctl(steady_loads_30, tau=42)
        assert result["ctl"] == pytest.approx(expected, rel=1e-12)

    def test_atl_matches_banister(self, steady_loads_30: list[float]) -> None:
        """Returned ATL equals direct banister.compute_atl() call."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": steady_loads_30,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": False,
            }
        )
        expected = compute_atl(steady_loads_30, tau=7)
        assert result["atl"] == pytest.approx(expected, rel=1e-12)

    def test_tsb_equals_ctl_minus_atl(self, steady_loads_30: list[float]) -> None:
        """TSB is always exactly CTL - ATL."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": steady_loads_30,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": False,
            }
        )
        assert result["tsb"] == pytest.approx(result["ctl"] - result["atl"], rel=1e-12)

    def test_tsb_matches_banister(self, steady_loads_30: list[float]) -> None:
        """Returned TSB equals direct banister.compute_tsb() call."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": steady_loads_30,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": False,
            }
        )
        expected = compute_tsb(steady_loads_30, fitness_tau=42, fatigue_tau=7)
        assert result["tsb"] == pytest.approx(expected, rel=1e-12)

    def test_known_ctl_reference(self, steady_loads_30: list[float]) -> None:
        """CTL after 30 days at 50 TSS/day (τ=42) ≈ 25.6 per literature."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": steady_loads_30,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": False,
            }
        )
        assert result["ctl"] == pytest.approx(25.6, abs=0.5)

    def test_known_atl_reference(self, steady_loads_30: list[float]) -> None:
        """ATL after 30 days at 50 TSS/day (τ=7) ≈ 49.2 per literature."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": steady_loads_30,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": False,
            }
        )
        assert result["atl"] == pytest.approx(49.2, abs=0.5)

    def test_mathematically_exact_ctl(self, steady_loads_30: list[float]) -> None:
        """CTL matches closed-form: L*(1 - exp(-n/τ)) for constant load L."""
        tau = 42
        expected_ctl = 50.0 * (1 - math.exp(-30 / tau))
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": steady_loads_30,
                "fitness_tau": tau,
                "fatigue_tau": 7,
                "include_series": False,
            }
        )
        assert result["ctl"] == pytest.approx(expected_ctl, rel=1e-10)

    def test_custom_tau_values(self, steady_loads_30: list[float]) -> None:
        """Non-default tau values are passed through to banister correctly."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": steady_loads_30,
                "fitness_tau": 28,
                "fatigue_tau": 5,
                "include_series": False,
            }
        )
        expected_ctl = compute_ctl(steady_loads_30, tau=28)
        expected_atl = compute_atl(steady_loads_30, tau=5)
        assert result["ctl"] == pytest.approx(expected_ctl, rel=1e-12)
        assert result["atl"] == pytest.approx(expected_atl, rel=1e-12)

    def test_recovery_status_present(self, steady_loads_30: list[float]) -> None:
        """Result always contains recovery_status key."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": steady_loads_30,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": False,
            }
        )
        assert "recovery_status" in result
        assert result["recovery_status"] in ("fresh", "neutral", "fatigued", "very_fatigued")

    def test_steady_state_is_very_fatigued(self, steady_loads_30: list[float]) -> None:
        """30 days of hard training → very negative TSB → very_fatigued."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": steady_loads_30,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": False,
            }
        )
        # ATL ≈ 49.2 >> CTL ≈ 25.6, so TSB ≈ -23.6 → very_fatigued
        assert result["recovery_status"] == "very_fatigued"


# ---------------------------------------------------------------------------
# Handler: include_series
# ---------------------------------------------------------------------------


class TestEvaluateFatigueStateHandlerSeries:
    """Handler correctly handles include_series flag."""

    def test_series_absent_by_default(self, steady_loads_30: list[float]) -> None:
        """When include_series=False, series fields are None."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": steady_loads_30,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": False,
            }
        )
        assert result["ctl_series"] is None
        assert result["atl_series"] is None
        assert result["tsb_series"] is None

    def test_series_present_when_requested(self, steady_loads_30: list[float]) -> None:
        """When include_series=True, all three series are returned."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": steady_loads_30,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": True,
            }
        )
        assert result["ctl_series"] is not None
        assert result["atl_series"] is not None
        assert result["tsb_series"] is not None

    def test_series_length_matches_input(self, steady_loads_30: list[float]) -> None:
        """Each series has the same length as daily_loads."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": steady_loads_30,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": True,
            }
        )
        n = len(steady_loads_30)
        assert len(result["ctl_series"]) == n
        assert len(result["atl_series"]) == n
        assert len(result["tsb_series"]) == n

    def test_series_last_value_matches_scalar(self, mixed_loads: list[float]) -> None:
        """The final element of each series equals the scalar CTL/ATL/TSB."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": mixed_loads,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": True,
            }
        )
        assert result["ctl_series"][-1] == pytest.approx(result["ctl"], rel=1e-12)
        assert result["atl_series"][-1] == pytest.approx(result["atl"], rel=1e-12)
        assert result["tsb_series"][-1] == pytest.approx(result["tsb"], rel=1e-12)

    def test_series_matches_banister_compute_tsb_series(self, mixed_loads: list[float]) -> None:
        """Series values match direct banister.compute_tsb_series() output."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": mixed_loads,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": True,
            }
        )
        expected = compute_tsb_series(mixed_loads, fitness_tau=42, fatigue_tau=7)
        assert result["ctl_series"] == pytest.approx(expected["ctl"], rel=1e-12)
        assert result["atl_series"] == pytest.approx(expected["atl"], rel=1e-12)
        assert result["tsb_series"] == pytest.approx(expected["tsb"], rel=1e-12)

    def test_tsb_series_equals_ctl_minus_atl_series(self, mixed_loads: list[float]) -> None:
        """Each element of tsb_series equals ctl_series[i] - atl_series[i]."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": mixed_loads,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": True,
            }
        )
        for i, (c, a, t) in enumerate(
            zip(result["ctl_series"], result["atl_series"], result["tsb_series"])
        ):
            assert t == pytest.approx(c - a, rel=1e-12), f"Mismatch at index {i}"

    def test_single_day_with_series(self, minimal_loads: list[float]) -> None:
        """Single-day input returns single-element series."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": minimal_loads,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": True,
            }
        )
        assert len(result["ctl_series"]) == 1
        assert len(result["atl_series"]) == 1
        assert len(result["tsb_series"]) == 1


# ---------------------------------------------------------------------------
# Handler: error paths
# ---------------------------------------------------------------------------


class TestEvaluateFatigueStateHandlerErrors:
    """Handler raises ValueError for invalid cross-field combinations."""

    def test_fatigue_tau_equal_to_fitness_tau_raises(self, minimal_loads: list[float]) -> None:
        """fatigue_tau == fitness_tau must raise ValueError."""
        with pytest.raises(ValueError, match="fatigue_tau"):
            evaluate_fatigue_state_handler(
                {
                    "daily_loads": minimal_loads,
                    "fitness_tau": 10,
                    "fatigue_tau": 10,
                    "include_series": False,
                }
            )

    def test_fatigue_tau_greater_than_fitness_tau_raises(self, minimal_loads: list[float]) -> None:
        """fatigue_tau > fitness_tau must raise ValueError."""
        with pytest.raises(ValueError, match="fatigue_tau"):
            evaluate_fatigue_state_handler(
                {
                    "daily_loads": minimal_loads,
                    "fitness_tau": 7,
                    "fatigue_tau": 42,
                    "include_series": False,
                }
            )

    def test_error_message_mentions_both_tau_values(self, minimal_loads: list[float]) -> None:
        """Error message must mention both tau values for debuggability."""
        with pytest.raises(ValueError) as exc_info:
            evaluate_fatigue_state_handler(
                {
                    "daily_loads": minimal_loads,
                    "fitness_tau": 14,
                    "fatigue_tau": 20,
                    "include_series": False,
                }
            )
        msg = str(exc_info.value)
        assert "20" in msg  # fatigue_tau
        assert "14" in msg  # fitness_tau


# ---------------------------------------------------------------------------
# Handler: output dict schema
# ---------------------------------------------------------------------------


class TestEvaluateFatigueStateHandlerOutputSchema:
    """Handler output always contains exactly the expected keys."""

    def test_output_keys_without_series(self, steady_loads_30: list[float]) -> None:
        """Output has seven keys; series fields are None."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": steady_loads_30,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": False,
            }
        )
        expected_keys = {
            "ctl",
            "atl",
            "tsb",
            "recovery_status",
            "ctl_series",
            "atl_series",
            "tsb_series",
        }
        assert set(result.keys()) == expected_keys

    def test_output_keys_with_series(self, steady_loads_30: list[float]) -> None:
        """Output has seven keys; series fields are populated lists."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": steady_loads_30,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": True,
            }
        )
        expected_keys = {
            "ctl",
            "atl",
            "tsb",
            "recovery_status",
            "ctl_series",
            "atl_series",
            "tsb_series",
        }
        assert set(result.keys()) == expected_keys

    def test_ctl_is_float(self, minimal_loads: list[float]) -> None:
        """ctl output is a float."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": minimal_loads,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": False,
            }
        )
        assert isinstance(result["ctl"], float)

    def test_atl_is_float(self, minimal_loads: list[float]) -> None:
        """atl output is a float."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": minimal_loads,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": False,
            }
        )
        assert isinstance(result["atl"], float)

    def test_tsb_is_float(self, minimal_loads: list[float]) -> None:
        """tsb output is a float."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": minimal_loads,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": False,
            }
        )
        assert isinstance(result["tsb"], float)

    def test_recovery_status_is_string(self, minimal_loads: list[float]) -> None:
        """recovery_status output is a string."""
        result = evaluate_fatigue_state_handler(
            {
                "daily_loads": minimal_loads,
                "fitness_tau": 42,
                "fatigue_tau": 7,
                "include_series": False,
            }
        )
        assert isinstance(result["recovery_status"], str)


# ---------------------------------------------------------------------------
# ToolRegistry integration
# ---------------------------------------------------------------------------


class TestRegistration:
    """register() integrates correctly with ToolRegistry."""

    def test_tool_registered(self, registry_with_tool: ToolRegistry) -> None:
        """After register(), the tool name appears in the registry."""
        assert "evaluate_fatigue_state" in registry_with_tool.tool_names

    def test_double_registration_raises(self) -> None:
        """Registering the same tool twice raises ValueError."""
        reg = ToolRegistry()
        register(reg)
        with pytest.raises(ValueError, match="already registered"):
            register(reg)

    def test_get_anthropic_tools_returns_list(self, registry_with_tool: ToolRegistry) -> None:
        """get_anthropic_tools() returns a non-empty list."""
        tools = registry_with_tool.get_anthropic_tools()
        assert isinstance(tools, list)
        assert len(tools) == 1

    def test_anthropic_tool_has_required_keys(self, registry_with_tool: ToolRegistry) -> None:
        """Each tool definition has name, description, and input_schema."""
        tool_def = registry_with_tool.get_anthropic_tools()[0]
        assert "name" in tool_def
        assert "description" in tool_def
        assert "input_schema" in tool_def

    def test_anthropic_tool_name(self, registry_with_tool: ToolRegistry) -> None:
        """Tool name in the Anthropic schema is correct."""
        tool_def = registry_with_tool.get_anthropic_tools()[0]
        assert tool_def["name"] == "evaluate_fatigue_state"

    def test_anthropic_tool_description_mentions_ctl(
        self, registry_with_tool: ToolRegistry
    ) -> None:
        """Description mentions CTL so the LLM knows what this tool does."""
        tool_def = registry_with_tool.get_anthropic_tools()[0]
        assert "CTL" in tool_def["description"]

    def test_anthropic_tool_description_mentions_atl(
        self, registry_with_tool: ToolRegistry
    ) -> None:
        """Description mentions ATL so the LLM knows what this tool does."""
        tool_def = registry_with_tool.get_anthropic_tools()[0]
        assert "ATL" in tool_def["description"]

    def test_anthropic_tool_description_mentions_tsb(
        self, registry_with_tool: ToolRegistry
    ) -> None:
        """Description mentions TSB so the LLM knows what this tool does."""
        tool_def = registry_with_tool.get_anthropic_tools()[0]
        assert "TSB" in tool_def["description"]

    def test_input_schema_type_object(self, registry_with_tool: ToolRegistry) -> None:
        """The input_schema root type is 'object'."""
        schema = registry_with_tool.get_anthropic_tools()[0]["input_schema"]
        assert schema["type"] == "object"

    def test_input_schema_has_daily_loads_property(self, registry_with_tool: ToolRegistry) -> None:
        """The input_schema exposes daily_loads as a property."""
        schema = registry_with_tool.get_anthropic_tools()[0]["input_schema"]
        assert "daily_loads" in schema["properties"]

    def test_input_schema_has_fitness_tau_property(self, registry_with_tool: ToolRegistry) -> None:
        """The input_schema exposes fitness_tau as a property."""
        schema = registry_with_tool.get_anthropic_tools()[0]["input_schema"]
        assert "fitness_tau" in schema["properties"]

    def test_input_schema_has_fatigue_tau_property(self, registry_with_tool: ToolRegistry) -> None:
        """The input_schema exposes fatigue_tau as a property."""
        schema = registry_with_tool.get_anthropic_tools()[0]["input_schema"]
        assert "fatigue_tau" in schema["properties"]

    def test_input_schema_has_include_series_property(
        self, registry_with_tool: ToolRegistry
    ) -> None:
        """The input_schema exposes include_series as a property."""
        schema = registry_with_tool.get_anthropic_tools()[0]["input_schema"]
        assert "include_series" in schema["properties"]


# ---------------------------------------------------------------------------
# ToolRegistry execute round-trip
# ---------------------------------------------------------------------------


class TestRegistryExecuteRoundTrip:
    """registry.execute() dispatches correctly and returns ToolResult."""

    def test_execute_success(
        self, registry_with_tool: ToolRegistry, steady_loads_30: list[float]
    ) -> None:
        """execute() returns a successful ToolResult for valid input."""
        result = registry_with_tool.execute(
            "evaluate_fatigue_state",
            {"daily_loads": steady_loads_30},
        )
        assert result.success is True
        assert result.tool_name == "evaluate_fatigue_state"

    def test_execute_output_contains_ctl(
        self, registry_with_tool: ToolRegistry, steady_loads_30: list[float]
    ) -> None:
        """Successful execute() output has a 'ctl' key."""
        result = registry_with_tool.execute(
            "evaluate_fatigue_state",
            {"daily_loads": steady_loads_30},
        )
        assert "ctl" in result.output

    def test_execute_output_contains_recovery_status(
        self, registry_with_tool: ToolRegistry, minimal_loads: list[float]
    ) -> None:
        """Successful execute() output has a 'recovery_status' key."""
        result = registry_with_tool.execute(
            "evaluate_fatigue_state",
            {"daily_loads": minimal_loads},
        )
        assert "recovery_status" in result.output

    def test_execute_with_include_series(
        self, registry_with_tool: ToolRegistry, mixed_loads: list[float]
    ) -> None:
        """execute() with include_series=True populates series in output."""
        result = registry_with_tool.execute(
            "evaluate_fatigue_state",
            {"daily_loads": mixed_loads, "include_series": True},
        )
        assert result.success is True
        assert result.output["ctl_series"] is not None

    def test_execute_invalid_empty_loads(self, registry_with_tool: ToolRegistry) -> None:
        """execute() returns failure for empty daily_loads."""
        result = registry_with_tool.execute(
            "evaluate_fatigue_state",
            {"daily_loads": []},
        )
        assert result.success is False
        assert "error" in result.output

    def test_execute_invalid_negative_load(self, registry_with_tool: ToolRegistry) -> None:
        """execute() returns failure for negative TSS value."""
        result = registry_with_tool.execute(
            "evaluate_fatigue_state",
            {"daily_loads": [50.0, -5.0, 60.0]},
        )
        assert result.success is False

    def test_execute_fatigue_tau_exceeds_fitness_tau(
        self, registry_with_tool: ToolRegistry, minimal_loads: list[float]
    ) -> None:
        """execute() returns failure when fatigue_tau >= fitness_tau."""
        result = registry_with_tool.execute(
            "evaluate_fatigue_state",
            {"daily_loads": minimal_loads, "fitness_tau": 7, "fatigue_tau": 42},
        )
        assert result.success is False
        assert "error" in result.output

    def test_execute_unknown_tool_returns_failure(self, registry_with_tool: ToolRegistry) -> None:
        """execute() with an unknown tool name returns a failure ToolResult."""
        result = registry_with_tool.execute("nonexistent_tool", {})
        assert result.success is False
        assert "Unknown tool" in result.output.get("error", "")

    def test_execute_to_content_block_is_json_string(
        self, registry_with_tool: ToolRegistry, minimal_loads: list[float]
    ) -> None:
        """to_content_block() produces a valid JSON string."""
        import json

        result = registry_with_tool.execute(
            "evaluate_fatigue_state",
            {"daily_loads": minimal_loads},
        )
        block = result.to_content_block()
        parsed = json.loads(block)
        assert isinstance(parsed, dict)
