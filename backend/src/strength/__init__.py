"""Running-specific strength playbook module.

Deterministic exercise selection based on athlete profile + injury tags.
LLM is only used for narrative blurb generation, never exercise selection.
"""

from src.strength.models import Exercise, ExerciseBlock, Playbook
from src.strength.playbook_builder import build_playbook, catalog_version

__all__ = [
    "Exercise",
    "ExerciseBlock",
    "Playbook",
    "build_playbook",
    "catalog_version",
]
