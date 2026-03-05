"""Tests for PlanChangeType enum."""

from src.models.plan_change import PlanChangeType


class TestPlanChangeType:
    """Tests for the PlanChangeType enum."""

    def test_enum_values(self) -> None:
        assert PlanChangeType.FULL == "full"
        assert PlanChangeType.ADAPTATION == "adaptation"
        assert PlanChangeType.TWEAK == "tweak"

    def test_all_three_members(self) -> None:
        assert len(PlanChangeType) == 3

    def test_construction_from_string(self) -> None:
        assert PlanChangeType("full") is PlanChangeType.FULL
        assert PlanChangeType("adaptation") is PlanChangeType.ADAPTATION
        assert PlanChangeType("tweak") is PlanChangeType.TWEAK

    def test_is_str_subclass(self) -> None:
        assert isinstance(PlanChangeType.FULL, str)

    def test_importable_from_package(self) -> None:
        from src.models import PlanChangeType as imported
        assert imported is PlanChangeType
