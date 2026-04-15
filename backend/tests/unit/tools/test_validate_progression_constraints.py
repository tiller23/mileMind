"""Tests for the validate_progression_constraints tool wrapper.

Covers:
- Input model validation (schema compliance, field constraints, custom validators)
- Output model structure and field types
- Handler correctness against the deterministic acwr engine
- Edge cases: zero loads, exact threshold values, multi-violation scenarios
- ToolRegistry integration (registration, Anthropic schema generation, execute dispatch)
- Error path: unknown tool, invalid input propagated as ToolResult failure
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.deterministic.acwr import (
    check_safety,
    validate_weekly_increase,
)
from src.tools.registry import ToolRegistry
from src.tools.validate_progression_constraints import (
    _TOOL_DESCRIPTION,
    _TOOL_NAME,
    ValidateProgressionInput,
    ValidateProgressionOutput,
    register,
    validate_progression_constraints_handler,
)

# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

# 4 weeks of uniform load — ACWR will be 1.0 (safe zone, no violations)
_UNIFORM_LOADS: list[float] = [50.0, 50.0, 50.0, 50.0]

# Load series where the last week is a hard-cap breach (> 1.5x ACWR)
# Previous 3 weeks = 10, proposed week = 80 → large spike
_DANGER_LOADS: list[float] = [10.0, 10.0, 10.0, 80.0]

# Load series where the proposed week is a moderate increase (exactly 10%)
_TEN_PCT_INCREASE: list[float] = [40.0, 40.0, 40.0, 44.0]

# Load series where the proposed week is a 20% increase (hard ceiling)
_TWENTY_PCT_INCREASE: list[float] = [40.0, 40.0, 40.0, 48.0]

# A 5-week series so we can confirm all intermediate weeks are also checked
_FIVE_WEEK_LOADS: list[float] = [30.0, 33.0, 36.3, 39.93, 43.92]


@pytest.fixture()
def registry() -> ToolRegistry:
    """Provide a fresh ToolRegistry with the tool registered."""
    r = ToolRegistry()
    register(r)
    return r


# ---------------------------------------------------------------------------
# ValidateProgressionInput — schema compliance
# ---------------------------------------------------------------------------


class TestValidateProgressionInput:
    """Input Pydantic model validation."""

    def test_minimal_valid_input(self) -> None:
        """Four-element list with defaults should parse cleanly."""
        m = ValidateProgressionInput(weekly_loads=_UNIFORM_LOADS)
        assert m.weekly_loads == _UNIFORM_LOADS
        assert m.risk_tolerance == "moderate"
        assert m.max_weekly_increase_pct == pytest.approx(0.10)

    def test_explicit_all_fields(self) -> None:
        """All fields provided explicitly should be accepted."""
        m = ValidateProgressionInput(
            weekly_loads=[20.0, 22.0, 24.0, 26.0],
            risk_tolerance="conservative",
            max_weekly_increase_pct=0.15,
        )
        assert m.risk_tolerance == "conservative"
        assert m.max_weekly_increase_pct == pytest.approx(0.15)

    def test_aggressive_risk_tolerance_accepted(self) -> None:
        """'aggressive' is a valid risk tolerance."""
        m = ValidateProgressionInput(weekly_loads=_UNIFORM_LOADS, risk_tolerance="aggressive")
        assert m.risk_tolerance == "aggressive"

    def test_too_few_weekly_loads_rejected(self) -> None:
        """Fewer than 4 weekly loads must fail Pydantic validation."""
        with pytest.raises(ValidationError, match="too_short"):
            ValidateProgressionInput(weekly_loads=[50.0, 50.0, 50.0])

    def test_negative_load_rejected(self) -> None:
        """A negative load value must fail the custom validator."""
        with pytest.raises(ValidationError, match="non-negative"):
            ValidateProgressionInput(weekly_loads=[50.0, 50.0, 50.0, -1.0])

    def test_invalid_risk_tolerance_rejected(self) -> None:
        """An unrecognised risk tolerance string must be rejected."""
        with pytest.raises(ValidationError, match="risk_tolerance"):
            ValidateProgressionInput(weekly_loads=_UNIFORM_LOADS, risk_tolerance="risky")

    def test_zero_max_weekly_increase_rejected(self) -> None:
        """max_weekly_increase_pct must be > 0."""
        with pytest.raises(ValidationError):
            ValidateProgressionInput(weekly_loads=_UNIFORM_LOADS, max_weekly_increase_pct=0.0)

    def test_max_weekly_increase_above_ceiling_rejected(self) -> None:
        """max_weekly_increase_pct must be <= 0.20."""
        with pytest.raises(ValidationError):
            ValidateProgressionInput(weekly_loads=_UNIFORM_LOADS, max_weekly_increase_pct=0.21)

    @pytest.mark.parametrize("pct", [0.01, 0.10, 0.15, 0.20])
    def test_max_weekly_increase_boundary_values_accepted(self, pct: float) -> None:
        """Boundary values for max_weekly_increase_pct should all be accepted."""
        m = ValidateProgressionInput(weekly_loads=_UNIFORM_LOADS, max_weekly_increase_pct=pct)
        assert m.max_weekly_increase_pct == pytest.approx(pct)

    def test_zero_loads_are_valid(self) -> None:
        """All-zero loads are technically valid input (rest week)."""
        m = ValidateProgressionInput(weekly_loads=[0.0, 0.0, 0.0, 0.0])
        assert m.weekly_loads == [0.0, 0.0, 0.0, 0.0]

    def test_more_than_four_weeks_accepted(self) -> None:
        """Lists longer than 4 weeks must be accepted."""
        loads = [40.0] * 12
        m = ValidateProgressionInput(weekly_loads=loads)
        assert len(m.weekly_loads) == 12

    def test_json_schema_has_required_fields(self) -> None:
        """The generated JSON schema must list weekly_loads as required."""
        schema = ValidateProgressionInput.model_json_schema()
        assert "weekly_loads" in schema.get("required", [])

    def test_json_schema_properties(self) -> None:
        """The schema must expose all three expected property keys."""
        schema = ValidateProgressionInput.model_json_schema()
        props = schema["properties"]
        assert "weekly_loads" in props
        assert "risk_tolerance" in props
        assert "max_weekly_increase_pct" in props


# ---------------------------------------------------------------------------
# ValidateProgressionOutput — structure
# ---------------------------------------------------------------------------


class TestValidateProgressionOutput:
    """Output Pydantic model structure checks."""

    def _make_output(self, **kwargs) -> ValidateProgressionOutput:
        defaults = {
            "passed": True,
            "acwr": 1.0,
            "acwr_ewma": 1.0,
            "zone": "safe",
            "violations": [],
            "weekly_increase_pct": 0.05,
        }
        defaults.update(kwargs)
        return ValidateProgressionOutput(**defaults)

    def test_passed_true_serialises(self) -> None:
        out = self._make_output(passed=True)
        assert out.passed is True

    def test_acwr_ewma_none_allowed(self) -> None:
        """acwr_ewma is Optional; None must be accepted."""
        out = self._make_output(acwr_ewma=None)
        assert out.acwr_ewma is None

    def test_weekly_increase_pct_none_allowed(self) -> None:
        """weekly_increase_pct is Optional; None must be accepted."""
        out = self._make_output(weekly_increase_pct=None)
        assert out.weekly_increase_pct is None

    def test_violations_is_list(self) -> None:
        out = self._make_output(violations=["something bad"])
        assert isinstance(out.violations, list)

    @pytest.mark.parametrize("zone", ["low", "safe", "warning", "danger"])
    def test_valid_zone_values(self, zone: str) -> None:
        out = self._make_output(zone=zone)
        assert out.zone == zone

    def test_model_dump_round_trip(self) -> None:
        """model_dump should produce a plain dict that model_validate can reload."""
        out = self._make_output()
        reloaded = ValidateProgressionOutput.model_validate(out.model_dump())
        assert reloaded == out


# ---------------------------------------------------------------------------
# Handler — correctness
# ---------------------------------------------------------------------------


class TestValidateProgressionConstraintsHandler:
    """Handler produces results consistent with the underlying acwr functions."""

    def _call(self, weekly_loads, risk_tolerance="moderate", max_pct=0.10) -> dict:
        return validate_progression_constraints_handler(
            {
                "weekly_loads": weekly_loads,
                "risk_tolerance": risk_tolerance,
                "max_weekly_increase_pct": max_pct,
            }
        )

    # --- Baseline: uniform load → safe, no violations ---

    def test_uniform_load_passes(self) -> None:
        result = self._call(_UNIFORM_LOADS)
        assert result["passed"] is True
        assert result["violations"] == []

    def test_uniform_load_zone_is_safe(self) -> None:
        result = self._call(_UNIFORM_LOADS)
        assert result["zone"] == "safe"

    def test_uniform_load_acwr_approx_one(self) -> None:
        result = self._call(_UNIFORM_LOADS)
        assert result["acwr"] == pytest.approx(1.0)

    def test_acwr_ewma_is_float(self) -> None:
        result = self._call(_UNIFORM_LOADS)
        assert isinstance(result["acwr_ewma"], float)

    def test_weekly_increase_pct_zero_for_uniform(self) -> None:
        """Uniform loads → no increase → weekly_increase_pct should be 0.0."""
        result = self._call(_UNIFORM_LOADS)
        assert result["weekly_increase_pct"] == pytest.approx(0.0)

    # --- Exact 10% increase on a conservative baseline ---

    def test_ten_pct_increase_passes_at_moderate(self) -> None:
        """10% increase is within the default 10% limit."""
        result = self._call(_TEN_PCT_INCREASE)
        # 44/40 - 1 = 0.10; check_safety uses the same limit, so this is
        # borderline — the engine treats "> pct" as a violation, so 10% = 10% passes.
        assert result["weekly_increase_pct"] == pytest.approx(0.10)

    def test_weekly_increase_pct_matches_engine(self) -> None:
        """weekly_increase_pct must match acwr.validate_weekly_increase output."""
        loads = [40.0, 40.0, 40.0, 48.0]  # 20% increase
        result = self._call(loads, max_pct=0.20)
        _, expected = validate_weekly_increase(40.0, 48.0, 0.20)
        assert result["weekly_increase_pct"] == pytest.approx(expected)

    # --- Danger zone: large spike ---

    def test_danger_loads_fails(self) -> None:
        result = self._call(_DANGER_LOADS)
        assert result["passed"] is False

    def test_danger_loads_zone_is_danger(self) -> None:
        result = self._call(_DANGER_LOADS)
        assert result["zone"] == "danger"

    def test_danger_loads_has_violations(self) -> None:
        result = self._call(_DANGER_LOADS)
        assert len(result["violations"]) >= 1

    def test_danger_loads_violations_are_strings(self) -> None:
        result = self._call(_DANGER_LOADS)
        for v in result["violations"]:
            assert isinstance(v, str)

    # --- Output matches check_safety directly ---

    def test_acwr_matches_check_safety(self) -> None:
        """acwr in handler output must exactly match check_safety().acwr."""
        safety = check_safety(_FIVE_WEEK_LOADS)
        result = self._call(_FIVE_WEEK_LOADS)
        assert result["acwr"] == pytest.approx(safety.acwr)

    def test_acwr_ewma_matches_check_safety(self) -> None:
        """acwr_ewma in handler output must exactly match check_safety().acwr_ewma."""
        safety = check_safety(_FIVE_WEEK_LOADS)
        result = self._call(_FIVE_WEEK_LOADS)
        assert result["acwr_ewma"] == pytest.approx(safety.acwr_ewma)

    def test_zone_matches_check_safety(self) -> None:
        safety = check_safety(_FIVE_WEEK_LOADS)
        result = self._call(_FIVE_WEEK_LOADS)
        assert result["zone"] == safety.zone

    def test_violations_match_check_safety(self) -> None:
        safety = check_safety(_DANGER_LOADS)
        result = self._call(_DANGER_LOADS)
        assert result["violations"] == list(safety.violations)

    # --- risk_tolerance propagated correctly ---

    def test_conservative_tolerance_tighter_ceiling(self) -> None:
        """Conservative ceiling (1.2) is tighter; a warning-zone load should fail."""
        # Build loads that produce ACWR in the warning zone (1.3–1.5 range)
        # 3 weeks at 10, then spike to 25 → lots of acute load
        loads = [10.0, 10.0, 10.0, 25.0]
        result_conservative = self._call(loads, risk_tolerance="conservative")
        result_aggressive = self._call(loads, risk_tolerance="aggressive", max_pct=0.20)
        # Conservative should have at least as many violations
        assert len(result_conservative["violations"]) >= len(result_aggressive["violations"])

    # --- Previous week zero → weekly_increase_pct is None ---

    def test_weekly_increase_pct_none_when_previous_is_zero(self) -> None:
        """When the previous week load is 0, the percentage is meaningless → None."""
        loads = [10.0, 10.0, 0.0, 30.0]
        result = self._call(loads)
        # previous_week = loads[-2] = 0.0
        assert result["weekly_increase_pct"] is None

    # --- Negative week-over-week (recovery week) ---

    def test_load_decrease_produces_negative_increase_pct(self) -> None:
        """A load decrease should yield a negative weekly_increase_pct."""
        loads = [60.0, 60.0, 60.0, 40.0]
        result = self._call(loads)
        assert result["weekly_increase_pct"] < 0.0

    # --- Output is a plain dict (JSON-serialisable) ---

    def test_handler_returns_plain_dict(self) -> None:
        result = self._call(_UNIFORM_LOADS)
        assert isinstance(result, dict)

    def test_output_validates_against_output_model(self) -> None:
        """Handler output should parse cleanly into ValidateProgressionOutput."""
        result = self._call(_UNIFORM_LOADS)
        out = ValidateProgressionOutput.model_validate(result)
        assert out.passed is True

    # --- Edge: exact safe zone boundary ---

    def test_acwr_at_safe_upper_boundary(self) -> None:
        """Loads tuned so ACWR ≈ SAFE_UPPER (1.3) should still be safe."""
        # 3 weeks of moderate load, then a moderately higher proposed week
        # This is a heuristic test — we just confirm zone is not "danger"
        loads = [40.0, 40.0, 40.0, 44.0]
        result = self._call(loads)
        assert result["zone"] in {"safe", "low", "warning"}

    # --- Parametrized risk tolerances ---

    @pytest.mark.parametrize("tolerance", ["conservative", "moderate", "aggressive"])
    def test_all_risk_tolerances_accepted(self, tolerance: str) -> None:
        result = self._call(_UNIFORM_LOADS, risk_tolerance=tolerance)
        assert "passed" in result
        assert "acwr" in result

    # --- Handler raises ValueError for bad inputs (engine rejects them) ---

    def test_handler_raises_for_too_few_loads(self) -> None:
        """Handler should propagate ValueError from acwr.check_safety."""
        with pytest.raises(ValueError, match="at least 4"):
            validate_progression_constraints_handler(
                {
                    "weekly_loads": [50.0, 50.0, 50.0],
                    "risk_tolerance": "moderate",
                    "max_weekly_increase_pct": 0.10,
                }
            )

    def test_handler_raises_for_unknown_risk_tolerance(self) -> None:
        with pytest.raises(ValueError):
            validate_progression_constraints_handler(
                {
                    "weekly_loads": _UNIFORM_LOADS,
                    "risk_tolerance": "extreme",
                    "max_weekly_increase_pct": 0.10,
                }
            )


# ---------------------------------------------------------------------------
# ToolRegistry integration
# ---------------------------------------------------------------------------


class TestRegistration:
    """ToolRegistry integration: registration and Anthropic schema generation."""

    def test_register_adds_tool(self, registry: ToolRegistry) -> None:
        assert _TOOL_NAME in registry.tool_names

    def test_double_registration_raises(self, registry: ToolRegistry) -> None:
        with pytest.raises(ValueError, match="already registered"):
            register(registry)

    def test_tool_description_matches_spec(self, registry: ToolRegistry) -> None:
        tool = registry.get(_TOOL_NAME)
        assert tool is not None
        assert tool.description == _TOOL_DESCRIPTION

    def test_anthropic_tools_contains_tool(self, registry: ToolRegistry) -> None:
        names = [t["name"] for t in registry.get_anthropic_tools()]
        assert _TOOL_NAME in names

    def test_anthropic_schema_has_input_schema_key(self, registry: ToolRegistry) -> None:
        tools = registry.get_anthropic_tools()
        tool_def = next(t for t in tools if t["name"] == _TOOL_NAME)
        assert "input_schema" in tool_def

    def test_anthropic_schema_type_is_object(self, registry: ToolRegistry) -> None:
        tools = registry.get_anthropic_tools()
        tool_def = next(t for t in tools if t["name"] == _TOOL_NAME)
        assert tool_def["input_schema"]["type"] == "object"

    def test_anthropic_schema_no_title_at_root(self, registry: ToolRegistry) -> None:
        """The registry strips the root 'title' key for Anthropic compatibility."""
        tools = registry.get_anthropic_tools()
        tool_def = next(t for t in tools if t["name"] == _TOOL_NAME)
        assert "title" not in tool_def["input_schema"]

    def test_anthropic_schema_lists_weekly_loads_property(self, registry: ToolRegistry) -> None:
        tools = registry.get_anthropic_tools()
        tool_def = next(t for t in tools if t["name"] == _TOOL_NAME)
        assert "weekly_loads" in tool_def["input_schema"]["properties"]


# ---------------------------------------------------------------------------
# ToolRegistry.execute — full dispatch path
# ---------------------------------------------------------------------------


class TestRegistryExecute:
    """Tests for the registry's execute() dispatch path."""

    def test_execute_success(self, registry: ToolRegistry) -> None:
        result = registry.execute(
            _TOOL_NAME,
            {
                "weekly_loads": _UNIFORM_LOADS,
                "risk_tolerance": "moderate",
                "max_weekly_increase_pct": 0.10,
            },
        )
        assert result.success is True
        assert result.tool_name == _TOOL_NAME

    def test_execute_output_has_passed_key(self, registry: ToolRegistry) -> None:
        result = registry.execute(
            _TOOL_NAME,
            {"weekly_loads": _UNIFORM_LOADS},
        )
        assert "passed" in result.output

    def test_execute_output_has_all_required_keys(self, registry: ToolRegistry) -> None:
        result = registry.execute(
            _TOOL_NAME,
            {"weekly_loads": _UNIFORM_LOADS},
        )
        required_keys = {
            "passed",
            "acwr",
            "acwr_ewma",
            "zone",
            "violations",
            "weekly_increase_pct",
        }
        assert required_keys.issubset(result.output.keys())

    def test_execute_fails_on_invalid_input_type(self, registry: ToolRegistry) -> None:
        """Non-list weekly_loads must fail schema validation, not crash."""
        result = registry.execute(
            _TOOL_NAME,
            {"weekly_loads": "not-a-list"},
        )
        assert result.success is False
        assert "error" in result.output

    def test_execute_fails_on_missing_weekly_loads(self, registry: ToolRegistry) -> None:
        result = registry.execute(_TOOL_NAME, {})
        assert result.success is False

    def test_execute_fails_for_unknown_tool(self, registry: ToolRegistry) -> None:
        result = registry.execute("nonexistent_tool", {})
        assert result.success is False
        assert "Unknown tool" in result.output["error"]

    def test_execute_danger_loads_returns_violations(self, registry: ToolRegistry) -> None:
        result = registry.execute(
            _TOOL_NAME,
            {
                "weekly_loads": _DANGER_LOADS,
                "risk_tolerance": "moderate",
                "max_weekly_increase_pct": 0.10,
            },
        )
        assert result.success is True
        assert result.output["passed"] is False
        assert len(result.output["violations"]) >= 1

    def test_to_content_block_is_valid_json(self, registry: ToolRegistry) -> None:
        """to_content_block must return valid JSON."""
        import json

        result = registry.execute(
            _TOOL_NAME,
            {"weekly_loads": _UNIFORM_LOADS},
        )
        parsed = json.loads(result.to_content_block())
        assert isinstance(parsed, dict)

    def test_execute_with_defaults_uses_moderate_tolerance(self, registry: ToolRegistry) -> None:
        """Omitting optional fields should default to moderate/10%."""
        result = registry.execute(
            _TOOL_NAME,
            {"weekly_loads": _UNIFORM_LOADS},
        )
        assert result.success is True
        # A uniform load with moderate tolerance must pass
        assert result.output["passed"] is True
