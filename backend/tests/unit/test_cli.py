"""Tests for the MileMind CLI (src/cli.py).

Covers both subprocess-based tests (verifying actual CLI output) and
direct unit tests of the pure functions: parse_args, load_athlete,
and print_dry_run.

Subprocess tests use the same pattern as tests/unit/evaluation/test_run_cli.py
so that they work correctly regardless of the working directory from which
pytest is invoked.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

# Resolve backend directory so subprocess tests work from any cwd
_BACKEND_DIR = str(Path(__file__).resolve().parents[2])

# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


def _run_cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run the MileMind CLI as a subprocess and return the result.

    Args:
        *args: Extra CLI arguments passed after ``python -m src.cli``.
        env: Optional environment override dict.

    Returns:
        CompletedProcess with returncode, stdout, stderr.
    """
    return subprocess.run(
        [sys.executable, "-m", "src.cli", *args],
        capture_output=True,
        text=True,
        cwd=_BACKEND_DIR,
        timeout=30,
        env=env,
    )


# ---------------------------------------------------------------------------
# Subprocess tests — help and basic options
# ---------------------------------------------------------------------------


class TestCLIHelp:
    """Tests for --help flag output."""

    def test_help_exits_zero(self) -> None:
        """--help must exit with code 0 and print usage information."""
        result = _run_cli("--help")
        assert result.returncode == 0

    def test_help_shows_usage(self) -> None:
        """--help output must include the word 'usage' (case-insensitive)."""
        result = _run_cli("--help")
        assert "usage" in result.stdout.lower()

    def test_help_mentions_profile_and_example(self) -> None:
        """--help must document both --profile and --example options."""
        result = _run_cli("--help")
        assert "--profile" in result.stdout
        assert "--example" in result.stdout


# ---------------------------------------------------------------------------
# Subprocess tests — dry-run with example profiles
# ---------------------------------------------------------------------------


class TestCLIDryRunExamples:
    """Tests for --dry-run mode with built-in example profiles."""

    def test_beginner_dry_run_exits_zero(self) -> None:
        """--example beginner --dry-run must exit 0 without any API calls."""
        result = _run_cli("--example", "beginner", "--dry-run")
        assert result.returncode == 0

    def test_beginner_dry_run_shows_system_prompt(self) -> None:
        """--dry-run output must contain the SYSTEM PROMPT section header."""
        result = _run_cli("--example", "beginner", "--dry-run")
        assert "SYSTEM PROMPT" in result.stdout

    def test_beginner_dry_run_shows_tool_definitions(self) -> None:
        """--dry-run output must list tool definitions so the caller can inspect them."""
        result = _run_cli("--example", "beginner", "--dry-run")
        assert "TOOL DEFINITIONS" in result.stdout

    def test_beginner_dry_run_shows_all_tools(self) -> None:
        """--dry-run must print all 6 registered tool names in the tool listing."""
        result = _run_cli("--example", "beginner", "--dry-run")
        for tool in [
            "compute_training_stress",
            "evaluate_fatigue_state",
            "validate_progression_constraints",
            "simulate_race_outcomes",
            "reallocate_week_load",
            "project_taper",
        ]:
            assert tool in result.stdout, f"Tool missing from dry-run output: {tool!r}"

    @pytest.mark.parametrize("example", ["beginner", "intermediate", "advanced", "aggressive"])
    def test_all_example_profiles_dry_run(self, example: str) -> None:
        """Every built-in example profile must work with --dry-run (exit 0).

        Exercises all four profiles so a broken profile dict is caught
        before any real API call is made.
        """
        result = _run_cli("--example", example, "--dry-run")
        assert result.returncode == 0, f"--example {example} --dry-run failed: {result.stderr}"

    def test_dry_run_shows_dry_run_header(self) -> None:
        """--dry-run output must include the 'DRY RUN' banner."""
        result = _run_cli("--example", "beginner", "--dry-run")
        assert "DRY RUN" in result.stdout


# ---------------------------------------------------------------------------
# Subprocess tests — reviewer mode flags
# ---------------------------------------------------------------------------


class TestCLIReviewerModeFlags:
    """Tests for --change-type flag and reviewer visibility in dry-run."""

    def test_tweak_dry_run_shows_reviewer_skipped(self) -> None:
        """--change-type tweak --dry-run must print that the reviewer is SKIPPED.

        TWEAK mode routes only through the planner so no reviewer cost is
        incurred; the dry-run output should confirm this.
        """
        result = _run_cli("--example", "beginner", "--change-type", "tweak", "--dry-run")
        assert result.returncode == 0
        # The main() banner printed before dry-run shows SKIPPED
        assert "SKIPPED" in result.stdout

    def test_full_dry_run_shows_reviewer_config(self) -> None:
        """--change-type full --dry-run must show reviewer model configuration.

        FULL mode runs the planner + reviewer loop; the user should see
        which model is being used as reviewer.
        """
        result = _run_cli("--example", "beginner", "--change-type", "full", "--dry-run")
        assert result.returncode == 0
        # --dry-run with review=True prints "Reviewer model: ..."
        assert "Reviewer model" in result.stdout

    def test_adaptation_dry_run_exits_zero(self) -> None:
        """--change-type adaptation --dry-run must exit 0."""
        result = _run_cli("--example", "beginner", "--change-type", "adaptation", "--dry-run")
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Subprocess tests — error cases
# ---------------------------------------------------------------------------


