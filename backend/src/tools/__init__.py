"""Tool layer — wraps deterministic models as Claude-callable tools.

Each tool has a JSON schema (derived from Pydantic), a handler function
that calls the deterministic engine, and is registered in the ToolRegistry
for dispatch during the agent loop.
"""

from src.tools.registry import ToolDefinition, ToolError, ToolRegistry, ToolResult

__all__ = ["ToolDefinition", "ToolError", "ToolRegistry", "ToolResult"]
