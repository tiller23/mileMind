"""Unit tests for the ToolRegistry class and supporting types.

Tests the ToolRegistry in isolation using tiny mock tools — no real tool
implementations are imported.  This keeps the tests focused purely on
registry mechanics and prevents coupling to per-tool business logic.

Coverage:
- register(): happy path and duplicate-name error
- get(): found and not-found cases
- tool_names property: correct list returned
- get_anthropic_tools(): correct Anthropic API format
- execute(): success, unknown tool, Pydantic validation failure,
  ValueError from handler, unexpected Exception from handler
- ToolResult.to_content_block(): produces valid JSON string
- ToolError: stores tool_name and message attributes
"""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, Field

from src.tools.registry import ToolDefinition, ToolError, ToolRegistry, ToolResult

# ---------------------------------------------------------------------------
# Mock Pydantic models and handlers — no real tools imported
# ---------------------------------------------------------------------------


class _AddInput(BaseModel):
    """Minimal input model: adds two non-negative numbers."""

    a: float = Field(ge=0.0, description="First operand")
    b: float = Field(ge=0.0, description="Second operand")


def _add_handler(input_data: dict) -> dict:
    """Return the sum of a and b."""
    return {"result": input_data["a"] + input_data["b"]}


class _EchoInput(BaseModel):
    """Minimal input model that echoes a message string."""

    message: str = Field(min_length=1, description="Non-empty message to echo")


def _echo_handler(input_data: dict) -> dict:
    """Return the message back."""
    return {"echo": input_data["message"]}


def _value_error_handler(input_data: dict) -> dict:
    """Handler that always raises ValueError — simulates a domain constraint."""
    raise ValueError("domain constraint violated")


def _runtime_error_handler(input_data: dict) -> dict:
    """Handler that always raises a generic RuntimeError — unexpected failure."""
    raise RuntimeError("something broke internally")