class TestCLIErrorCases:
    """Tests for CLI error handling."""

    def test_nonexistent_profile_exits_nonzero(self) -> None:
        """--profile pointing to a non-existent file must exit with non-zero status."""
        result = _run_cli("--profile", "/nonexistent/path/athlete.json")
        assert result.returncode != 0

    def test_nonexistent_profile_prints_error_to_stderr(self) -> None:
        """--profile with a missing file must print an error message to stderr."""
        result = _run_cli("--profile", "/nonexistent/path/athlete.json")
        assert "Error" in result.stderr or "not found" in result.stderr

    def test_invalid_example_value_rejected(self) -> None:
        """--example with an unknown profile name must fail with a non-zero exit code.

        argparse enforces the choices list; this ensures the list is wired up.
        """
        result = _run_cli("--example", "ultramarathoner")
        assert result.returncode != 0

    def test_invalid_example_shows_argparse_error(self) -> None:
        """--example with an invalid value must produce an argparse 'invalid choice' error."""
        result = _run_cli("--example", "ultramarathoner")
        assert "invalid choice" in result.stderr

    def test_no_args_exits_nonzero(self) -> None:
        """Running with no arguments must exit with non-zero (profile/example required)."""
        result = _run_cli()
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# Unit tests — parse_args
# ---------------------------------------------------------------------------


class TestParseArgs:
    """Direct unit tests for the parse_args() function."""

    def test_example_beginner(self) -> None:
        """parse_args accepts --example beginner and sets example='beginner'."""
        from src.cli import parse_args

        with patch("sys.argv", ["cli", "--example", "beginner"]):
            args = parse_args()
        assert args.example == "beginner"
        assert args.profile is None

    def test_example_intermediate(self) -> None:
        """parse_args accepts --example intermediate."""
        from src.cli import parse_args

        with patch("sys.argv", ["cli", "--example", "intermediate"]):
            args = parse_args()
        assert args.example == "intermediate"

    def test_dry_run_flag(self) -> None:
        """parse_args sets dry_run=True when --dry-run is passed."""
        from src.cli import parse_args

        with patch("sys.argv", ["cli", "--example", "beginner", "--dry-run"]):
            args = parse_args()
        assert args.dry_run is True

    def test_change_type_defaults_to_full(self) -> None:
        """parse_args default change_type is 'full' when --change-type is omitted."""
        from src.cli import parse_args

        with patch("sys.argv", ["cli", "--example", "beginner"]):
            args = parse_args()
        assert args.change_type == "full"

    def test_change_type_tweak(self) -> None:
        """parse_args accepts --change-type tweak."""
        from src.cli import parse_args

        with patch("sys.argv", ["cli", "--example", "beginner", "--change-type", "tweak"]):
            args = parse_args()
        assert args.change_type == "tweak"

    def test_yes_flag(self) -> None:
        """parse_args sets yes=True when -y is passed."""
        from src.cli import parse_args

        with patch("sys.argv", ["cli", "--example", "beginner", "-y"]):
            args = parse_args()
        assert args.yes is True

    def test_max_iterations_default(self) -> None:
        """parse_args default max_iterations is 15."""
        from src.cli import parse_args

        with patch("sys.argv", ["cli", "--example", "beginner"]):
            args = parse_args()
        assert args.max_iterations == 15

    def test_max_retries_default(self) -> None:
        """parse_args default max_retries is 3."""
        from src.cli import parse_args

        with patch("sys.argv", ["cli", "--example", "beginner"]):
            args = parse_args()
        assert args.max_retries == 3


# ---------------------------------------------------------------------------
# Unit tests — load_athlete
# ---------------------------------------------------------------------------


