"""Unit tests for the simulate_race_outcomes tool wrapper.

Coverage areas:
- SimulateRaceInput validation (happy paths, every error branch)
- SimulateRaceOutput schema completeness
- simulate_race_outcomes_handler — VDOT path
- simulate_race_outcomes_handler — recent-race path
- Environmental condition pass-through (heat, elevation, wind)
- TSB / fitness-factor pass-through
- Seed reproducibility
- Registration via register()
- Anthropic schema generation round-trip
- Registry.execute() integration (valid + invalid inputs)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.deterministic.daniels import RACE_DISTANCES
from src.tools.registry import ToolRegistry
from src.tools.simulate_race_outcomes import (
    _DESCRIPTION,
    SimulateRaceInput,
    SimulateRaceOutput,
    register,
    simulate_race_outcomes_handler,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry() -> ToolRegistry:
    """Fresh ToolRegistry with simulate_race_outcomes registered."""
    r = ToolRegistry()
    register(r)
    return r


@pytest.fixture()
def vdot_input_dict() -> dict:
    """Minimal valid input dict using the VDOT path."""
    return {
        "vdot": 50.0,
        "target_distance": "marathon",
        "num_simulations": 500,
        "seed": 42,
    }


@pytest.fixture()
def recent_race_input_dict() -> dict:
    """Minimal valid input dict using the recent-race path."""
    return {
        "recent_race_distance": "5K",
        "recent_race_time_minutes": 20.0,
        "target_distance": "10K",
        "num_simulations": 500,
        "seed": 42,
    }


# ---------------------------------------------------------------------------
# SimulateRaceInput — valid configurations
# ---------------------------------------------------------------------------


class TestSimulateRaceInputValidPaths:
    def test_vdot_path_minimal(self):
        """Accepts vdot with only target_distance."""
        m = SimulateRaceInput(vdot=45.0, target_distance="5K")
        assert m.vdot == 45.0
        assert m.recent_race_distance is None
        assert m.recent_race_time_minutes is None

    def test_recent_race_path_minimal(self):
        """Accepts recent-race pair with only target_distance."""
        m = SimulateRaceInput(
            recent_race_distance="5K",
            recent_race_time_minutes=20.0,
            target_distance="10K",
        )
        assert m.vdot is None
        assert m.recent_race_distance == "5K"
        assert m.recent_race_time_minutes == 20.0

    def test_defaults_applied(self):
        """Default fields are set correctly."""
        m = SimulateRaceInput(vdot=50.0, target_distance="5K")
        assert m.tsb == 0.0
        assert m.temperature_c == 18.0
        assert m.elevation_gain_m == 0.0
        assert m.headwind_ms == 0.0
        assert m.num_simulations == 10_000
        assert m.seed is None

    def test_all_optional_fields_accepted(self):
        """All optional environment/simulation fields round-trip."""
        m = SimulateRaceInput(
            vdot=55.0,
            target_distance="half_marathon",
            tsb=-10.5,
            temperature_c=28.0,
            elevation_gain_m=400.0,
            headwind_ms=3.0,
            num_simulations=200,
            seed=99,
        )
        assert m.tsb == -10.5
        assert m.temperature_c == 28.0
        assert m.elevation_gain_m == 400.0
        assert m.headwind_ms == 3.0
        assert m.num_simulations == 200
        assert m.seed == 99

    @pytest.mark.parametrize("distance_key", list(RACE_DISTANCES.keys()))
    def test_all_target_distances_accepted(self, distance_key: str):
        """All canonical distance keys are accepted as target_distance."""
        m = SimulateRaceInput(vdot=50.0, target_distance=distance_key)
        assert m.target_distance == distance_key

    @pytest.mark.parametrize("distance_key", list(RACE_DISTANCES.keys()))
    def test_all_recent_race_distances_accepted(self, distance_key: str):
        """All canonical distance keys are accepted as recent_race_distance."""
        m = SimulateRaceInput(
            recent_race_distance=distance_key,
            recent_race_time_minutes=30.0,
            target_distance="marathon",
        )
        assert m.recent_race_distance == distance_key

    def test_negative_tsb_accepted(self):
        """Negative TSB (fatigue) is valid."""
        m = SimulateRaceInput(vdot=50.0, target_distance="5K", tsb=-25.0)
        assert m.tsb == -25.0

    def test_tailwind_negative_headwind_accepted(self):
        """Negative headwind (= tailwind) is valid."""
        m = SimulateRaceInput(vdot=50.0, target_distance="5K", headwind_ms=-2.0)
        assert m.headwind_ms == -2.0

    def test_zero_elevation_accepted(self):
        """Zero elevation gain is valid."""
        m = SimulateRaceInput(vdot=50.0, target_distance="5K", elevation_gain_m=0.0)
        assert m.elevation_gain_m == 0.0


# ---------------------------------------------------------------------------
# SimulateRaceInput — validation errors
# ---------------------------------------------------------------------------


class TestSimulateRaceInputErrors:
    def test_neither_vdot_nor_recent_race_raises(self):
        """Missing both fitness paths raises ValidationError."""
        with pytest.raises(ValidationError, match="Must provide either"):
            SimulateRaceInput(target_distance="5K")

    def test_both_vdot_and_recent_race_raises(self):
        """Supplying both fitness paths raises ValidationError."""
        with pytest.raises(ValidationError, match="not both"):
            SimulateRaceInput(
                vdot=50.0,
                recent_race_distance="5K",
                recent_race_time_minutes=20.0,
                target_distance="10K",
            )

    def test_partial_recent_race_only_distance_raises(self):
        """Providing only recent_race_distance without time raises."""
        with pytest.raises(ValidationError, match="both be provided together"):
            SimulateRaceInput(
                recent_race_distance="5K",
                target_distance="10K",
            )

    def test_partial_recent_race_only_time_raises(self):
        """Providing only recent_race_time_minutes without distance raises."""
        with pytest.raises(ValidationError, match="both be provided together"):
            SimulateRaceInput(
                recent_race_time_minutes=20.0,
                target_distance="10K",
            )

    def test_invalid_target_distance_raises(self):
        """Unknown target_distance key raises ValidationError."""
        with pytest.raises(ValidationError, match="not a recognised distance key"):
            SimulateRaceInput(vdot=50.0, target_distance="ultramarathon")

    def test_invalid_recent_race_distance_raises(self):
        """Unknown recent_race_distance key raises ValidationError."""
        with pytest.raises(ValidationError, match="not a recognised distance key"):
            SimulateRaceInput(
                recent_race_distance="100m",
                recent_race_time_minutes=10.0,
                target_distance="5K",
            )

    def test_vdot_zero_raises(self):
        """VDOT of zero raises ValidationError (must be > 0)."""
        with pytest.raises(ValidationError):
            SimulateRaceInput(vdot=0.0, target_distance="5K")

    def test_vdot_negative_raises(self):
        """Negative VDOT raises ValidationError."""
        with pytest.raises(ValidationError):
            SimulateRaceInput(vdot=-5.0, target_distance="5K")

    def test_recent_race_time_zero_raises(self):
        """Reference race time of zero raises ValidationError."""
        with pytest.raises(ValidationError):
            SimulateRaceInput(
                recent_race_distance="5K",
                recent_race_time_minutes=0.0,
                target_distance="10K",
            )

    def test_recent_race_time_negative_raises(self):
        """Negative reference race time raises ValidationError."""
        with pytest.raises(ValidationError):
            SimulateRaceInput(
                recent_race_distance="5K",
                recent_race_time_minutes=-5.0,
                target_distance="10K",
            )

    def test_num_simulations_zero_raises(self):
        """num_simulations of zero raises ValidationError."""
        with pytest.raises(ValidationError):
            SimulateRaceInput(vdot=50.0, target_distance="5K", num_simulations=0)

    def test_num_simulations_negative_raises(self):
        """Negative num_simulations raises ValidationError."""
        with pytest.raises(ValidationError):
            SimulateRaceInput(vdot=50.0, target_distance="5K", num_simulations=-100)

    def test_elevation_gain_negative_raises(self):
        """Negative elevation gain raises ValidationError."""
        with pytest.raises(ValidationError):
            SimulateRaceInput(vdot=50.0, target_distance="5K", elevation_gain_m=-10.0)


# ---------------------------------------------------------------------------
# SimulateRaceOutput — schema completeness
# ---------------------------------------------------------------------------


class TestSimulateRaceOutputSchema:
    _EXPECTED_FIELDS = {
        "median_time_minutes",
        "mean_time_minutes",
        "std_time_minutes",
        "p5_time_minutes",
        "p25_time_minutes",
        "p75_time_minutes",
        "p95_time_minutes",
        "fastest_time_minutes",
        "slowest_time_minutes",
        "baseline_time_minutes",
        "num_simulations",
        "environment_factor",
        "fitness_factor",
    }

    def test_all_expected_fields_present(self):
        """SimulateRaceOutput has exactly the required fields."""
        model_fields = set(SimulateRaceOutput.model_fields.keys())
        assert model_fields == self._EXPECTED_FIELDS

    def test_output_serialises_to_dict(self):
        """SimulateRaceOutput.model_dump() produces a plain dict."""
        out = SimulateRaceOutput(
            median_time_minutes=240.0,
            mean_time_minutes=241.0,
            std_time_minutes=3.0,
            p5_time_minutes=235.0,
            p25_time_minutes=238.0,
            p75_time_minutes=244.0,
            p95_time_minutes=248.0,
            fastest_time_minutes=230.0,
            slowest_time_minutes=260.0,
            baseline_time_minutes=239.0,
            num_simulations=10_000,
            environment_factor=1.0,
            fitness_factor=1.0,
        )
        d = out.model_dump()
        assert isinstance(d, dict)
        assert d["num_simulations"] == 10_000
        assert d["environment_factor"] == 1.0


# ---------------------------------------------------------------------------
# Handler — VDOT path
# ---------------------------------------------------------------------------


class TestHandlerVdotPath:
    def test_returns_dict_with_all_output_fields(self, vdot_input_dict):
        """Handler returns a dict containing all SimulateRaceOutput fields."""
        m = SimulateRaceInput(**vdot_input_dict)
        result = simulate_race_outcomes_handler(m.model_dump())
        expected_keys = set(SimulateRaceOutput.model_fields.keys())
        assert expected_keys.issubset(set(result.keys()))

    def test_num_simulations_preserved(self, vdot_input_dict):
        """Handler preserves the requested num_simulations in output."""
        m = SimulateRaceInput(**vdot_input_dict)
        result = simulate_race_outcomes_handler(m.model_dump())
        assert result["num_simulations"] == 500

    def test_median_is_positive(self, vdot_input_dict):
        """Median finish time must be a positive number."""
        m = SimulateRaceInput(**vdot_input_dict)
        result = simulate_race_outcomes_handler(m.model_dump())
        assert result["median_time_minutes"] > 0

    def test_percentile_ordering(self, vdot_input_dict):
        """p5 <= p25 <= median <= p75 <= p95."""
        m = SimulateRaceInput(**vdot_input_dict)
        r = simulate_race_outcomes_handler(m.model_dump())
        assert r["p5_time_minutes"] <= r["p25_time_minutes"]
        assert r["p25_time_minutes"] <= r["median_time_minutes"]
        assert r["median_time_minutes"] <= r["p75_time_minutes"]
        assert r["p75_time_minutes"] <= r["p95_time_minutes"]

    def test_fastest_slowest_bounds(self, vdot_input_dict):
        """fastest <= p5 and p95 <= slowest."""
        m = SimulateRaceInput(**vdot_input_dict)
        r = simulate_race_outcomes_handler(m.model_dump())
        assert r["fastest_time_minutes"] <= r["p5_time_minutes"]
        assert r["p95_time_minutes"] <= r["slowest_time_minutes"]

    def test_baseline_is_positive(self, vdot_input_dict):
        """Baseline time must be a positive number."""
        m = SimulateRaceInput(**vdot_input_dict)
        r = simulate_race_outcomes_handler(m.model_dump())
        assert r["baseline_time_minutes"] > 0

    def test_environment_factor_neutral_defaults(self, vdot_input_dict):
        """Flat, 18C, no wind → environment_factor should be 1.0."""
        m = SimulateRaceInput(**vdot_input_dict)
        r = simulate_race_outcomes_handler(m.model_dump())
        assert r["environment_factor"] == pytest.approx(1.0)

    def test_fitness_factor_neutral_tsb(self, vdot_input_dict):
        """TSB=0 → fitness_factor should be 1.0."""
        m = SimulateRaceInput(**vdot_input_dict)
        r = simulate_race_outcomes_handler(m.model_dump())
        assert r["fitness_factor"] == pytest.approx(1.0)

    def test_seed_reproducibility(self, vdot_input_dict):
        """Same seed produces identical output."""
        m = SimulateRaceInput(**vdot_input_dict)
        r1 = simulate_race_outcomes_handler(m.model_dump())
        r2 = simulate_race_outcomes_handler(m.model_dump())
        assert r1["median_time_minutes"] == r2["median_time_minutes"]
        assert r1["mean_time_minutes"] == r2["mean_time_minutes"]

    def test_different_seeds_differ(self, vdot_input_dict):
        """Different seeds generally produce different results."""
        m1 = SimulateRaceInput(**{**vdot_input_dict, "seed": 1})
        m2 = SimulateRaceInput(**{**vdot_input_dict, "seed": 2})
        r1 = simulate_race_outcomes_handler(m1.model_dump())
        r2 = simulate_race_outcomes_handler(m2.model_dump())
        # With 500 simulations, different seeds will almost certainly differ
        assert r1["mean_time_minutes"] != r2["mean_time_minutes"]

    @pytest.mark.parametrize("distance_key", list(RACE_DISTANCES.keys()))
    def test_all_distances_produce_result(self, distance_key: str):
        """Every canonical distance key is handled correctly."""
        m = SimulateRaceInput(vdot=50.0, target_distance=distance_key, num_simulations=100, seed=0)
        r = simulate_race_outcomes_handler(m.model_dump())
        assert r["median_time_minutes"] > 0


# ---------------------------------------------------------------------------
# Handler — recent-race path
# ---------------------------------------------------------------------------


class TestHandlerRecentRacePath:
    def test_returns_complete_output(self, recent_race_input_dict):
        """Recent-race path returns all expected output fields."""
        m = SimulateRaceInput(**recent_race_input_dict)
        result = simulate_race_outcomes_handler(m.model_dump())
        expected_keys = set(SimulateRaceOutput.model_fields.keys())
        assert expected_keys.issubset(set(result.keys()))

    def test_10k_slower_than_5k_for_same_fitness(self):
        """10K prediction should be slower than 5K for the same athlete."""
        base = dict(
            recent_race_distance="5K",
            recent_race_time_minutes=20.0,
            num_simulations=100,
            seed=7,
        )
        r5k = simulate_race_outcomes_handler(
            SimulateRaceInput(**{**base, "target_distance": "5K"}).model_dump()
        )
        r10k = simulate_race_outcomes_handler(
            SimulateRaceInput(**{**base, "target_distance": "10K"}).model_dump()
        )
        assert r10k["median_time_minutes"] > r5k["median_time_minutes"]

    def test_recent_race_consistent_with_vdot(self):
        """Recent-race path and VDOT path produce close results for equivalent fitness."""
        from src.deterministic.daniels import compute_vdot

        # Derive VDOT from the reference race
        ref_dist = RACE_DISTANCES["5K"]
        ref_time = 20.0
        derived_vdot = compute_vdot(ref_dist, ref_time)

        common = dict(target_distance="10K", num_simulations=1000, seed=123)

        r_race = simulate_race_outcomes_handler(
            SimulateRaceInput(
                recent_race_distance="5K",
                recent_race_time_minutes=ref_time,
                **common,
            ).model_dump()
        )
        r_vdot = simulate_race_outcomes_handler(
            SimulateRaceInput(vdot=derived_vdot, **common).model_dump()
        )

        # Both paths use the same underlying VDOT so results should be identical
        assert r_race["baseline_time_minutes"] == pytest.approx(
            r_vdot["baseline_time_minutes"], rel=1e-6
        )


# ---------------------------------------------------------------------------
# Handler — environmental effects
# ---------------------------------------------------------------------------


class TestHandlerEnvironment:
    _BASE = dict(vdot=50.0, target_distance="marathon", num_simulations=200, seed=1)

    def test_heat_slows_race(self):
        """Hot conditions produce a higher median finish time than optimal."""
        r_cool = simulate_race_outcomes_handler(
            SimulateRaceInput(**self._BASE, temperature_c=18.0).model_dump()
        )
        r_hot = simulate_race_outcomes_handler(
            SimulateRaceInput(**self._BASE, temperature_c=35.0).model_dump()
        )
        assert r_hot["median_time_minutes"] > r_cool["median_time_minutes"]
        assert r_hot["environment_factor"] > 1.0

    def test_below_optimal_temperature_no_penalty(self):
        """Temperature at or below 18C applies no heat penalty."""
        r_optimal = simulate_race_outcomes_handler(
            SimulateRaceInput(**self._BASE, temperature_c=18.0).model_dump()
        )
        r_cold = simulate_race_outcomes_handler(
            SimulateRaceInput(**self._BASE, temperature_c=5.0).model_dump()
        )
        # Both should have environment_factor == 1.0 (no heat penalty)
        assert r_optimal["environment_factor"] == pytest.approx(1.0)
        assert r_cold["environment_factor"] == pytest.approx(1.0)

    def test_elevation_slows_race(self):
        """Elevation gain produces a higher environment_factor than flat."""
        r_flat = simulate_race_outcomes_handler(
            SimulateRaceInput(**self._BASE, elevation_gain_m=0.0).model_dump()
        )
        r_hilly = simulate_race_outcomes_handler(
            SimulateRaceInput(**self._BASE, elevation_gain_m=1000.0).model_dump()
        )
        assert r_hilly["environment_factor"] > r_flat["environment_factor"]

    def test_headwind_slows_race(self):
        """Positive headwind produces a higher environment_factor."""
        r_calm = simulate_race_outcomes_handler(
            SimulateRaceInput(**self._BASE, headwind_ms=0.0).model_dump()
        )
        r_windy = simulate_race_outcomes_handler(
            SimulateRaceInput(**self._BASE, headwind_ms=5.0).model_dump()
        )
        assert r_windy["environment_factor"] > r_calm["environment_factor"]

    def test_tailwind_helps_race(self):
        """Negative headwind (tailwind) produces a lower environment_factor."""
        r_calm = simulate_race_outcomes_handler(
            SimulateRaceInput(**self._BASE, headwind_ms=0.0).model_dump()
        )
        r_tailwind = simulate_race_outcomes_handler(
            SimulateRaceInput(**self._BASE, headwind_ms=-3.0).model_dump()
        )
        assert r_tailwind["environment_factor"] < r_calm["environment_factor"]


# ---------------------------------------------------------------------------
# Handler — TSB / fitness factor
# ---------------------------------------------------------------------------


class TestHandlerFitnessFactor:
    _BASE = dict(vdot=50.0, target_distance="marathon", num_simulations=200, seed=2)

    def test_positive_tsb_gives_factor_below_one(self):
        """Being fresh (positive TSB) speeds up predicted finish time."""
        r = simulate_race_outcomes_handler(SimulateRaceInput(**self._BASE, tsb=20.0).model_dump())
        assert r["fitness_factor"] < 1.0

    def test_negative_tsb_gives_factor_above_one(self):
        """Being fatigued (negative TSB) slows predicted finish time."""
        r = simulate_race_outcomes_handler(SimulateRaceInput(**self._BASE, tsb=-20.0).model_dump())
        assert r["fitness_factor"] > 1.0

    def test_fresh_athlete_faster_than_fatigued(self):
        """Athlete with positive TSB has lower median time than with negative TSB."""
        r_fresh = simulate_race_outcomes_handler(
            SimulateRaceInput(**self._BASE, tsb=15.0).model_dump()
        )
        r_fatigued = simulate_race_outcomes_handler(
            SimulateRaceInput(**self._BASE, tsb=-15.0).model_dump()
        )
        assert r_fresh["median_time_minutes"] < r_fatigued["median_time_minutes"]


# ---------------------------------------------------------------------------
# Registration & Anthropic schema
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_adds_tool(self, registry):
        """register() adds 'simulate_race_outcomes' to the registry."""
        assert "simulate_race_outcomes" in registry.tool_names

    def test_double_register_raises(self, registry):
        """Registering the same tool twice raises ValueError."""
        with pytest.raises(ValueError, match="already registered"):
            register(registry)

    def test_description_matches(self, registry):
        """Registered description matches the module-level constant."""
        tool = registry.get("simulate_race_outcomes")
        assert tool is not None
        assert tool.description == _DESCRIPTION

    def test_anthropic_tools_list(self, registry):
        """get_anthropic_tools() returns a list with exactly one entry."""
        tools = registry.get_anthropic_tools()
        assert len(tools) == 1
        tool_def = tools[0]
        assert tool_def["name"] == "simulate_race_outcomes"
        assert "description" in tool_def
        assert "input_schema" in tool_def

    def test_anthropic_schema_has_required_field(self, registry):
        """The Anthropic schema marks 'target_distance' as required."""
        tools = registry.get_anthropic_tools()
        schema = tools[0]["input_schema"]
        assert "target_distance" in schema.get("required", [])

    def test_anthropic_schema_has_no_title_key(self, registry):
        """registry strips the 'title' key from the Pydantic schema."""
        tools = registry.get_anthropic_tools()
        schema = tools[0]["input_schema"]
        assert "title" not in schema

    def test_anthropic_schema_properties_include_vdot(self, registry):
        """Schema properties include 'vdot'."""
        tools = registry.get_anthropic_tools()
        props = tools[0]["input_schema"]["properties"]
        assert "vdot" in props

    def test_anthropic_schema_properties_include_target_distance(self, registry):
        """Schema properties include 'target_distance'."""
        tools = registry.get_anthropic_tools()
        props = tools[0]["input_schema"]["properties"]
        assert "target_distance" in props


# ---------------------------------------------------------------------------
# Registry.execute() integration
# ---------------------------------------------------------------------------


class TestRegistryExecute:
    def test_execute_vdot_path_success(self, registry):
        """registry.execute() succeeds with a valid VDOT-path input."""
        result = registry.execute(
            "simulate_race_outcomes",
            {
                "vdot": 50.0,
                "target_distance": "marathon",
                "num_simulations": 100,
                "seed": 0,
            },
        )
        assert result.success is True
        assert result.tool_name == "simulate_race_outcomes"
        assert "median_time_minutes" in result.output

    def test_execute_recent_race_path_success(self, registry):
        """registry.execute() succeeds with a valid recent-race-path input."""
        result = registry.execute(
            "simulate_race_outcomes",
            {
                "recent_race_distance": "5K",
                "recent_race_time_minutes": 20.0,
                "target_distance": "10K",
                "num_simulations": 100,
                "seed": 0,
            },
        )
        assert result.success is True
        assert result.output["median_time_minutes"] > 0

    def test_execute_invalid_no_fitness_input(self, registry):
        """registry.execute() returns failure when no fitness input is given."""
        result = registry.execute(
            "simulate_race_outcomes",
            {"target_distance": "5K"},
        )
        assert result.success is False
        assert "error" in result.output

    def test_execute_invalid_distance_key(self, registry):
        """registry.execute() returns failure for unknown distance key."""
        result = registry.execute(
            "simulate_race_outcomes",
            {"vdot": 50.0, "target_distance": "ultramarathon"},
        )
        assert result.success is False
        assert "error" in result.output

    def test_execute_unknown_tool_returns_failure(self, registry):
        """registry.execute() returns failure for unregistered tool name."""
        result = registry.execute("nonexistent_tool", {})
        assert result.success is False
        assert "Unknown tool" in result.output["error"]

    def test_execute_to_content_block(self, registry):
        """ToolResult.to_content_block() returns valid JSON string."""
        import json

        result = registry.execute(
            "simulate_race_outcomes",
            {
                "vdot": 55.0,
                "target_distance": "5K",
                "num_simulations": 50,
                "seed": 5,
            },
        )
        assert result.success is True
        parsed = json.loads(result.to_content_block())
        assert "median_time_minutes" in parsed

    def test_execute_invalid_vdot_zero(self, registry):
        """registry.execute() fails gracefully when vdot=0."""
        result = registry.execute(
            "simulate_race_outcomes",
            {"vdot": 0.0, "target_distance": "5K"},
        )
        assert result.success is False

    def test_execute_both_fitness_paths_fails(self, registry):
        """Providing both vdot and recent-race inputs triggers a validation failure."""
        result = registry.execute(
            "simulate_race_outcomes",
            {
                "vdot": 50.0,
                "recent_race_distance": "5K",
                "recent_race_time_minutes": 20.0,
                "target_distance": "10K",
            },
        )
        assert result.success is False

    def test_execute_partial_recent_race_fails(self, registry):
        """Providing only recent_race_distance without time triggers failure."""
        result = registry.execute(
            "simulate_race_outcomes",
            {
                "recent_race_distance": "5K",
                "target_distance": "10K",
            },
        )
        assert result.success is False

    def test_execute_output_all_floats(self, registry):
        """All time-valued outputs are floats and factors are floats."""
        result = registry.execute(
            "simulate_race_outcomes",
            {
                "vdot": 50.0,
                "target_distance": "5K",
                "num_simulations": 200,
                "seed": 77,
            },
        )
        assert result.success is True
        out = result.output
        time_keys = [
            "median_time_minutes",
            "mean_time_minutes",
            "std_time_minutes",
            "p5_time_minutes",
            "p25_time_minutes",
            "p75_time_minutes",
            "p95_time_minutes",
            "fastest_time_minutes",
            "slowest_time_minutes",
            "baseline_time_minutes",
            "environment_factor",
            "fitness_factor",
        ]
        for key in time_keys:
            assert isinstance(out[key], float), f"{key} should be float, got {type(out[key])}"

    def test_execute_num_simulations_is_int(self, registry):
        """num_simulations in output is an integer."""
        result = registry.execute(
            "simulate_race_outcomes",
            {
                "vdot": 50.0,
                "target_distance": "5K",
                "num_simulations": 300,
                "seed": 0,
            },
        )
        assert result.success is True
        assert isinstance(result.output["num_simulations"], int)
        assert result.output["num_simulations"] == 300
