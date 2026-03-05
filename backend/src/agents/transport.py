"""Transport abstraction for Claude API calls.

Decouples agent logic from the API transport, enabling:
- Synchronous single-message calls (default, current behavior)
- Batch API calls (50% cost savings, Phase 4+)
- Mock transports for testing
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import anthropic


@runtime_checkable
class MessageTransport(Protocol):
    """Protocol for sending messages to a Claude model.

    Implementations must accept the same keyword arguments as
    ``anthropic.AsyncAnthropic().messages.create()``.
    """

    async def create_message(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> Any:
        """Send a message and return the API response."""
        ...


class AnthropicTransport:
    """Default transport wrapping the Anthropic async client.

    Args:
        api_key: Anthropic API key.
    """

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def create_message(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> Any:
        """Delegate to the Anthropic messages API."""
        return await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )
