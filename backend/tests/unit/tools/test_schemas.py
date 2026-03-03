"""Schema validation tests for all 5 tool wrappers.

Verifies that every tool registered in the ToolRegistry produces a valid
Anthropic API tool definition:

- JSON schema structure (type, properties, required)
- No Pydantic "title" key at the root level (Anthropic rejects it)
- All 5 tools can coexist in the same registry without naming conflicts
- get_anthropic_tools() returns exactly 5 entries
- Each entry has the required keys: name, description, input_schema
- Tool names match the expected snake_case identifiers
- Descriptions are non-empty strings
- No duplicate tool names across the full registry

These tests are intentionally schema-level only and do NOT call handlers.
Per-tool input/output validation and handler correctness live in the
individual test_*.py files for each tool.
"""

from __future__ import annotations

import pytest

from src.tools.compute_training_stress import register as register_compute_training_stress
from src.tools.evaluate_fatigue_state import register as register_evaluate_fatigue_state
from src.tools.reallocate_week_load import register as register_reallocate_week_load
from src.tools.registry import ToolRegistry
from src.tools.simulate_race_outcomes import register as register_simulate_race_outcomes
from src.tools.validate_progression_constraints import (
    register as register_validate_progression_constraints,
)

# ---------------------------------------------------------------------------
# Expected constants — single source of truth for this test module
# ---------------------------------------------------------------------------

EXPECTED_TOOL_NAMES = [
    "compute_training_stress",
    "evaluate_fatigue_state",
    "validate_progression_constraints",
    "simulate_race_outcomes",
    "reallocate_week_load",
]

