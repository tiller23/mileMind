"""Tests for the evaluation CLI entry point."""

import subprocess
import sys
from pathlib import Path

import pytest

# Resolve backend directory so tests work from any cwd
_BACKEND_DIR = str(Path(__file__).resolve().parents[3])


class TestEvaluationCLI:
    """Tests for the evaluation CLI."""

    def test_dry_run_lists_personas(self) -> None:
        """--dry-run prints persona info without API calls."""
        result = subprocess.run(
            [sys.executable, "-m", "src.evaluation.run", "--dry-run"],
            capture_output=True,
            text=True,
            cwd=_BACKEND_DIR,
            timeout=30,
        )
        assert result.returncode == 0
        assert "Dry Run" in result.stdout
        assert "beginner_runner" in result.stdout
        assert "advanced_marathoner" in result.stdout
        assert "Beginner Runner" in result.stdout

    def test_dry_run_with_persona_filter(self) -> None:
        """--dry-run with --persona filter shows only selected."""
        result = subprocess.run(
            [sys.executable, "-m", "src.evaluation.run", "--dry-run", "--persona", "beginner_runner"],
            capture_output=True,
            text=True,
            cwd=_BACKEND_DIR,
            timeout=30,
        )
        assert result.returncode == 0
        assert "beginner_runner" in result.stdout
        # Should NOT list other personas
        assert "aggressive_spiker" not in result.stdout

    def test_dry_run_shows_model_config(self) -> None:
        """--dry-run prints model configuration."""
        result = subprocess.run(
            [sys.executable, "-m", "src.evaluation.run", "--dry-run",
             "--planner-model", "test-planner",
             "--reviewer-model", "test-reviewer"],
            capture_output=True,
            text=True,
            cwd=_BACKEND_DIR,
            timeout=30,
        )
        assert result.returncode == 0
        assert "test-planner" in result.stdout
        assert "test-reviewer" in result.stdout

    def test_no_api_key_exits_with_error(self) -> None:
        """Running without API key and without --dry-run exits with error."""
        import os
        env = os.environ.copy()
        # Set to empty string so load_dotenv() won't fill it from .env file
        env["ANTHROPIC_API_KEY"] = ""

        result = subprocess.run(
            [sys.executable, "-m", "src.evaluation.run"],
            capture_output=True,
            text=True,
            cwd=_BACKEND_DIR,
            timeout=30,
            env=env,
        )
        assert result.returncode != 0
        assert "ANTHROPIC_API_KEY" in result.stderr

    def test_module_runnable(self) -> None:
        """python -m src.evaluation --dry-run works via __main__.py."""
        result = subprocess.run(
            [sys.executable, "-m", "src.evaluation", "--dry-run"],
            capture_output=True,
            text=True,
            cwd=_BACKEND_DIR,
            timeout=30,
        )
        assert result.returncode == 0
        assert "Dry Run" in result.stdout

    def test_invalid_persona_rejected(self) -> None:
        """--persona with unknown ID exits with error."""
        result = subprocess.run(
            [sys.executable, "-m", "src.evaluation.run", "--dry-run",
             "--persona", "nonexistent_runner"],
            capture_output=True,
            text=True,
            cwd=_BACKEND_DIR,
            timeout=30,
        )
        assert result.returncode != 0
        assert "invalid choice" in result.stderr

    def test_compare_dry_run(self) -> None:
        """--compare --dry-run shows compare mode enabled."""
        result = subprocess.run(
            [sys.executable, "-m", "src.evaluation.run", "--dry-run", "--compare"],
            capture_output=True,
            text=True,
            cwd=_BACKEND_DIR,
            timeout=30,
        )
        assert result.returncode == 0
        assert "Compare mode: True" in result.stdout

    def test_batch_and_compare_mutually_exclusive(self) -> None:
        """--batch and --compare together exits with error."""
        result = subprocess.run(
            [sys.executable, "-m", "src.evaluation.run",
             "--batch", "--compare", "--dry-run"],
            capture_output=True,
            text=True,
            cwd=_BACKEND_DIR,
            timeout=30,
        )
        assert result.returncode != 0
        assert "mutually exclusive" in result.stderr
