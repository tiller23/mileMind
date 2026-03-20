"""Tool registry and execution layer.

Provides the dispatch system that the Claude API tool-use loop calls into.
Each tool is registered with a name, description, Pydantic input model,
and handler function. The registry:

1. Generates Anthropic-format tool definitions from Pydantic schemas
2. Validates incoming tool call inputs
3. Dispatches to the correct handler
4. Serializes outputs as JSON
5. Returns structured errors (never crashes)
"""

from __future__ import annotations

import json
import logging
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """Raised when a tool execution fails in a structured way."""

    def __init__(self, tool_name: str, message: str) -> None:
        self.tool_name = tool_name
        self.message = message
        super().__init__(f"Tool '{tool_name}' error: {message}")


@dataclass(frozen=True)
class ToolDefinition:
    """A registered tool with its schema, description, and handler.

    Attributes:
        name: Tool name matching the Anthropic tool-use API (snake_case).
        description: Human-readable description for the LLM system prompt.
        input_model: Pydantic model class for input validation and schema generation.
        handler: Callable that takes validated input dict and returns output dict.
    """

    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class ToolResult:
    """Result of a tool execution.

    Attributes:
        tool_name: Name of the tool that was called.
        success: Whether the execution succeeded.
        output: The tool's output (on success) or error details (on failure).
    """

    tool_name: str
    success: bool
    output: dict[str, Any]

    def to_content_block(self) -> str:
        """Serialize to JSON string for the Anthropic API tool_result content."""
        return json.dumps(self.output)


class ToolRegistry:
    """Registry of callable tools for the Claude API tool-use loop.

    Usage:
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="compute_training_stress",
            description="Compute TSS for a workout",
            input_model=ComputeTrainingStressInput,
            handler=compute_training_stress_handler,
        ))

        # Get Anthropic-format definitions for the API call
        tool_defs = registry.get_anthropic_tools()

        # Execute a tool call from the API response
        result = registry.execute("compute_training_stress", {"duration_minutes": 60, ...})
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._anthropic_tools_cache: list[dict[str, Any]] | None = None

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition.

        Args:
            tool: The tool to register.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool
        self._anthropic_tools_cache = None  # Invalidate cache on registration
        logger.info("Registered tool: %s", tool.name)

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name.

        Args:
            name: Tool name.

        Returns:
            The ToolDefinition, or None if not found.
        """
        return self._tools.get(name)

    @property
    def tool_names(self) -> list[str]:
        """List of all registered tool names."""
        return list(self._tools.keys())

    def get_anthropic_tools(self) -> list[dict[str, Any]]:
        """Generate tool definitions in Anthropic API format.

        Returns a list of dicts matching the Anthropic tool-use schema:
        [{"name": ..., "description": ..., "input_schema": {...}}, ...]

        The result is cached and invalidated on new tool registration.

        Returns:
            List of Anthropic-format tool definitions.
        """
        if self._anthropic_tools_cache is not None:
            return self._anthropic_tools_cache

        tools = []
        for tool in self._tools.values():
            schema = tool.input_model.model_json_schema()
            # Remove Pydantic metadata keys that Anthropic doesn't need
            schema.pop("title", None)
            # Also strip titles from nested $defs (enum/model references)
            for definition in schema.get("$defs", {}).values():
                definition.pop("title", None)
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": schema,
            })
        self._anthropic_tools_cache = tools
        return tools

    def execute(self, tool_name: str, input_data: dict[str, Any]) -> ToolResult:
        """Execute a tool call with validation and error handling.

        Args:
            tool_name: Name of the tool to execute.
            input_data: Raw input dict from the Claude API tool_use block.

        Returns:
            ToolResult with success/failure status and output.
        """
        # Check tool exists
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output={"error": f"Unknown tool: '{tool_name}'"},
            )

        # Validate input
        try:
            validated = tool.input_model.model_validate(input_data)
        except ValidationError as e:
            logger.warning("Tool '%s' input validation failed: %s", tool_name, e)
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output={
                    "error": "Input validation failed",
                    "details": e.errors(),
                },
            )

        # Execute handler
        try:
            output = tool.handler(validated.model_dump())
            return ToolResult(
                tool_name=tool_name,
                success=True,
                output=output,
            )
        except (ValueError, TypeError) as e:
            logger.warning("Tool '%s' execution failed: %s", tool_name, e)
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output={"error": str(e)},
            )
        except Exception as e:
            logger.error(
                "Tool '%s' unexpected error: %s\n%s",
                tool_name, e, traceback.format_exc(),
            )
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output={"error": f"Internal error: {type(e).__name__}: {e}"},
            )