_REGISTER_FUNCS = [
    register_compute_training_stress,
    register_evaluate_fatigue_state,
    register_validate_progression_constraints,
    register_simulate_race_outcomes,
    register_reallocate_week_load,
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def full_registry() -> ToolRegistry:
    """A ToolRegistry with all 5 tools registered.

    Module-scoped because registration is side-effect-free and building it
    once is cheaper than repeating it per test.
    """
    registry = ToolRegistry()
    for register_fn in _REGISTER_FUNCS:
        register_fn(registry)
    return registry


@pytest.fixture(scope="module")
def anthropic_tools(full_registry: ToolRegistry) -> list[dict]:
    """The list returned by get_anthropic_tools() for the full registry."""
    return full_registry.get_anthropic_tools()


# ---------------------------------------------------------------------------
# Registration — all 5 tools coexist without conflicts
# ---------------------------------------------------------------------------


class TestRegistrationNoConflicts:
    """All 5 tools can be registered together without raising ValueError."""

    def test_all_five_register_without_error(self) -> None:
        """Creating a fresh registry and registering all 5 tools must succeed."""
        registry = ToolRegistry()
        for register_fn in _REGISTER_FUNCS:
            register_fn(registry)  # must not raise
        assert len(registry.tool_names) == 5

    def test_tool_names_list_length(self, full_registry: ToolRegistry) -> None:
        """tool_names property reports exactly 5 registered tools."""
        assert len(full_registry.tool_names) == 5

    @pytest.mark.parametrize("name", EXPECTED_TOOL_NAMES)
    def test_each_expected_name_is_registered(
        self, full_registry: ToolRegistry, name: str
    ) -> None:
        """Every expected tool name must appear in the registry."""
        assert name in full_registry.tool_names

    def test_no_extra_names_registered(self, full_registry: ToolRegistry) -> None:
        """The registry must contain exactly the 5 expected names and no others."""
        assert sorted(full_registry.tool_names) == sorted(EXPECTED_TOOL_NAMES)

    @pytest.mark.parametrize("register_fn", _REGISTER_FUNCS, ids=EXPECTED_TOOL_NAMES)
    def test_duplicate_registration_raises_value_error(self, register_fn) -> None:
        """Registering any tool a second time must raise ValueError."""
        registry = ToolRegistry()
        register_fn(registry)
        with pytest.raises(ValueError, match="already registered"):
            register_fn(registry)


# ---------------------------------------------------------------------------
# get_anthropic_tools() — top-level list shape
# ---------------------------------------------------------------------------


class TestGetAnthropicToolsList:
    """get_anthropic_tools() returns a properly-shaped list."""

    def test_returns_list(self, anthropic_tools: list[dict]) -> None:
        """Return type must be a list."""
        assert isinstance(anthropic_tools, list)

    def test_returns_exactly_five_tools(self, anthropic_tools: list[dict]) -> None:
        """The list must contain exactly 5 tool definitions."""
        assert len(anthropic_tools) == 5

    def test_no_duplicate_tool_names(self, anthropic_tools: list[dict]) -> None:
        """All tool names in the returned list must be unique."""
        names = [t["name"] for t in anthropic_tools]
        assert len(names) == len(set(names)), f"Duplicate tool names found: {names}"

    def test_all_expected_names_present(self, anthropic_tools: list[dict]) -> None:
        """Every expected tool name must appear in the returned definitions."""
        returned_names = {t["name"] for t in anthropic_tools}
        for name in EXPECTED_TOOL_NAMES:
            assert name in returned_names, f"'{name}' missing from get_anthropic_tools()"


# ---------------------------------------------------------------------------
# Per-tool definition shape — parametrized over all 5 tools
# ---------------------------------------------------------------------------


class TestEachToolDefinitionShape:
    """Each of the 5 tool definitions has the required Anthropic API keys."""

    @pytest.fixture(params=EXPECTED_TOOL_NAMES)
    def tool_def(self, request: pytest.FixtureRequest, anthropic_tools: list[dict]) -> dict:
        """Parametrized fixture returning the definition for each expected tool."""
        name = request.param
        matches = [t for t in anthropic_tools if t["name"] == name]
        assert len(matches) == 1, f"Expected exactly 1 tool named '{name}', found {len(matches)}"
        return matches[0]

    def test_has_name_key(self, tool_def: dict) -> None:
        """Tool definition must have a 'name' key."""
        assert "name" in tool_def

    def test_has_description_key(self, tool_def: dict) -> None:
        """Tool definition must have a 'description' key."""
        assert "description" in tool_def

    def test_has_input_schema_key(self, tool_def: dict) -> None:
        """Tool definition must have an 'input_schema' key."""
        assert "input_schema" in tool_def

    def test_name_is_non_empty_string(self, tool_def: dict) -> None:
        """Tool name must be a non-empty string."""
        assert isinstance(tool_def["name"], str)
        assert len(tool_def["name"]) > 0

    def test_description_is_non_empty_string(self, tool_def: dict) -> None:
        """Tool description must be a non-empty string (the LLM reads it)."""
        desc = tool_def["description"]
        assert isinstance(desc, str), f"description is {type(desc).__name__}, expected str"
        assert len(desc.strip()) > 0, "description must not be blank"

    def test_no_title_at_root_of_input_schema(self, tool_def: dict) -> None:
        """input_schema must NOT have a 'title' key at the root level.

        Pydantic generates a 'title' by default; the registry strips it.
        Anthropic's tool-use API rejects definitions that include 'title' at
        the schema root.
        """
        schema = tool_def["input_schema"]
        assert "title" not in schema, (
            f"Tool '{tool_def['name']}' schema has a root 'title' key — "
            "the registry must strip it via schema.pop('title', None)"
        )

    def test_input_schema_type_is_object(self, tool_def: dict) -> None:
        """input_schema root must have \"type\": \"object\"."""
        schema = tool_def["input_schema"]
        assert "type" in schema, f"Schema for '{tool_def['name']}' has no 'type' key"
        assert schema["type"] == "object", (
            f"Schema for '{tool_def['name']}' has type '{schema['type']}', expected 'object'"
        )

    def test_input_schema_has_properties(self, tool_def: dict) -> None:
        """input_schema must have a 'properties' key (LLM uses it to fill inputs)."""
        schema = tool_def["input_schema"]
        assert "properties" in schema, (
            f"Schema for '{tool_def['name']}' is missing 'properties'"
        )
        assert isinstance(schema["properties"], dict)
        assert len(schema["properties"]) > 0, (
            f"Schema for '{tool_def['name']}' has an empty 'properties' dict"
        )

    def test_input_schema_has_required(self, tool_def: dict) -> None:
        """input_schema must have a 'required' key listing mandatory fields."""
        schema = tool_def["input_schema"]
        assert "required" in schema, (
            f"Schema for '{tool_def['name']}' is missing 'required'"
        )
        assert isinstance(schema["required"], list)

    def test_required_fields_are_in_properties(self, tool_def: dict) -> None:
        """Every field listed in 'required' must also appear in 'properties'."""
        schema = tool_def["input_schema"]
        properties = schema.get("properties", {})
        for field in schema.get("required", []):
            assert field in properties, (
                f"Tool '{tool_def['name']}': required field '{field}' "
                "not found in schema properties"
            )


# ---------------------------------------------------------------------------
# Per-tool name correctness — sanity checks by name
# ---------------------------------------------------------------------------


class TestToolNames:
    """Tool names match the expected snake_case identifiers precisely."""

    @pytest.mark.parametrize("expected_name", EXPECTED_TOOL_NAMES)
    def test_name_matches_expected(
        self, full_registry: ToolRegistry, expected_name: str
    ) -> None:
        """get() must return a definition for each exact expected name."""
        tool_def = full_registry.get(expected_name)
        assert tool_def is not None, f"Tool '{expected_name}' not found in registry"
        assert tool_def.name == expected_name


# ---------------------------------------------------------------------------
# Individual tool schema spot-checks — required fields by tool
# ---------------------------------------------------------------------------


class TestComputeTrainingStressSchema:
    """Schema spot-checks for compute_training_stress."""

    @pytest.fixture
    def schema(self, anthropic_tools: list[dict]) -> dict:
        """input_schema for compute_training_stress."""
        return next(t for t in anthropic_tools if t["name"] == "compute_training_stress")[
            "input_schema"
        ]

    def test_workout_type_in_required(self, schema: dict) -> None:
        """workout_type is a required input field."""
        assert "workout_type" in schema["required"]

    def test_duration_minutes_in_required(self, schema: dict) -> None:
        """duration_minutes is a required input field."""
        assert "duration_minutes" in schema["required"]

    def test_intensity_in_required(self, schema: dict) -> None:
        """intensity is a required input field."""
        assert "intensity" in schema["required"]

    def test_optional_fields_in_properties(self, schema: dict) -> None:
        """Optional fields distance_km and avg_heart_rate appear in properties."""
        assert "distance_km" in schema["properties"]
        assert "avg_heart_rate" in schema["properties"]


class TestEvaluateFatigueStateSchema:
    """Schema spot-checks for evaluate_fatigue_state."""

    @pytest.fixture
    def schema(self, anthropic_tools: list[dict]) -> dict:
        """input_schema for evaluate_fatigue_state."""
        return next(t for t in anthropic_tools if t["name"] == "evaluate_fatigue_state")[
            "input_schema"
        ]

    def test_daily_loads_in_required(self, schema: dict) -> None:
        """daily_loads is a required input field."""
        assert "daily_loads" in schema["required"]

    def test_optional_tau_fields_in_properties(self, schema: dict) -> None:
        """fitness_tau and fatigue_tau are exposed as schema properties."""
        assert "fitness_tau" in schema["properties"]
        assert "fatigue_tau" in schema["properties"]

    def test_include_series_in_properties(self, schema: dict) -> None:
        """include_series is exposed as a schema property."""
        assert "include_series" in schema["properties"]


class TestValidateProgressionConstraintsSchema:
    """Schema spot-checks for validate_progression_constraints."""

    @pytest.fixture
    def schema(self, anthropic_tools: list[dict]) -> dict:
        """input_schema for validate_progression_constraints."""
        return next(
            t for t in anthropic_tools
            if t["name"] == "validate_progression_constraints"
        )["input_schema"]

    def test_weekly_loads_in_required(self, schema: dict) -> None:
        """weekly_loads is a required input field."""
        assert "weekly_loads" in schema["required"]

    def test_risk_tolerance_in_properties(self, schema: dict) -> None:
        """risk_tolerance is exposed as a schema property."""
        assert "risk_tolerance" in schema["properties"]

    def test_max_weekly_increase_pct_in_properties(self, schema: dict) -> None:
        """max_weekly_increase_pct is exposed as a schema property."""
        assert "max_weekly_increase_pct" in schema["properties"]


class TestSimulateRaceOutcomesSchema:
    """Schema spot-checks for simulate_race_outcomes."""

    @pytest.fixture
    def schema(self, anthropic_tools: list[dict]) -> dict:
        """input_schema for simulate_race_outcomes."""
        return next(t for t in anthropic_tools if t["name"] == "simulate_race_outcomes")[
            "input_schema"
        ]

    def test_target_distance_in_required(self, schema: dict) -> None:
        """target_distance is a required input field."""
        assert "target_distance" in schema["required"]

    def test_optional_fitness_fields_in_properties(self, schema: dict) -> None:
        """vdot and recent_race_distance are exposed as schema properties."""
        assert "vdot" in schema["properties"]
        assert "recent_race_distance" in schema["properties"]

    def test_environment_fields_in_properties(self, schema: dict) -> None:
        """temperature_c, elevation_gain_m, and headwind_ms are in properties."""
        assert "temperature_c" in schema["properties"]
        assert "elevation_gain_m" in schema["properties"]
        assert "headwind_ms" in schema["properties"]


class TestReallocateWeekLoadSchema:
    """Schema spot-checks for reallocate_week_load."""

    @pytest.fixture
    def schema(self, anthropic_tools: list[dict]) -> dict:
        """input_schema for reallocate_week_load."""
        return next(t for t in anthropic_tools if t["name"] == "reallocate_week_load")[
            "input_schema"
        ]

    def test_workouts_in_required(self, schema: dict) -> None:
        """workouts is a required input field."""
        assert "workouts" in schema["required"]

    def test_swap_day_in_required(self, schema: dict) -> None:
        """swap_day is a required input field."""
        assert "swap_day" in schema["required"]

    def test_new_workout_type_in_required(self, schema: dict) -> None:
        """new_workout_type is a required input field."""
        assert "new_workout_type" in schema["required"]

    def test_optional_fields_in_properties(self, schema: dict) -> None:
        """Optional fields target_weekly_load and previous_week_load are in properties."""
        assert "target_weekly_load" in schema["properties"]
        assert "previous_week_load" in schema["properties"]
