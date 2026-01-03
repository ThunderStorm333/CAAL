# syntax=docker/dockerfile:1

# CAAL - Voice Agent (Cloud APIs Version)
# ========================================
# Lightweight Python agent for voice orchestration using cloud APIs:
# - Google Cloud STT/TTS
# - Gemini LLM via geminicli2api proxy

# ============================================================================
# Base image - slim Python (no GPU needed, using cloud APIs)
# ============================================================================
FROM python:3.11-slim-bookworm AS base

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# ============================================================================
# Dependencies stage
# ============================================================================
FROM base AS deps

WORKDIR /app

# Copy files needed for dependency installation
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Create virtual environment and install dependencies (without lockfile for fresh deps)
RUN uv sync --no-dev --no-editable

# ============================================================================
# Production image
# ============================================================================
FROM base AS runner

WORKDIR /app

# Copy virtual environment from deps stage
COPY --from=deps /app/.venv /app/.venv

# Copy application code
COPY src/ ./src/
COPY voice_agent.py ./
COPY prompt/ ./prompt/
COPY entrypoint.sh ./

# Create directories for credentials and data
RUN mkdir -p /app/credentials /app/data /app/models && \
    chmod +x /app/entrypoint.sh

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default command - use entrypoint to handle credentials
CMD ["/app/entrypoint.sh"]
