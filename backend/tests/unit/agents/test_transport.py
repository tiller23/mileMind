"""Tests for the MessageTransport protocol and AnthropicTransport."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.batch import BatchTransport
from src.agents.transport import AnthropicTransport, MessageTransport


class TestMessageTransportProtocol:
    """Tests for the MessageTransport protocol."""

    def test_anthropic_transport_satisfies_protocol(self) -> None:
        with patch("src.agents.transport.anthropic"):
            transport = AnthropicTransport(api_key="test-key")
        assert isinstance(transport, MessageTransport)

    def test_custom_transport_satisfies_protocol(self) -> None:
        """A class with create_message satisfies MessageTransport."""

        class CustomTransport:
            async def create_message(
                self, *, model: str, max_tokens: int, system: str,
                tools: list, messages: list,
            ) -> dict:
                return {}

        assert isinstance(CustomTransport(), MessageTransport)

    def test_batch_transport_satisfies_protocol(self) -> None:
        """BatchTransport satisfies MessageTransport."""
        transport = BatchTransport("test", MagicMock())
        assert isinstance(transport, MessageTransport)

    def test_non_transport_does_not_satisfy(self) -> None:
        """A class without create_message does not satisfy the protocol."""

        class NotATransport:
            async def send(self) -> None:
                pass

        assert not isinstance(NotATransport(), MessageTransport)


class TestAnthropicTransport:
    """Tests for the default AnthropicTransport wrapper."""

    @pytest.mark.asyncio
    async def test_delegates_to_client(self) -> None:
        """create_message should delegate to client.messages.create."""
        with patch("src.agents.transport.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value="response")
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            transport = AnthropicTransport(api_key="test-key")
            result = await transport.create_message(
                model="test-model",
                max_tokens=1024,
                system="prompt",
                tools=[],
                messages=[],
            )

            assert result == "response"
            mock_client.messages.create.assert_called_once_with(
                model="test-model",
                max_tokens=1024,
                system="prompt",
                tools=[],
                messages=[],
            )
