"""Tests for the BatchTransport and BatchCoordinator."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.batch import BatchCoordinator, BatchTransport
from src.agents.transport import MessageTransport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeMessage:
    """Minimal fake API response."""
    custom_id: str = ""
    content: list[dict[str, Any]] | None = None
    stop_reason: str = "end_turn"

    class usage:
        input_tokens: int = 100
        output_tokens: int = 50


@dataclass
class FakeBatchResult:
    """Fake individual result from a batch."""
    custom_id: str

    @dataclass
    class _Result:
        type: str = "succeeded"
        message: Any = None

    result: _Result | None = None


def _make_batch_result(custom_id: str, message: Any = None) -> FakeBatchResult:
    """Build a fake batch result with a succeeded message."""
    r = FakeBatchResult(custom_id=custom_id)
    r.result = FakeBatchResult._Result(type="succeeded", message=message or FakeMessage())
    return r


@dataclass
class FakeBatch:
    """Fake batch object from create/retrieve."""
    id: str = "batch_123"
    processing_status: str = "ended"


# ---------------------------------------------------------------------------
# BatchTransport protocol conformance
# ---------------------------------------------------------------------------


class TestBatchTransportProtocol:
    """Verify BatchTransport satisfies MessageTransport protocol."""

    def test_satisfies_message_transport(self) -> None:
        """BatchTransport should satisfy the MessageTransport protocol."""
        coordinator = MagicMock()
        transport = BatchTransport("test", coordinator)
        assert isinstance(transport, MessageTransport)

    def test_transport_id(self) -> None:
        """transport_id property returns the configured ID."""
        coordinator = MagicMock()
        transport = BatchTransport("my-transport", coordinator)
        assert transport.transport_id == "my-transport"


# ---------------------------------------------------------------------------
# BatchTransport create_message
# ---------------------------------------------------------------------------


class TestBatchTransportCreateMessage:
    """Tests for BatchTransport.create_message."""

    @pytest.mark.asyncio
    async def test_enqueues_and_awaits_future(self) -> None:
        """create_message enqueues with coordinator and awaits the future."""
        coordinator = MagicMock()

        # Capture the future so we can resolve it
        captured_future = None
        def capture_enqueue(custom_id, params, future):
            nonlocal captured_future
            captured_future = future
            # Resolve immediately for the test
            future.set_result(FakeMessage())

        coordinator.enqueue = capture_enqueue

        transport = BatchTransport("test", coordinator)
        result = await transport.create_message(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system="prompt",
            tools=[],
            messages=[{"role": "user", "content": "hello"}],
        )

        assert isinstance(result, FakeMessage)
        assert captured_future is not None

    @pytest.mark.asyncio
    async def test_increments_call_counter(self) -> None:
        """Each call gets a unique custom_id with incrementing counter."""
        coordinator = MagicMock()
        custom_ids = []

        def capture_enqueue(custom_id, params, future):
            custom_ids.append(custom_id)
            future.set_result(FakeMessage())

        coordinator.enqueue = capture_enqueue

        transport = BatchTransport("persona1:planner", coordinator)
        await transport.create_message(
            model="m", max_tokens=1, system="s", tools=[], messages=[],
        )
        await transport.create_message(
            model="m", max_tokens=1, system="s", tools=[], messages=[],
        )

        assert custom_ids == ["persona1:planner:1", "persona1:planner:2"]

    @pytest.mark.asyncio
    async def test_passes_system_as_plain_string(self) -> None:
        """System prompt is passed as a plain string (same as AnthropicTransport)."""
        coordinator = MagicMock()
        captured_params = None

        def capture_enqueue(custom_id, params, future):
            nonlocal captured_params
            captured_params = params
            future.set_result(FakeMessage())

        coordinator.enqueue = capture_enqueue

        transport = BatchTransport("test", coordinator)
        await transport.create_message(
            model="m", max_tokens=1, system="My prompt", tools=[], messages=[],
        )

        assert captured_params is not None
        assert captured_params["system"] == "My prompt"


# ---------------------------------------------------------------------------
# BatchCoordinator registration
# ---------------------------------------------------------------------------


class TestBatchCoordinatorRegistration:
    """Tests for transport registration and deregistration."""

    def test_register_returns_batch_transport(self) -> None:
        """register_transport returns a BatchTransport instance."""
        with patch("src.agents.batch.anthropic"):
            coordinator = BatchCoordinator(api_key="test-key")
        transport = coordinator.register_transport("test")
        assert isinstance(transport, BatchTransport)
        assert transport.transport_id == "test"

    def test_register_adds_to_active(self) -> None:
        """Registered transports are tracked in active set."""
        with patch("src.agents.batch.anthropic"):
            coordinator = BatchCoordinator(api_key="test-key")
        coordinator.register_transport("t1")
        coordinator.register_transport("t2")
        assert "t1" in coordinator._active_transports
        assert "t2" in coordinator._active_transports

    def test_deregister_removes_from_active(self) -> None:
        """Deregistered transports are removed from active set."""
        with patch("src.agents.batch.anthropic"):
            coordinator = BatchCoordinator(api_key="test-key")
        coordinator.register_transport("t1")
        coordinator.deregister_transport("t1")
        assert "t1" not in coordinator._active_transports

    def test_deregister_nonexistent_is_safe(self) -> None:
        """Deregistering a non-existent transport does not raise."""
        with patch("src.agents.batch.anthropic"):
            coordinator = BatchCoordinator(api_key="test-key")
        coordinator.deregister_transport("ghost")


# ---------------------------------------------------------------------------
# BatchCoordinator enqueue and round detection
# ---------------------------------------------------------------------------


class TestBatchCoordinatorEnqueue:
    """Tests for the enqueue and round-ready detection."""

    def test_enqueue_stores_pending(self) -> None:
        """Enqueue adds to pending dict."""
        with patch("src.agents.batch.anthropic"):
            coordinator = BatchCoordinator(api_key="test-key")
        coordinator.register_transport("t1")

        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        coordinator.enqueue("t1:1", {"model": "m"}, future)

        assert "t1:1" in coordinator._pending

    def test_round_ready_when_all_active_enqueued(self) -> None:
        """Round ready event is set when all active transports have enqueued."""
        with patch("src.agents.batch.anthropic"):
            coordinator = BatchCoordinator(api_key="test-key")
        coordinator.register_transport("t1")
        coordinator.register_transport("t2")

        f1: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        f2: asyncio.Future[Any] = asyncio.get_event_loop().create_future()

        coordinator.enqueue("t1:1", {"model": "m"}, f1)
        assert not coordinator._round_ready.is_set()

        coordinator.enqueue("t2:1", {"model": "m"}, f2)
        assert coordinator._round_ready.is_set()

    def test_round_not_ready_with_partial_enqueue(self) -> None:
        """Round is not ready if only some transports have enqueued."""
        with patch("src.agents.batch.anthropic"):
            coordinator = BatchCoordinator(api_key="test-key")
        coordinator.register_transport("t1")
        coordinator.register_transport("t2")
        coordinator.register_transport("t3")

        f1: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        coordinator.enqueue("t1:1", {"model": "m"}, f1)

        assert not coordinator._round_ready.is_set()

    def test_deregister_triggers_round_ready(self) -> None:
        """Deregistering a transport can make remaining transports ready."""
        with patch("src.agents.batch.anthropic"):
            coordinator = BatchCoordinator(api_key="test-key")
        coordinator.register_transport("t1")
        coordinator.register_transport("t2")

        f1: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        coordinator.enqueue("t1:1", {"model": "m"}, f1)
        assert not coordinator._round_ready.is_set()

        # t2 finishes without enqueuing — deregister it
        coordinator.deregister_transport("t2")
        assert coordinator._round_ready.is_set()


# ---------------------------------------------------------------------------
# BatchCoordinator submit round (mocked API)
# ---------------------------------------------------------------------------


class TestBatchCoordinatorSubmitRound:
    """Tests for batch submission and result distribution."""

    @pytest.mark.asyncio
    async def test_submit_round_resolves_futures(self) -> None:
        """_submit_round resolves all pending futures with batch results."""
        with patch("src.agents.batch.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            coordinator = BatchCoordinator(api_key="test-key")

        # Set up mock batch create
        mock_client.messages.batches.create = AsyncMock(
            return_value=FakeBatch(id="batch_1"),
        )
        mock_client.messages.batches.retrieve = AsyncMock(
            return_value=FakeBatch(id="batch_1", processing_status="ended"),
        )

        msg_a = FakeMessage(custom_id="t1:1")
        msg_b = FakeMessage(custom_id="t2:1")

        # Mock async iterator for results
        async def mock_results(batch_id):
            yield _make_batch_result("t1:1", msg_a)
            yield _make_batch_result("t2:1", msg_b)

        mock_client.messages.batches.results = mock_results

        # Enqueue two requests
        coordinator.register_transport("t1")
        coordinator.register_transport("t2")

        f1: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        f2: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        coordinator.enqueue("t1:1", {"model": "m", "max_tokens": 1, "system": "s", "tools": [], "messages": []}, f1)
        coordinator.enqueue("t2:1", {"model": "m", "max_tokens": 1, "system": "s", "tools": [], "messages": []}, f2)

        await coordinator._submit_round()

        assert f1.done()
        assert f2.done()
        assert f1.result() is msg_a
        assert f2.result() is msg_b

    @pytest.mark.asyncio
    async def test_submit_round_handles_failed_request(self) -> None:
        """Failed batch results set exceptions on the future."""
        with patch("src.agents.batch.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            coordinator = BatchCoordinator(api_key="test-key")

        mock_client.messages.batches.create = AsyncMock(
            return_value=FakeBatch(id="batch_1"),
        )
        mock_client.messages.batches.retrieve = AsyncMock(
            return_value=FakeBatch(id="batch_1", processing_status="ended"),
        )

        # Return a failed result
        failed = FakeBatchResult(custom_id="t1:1")
        failed.result = FakeBatchResult._Result(type="errored", message=None)

        async def mock_results(batch_id):
            yield failed

        mock_client.messages.batches.results = mock_results

        coordinator.register_transport("t1")
        f1: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        coordinator.enqueue("t1:1", {"model": "m", "max_tokens": 1, "system": "s", "tools": [], "messages": []}, f1)

        await coordinator._submit_round()

        assert f1.done()
        with pytest.raises(RuntimeError, match="errored"):
            f1.result()

    @pytest.mark.asyncio
    async def test_submit_round_handles_missing_result(self) -> None:
        """Missing batch result sets exception on the future."""
        with patch("src.agents.batch.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            coordinator = BatchCoordinator(api_key="test-key")

        mock_client.messages.batches.create = AsyncMock(
            return_value=FakeBatch(id="batch_1"),
        )
        mock_client.messages.batches.retrieve = AsyncMock(
            return_value=FakeBatch(id="batch_1", processing_status="ended"),
        )

        # Return empty results (nothing for our request)
        async def mock_results(batch_id):
            return
            yield  # Make it an async generator

        mock_client.messages.batches.results = mock_results

        coordinator.register_transport("t1")
        f1: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        coordinator.enqueue("t1:1", {"model": "m", "max_tokens": 1, "system": "s", "tools": [], "messages": []}, f1)

        await coordinator._submit_round()

        assert f1.done()
        with pytest.raises(RuntimeError, match="missing"):
            f1.result()

    @pytest.mark.asyncio
    async def test_batch_create_failure_rejects_all_futures(self) -> None:
        """If batch creation fails, all pending futures get the exception."""
        with patch("src.agents.batch.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            coordinator = BatchCoordinator(api_key="test-key")

        mock_client.messages.batches.create = AsyncMock(
            side_effect=RuntimeError("API error"),
        )

        coordinator.register_transport("t1")
        coordinator.register_transport("t2")

        f1: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        f2: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        coordinator.enqueue("t1:1", {"model": "m", "max_tokens": 1, "system": "s", "tools": [], "messages": []}, f1)
        coordinator.enqueue("t2:1", {"model": "m", "max_tokens": 1, "system": "s", "tools": [], "messages": []}, f2)

        await coordinator._submit_round()

        assert f1.done()
        assert f2.done()
        with pytest.raises(RuntimeError, match="API error"):
            f1.result()
        with pytest.raises(RuntimeError, match="API error"):
            f2.result()


# ---------------------------------------------------------------------------
# BatchCoordinator polling
# ---------------------------------------------------------------------------


class TestBatchCoordinatorPolling:
    """Tests for batch status polling."""

    @pytest.mark.asyncio
    async def test_polls_until_ended(self) -> None:
        """_poll_until_complete retries until status is 'ended'."""
        with patch("src.agents.batch.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            coordinator = BatchCoordinator(api_key="test-key", poll_interval_seconds=0.01)

        call_count = 0
        async def mock_retrieve(batch_id):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return FakeBatch(id=batch_id, processing_status="in_progress")
            return FakeBatch(id=batch_id, processing_status="ended")

        mock_client.messages.batches.retrieve = mock_retrieve

        async def mock_results(batch_id):
            return
            yield

        mock_client.messages.batches.results = mock_results

        results = await coordinator._poll_until_complete("batch_1")
        assert call_count == 3
        assert results == {}

    @pytest.mark.asyncio
    async def test_raises_on_canceled_status(self) -> None:
        """_poll_until_complete raises RuntimeError if batch is canceled."""
        with patch("src.agents.batch.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            coordinator = BatchCoordinator(api_key="test-key", poll_interval_seconds=0.01)

        mock_client.messages.batches.retrieve = AsyncMock(
            return_value=FakeBatch(id="batch_1", processing_status="canceled"),
        )

        with pytest.raises(RuntimeError, match="canceled"):
            await coordinator._poll_until_complete("batch_1")

    @pytest.mark.asyncio
    async def test_raises_on_poll_timeout(self) -> None:
        """_poll_until_complete raises TimeoutError if max_poll_seconds exceeded."""
        with patch("src.agents.batch.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            coordinator = BatchCoordinator(
                api_key="test-key",
                poll_interval_seconds=0.01,
                max_poll_seconds=0.02,
            )

        mock_client.messages.batches.retrieve = AsyncMock(
            return_value=FakeBatch(id="batch_1", processing_status="in_progress"),
        )

        with pytest.raises(TimeoutError, match="did not complete"):
            await coordinator._poll_until_complete("batch_1")


# ---------------------------------------------------------------------------
# BatchCoordinator start/stop lifecycle
# ---------------------------------------------------------------------------


class TestBatchCoordinatorLifecycle:
    """Tests for coordinator start and stop."""

    @pytest.mark.asyncio
    async def test_start_and_stop(self) -> None:
        """Coordinator can start and stop cleanly with no pending work."""
        with patch("src.agents.batch.anthropic"):
            coordinator = BatchCoordinator(api_key="test-key")

        await coordinator.start()
        await coordinator.stop()

    @pytest.mark.asyncio
    async def test_full_round_via_lifecycle(self) -> None:
        """End-to-end: register, enqueue, batch resolves, futures complete."""
        with patch("src.agents.batch.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client

            coordinator = BatchCoordinator(api_key="test-key", poll_interval_seconds=0.01)

        msg = FakeMessage()

        mock_client.messages.batches.create = AsyncMock(
            return_value=FakeBatch(id="batch_1"),
        )
        mock_client.messages.batches.retrieve = AsyncMock(
            return_value=FakeBatch(id="batch_1", processing_status="ended"),
        )

        async def mock_results(batch_id):
            yield _make_batch_result("t1:1", msg)

        mock_client.messages.batches.results = mock_results

        await coordinator.start()

        transport = coordinator.register_transport("t1")

        # Launch create_message in a task (it will block on the future)
        result_task = asyncio.create_task(
            transport.create_message(
                model="m", max_tokens=1, system="s", tools=[], messages=[],
            )
        )

        # Wait for the round to process
        result = await asyncio.wait_for(result_task, timeout=5.0)
        assert result is msg

        coordinator.deregister_transport("t1")
        await coordinator.stop()
