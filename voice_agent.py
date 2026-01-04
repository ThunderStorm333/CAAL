#!/usr/bin/env python3
"""
CAAL Voice Framework - Voice Agent (Cloud APIs Version)
========================================================

A voice assistant using cloud APIs for STT/TTS/LLM:
- Google Cloud STT (Speech-to-Text)
- Google Cloud TTS (Text-to-Speech)
- Gemini LLM via geminicli2api proxy

Usage:
    python voice_agent.py dev

Configuration:
    - .env: Environment variables
    - prompt/default.md: Agent system prompt
    - credentials/gcp-service-account.json: Google Cloud credentials
    - credentials/gemini-oauth.json: Gemini OAuth for geminicli2api

Environment Variables:
    GEMINI_API_URL      - geminicli2api proxy URL (default: "http://geminicli2api:8888/v1")
    GEMINI_API_KEY      - Proxy password (default: "caal-secret")
    GEMINI_MODEL        - Gemini model name (default: "gemini-3-flash")
    STT_MODEL           - Google Cloud STT model (default: "chirp_2")
    TTS_VOICE           - Google Cloud TTS voice (default: "en-US-Chirp3-HD-Callirrhoe")
    TTS_MODEL           - Google Cloud TTS model (default: "chirp_3")
    TIMEZONE            - Timezone for date/time (default: "America/Los_Angeles")
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

# Add src directory to path for local development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv

# Load environment variables from .env
_script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_script_dir, ".env"))

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, mcp
from livekit.plugins import silero, google

from caal import GeminiLLM
from caal.integrations import (
    load_mcp_config,
    initialize_mcp_servers,
    WebSearchTools,
    discover_n8n_workflows,
)
from caal.llm import gemini_llm_node, ToolDataCache
from caal import session_registry
from caal.stt import WakeWordGatedSTT

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)
logger = logging.getLogger("voice-agent")
logger.setLevel(logging.INFO)

# Suppress verbose logs from dependencies
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai._base_client").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)
logging.getLogger("livekit").setLevel(logging.WARNING)
logging.getLogger("livekit_api").setLevel(logging.WARNING)
logging.getLogger("livekit.agents.voice").setLevel(logging.WARNING)
logging.getLogger("livekit.plugins.google").setLevel(logging.WARNING)
logging.getLogger("caal").setLevel(logging.INFO)

# =============================================================================
# Configuration
# =============================================================================

# Gemini LLM via geminicli2api proxy
GEMINI_API_URL = os.getenv("GEMINI_API_URL", "http://geminicli2api:8888/v1")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "caal-secret")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash")

# Google Cloud STT configuration
STT_MODEL = os.getenv("STT_MODEL", "chirp_2")
STT_LANGUAGES = os.getenv("STT_LANGUAGES", "en-US").split(",")

# Google Cloud TTS configuration
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-Chirp3-HD-Callirrhoe")
TTS_MODEL = os.getenv("TTS_MODEL", "chirp_3")

# Google Cloud credentials
GCP_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "/app/credentials/gcp-service-account.json"
)

# General settings
TIMEZONE_ID = os.getenv("TIMEZONE", "America/Los_Angeles")
TIMEZONE_DISPLAY = os.getenv("TIMEZONE_DISPLAY", "Pacific Time")

# Import settings module for runtime-configurable values
from caal import settings as settings_module


def get_runtime_settings() -> dict:
    """Get runtime-configurable settings.

    Priority: Environment variables > settings.json > defaults
    Env vars take priority to allow Docker/Portainer configuration.
    """
    settings = settings_module.load_settings()

    return {
        # Env vars take priority over settings.json
        "tts_voice": TTS_VOICE if os.getenv("TTS_VOICE") else settings.get("tts_voice", TTS_VOICE),
        "model": GEMINI_MODEL if os.getenv("GEMINI_MODEL") else settings.get("model", GEMINI_MODEL),
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0")) or settings.get("temperature", 0.7),
        "max_turns": int(os.getenv("MAX_TURNS", "0")) or settings.get("max_turns", 20),
        "tool_cache_size": int(os.getenv("TOOL_CACHE_SIZE", "0")) or settings.get("tool_cache_size", 3),
    }


def load_prompt() -> str:
    """Load and populate prompt template with date context."""
    return settings_module.load_prompt_with_context(
        timezone_id=TIMEZONE_ID,
        timezone_display=TIMEZONE_DISPLAY,
    )


# =============================================================================
# Agent Definition
# =============================================================================

ToolStatusCallback = callable  # async (bool, list[str], list[dict]) -> None


class VoiceAssistant(WebSearchTools, Agent):
    """Voice assistant with MCP tools and web search."""

    def __init__(
        self,
        gemini_llm: GeminiLLM,
        mcp_servers: dict[str, mcp.MCPServerHTTP] | None = None,
        n8n_workflow_tools: list[dict] | None = None,
        n8n_workflow_name_map: dict[str, str] | None = None,
        n8n_base_url: str | None = None,
        on_tool_status: ToolStatusCallback | None = None,
        tool_cache_size: int = 3,
        max_turns: int = 20,
    ) -> None:
        super().__init__(
            instructions=load_prompt(),
            llm=gemini_llm,
        )

        self._caal_mcp_servers = mcp_servers or {}
        self._n8n_workflow_tools = n8n_workflow_tools or []
        self._n8n_workflow_name_map = n8n_workflow_name_map or {}
        self._n8n_base_url = n8n_base_url
        self._on_tool_status = on_tool_status
        self._tool_data_cache = ToolDataCache(max_entries=tool_cache_size)
        self._max_turns = max_turns

        # For n8n MCP access in reload-tools webhook
        self._n8n_mcp = mcp_servers.get("n8n") if mcp_servers else None

    async def llm_node(self, chat_ctx, tools, model_settings):
        """Custom LLM node using Gemini via geminicli2api proxy."""
        async for chunk in gemini_llm_node(
            self,
            chat_ctx,
            model=self.llm.model,
            base_url=self.llm.base_url,
            api_key=self.llm.api_key,
            temperature=self.llm.temperature,
            tool_data_cache=self._tool_data_cache,
            max_turns=self._max_turns,
        ):
            yield chunk


# =============================================================================
# Agent Entrypoint
# =============================================================================

async def entrypoint(ctx: agents.JobContext) -> None:
    """Main entrypoint for the voice agent."""

    # Start webhook server in the same event loop (first job only)
    global _webhook_server_task
    if _webhook_server_task is None:
        _webhook_server_task = asyncio.create_task(start_webhook_server())

    logger.debug(f"Joining room: {ctx.room.name}")
    await ctx.connect()

    # Load MCP servers from config
    mcp_servers = {}
    try:
        mcp_configs = load_mcp_config()
        mcp_servers = await initialize_mcp_servers(mcp_configs)
    except Exception as e:
        logger.warning(f"Failed to load MCP config: {e}")

    # Discover n8n workflows
    n8n_workflow_tools = []
    n8n_workflow_name_map = {}
    n8n_base_url = None
    n8n_mcp = mcp_servers.get("n8n")
    if n8n_mcp:
        try:
            n8n_config = next((c for c in mcp_configs if c.name == "n8n"), None)
            if n8n_config:
                url_parts = n8n_config.url.rsplit("/", 2)
                n8n_base_url = url_parts[0] if len(url_parts) >= 2 else n8n_config.url

            n8n_workflow_tools, n8n_workflow_name_map = await discover_n8n_workflows(
                n8n_mcp, n8n_base_url
            )
        except Exception as e:
            logger.warning(f"Failed to discover n8n workflows: {e}")

    # Get runtime settings
    runtime = get_runtime_settings()

    # Create GeminiLLM instance
    gemini_llm = GeminiLLM(
        model=runtime["model"],
        base_url=GEMINI_API_URL,
        api_key=GEMINI_API_KEY,
        temperature=runtime["temperature"],
    )

    # Log configuration
    logger.info("=" * 60)
    logger.info("STARTING VOICE AGENT (Cloud APIs)")
    logger.info("=" * 60)
    logger.info(f"  STT: Google Cloud ({STT_MODEL})")
    logger.info(f"  TTS: Google Cloud ({runtime['tts_voice']})")
    logger.info(f"  LLM: Gemini ({runtime['model']}) via {GEMINI_API_URL}")
    logger.info(f"  MCP: {list(mcp_servers.keys()) or 'None'}")
    logger.info("=" * 60)

    # Build STT - Google Cloud with optional wake word
    base_stt = google.STT(
        model=STT_MODEL,
        languages=STT_LANGUAGES,
        credentials_file=GCP_CREDENTIALS_FILE,
    )

    # Load wake word settings
    all_settings = settings_module.load_settings()
    wake_word_enabled = all_settings.get("wake_word_enabled", False)

    # Session reference for wake word callback
    _session_ref: AgentSession | None = None

    if wake_word_enabled:
        import json
        import random

        wake_word_model = all_settings.get("wake_word_model", "models/hey_jarvis.onnx")
        wake_word_threshold = all_settings.get("wake_word_threshold", 0.5)
        wake_word_timeout = all_settings.get("wake_word_timeout", 3.0)
        wake_greetings = all_settings.get("wake_greetings", ["Hey, what's up?"])

        async def on_wake_detected():
            """Play wake greeting directly via TTS."""
            nonlocal _session_ref
            if _session_ref is None:
                logger.warning("Wake detected but session not ready yet")
                return

            try:
                greeting = random.choice(wake_greetings)
                logger.info(f"Wake word detected, playing greeting: {greeting}")

                tts = _session_ref.tts
                audio_output = _session_ref.output.audio
                audio_stream = tts.synthesize(greeting)
                async for event in audio_stream:
                    if hasattr(event, "frame") and event.frame:
                        await audio_output.capture_frame(event.frame)
                audio_output.flush()

            except Exception as e:
                logger.warning(f"Failed to play wake greeting: {e}")

        async def on_state_changed(state):
            """Publish wake word state to connected clients."""
            payload = json.dumps({
                "type": "wakeword_state",
                "state": state.value,
            })
            try:
                await ctx.room.local_participant.publish_data(
                    payload.encode("utf-8"),
                    reliable=True,
                    topic="wakeword_state",
                )
            except Exception as e:
                logger.warning(f"Failed to publish wake word state: {e}")

        stt_instance = WakeWordGatedSTT(
            inner_stt=base_stt,
            model_path=wake_word_model,
            threshold=wake_word_threshold,
            silence_timeout=wake_word_timeout,
            on_wake_detected=on_wake_detected,
            on_state_changed=on_state_changed,
        )
        logger.info(f"  Wake word: ENABLED (model={wake_word_model})")
    else:
        stt_instance = base_stt
        logger.info("  Wake word: disabled")

    # Create session with Google Cloud STT/TTS
    session = AgentSession(
        stt=stt_instance,
        llm=gemini_llm,
        tts=google.TTS(
            model_name=TTS_MODEL,
            voice_name=runtime["tts_voice"],
            language="en-US",
            credentials_file=GCP_CREDENTIALS_FILE,
            use_streaming=False,  # Streaming has decoder bug with Chirp3-HD
        ),
        vad=silero.VAD.load(),
        allow_interruptions=False,
    )

    _session_ref = session

    # ==========================================================================
    # Round-trip latency tracking
    # ==========================================================================

    _transcription_time: float | None = None

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(ev) -> None:
        nonlocal _transcription_time
        _transcription_time = time.perf_counter()
        logger.debug(f"User said: {ev.transcript[:80]}...")

    @session.on("agent_state_changed")
    def on_agent_state_changed(ev) -> None:
        nonlocal _transcription_time
        if ev.new_state == "speaking" and _transcription_time is not None:
            latency_ms = (time.perf_counter() - _transcription_time) * 1000
            logger.info(f"ROUND-TRIP LATENCY: {latency_ms:.0f}ms (LLM + TTS)")
            _transcription_time = None

        if isinstance(stt_instance, WakeWordGatedSTT):
            stt_instance.set_agent_busy(ev.new_state in ("thinking", "speaking"))

    async def _publish_tool_status(
        tool_used: bool,
        tool_names: list[str],
        tool_params: list[dict],
    ) -> None:
        """Publish tool usage status to frontend."""
        import json
        payload = json.dumps({
            "tool_used": tool_used,
            "tool_names": tool_names,
            "tool_params": tool_params,
        })

        try:
            await ctx.room.local_participant.publish_data(
                payload.encode("utf-8"),
                reliable=True,
                topic="tool_status",
            )
        except Exception as e:
            logger.warning(f"Failed to publish tool status: {e}")

    # ==========================================================================

    assistant = VoiceAssistant(
        gemini_llm=gemini_llm,
        mcp_servers=mcp_servers,
        n8n_workflow_tools=n8n_workflow_tools,
        n8n_workflow_name_map=n8n_workflow_name_map,
        n8n_base_url=n8n_base_url,
        on_tool_status=_publish_tool_status,
        tool_cache_size=runtime["tool_cache_size"],
        max_turns=runtime["max_turns"],
    )

    await session.start(
        room=ctx.room,
        agent=assistant,
        room_input_options=RoomInputOptions(),
    )

    session_registry.register(ctx.room.name, session, assistant)

    close_event = asyncio.Event()

    @session.on("close")
    def on_session_close(ev) -> None:
        logger.info(f"Session closed: {ev.reason}")
        close_event.set()

    try:
        await session.generate_reply(
            instructions="Greet the user briefly and let them know you're ready to help."
        )

        logger.info("Agent ready - listening for speech...")
        await close_event.wait()

    finally:
        session_registry.unregister(ctx.room.name)


# =============================================================================
# Webhook Server
# =============================================================================

WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8889"))

_webhook_server_task: asyncio.Task | None = None


async def start_webhook_server():
    """Start FastAPI webhook server in the current event loop."""
    import uvicorn
    from caal.webhooks import app

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=WEBHOOK_PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    logger.debug(f"Starting webhook server on port {WEBHOOK_PORT}")
    await server.serve()


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            job_memory_warn_mb=0,
        )
    )
