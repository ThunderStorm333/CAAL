"""
GeminiLLM Plugin for LiveKit Agents
====================================

OpenAI-compatible LLM integration for Gemini via geminicli2api proxy.

This plugin provides an LLM interface that uses the geminicli2api proxy
to access Gemini models using your Google AI Pro subscription via OAuth.

Features:
    - Uses geminicli2api proxy (OpenAI-compatible API)
    - Supports Gemini 3 Flash for low-latency voice responses
    - Configuration accessible via properties for llm_node override
    - Works with Google AI Pro subscription (no API key costs)

Example:
    >>> from caal import GeminiLLM
    >>> from livekit.agents import AgentSession
    >>>
    >>> llm = GeminiLLM(
    ...     model="gemini-3-flash",
    ...     base_url="http://geminicli2api:8888/v1",
    ...     api_key="your-proxy-password",
    ... )
    >>>
    >>> session = AgentSession(stt=..., llm=llm, tts=...)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from livekit.agents import llm
from livekit.agents.llm import ChatContext, ChatChunk, ChoiceDelta
from livekit.agents.llm.tool_context import FunctionTool, RawFunctionTool
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions, NOT_GIVEN, NotGivenOr

__all__ = ["GeminiLLM"]

logger = logging.getLogger(__name__)


class GeminiLLM(llm.LLM):
    """
    LiveKit LLM plugin for Gemini via geminicli2api proxy.

    This plugin is designed to be used with a VoiceAssistant that overrides
    the llm_node method. The actual LLM calls are handled by gemini_llm_node(),
    which supports MCP tool discovery and execution.

    The GeminiLLM class:
    1. Satisfies LiveKit's llm.LLM interface (prevents "no LLM" errors)
    2. Stores configuration accessible via properties
    3. Provides model/provider info for logging and metrics

    Args:
        model: Gemini model name (e.g., "gemini-3-flash", "gemini-3-pro")
        base_url: geminicli2api proxy URL (e.g., "http://geminicli2api:8888/v1")
        api_key: Proxy password (matches GEMINI_AUTH_PASSWORD)
        temperature: Sampling temperature (0.0-2.0)

    Example:
        >>> llm = GeminiLLM(
        ...     model="gemini-3-flash",
        ...     base_url="http://geminicli2api:8888/v1",
        ...     api_key="caal-secret",
        ... )
        >>> session = AgentSession(llm=llm, ...)
    """

    def __init__(
        self,
        *,
        model: str = "gemini-3-flash",
        base_url: str = "http://localhost:8888/v1",
        api_key: str = "caal-secret",
        temperature: float = 0.7,
    ) -> None:
        super().__init__()
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._temperature = temperature

        logger.debug(f"GeminiLLM initialized: {model} @ {base_url}")

    # === Required LLM interface properties ===

    @property
    def model(self) -> str:
        """Model name for logging and metrics."""
        return self._model

    @property
    def provider(self) -> str:
        """Provider name for logging and metrics."""
        return "gemini"

    # === Configuration accessors for llm_node ===

    @property
    def base_url(self) -> str:
        """geminicli2api proxy URL."""
        return self._base_url

    @property
    def api_key(self) -> str:
        """Proxy password."""
        return self._api_key

    @property
    def temperature(self) -> float:
        """Sampling temperature."""
        return self._temperature

    # === Required LLM interface method ===

    def chat(
        self,
        *,
        chat_ctx: ChatContext,
        tools: list[FunctionTool | RawFunctionTool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[llm.ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> llm.LLMStream:
        """
        Create an LLM stream for chat completion.

        Note: When using VoiceAssistant with llm_node override, this method
        is bypassed. The llm_node override calls gemini_llm_node() directly.

        This implementation exists for interface compliance and fallback.
        """
        return _GeminiLLMStream(
            llm=self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
        )

    async def aclose(self) -> None:
        """Cleanup (no-op for stateless proxy client)."""
        pass


class _GeminiLLMStream(llm.LLMStream):
    """
    Minimal LLMStream implementation for interface compliance.

    In practice, VoiceAssistant's llm_node override bypasses this entirely.
    This exists to satisfy the type system and handle edge cases.
    """

    def __init__(
        self,
        llm: GeminiLLM,
        *,
        chat_ctx: ChatContext,
        tools: list[FunctionTool | RawFunctionTool],
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(llm, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._gemini_llm = llm

    async def _run(self) -> None:
        """
        Minimal implementation that emits an empty response.

        This method is typically never called because VoiceAssistant's
        llm_node override handles all LLM interactions via gemini_llm_node().

        If this is called unexpectedly, it emits a placeholder response
        to prevent crashes.
        """
        request_id = str(uuid.uuid4())

        # Emit a minimal response for interface compliance
        # In normal operation, llm_node override prevents this from running
        logger.warning(
            "GeminiLLM._run() called directly - this usually means llm_node "
            "override is not active. Using fallback response."
        )

        chunk = ChatChunk(
            id=request_id,
            delta=ChoiceDelta(
                role="assistant",
                content="I'm configured to use a custom LLM node. Please ensure the agent's llm_node override is active.",
            ),
        )
        self._event_ch.send_nowait(chunk)