class TestLoadAthlete:
    """Direct unit tests for the load_athlete() function."""

    @pytest.mark.parametrize(
        "example_name", ["beginner", "intermediate", "advanced", "aggressive"]
    )
    def test_load_example_profile(self, example_name: str) -> None:
        """load_athlete returns a valid AthleteProfile for every built-in example.

        If any example dict is malformed, model_validate raises and load_athlete
        calls sys.exit(1) — this test catches that early.
        """
        from src.cli import load_athlete
        from src.models.athlete import AthleteProfile

        args = argparse.Namespace(example=example_name, profile=None)
        profile = load_athlete(args)
        assert isinstance(profile, AthleteProfile)

    def test_beginner_profile_name(self) -> None:
        """Beginner example profile has the expected athlete name."""
        from src.cli import load_athlete

        args = argparse.Namespace(example="beginner", profile=None)
        profile = load_athlete(args)
        assert profile.name == "Sarah Chen"

    def test_missing_profile_file_exits(self, tmp_path: Path) -> None:
        """load_athlete calls sys.exit(1) when the profile file does not exist."""
        from src.cli import load_athlete

        args = argparse.Namespace(example=None, profile=str(tmp_path / "missing.json"))
        with pytest.raises(SystemExit) as exc_info:
            load_athlete(args)
        assert exc_info.value.code == 1

    def test_invalid_json_profile_exits(self, tmp_path: Path) -> None:
        """load_athlete calls sys.exit(1) when the profile file has invalid JSON."""
        from src.cli import load_athlete

        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{ not valid json }")
        args = argparse.Namespace(example=None, profile=str(bad_json))
        with pytest.raises(SystemExit) as exc_info:
            load_athlete(args)
        assert exc_info.value.code == 1

    def test_valid_json_profile_file(self, tmp_path: Path) -> None:
        """load_athlete loads a valid JSON profile from disk and returns AthleteProfile."""
        import json

        from src.cli import load_athlete
        from src.models.athlete import AthleteProfile

        profile_data = {
            "name": "Test Runner",
            "age": 30,
            "weekly_mileage_base": 40.0,
            "goal_distance": "10K",
            "vdot": 40.0,
            "risk_tolerance": "moderate",
            "training_days_per_week": 4,
            "injury_history": "",
        }
        profile_file = tmp_path / "athlete.json"
        profile_file.write_text(json.dumps(profile_data))

        args = argparse.Namespace(example=None, profile=str(profile_file))
        profile = load_athlete(args)
        assert isinstance(profile, AthleteProfile)
        assert profile.name == "Test Runner"


# ---------------------------------------------------------------------------
# Unit tests — print_dry_run
# ---------------------------------------------------------------------------


class TestPrintDryRun:
    """Direct unit tests for the print_dry_run() function."""

    def _capture(self, *args, **kwargs) -> str:
        """Run print_dry_run and capture its stdout output."""
        from src.cli import print_dry_run

        buf = StringIO()
        with patch("sys.stdout", buf):
            print_dry_run(*args, **kwargs)
        return buf.getvalue()

    def test_print_dry_run_with_review_does_not_crash(self) -> None:
        """print_dry_run with review=True must complete without raising."""
        from src.cli import load_athlete

        args = argparse.Namespace(example="beginner", profile=None)
        athlete = load_athlete(args)
        output = self._capture(athlete, "claude-sonnet-4-20250514", 15, review=True)
        assert len(output) > 0

    def test_print_dry_run_without_review_does_not_crash(self) -> None:
        """print_dry_run with review=False must complete without raising."""
        from src.cli import load_athlete

        args = argparse.Namespace(example="beginner", profile=None)
        athlete = load_athlete(args)
        output = self._capture(athlete, "claude-sonnet-4-20250514", 15, review=False)
        assert len(output) > 0

    def test_print_dry_run_shows_reviewer_disabled_when_no_review(self) -> None:
        """print_dry_run with review=False must print 'DISABLED' for reviewer."""
        from src.cli import load_athlete

        args = argparse.Namespace(example="beginner", profile=None)
        athlete = load_athlete(args)
        output = self._capture(athlete, "claude-sonnet-4-20250514", 15, review=False)
        assert "DISABLED" in output

    def test_print_dry_run_shows_reviewer_model_when_review_enabled(self) -> None:
        """print_dry_run with review=True must show the reviewer model name."""
        from src.cli import load_athlete

        args = argparse.Namespace(example="beginner", profile=None)
        athlete = load_athlete(args)
        output = self._capture(
            athlete,
            "claude-sonnet-4-20250514",
            15,
            review=True,
            reviewer_model="claude-opus-4-20250514",
        )
        assert "claude-opus-4-20250514" in output

    def test_print_dry_run_includes_system_prompt_content(self) -> None:
        """print_dry_run output must include PLANNER_SYSTEM_PROMPT text."""
        from src.cli import load_athlete

        args = argparse.Namespace(example="beginner", profile=None)
        athlete = load_athlete(args)
        output = self._capture(athlete, "claude-sonnet-4-20250514", 15, review=True)
        # The planner prompt contains "CRITICAL CONSTRAINTS" — confirm it's printed
        assert "CRITICAL CONSTRAINTS" in output

    def test_print_dry_run_lists_all_tools(self) -> None:
        """print_dry_run must print all 6 registered tool names."""
        from src.cli import load_athlete

        args = argparse.Namespace(example="beginner", profile=None)
        athlete = load_athlete(args)
        output = self._capture(athlete, "claude-sonnet-4-20250514", 15, review=True)
        for tool in [
            "compute_training_stress",
            "evaluate_fatigue_state",
            "validate_progression_constraints",
            "simulate_race_outcomes",
            "reallocate_week_load",
            "project_taper",
        ]:
            assert tool in output, f"Tool missing from print_dry_run output: {tool!r}"
