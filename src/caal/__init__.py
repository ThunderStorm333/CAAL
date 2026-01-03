"""
CAAL - Voice Assistant (Cloud APIs Version)
============================================

A modular voice assistant with n8n workflow integrations and cloud-based AI services.

Core Components:
    GeminiLLM: Gemini LLM via geminicli2api proxy (uses Google AI Pro subscription)

STT/TTS:
    - Google Cloud Speech-to-Text
    - Google Cloud Text-to-Speech

Integrations:
    n8n: Workflow discovery and execution via n8n MCP

Example:
    >>> from caal import GeminiLLM
    >>> from caal.integrations import load_mcp_config
    >>>
    >>> llm = GeminiLLM(model="gemini-3-flash", base_url="http://proxy:8888/v1")
    >>> mcp_configs = load_mcp_config()

Repository: https://github.com/CoreWorxLab/caal
License: MIT
"""

__version__ = "0.2.0"
__author__ = "CoreWorxLab"

from .llm import GeminiLLM

__all__ = [
    "GeminiLLM",
    "__version__",
]