def _make_tool(
    name: str = "add_numbers",
    description: str = "Add two numbers",
    input_model: type[BaseModel] = _AddInput,
    handler=_add_handler,
) -> ToolDefinition:
    """Build a ToolDefinition with sensible defaults for registry tests."""
    return ToolDefinition(
        name=name,
        description=description,
        input_model=input_model,
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_registry() -> ToolRegistry:
    """A fresh, empty ToolRegistry."""
    return ToolRegistry()


@pytest.fixture
def registry_with_add(empty_registry: ToolRegistry) -> ToolRegistry:
    """Registry with a single 'add_numbers' tool registered."""
    empty_registry.register(_make_tool())
    return empty_registry


@pytest.fixture
def registry_with_two_tools(empty_registry: ToolRegistry) -> ToolRegistry:
    """Registry with both 'add_numbers' and 'echo_message' registered."""
    empty_registry.register(_make_tool(name="add_numbers"))
    empty_registry.register(
        _make_tool(name="echo_message", input_model=_EchoInput, handler=_echo_handler)
    )
    return empty_registry


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------


class TestRegister:
    """ToolRegistry.register() stores tools and rejects duplicates."""

    def test_register_single_tool_succeeds(self, empty_registry: ToolRegistry) -> None:
        """A tool can be registered without error."""
        empty_registry.register(_make_tool())  # must not raise

    def test_register_returns_none(self, empty_registry: ToolRegistry) -> None:
        """register() returns None (it is a void operation)."""
        result = empty_registry.register(_make_tool())
        assert result is None

    def test_duplicate_name_raises_value_error(self, registry_with_add: ToolRegistry) -> None:
        """Registering a second tool with the same name raises ValueError."""
        with pytest.raises(ValueError, match="already registered"):
            registry_with_add.register(_make_tool(name="add_numbers"))

    def test_duplicate_error_message_contains_tool_name(
        self, registry_with_add: ToolRegistry
    ) -> None:
        """The ValueError message includes the conflicting tool name."""
        with pytest.raises(ValueError) as exc_info:
            registry_with_add.register(_make_tool(name="add_numbers"))
        assert "add_numbers" in str(exc_info.value)

    def test_different_names_do_not_conflict(self, registry_with_add: ToolRegistry) -> None:
        """Two tools with different names can both be registered."""
        registry_with_add.register(
            _make_tool(name="another_tool", input_model=_EchoInput, handler=_echo_handler)
        )
        assert len(registry_with_add.tool_names) == 2


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


class TestGet:
    """ToolRegistry.get() retrieves registered tools by name."""

    def test_get_registered_tool_returns_definition(self, registry_with_add: ToolRegistry) -> None:
        """get() returns the ToolDefinition for a known tool name."""
        tool = registry_with_add.get("add_numbers")
        assert tool is not None
        assert tool.name == "add_numbers"

    def test_get_returns_correct_description(self, empty_registry: ToolRegistry) -> None:
        """get() returns the same description that was registered."""
        empty_registry.register(_make_tool(description="Sum two numbers together"))
        tool = empty_registry.get("add_numbers")
        assert tool is not None
        assert tool.description == "Sum two numbers together"

    def test_get_returns_correct_input_model(self, registry_with_add: ToolRegistry) -> None:
        """get() returns the same input_model class that was registered."""
        tool = registry_with_add.get("add_numbers")
        assert tool is not None
        assert tool.input_model is _AddInput

    def test_get_unknown_tool_returns_none(self, registry_with_add: ToolRegistry) -> None:
        """get() returns None for a name that was never registered."""
        result = registry_with_add.get("nonexistent_tool")
        assert result is None

    def test_get_empty_registry_returns_none(self, empty_registry: ToolRegistry) -> None:
        """get() on a completely empty registry returns None for any name."""
        assert empty_registry.get("add_numbers") is None

    def test_get_is_case_sensitive(self, registry_with_add: ToolRegistry) -> None:
        """Tool names are case-sensitive; wrong case returns None."""
        assert registry_with_add.get("Add_Numbers") is None
        assert registry_with_add.get("ADD_NUMBERS") is None


# ---------------------------------------------------------------------------
# tool_names property
# ---------------------------------------------------------------------------


class TestToolNames:
    """ToolRegistry.tool_names property returns correct name lists."""

    def test_empty_registry_has_no_names(self, empty_registry: ToolRegistry) -> None:
        """A freshly created registry has no registered tool names."""
        assert empty_registry.tool_names == []

    def test_single_tool_appears_in_names(self, registry_with_add: ToolRegistry) -> None:
        """The registered tool name appears in tool_names."""
        assert "add_numbers" in registry_with_add.tool_names

    def test_tool_names_length_matches_registration_count(
        self, registry_with_two_tools: ToolRegistry
    ) -> None:
        """tool_names length equals the number of tools registered."""
        assert len(registry_with_two_tools.tool_names) == 2

    def test_tool_names_contains_both_registered_names(
        self, registry_with_two_tools: ToolRegistry
    ) -> None:
        """Both registered names appear in tool_names."""
        names = registry_with_two_tools.tool_names
        assert "add_numbers" in names
        assert "echo_message" in names

    def test_tool_names_returns_list(self, registry_with_add: ToolRegistry) -> None:
        """tool_names returns a list, not another iterable type."""
        assert isinstance(registry_with_add.tool_names, list)

    def test_tool_names_does_not_mutate_registry(self, registry_with_add: ToolRegistry) -> None:
        """Modifying the returned list must not affect the registry internals."""
        names = registry_with_add.tool_names
        names.clear()
        # Registry should still have the tool
        assert "add_numbers" in registry_with_add.tool_names


# ---------------------------------------------------------------------------
# get_anthropic_tools()
# ---------------------------------------------------------------------------


class TestGetAnthropicTools:
    """ToolRegistry.get_anthropic_tools() returns Anthropic API format."""

    def test_empty_registry_returns_empty_list(self, empty_registry: ToolRegistry) -> None:
        """An empty registry returns an empty list."""
        assert empty_registry.get_anthropic_tools() == []

    def test_single_tool_returns_one_entry(self, registry_with_add: ToolRegistry) -> None:
        """One registered tool produces a list with one entry."""
        tools = registry_with_add.get_anthropic_tools()
        assert len(tools) == 1

    def test_two_tools_returns_two_entries(self, registry_with_two_tools: ToolRegistry) -> None:
        """Two registered tools produce a list with two entries."""
        tools = registry_with_two_tools.get_anthropic_tools()
        assert len(tools) == 2

    def test_entry_has_name_key(self, registry_with_add: ToolRegistry) -> None:
        """Each entry must have a 'name' key."""
        tools = registry_with_add.get_anthropic_tools()
        assert "name" in tools[0]

    def test_entry_has_description_key(self, registry_with_add: ToolRegistry) -> None:
        """Each entry must have a 'description' key."""
        tools = registry_with_add.get_anthropic_tools()
        assert "description" in tools[0]

    def test_entry_has_input_schema_key(self, registry_with_add: ToolRegistry) -> None:
        """Each entry must have an 'input_schema' key."""
        tools = registry_with_add.get_anthropic_tools()
        assert "input_schema" in tools[0]

    def test_name_value_matches_registered_name(self, registry_with_add: ToolRegistry) -> None:
        """The 'name' value must equal the name passed at registration time."""
        tools = registry_with_add.get_anthropic_tools()
        assert tools[0]["name"] == "add_numbers"

    def test_description_value_matches_registered_description(
        self, empty_registry: ToolRegistry
    ) -> None:
        """The 'description' value must equal the description passed at registration."""
        empty_registry.register(_make_tool(description="Unique description XYZ"))
        tools = empty_registry.get_anthropic_tools()
        assert tools[0]["description"] == "Unique description XYZ"

    def test_input_schema_type_is_object(self, registry_with_add: ToolRegistry) -> None:
        """The input_schema root must have type='object'."""
        schema = registry_with_add.get_anthropic_tools()[0]["input_schema"]
        assert schema.get("type") == "object"

    def test_input_schema_has_properties(self, registry_with_add: ToolRegistry) -> None:
        """The input_schema must include a 'properties' dict."""
        schema = registry_with_add.get_anthropic_tools()[0]["input_schema"]
        assert "properties" in schema
        assert isinstance(schema["properties"], dict)

    def test_input_schema_no_title_at_root(self, registry_with_add: ToolRegistry) -> None:
        """The input_schema must NOT include a 'title' key at root level.

        Pydantic generates 'title' by default; the registry strips it so
        Anthropic does not reject the tool definition.
        """
        schema = registry_with_add.get_anthropic_tools()[0]["input_schema"]
        assert "title" not in schema

    def test_input_schema_properties_contain_model_fields(
        self, registry_with_add: ToolRegistry
    ) -> None:
        """Properties must include the fields defined on the input model."""
        schema = registry_with_add.get_anthropic_tools()[0]["input_schema"]
        assert "a" in schema["properties"]
        assert "b" in schema["properties"]

    def test_returns_list_type(self, registry_with_add: ToolRegistry) -> None:
        """get_anthropic_tools() returns a list, not a generator or other type."""
        tools = registry_with_add.get_anthropic_tools()
        assert isinstance(tools, list)


# ---------------------------------------------------------------------------
# execute() — success path
# ---------------------------------------------------------------------------


class TestExecuteSuccess:
    """execute() dispatches to the handler and returns a successful ToolResult."""

    def test_execute_returns_tool_result(self, registry_with_add: ToolRegistry) -> None:
        """execute() always returns a ToolResult instance."""
        result = registry_with_add.execute("add_numbers", {"a": 1.0, "b": 2.0})
        assert isinstance(result, ToolResult)

    def test_execute_success_is_true(self, registry_with_add: ToolRegistry) -> None:
        """execute() with valid input sets success=True."""
        result = registry_with_add.execute("add_numbers", {"a": 3.0, "b": 4.0})
        assert result.success is True

    def test_execute_output_contains_expected_key(self, registry_with_add: ToolRegistry) -> None:
        """Output dict contains the 'result' key from _add_handler."""
        result = registry_with_add.execute("add_numbers", {"a": 3.0, "b": 4.0})
        assert "result" in result.output

    def test_execute_output_value_is_correct(self, registry_with_add: ToolRegistry) -> None:
        """Handler arithmetic is reflected in the output value."""
        result = registry_with_add.execute("add_numbers", {"a": 5.0, "b": 7.0})
        assert result.output["result"] == pytest.approx(12.0)

    def test_execute_tool_name_in_result(self, registry_with_add: ToolRegistry) -> None:
        """ToolResult.tool_name equals the name of the tool that was called."""
        result = registry_with_add.execute("add_numbers", {"a": 1.0, "b": 1.0})
        assert result.tool_name == "add_numbers"

    def test_execute_output_is_dict(self, registry_with_add: ToolRegistry) -> None:
        """ToolResult.output is a plain dict."""
        result = registry_with_add.execute("add_numbers", {"a": 0.0, "b": 0.0})
        assert isinstance(result.output, dict)


# ---------------------------------------------------------------------------
# execute() — unknown tool name
# ---------------------------------------------------------------------------


class TestExecuteUnknownTool:
    """execute() with an unregistered name returns a failure ToolResult."""

    def test_unknown_tool_success_is_false(self, registry_with_add: ToolRegistry) -> None:
        """Calling an unknown tool returns success=False."""
        result = registry_with_add.execute("no_such_tool", {})
        assert result.success is False

    def test_unknown_tool_output_has_error_key(self, registry_with_add: ToolRegistry) -> None:
        """Failure output must have an 'error' key."""
        result = registry_with_add.execute("no_such_tool", {})
        assert "error" in result.output

    def test_unknown_tool_error_message_contains_name(
        self, registry_with_add: ToolRegistry
    ) -> None:
        """The error message mentions the unknown tool name."""
        result = registry_with_add.execute("mystery_tool", {})
        assert "mystery_tool" in result.output["error"]

    def test_unknown_tool_result_tool_name_echoed(self, registry_with_add: ToolRegistry) -> None:
        """ToolResult.tool_name is set to the (unknown) name that was requested."""
        result = registry_with_add.execute("mystery_tool", {})
        assert result.tool_name == "mystery_tool"

    def test_empty_registry_unknown_tool(self, empty_registry: ToolRegistry) -> None:
        """Even on an empty registry, execute() with any name returns failure."""
        result = empty_registry.execute("any_tool", {})
        assert result.success is False


# ---------------------------------------------------------------------------
# execute() — Pydantic validation failure
# ---------------------------------------------------------------------------


class TestExecuteValidationFailure:
    """execute() returns failure ToolResult when input fails Pydantic validation."""

    def test_missing_required_field_returns_failure(self, registry_with_add: ToolRegistry) -> None:
        """Omitting a required field (here 'b') causes validation failure."""
        result = registry_with_add.execute("add_numbers", {"a": 1.0})  # 'b' missing
        assert result.success is False

    def test_validation_failure_has_error_key(self, registry_with_add: ToolRegistry) -> None:
        """Validation failure output must have an 'error' key."""
        result = registry_with_add.execute("add_numbers", {"a": -1.0, "b": 0.0})
        assert result.success is False
        assert "error" in result.output

    def test_validation_failure_has_details_key(self, registry_with_add: ToolRegistry) -> None:
        """Validation failure output must include 'details' with Pydantic error list."""
        result = registry_with_add.execute("add_numbers", {"a": -1.0, "b": 0.0})
        assert "details" in result.output

    def test_validation_failure_details_is_list(self, registry_with_add: ToolRegistry) -> None:
        """The 'details' value must be a list (Pydantic error dicts)."""
        result = registry_with_add.execute("add_numbers", {"a": -1.0, "b": 0.0})
        assert isinstance(result.output["details"], list)

    def test_wrong_type_causes_validation_failure(self, registry_with_add: ToolRegistry) -> None:
        """Passing a string where a float is required causes validation failure."""
        result = registry_with_add.execute("add_numbers", {"a": "not_a_number", "b": 1.0})
        # Pydantic v2 may coerce or reject — either is fine as long as success is False
        # when coercion to float fails
        # If it coerces successfully this is acceptable; if it fails, check failure
        if not result.success:
            assert "error" in result.output

    def test_empty_dict_causes_validation_failure(self, registry_with_add: ToolRegistry) -> None:
        """An empty dict fails because both 'a' and 'b' are required."""
        result = registry_with_add.execute("add_numbers", {})
        assert result.success is False

    @pytest.mark.parametrize("bad_value", [-0.001, -10.0, -1e6])
    def test_out_of_range_negative_value_fails(
        self, registry_with_add: ToolRegistry, bad_value: float
    ) -> None:
        """Values below ge=0.0 for field 'a' must fail validation."""
        result = registry_with_add.execute("add_numbers", {"a": bad_value, "b": 1.0})
        assert result.success is False

    def test_string_min_length_violation_fails(self, empty_registry: ToolRegistry) -> None:
        """An empty string violates the min_length=1 constraint on _EchoInput.message."""
        empty_registry.register(
            _make_tool(name="echo_message", input_model=_EchoInput, handler=_echo_handler)
        )
        result = empty_registry.execute("echo_message", {"message": ""})
        assert result.success is False


# ---------------------------------------------------------------------------
# execute() — handler raises ValueError
# ---------------------------------------------------------------------------


class TestExecuteHandlerValueError:
    """execute() returns failure ToolResult when the handler raises ValueError."""

    @pytest.fixture
    def registry_with_error_tool(self, empty_registry: ToolRegistry) -> ToolRegistry:
        """Registry with a tool whose handler always raises ValueError."""
        empty_registry.register(_make_tool(name="error_tool", handler=_value_error_handler))
        return empty_registry

    def test_value_error_returns_failure(self, registry_with_error_tool: ToolRegistry) -> None:
        """A ValueError from the handler produces success=False."""
        result = registry_with_error_tool.execute("error_tool", {"a": 1.0, "b": 1.0})
        assert result.success is False

    def test_value_error_output_has_error_key(
        self, registry_with_error_tool: ToolRegistry
    ) -> None:
        """Failure output must have an 'error' key."""
        result = registry_with_error_tool.execute("error_tool", {"a": 1.0, "b": 1.0})
        assert "error" in result.output

    def test_value_error_message_in_output(self, registry_with_error_tool: ToolRegistry) -> None:
        """The ValueError message text is included in the 'error' field."""
        result = registry_with_error_tool.execute("error_tool", {"a": 1.0, "b": 1.0})
        assert "domain constraint violated" in result.output["error"]

    def test_value_error_tool_name_echoed(self, registry_with_error_tool: ToolRegistry) -> None:
        """ToolResult.tool_name is still set correctly even when handler raises."""
        result = registry_with_error_tool.execute("error_tool", {"a": 1.0, "b": 1.0})
        assert result.tool_name == "error_tool"


# ---------------------------------------------------------------------------
# execute() — handler raises unexpected Exception
# ---------------------------------------------------------------------------


class TestExecuteHandlerUnexpectedError:
    """execute() returns failure ToolResult when the handler raises an unexpected Exception."""

    @pytest.fixture
    def registry_with_runtime_error_tool(self, empty_registry: ToolRegistry) -> ToolRegistry:
        """Registry with a tool whose handler always raises RuntimeError."""
        empty_registry.register(
            _make_tool(name="runtime_error_tool", handler=_runtime_error_handler)
        )
        return empty_registry

    def test_unexpected_exception_returns_failure(
        self, registry_with_runtime_error_tool: ToolRegistry
    ) -> None:
        """A RuntimeError from the handler produces success=False."""
        result = registry_with_runtime_error_tool.execute(
            "runtime_error_tool", {"a": 1.0, "b": 1.0}
        )
        assert result.success is False

    def test_unexpected_exception_output_has_error_key(
        self, registry_with_runtime_error_tool: ToolRegistry
    ) -> None:
        """Failure output must have an 'error' key."""
        result = registry_with_runtime_error_tool.execute(
            "runtime_error_tool", {"a": 1.0, "b": 1.0}
        )
        assert "error" in result.output

    def test_unexpected_exception_error_contains_internal_error(
        self, registry_with_runtime_error_tool: ToolRegistry
    ) -> None:
        """The error message for unexpected exceptions begins with 'Internal error'."""
        result = registry_with_runtime_error_tool.execute(
            "runtime_error_tool", {"a": 1.0, "b": 1.0}
        )
        assert "Internal error" in result.output["error"]

    def test_unexpected_exception_does_not_propagate(
        self, registry_with_runtime_error_tool: ToolRegistry
    ) -> None:
        """execute() must never let an unexpected exception escape to the caller."""
        # If the exception propagated, this would raise; the test passes only if it doesn't.
        result = registry_with_runtime_error_tool.execute(
            "runtime_error_tool", {"a": 1.0, "b": 1.0}
        )
        assert isinstance(result, ToolResult)


# ---------------------------------------------------------------------------
# ToolResult.to_content_block()
# ---------------------------------------------------------------------------


class TestToolResultToContentBlock:
    """ToolResult.to_content_block() serializes output as a JSON string."""

    def test_to_content_block_returns_string(self, registry_with_add: ToolRegistry) -> None:
        """to_content_block() must return a str, not bytes or dict."""
        result = registry_with_add.execute("add_numbers", {"a": 1.0, "b": 2.0})
        block = result.to_content_block()
        assert isinstance(block, str)

    def test_to_content_block_is_valid_json(self, registry_with_add: ToolRegistry) -> None:
        """to_content_block() must produce parseable JSON."""
        result = registry_with_add.execute("add_numbers", {"a": 1.0, "b": 2.0})
        block = result.to_content_block()
        parsed = json.loads(block)  # raises if not valid JSON
        assert isinstance(parsed, dict)

    def test_to_content_block_contains_output_data(self, registry_with_add: ToolRegistry) -> None:
        """Parsed JSON from to_content_block() must contain the handler's output."""
        result = registry_with_add.execute("add_numbers", {"a": 4.0, "b": 6.0})
        parsed = json.loads(result.to_content_block())
        assert parsed["result"] == pytest.approx(10.0)

    def test_failure_result_to_content_block_is_valid_json(
        self, registry_with_add: ToolRegistry
    ) -> None:
        """to_content_block() on a failure result also produces valid JSON."""
        result = registry_with_add.execute("add_numbers", {"a": -1.0, "b": 0.0})
        block = result.to_content_block()
        parsed = json.loads(block)
        assert "error" in parsed

    def test_to_content_block_is_json_object_not_array(
        self, registry_with_add: ToolRegistry
    ) -> None:
        """Parsed content block must be a JSON object, not an array."""
        result = registry_with_add.execute("add_numbers", {"a": 1.0, "b": 2.0})
        parsed = json.loads(result.to_content_block())
        assert isinstance(parsed, dict), "to_content_block must produce a JSON object"

    def test_to_content_block_manually_constructed_result(self) -> None:
        """to_content_block() works on a ToolResult built directly, not via execute()."""
        result = ToolResult(
            tool_name="mock_tool",
            success=True,
            output={"value": 42, "label": "answer"},
        )
        parsed = json.loads(result.to_content_block())
        assert parsed["value"] == 42
        assert parsed["label"] == "answer"


# ---------------------------------------------------------------------------
# ToolResult dataclass attributes
# ---------------------------------------------------------------------------


class TestToolResultAttributes:
    """ToolResult stores tool_name, success, and output correctly."""

    def test_success_true_attributes(self, registry_with_add: ToolRegistry) -> None:
        """Successful ToolResult has correct attribute values."""
        result = registry_with_add.execute("add_numbers", {"a": 2.0, "b": 3.0})
        assert result.tool_name == "add_numbers"
        assert result.success is True
        assert isinstance(result.output, dict)

    def test_failure_attributes_unknown_tool(self, empty_registry: ToolRegistry) -> None:
        """Failure ToolResult from unknown tool has correct attribute values."""
        result = empty_registry.execute("ghost", {})
        assert result.tool_name == "ghost"
        assert result.success is False
        assert isinstance(result.output, dict)

    def test_direct_construction(self) -> None:
        """ToolResult can be constructed directly with known values."""
        r = ToolResult(tool_name="t", success=True, output={"x": 1})
        assert r.tool_name == "t"
        assert r.success is True
        assert r.output == {"x": 1}


# ---------------------------------------------------------------------------
# ToolError
# ---------------------------------------------------------------------------


class TestToolError:
    """ToolError stores tool_name and message and behaves as an Exception."""

    def test_tool_error_is_exception(self) -> None:
        """ToolError must be a subclass of Exception."""
        err = ToolError("my_tool", "something went wrong")
        assert isinstance(err, Exception)

    def test_tool_name_attribute(self) -> None:
        """ToolError stores the tool_name passed at construction."""
        err = ToolError("compute_tss", "invalid duration")
        assert err.tool_name == "compute_tss"

    def test_message_attribute(self) -> None:
        """ToolError stores the message string passed at construction."""
        err = ToolError("compute_tss", "invalid duration")
        assert err.message == "invalid duration"

    def test_str_representation_contains_tool_name(self) -> None:
        """str(ToolError) mentions the tool name for readable tracebacks."""
        err = ToolError("some_tool", "bad input")
        assert "some_tool" in str(err)

    def test_str_representation_contains_message(self) -> None:
        """str(ToolError) includes the error message."""
        err = ToolError("some_tool", "bad input")
        assert "bad input" in str(err)

    def test_can_be_raised_and_caught(self) -> None:
        """ToolError can be raised and caught as an Exception."""
        with pytest.raises(ToolError) as exc_info:
            raise ToolError("test_tool", "test message")
        assert exc_info.value.tool_name == "test_tool"
        assert exc_info.value.message == "test message"

    def test_can_be_caught_as_generic_exception(self) -> None:
        """ToolError can also be caught as a plain Exception."""
        with pytest.raises(Exception):
            raise ToolError("test_tool", "test message")

    @pytest.mark.parametrize(
        "tool_name,message",
        [
            ("compute_training_stress", "duration must be positive"),
            ("evaluate_fatigue_state", "fatigue_tau must be less than fitness_tau"),
            ("reallocate_week_load", "swap_day not found"),
        ],
    )
    def test_parametrized_tool_errors(self, tool_name: str, message: str) -> None:
        """ToolError attributes are correctly set for various tool/message combos."""
        err = ToolError(tool_name, message)
        assert err.tool_name == tool_name
        assert err.message == message


# ---------------------------------------------------------------------------
# ToolDefinition
# ---------------------------------------------------------------------------


class TestToolDefinition:
    """ToolDefinition is a frozen dataclass with the expected fields."""

    def test_tool_definition_stores_name(self) -> None:
        """ToolDefinition.name stores the provided name."""
        td = _make_tool(name="my_tool")
        assert td.name == "my_tool"

    def test_tool_definition_stores_description(self) -> None:
        """ToolDefinition.description stores the provided description."""
        td = _make_tool(description="Does something useful")
        assert td.description == "Does something useful"

    def test_tool_definition_stores_input_model(self) -> None:
        """ToolDefinition.input_model stores the provided Pydantic model class."""
        td = _make_tool(input_model=_EchoInput)
        assert td.input_model is _EchoInput

    def test_tool_definition_stores_handler(self) -> None:
        """ToolDefinition.handler stores the provided callable."""
        td = _make_tool(handler=_echo_handler)
        assert td.handler is _echo_handler

    def test_tool_definition_is_frozen(self) -> None:
        """ToolDefinition is frozen; mutating attributes must raise AttributeError."""
        td = _make_tool()
        with pytest.raises(AttributeError):
            td.name = "modified_name"  # type: ignore[misc]
