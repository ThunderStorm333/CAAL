#!/bin/bash
# CAAL Agent Entrypoint
# Writes credentials from environment variables to files if provided

# Write GCP credentials if provided as env var
if [ -n "$GCP_CREDENTIALS" ]; then
    mkdir -p /app/credentials
    echo "$GCP_CREDENTIALS" > /app/credentials/gcp-service-account.json
    export GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/gcp-service-account.json
    echo "GCP credentials written from environment variable"
fi

# Start the agent
exec python voice_agent.py start
