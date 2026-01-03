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
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Create virtual environment and install dependencies (non-editable)
RUN uv sync --frozen --no-dev --no-editable

# ============================================================================
# Production image
# ============================================================================
FROM base AS runner

WORKDIR /app

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash agent

# Copy virtual environment from deps stage
COPY --from=deps /app/.venv /app/.venv

# Copy application code
COPY --chown=agent:agent src/ ./src/
COPY --chown=agent:agent voice_agent.py ./
COPY --chown=agent:agent prompt/ ./prompt/

# Create directories for credentials and data
RUN mkdir -p /app/credentials /app/data && chown -R agent:agent /app/credentials /app/data

# Copy OpenWakeWord models if they exist
COPY --chown=agent:agent models/ ./models/

# Copy OpenWakeWord resource models to the package location
RUN mkdir -p /app/.venv/lib/python3.11/site-packages/openwakeword/resources/models && \
    cp /app/models/melspectrogram.onnx /app/models/embedding_model.onnx \
    /app/.venv/lib/python3.11/site-packages/openwakeword/resources/models/ 2>/dev/null || true

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER agent

# Default command - start mode for production
CMD ["python", "voice_agent.py", "start"]
