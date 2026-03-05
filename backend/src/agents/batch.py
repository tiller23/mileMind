"""Batch transport for 50% cost savings on evaluation harness runs.

Implements the round-batching pattern: multiple agent loops run concurrently,
and each round of API calls (one per active agent) is submitted as a single
Anthropic Batch API request. This is transparent to the agent loops — they
call ``create_message`` as normal, which blocks until the batch resolves.

Note: Batch mode is only for non-interactive workloads (evaluation harness).
The Batch API processes asynchronously and may take minutes per round.

Usage:
    coordinator = BatchCoordinator(api_key="sk-...")
    planner_transport = coordinator.register_transport("persona:planner")
    reviewer_transport = coordinator.register_transport("persona:reviewer")
    # Pass transports to agents, run concurrently via asyncio.gather
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

# Terminal batch statuses that should stop polling
_TERMINAL_STATUSES = {"ended", "canceled", "expired"}


class BatchTransport:
    """Transport that queues requests for batch submission.

    Each ``create_message`` call stores the request and returns an awaitable
    that blocks until the ``BatchCoordinator`` submits the batch and distributes
    results. Conforms to the ``MessageTransport`` protocol.

    Args:
        transport_id: Unique ID for this transport (used in batch custom_id).
        coordinator: The BatchCoordinator managing this transport.
    """

    def __init__(self, transport_id: str, coordinator: BatchCoordinator) -> None:
        self._transport_id = transport_id
        self._coordinator = coordinator
        self._call_counter = 0

    @property
    def transport_id(self) -> str:
        """Unique identifier for this transport.

        Returns:
            The transport ID string.
        """
        return self._transport_id

    async def create_message(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> Any:
        """Queue a request and wait for the batch result.

        Args:
            model: Claude model ID.
            max_tokens: Maximum response tokens.
            system: System prompt.
            tools: Tool definitions.
            messages: Conversation messages.

        Returns:
            API response (same shape as direct API call).
        """
        self._call_counter += 1
        custom_id = f"{self._transport_id}:{self._call_counter}"

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()

        self._coordinator.enqueue(
            custom_id=custom_id,
            params={
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "tools": tools,
                "messages": messages,
            },
            future=future,
        )

        return await future


class BatchCoordinator:
    """Coordinates batch submission across concurrent agent loops.

    Manages a set of ``BatchTransport`` instances. When all active transports
    have a pending request, submits them as a single Anthropic Batch API call,
    polls for completion, and resolves each transport's future with its result.

    Args:
        api_key: Anthropic API key.
        poll_interval_seconds: How often to poll for batch completion.
        max_poll_seconds: Maximum time to poll before raising TimeoutError.
    """

    def __init__(
        self,
        api_key: str,
        poll_interval_seconds: float = 5.0,
        max_poll_seconds: float = 7200.0,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._poll_interval = poll_interval_seconds
        self._max_poll_seconds = max_poll_seconds

        # Active transports that haven't finished yet
        self._active_transports: set[str] = set()
        # Pending requests: custom_id -> (params, future)
        self._pending: dict[str, tuple[dict[str, Any], asyncio.Future[Any]]] = {}
        # Transport IDs that have enqueued in the current round
        self._enqueued_transport_ids: set[str] = set()
        # Event signaling that a batch round is ready
        self._round_ready = asyncio.Event()
        # Background task that processes batch rounds
        self._processor_task: asyncio.Task[None] | None = None
        # Event signaling coordinator shutdown
        self._shutdown = asyncio.Event()

    def register_transport(self, transport_id: str) -> BatchTransport:
        """Create and register a new BatchTransport.

        Args:
            transport_id: Unique ID for the transport.

        Returns:
            A new BatchTransport instance bound to this coordinator.
        """
        self._active_transports.add(transport_id)
        logger.debug("Registered transport: %s (active=%d)", transport_id, len(self._active_transports))
        return BatchTransport(transport_id, self)

    def deregister_transport(self, transport_id: str) -> None:
        """Mark a transport as finished (agent loop completed).

        Args:
            transport_id: The transport to deregister.
        """
        self._active_transports.discard(transport_id)
        self._enqueued_transport_ids.discard(transport_id)
        logger.debug("Deregistered transport: %s (active=%d)", transport_id, len(self._active_transports))
        # Check if remaining active transports are all enqueued
        self._check_round_ready()

    def enqueue(
        self,
        custom_id: str,
        params: dict[str, Any],
        future: asyncio.Future[Any],
    ) -> None:
        """Add a request to the pending batch.

        Called by ``BatchTransport.create_message``. The future will be resolved
        when the batch completes.

        Args:
            custom_id: Unique request ID within the batch.
            params: API request parameters.
            future: Future to resolve with the API response.
        """
        transport_id = custom_id.rsplit(":", 1)[0]
        self._pending[custom_id] = (params, future)
        self._enqueued_transport_ids.add(transport_id)
        logger.debug(
            "Enqueued %s (pending=%d, active=%d, enqueued=%d)",
            custom_id, len(self._pending),
            len(self._active_transports), len(self._enqueued_transport_ids),
        )
        self._check_round_ready()

    def _check_round_ready(self) -> None:
        """Check if all active transports have enqueued and signal if so."""
        if (
            self._active_transports
            and self._enqueued_transport_ids >= self._active_transports
            and self._pending
        ):
            logger.info(
                "Batch round ready: %d requests from %d transports",
                len(self._pending), len(self._active_transports),
            )
            self._round_ready.set()

    async def start(self) -> None:
        """Start the background batch processor.

        Must be called before any transports enqueue requests.
        """
        self._processor_task = asyncio.create_task(self._process_rounds())

    async def stop(self) -> None:
        """Signal shutdown and wait for the processor to finish."""
        self._shutdown.set()
        self._round_ready.set()  # Unblock if waiting
        if self._processor_task:
            await self._processor_task

    async def _process_rounds(self) -> None:
        """Background loop that submits batches as rounds become ready.

        Exits when shutdown is signaled and no pending requests remain.
        The round_ready event is set both by enqueue (when all active
        transports have a request) and by stop() (to unblock on shutdown).
        """
        while not self._shutdown.is_set():
            await self._round_ready.wait()
            self._round_ready.clear()

            if self._shutdown.is_set() and not self._pending:
                break

            if not self._pending:
                continue

            await self._submit_round()

    async def _submit_round(self) -> None:
        """Submit all pending requests as a batch and resolve futures."""
        # Snapshot and clear pending state atomically (no await between)
        round_requests = dict(self._pending)
        self._pending.clear()
        self._enqueued_transport_ids.clear()

        logger.info("Submitting batch with %d requests", len(round_requests))

        # Build batch requests
        batch_requests = []
        for custom_id, (params, _future) in round_requests.items():
            batch_requests.append({
                "custom_id": custom_id,
                "params": {
                    "model": params["model"],
                    "max_tokens": params["max_tokens"],
                    "system": params["system"],
                    "tools": params["tools"],
                    "messages": params["messages"],
                },
            })

        try:
            batch = await self._client.messages.batches.create(
                requests=batch_requests,
            )
            logger.info("Batch created: id=%s, status=%s", batch.id, batch.processing_status)

            results = await self._poll_until_complete(batch.id)

            # Distribute results to futures
            for custom_id, (_params, future) in round_requests.items():
                if custom_id in results:
                    result = results[custom_id]
                    if result.result.type == "succeeded":
                        future.set_result(result.result.message)
                    else:
                        error_msg = (
                            f"Batch request {custom_id} {result.result.type}"
                        )
                        if hasattr(result.result, "error") and result.result.error:
                            error_msg += f": {result.result.error.message}"
                        future.set_exception(RuntimeError(error_msg))
                else:
                    future.set_exception(
                        RuntimeError(f"Batch result missing for {custom_id}")
                    )

        except Exception as e:
            logger.error("Batch submission failed: %s", e, exc_info=True)
            for _custom_id, (_params, future) in round_requests.items():
                if not future.done():
                    future.set_exception(e)

    async def _poll_until_complete(
        self,
        batch_id: str,
    ) -> dict[str, Any]:
        """Poll a batch until it reaches a terminal status.

        Terminal statuses: ``ended``, ``canceled``, ``expired``.

        Args:
            batch_id: The batch ID to poll.

        Returns:
            Dict mapping custom_id to batch result object.

        Raises:
            TimeoutError: If polling exceeds max_poll_seconds.
            RuntimeError: If batch reaches canceled or expired status.
        """
        elapsed = 0.0
        while True:
            batch = await self._client.messages.batches.retrieve(batch_id)
            logger.debug(
                "Batch %s: status=%s (%.0fs elapsed)",
                batch_id, batch.processing_status, elapsed,
            )

            if batch.processing_status in _TERMINAL_STATUSES:
                if batch.processing_status != "ended":
                    raise RuntimeError(
                        f"Batch {batch_id} terminated with status: "
                        f"{batch.processing_status}"
                    )
                break

            elapsed += self._poll_interval
            if elapsed >= self._max_poll_seconds:
                raise TimeoutError(
                    f"Batch {batch_id} did not complete within "
                    f"{self._max_poll_seconds:.0f}s"
                )

            await asyncio.sleep(self._poll_interval)

        # Collect results
        results: dict[str, Any] = {}
        async for result in self._client.messages.batches.results(batch_id):
            results[result.custom_id] = result

        logger.info("Batch %s complete: %d results", batch_id, len(results))
        return results
