# CAAL

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LiveKit](https://img.shields.io/badge/LiveKit-Agents-purple.svg)](https://docs.livekit.io/agents/)

**Voice assistant that learns new abilities via auto-discovered n8n workflows exposed as tools via MCP**

Built on [LiveKit Agents](https://docs.livekit.io/agents/) with cloud STT/TTS/LLM using [Google Cloud Speech](https://cloud.google.com/speech-to-text), [Google Cloud TTS](https://cloud.google.com/text-to-speech), and [Gemini](https://ai.google.dev/) (via [geminicli2api](https://github.com/gzzhongqi/geminicli2api)).

## Features

- **Cloud Voice Pipeline**: Google Cloud STT (Chirp 2) + Google Cloud TTS (Chirp 3 HD) + Gemini LLM
- **Free LLM Access**: Uses your Google AI Pro subscription via OAuth (no per-request API costs)
- **Wake Word Detection**: "Hey Cal" activation via Picovoice Porcupine
- **n8n Integrations**: Home Assistant, APIs, databases - anything n8n can connect to
- **Web Search**: DuckDuckGo integration for real-time information
- **Webhook API**: External triggers for announcements and tool reload
- **Mobile App**: Flutter client for Android and iOS (see `mobile/`)

## Quick Start (Docker)

```bash
# Clone and configure
git clone https://github.com/CoreWorxLab/caal.git
cd caal
cp .env.example .env

# Set up credentials (see Credentials Setup below)
mkdir -p credentials
cp /path/to/your/gcp-service-account.json credentials/gcp-service-account.json
cp ~/.gemini/oauth_creds.json credentials/gemini-oauth.json

# Edit configuration
nano .env  # Set CAAL_HOST_IP, N8N_MCP_URL, N8N_MCP_TOKEN

# Deploy
docker compose up -d
```

Open `http://YOUR_SERVER_IP:3000` from any device on your network.

**Requirements:**
- Docker (no GPU needed)
- Google Cloud project with Speech-to-Text and Text-to-Speech APIs enabled
- Google AI Pro subscription (for Gemini via geminicli2api)
- [n8n](https://n8n.io/) with MCP enabled (Settings > MCP Access)

## Credentials Setup

CAAL requires two credential files in the `credentials/` directory.

### Google Cloud Service Account

Used for Speech-to-Text and Text-to-Speech APIs.

1. **Create a Google Cloud project** at [console.cloud.google.com](https://console.cloud.google.com)

2. **Enable APIs**:
   - Go to APIs & Services > Enable APIs
   - Enable "Cloud Speech-to-Text API"
   - Enable "Cloud Text-to-Speech API"

3. **Create a service account**:
   - Go to IAM & Admin > Service Accounts
   - Click "Create Service Account"
   - Name it (e.g., "caal-voice")
   - Grant roles: "Cloud Speech Client" and "Cloud Text-to-Speech Client"

4. **Download the key**:
   - Click on the service account
   - Go to Keys > Add Key > Create new key > JSON
   - Download and save as `credentials/gcp-service-account.json`

### Gemini OAuth (for geminicli2api)

Used to access Gemini LLM via your Google AI Pro subscription.

1. **Subscribe to Google AI Pro** at [ai.google.dev](https://ai.google.dev/)

2. **Install gemini-cli**:
   ```bash
   pip install gemini-cli
   ```

3. **Authenticate**:
   ```bash
   gemini auth login
   ```
   This opens a browser for Google OAuth. After authenticating, credentials are saved to `~/.gemini/oauth_creds.json`.

4. **Copy to project**:
   ```bash
   cp ~/.gemini/oauth_creds.json credentials/gemini-oauth.json
   ```

## Network Modes

CAAL supports three network configurations:

| Mode | Voice From | Access URL | Command |
|------|------------|------------|---------|
| **LAN HTTP** | Host machine only | `http://localhost:3000` | `docker compose up -d` |
| **LAN HTTPS** | Any LAN device | `https://192.168.1.100` | `docker compose --profile https up -d` |
| **Tailscale** | Anywhere | `https://your-machine.tailnet.ts.net` | `docker compose --profile https up -d` |

> **Why the difference?** Browsers block microphone access on HTTP except from localhost. HTTPS is required for voice from other devices.

### LAN HTTP Mode (Default)

Simplest setup. Voice works from the host machine; other devices can use text chat:

```bash
# Set your LAN IP in .env
CAAL_HOST_IP=192.168.1.100

# Start
docker compose up -d
```

### LAN HTTPS Mode (mkcert)

Full voice from any device on your LAN using locally-trusted certificates:

**1. Install mkcert and generate certs:**
```bash
# Install mkcert (Ubuntu/Debian)
sudo apt install mkcert

# Install mkcert (macOS)
brew install mkcert

# Install local CA (one-time, may need browser restart)
mkcert -install

# Generate cert for your LAN IP
mkcert 192.168.1.100

# Move to certs folder with standard names
mkdir -p certs
mv 192.168.1.100.pem certs/server.crt
mv 192.168.1.100-key.pem certs/server.key
```

**2. Configure `.env`:**
```bash
CAAL_HOST_IP=192.168.1.100
HTTPS_DOMAIN=192.168.1.100
```

**3. Set key permissions and rebuild frontend:**
```bash
chmod 644 certs/server.key  # nginx needs read access

# Frontend bakes in wss:// URL at build time - must rebuild
docker compose --profile https build frontend
```

**4. Start with HTTPS profile:**
```bash
docker compose --profile https up -d
```

**5. Access from any LAN device:**
```
https://192.168.1.100
```

> **Note:** Other devices on your LAN need the mkcert CA installed to avoid certificate warnings. Run `mkcert -CAROOT` to find the CA cert, then install it on other devices.

### Tailscale Mode (Remote Access)

Access CAAL from anywhere with HTTPS via [Tailscale](https://tailscale.com/):

**1. Generate Tailscale certificates:**
```bash
# Get your Tailscale hostname
tailscale status | head -1

# Generate certs (replace with your hostname)
tailscale cert your-machine.tailnet.ts.net

# Move certs to project with standard names
mkdir -p certs
mv your-machine.tailnet.ts.net.crt certs/server.crt
mv your-machine.tailnet.ts.net.key certs/server.key
```

**2. Configure `.env`:**
```bash
CAAL_HOST_IP=100.x.x.x                         # Your Tailscale IP (tailscale ip -4)
HTTPS_DOMAIN=your-machine.tailnet.ts.net       # Your Tailscale hostname
```

**3. Rebuild frontend and start:**
```bash
# Frontend bakes in wss:// URL at build time - must rebuild
docker compose --profile https build frontend

# Start all services
docker compose --profile https up -d
```

**4. Access from any Tailscale device:**
```
https://your-machine.tailnet.ts.net
```

## Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│  Docker Compose Stack                                                 │
│                                                                       │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐       │
│  │  Frontend  │  │  LiveKit   │  │ geminicli  │  │   Agent    │       │
│  │  (Next.js) │  │   Server   │  │   2api     │  │   (CAAL)   │       │
│  │   :3000    │  │   :7880    │  │   :8888    │  │   :8889    │       │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘       │
│        │               │               │               │              │
│        └───────────────┴───────────────┴───────────────┘              │
│                                    │                                  │
└────────────────────────────────────┼──────────────────────────────────┘
                                     │
                   ┌─────────────────┼─────────────────┐
                   │                 │                 │
             ┌─────┴─────┐     ┌─────┴─────┐     ┌─────┴─────┐
             │  Google   │     │    n8n    │     │   Your    │
             │   Cloud   │     │ Workflows │     │   APIs    │
             └───────────┘     └───────────┘     └───────────┘
                    External Services (Cloud + Your Network)
```

**Services:**
- **Frontend**: Next.js web interface for voice interaction
- **LiveKit**: WebRTC server for real-time audio streaming
- **geminicli2api**: Proxy that exposes Gemini via OpenAI-compatible API
- **Agent**: Python voice pipeline connecting STT → LLM → TTS

## Configuration

### Environment Variables (`.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `CAAL_HOST_IP` | Your server's LAN IP (required for WebRTC) | - |
| `GEMINI_PROXY_PASSWORD` | Password for geminicli2api proxy | `caal-secret` |
| `GEMINI_MODEL` | Gemini model name | `gemini-3-flash` |
| `STT_MODEL` | Google Cloud STT model | `chirp_2` |
| `STT_LANGUAGES` | Languages to recognize (comma-separated) | `en-US` |
| `TTS_VOICE` | Google Cloud TTS voice | `en-US-Chirp3-HD-Callirrhoe` |
| `TTS_MODEL` | Google Cloud TTS model | `chirp_3` |
| `N8N_MCP_URL` | n8n MCP server URL | - |
| `N8N_MCP_TOKEN` | n8n MCP access token | - |
| `LIVEKIT_URL` | LiveKit server URL | `ws://localhost:7880` |
| `PORCUPINE_ACCESS_KEY` | Picovoice key for wake word | - |
| `TIMEZONE` | IANA timezone ID | `America/Los_Angeles` |

### Gemini Models

Available models via geminicli2api (see [geminicli2api docs](https://github.com/gzzhongqi/geminicli2api)):

| Model | Description |
|-------|-------------|
| `gemini-3-flash` | Fast, low-latency (recommended for voice) |
| `gemini-3-pro` | More capable, slower |
| `gemini-2.5-pro` | Previous generation |

Suffixes: `-search` (grounded), `-maxthinking`, `-nothinking`

### Google Cloud TTS Voices

See [Google Cloud TTS voices](https://cloud.google.com/text-to-speech/docs/voices) for full list.

Recommended Chirp 3 HD voices:
- `en-US-Chirp3-HD-Callirrhoe` (female)
- `en-US-Chirp3-HD-Charon` (male)
- `en-US-Chirp3-HD-Kore` (female)

## n8n Workflow Integration

CAAL discovers tools from n8n workflows via MCP. Each workflow with a webhook trigger becomes a voice command.

### Quick Start

Example workflows are included in the `n8n-workflows/` folder:

```bash
cd n8n-workflows
cp config.env.example config.env
nano config.env  # Set your n8n IP and API key
python setup.py  # Creates all workflows in n8n
```

### Setup n8n

1. Enable MCP in n8n: **Settings > MCP Access > Enable MCP**
2. Set connection method to **Access Token** and copy the token
3. Enable workflow access in each workflow's settings
4. Set `N8N_MCP_URL` in `.env` to your n8n MCP endpoint (e.g., `http://192.168.1.100:5678/mcp-server/http`)

### Included Workflows

| Workflow | Voice Command |
|----------|---------------|
| `espn_get_nfl_scores` | "What are the NFL scores?" |
| `calendar_get_events` | "What's on my calendar today?" |
| `hass_control` | "Turn on the office lamp" |
| `radarr_search_movies` | "Do I have any Batman movies?" |
| `n8n_create_caal_tool` | "Create a tool that..." (self-extending!) |

See `n8n-workflows/README.md` for full documentation.

## Wake Word Detection

CAAL supports "Hey Cal" wake word detection using Picovoice Porcupine.

**Setup:**
1. Get a free access key from [Picovoice Console](https://console.picovoice.ai/)
2. Train a custom "Hey Cal" wake word and download the **Web (WASM)** model
3. Place file in `frontend/public/`:
   - `hey_cal.ppn` - Custom wake word model (must replace with your own)
4. Add to `.env`: `PORCUPINE_ACCESS_KEY=your_key_here`
5. Rebuild frontend: `docker compose build frontend && docker compose up -d`

**Usage:**
- Toggle wake word on/off with the ear icon in the control bar
- Say "Hey Cal" to activate - CAAL responds with a greeting
- Conversation continues until agent finishes speaking

## Webhook API

External systems can trigger CAAL actions via HTTP:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/announce` | POST | Make CAAL speak a message |
| `/wake` | POST | Trigger wake word greeting |
| `/reload-tools` | POST | Refresh MCP tool cache |
| `/health` | GET | Health check |

**Example - Announce:**
```bash
curl -X POST http://localhost:8889/announce \
  -H "Content-Type: application/json" \
  -d '{"message": "Package delivered at front door"}'
```

**Example - Reload Tools:**
```bash
curl -X POST http://localhost:8889/reload-tools \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "calendar_create_event"}'
```

## Mobile App

A Flutter mobile client is available in the `mobile/` directory for Android and iOS.

```bash
cd mobile
cp .env.example .env
nano .env  # Set CAAL_SERVER_URL to your server

flutter pub get
flutter run
```

**Note:** Wake word requires training separate mobile models from Picovoice Console (the web WASM models don't work on mobile).

See `mobile/README.md` for full documentation.

## Local Development

```bash
# Install dependencies
uv sync

# Start infrastructure (LiveKit + geminicli2api)
docker compose up -d livekit geminicli2api

# Set up credentials for local development
export GOOGLE_APPLICATION_CREDENTIALS=./credentials/gcp-service-account.json

# Run agent locally
uv run voice_agent.py dev

# Run frontend locally
cd frontend && pnpm install && pnpm dev
```

**Development commands:**
```bash
uv run ruff check src/        # Lint
uv run mypy src/              # Type check
uv run pytest                 # Test
```

## Project Structure

```
caal/
├── voice_agent.py              # Main entry point
├── .env                        # Environment variables
├── docker-compose.yaml         # Docker deployment
├── credentials/                # API credentials (gitignored)
│   ├── gcp-service-account.json
│   └── gemini-oauth.json
├── prompt/
│   └── default.md              # System prompt template
├── frontend/                   # Next.js web interface
│   ├── public/                 # Wake word models go here
│   └── components/             # UI components
├── mobile/                     # Flutter mobile app
│   ├── lib/                    # Dart source code
│   ├── android/                # Android config
│   └── ios/                    # iOS config
├── n8n-workflows/              # Example n8n workflows
│   ├── setup.py                # One-command deployment
│   ├── config.env.example      # Configuration template
│   └── *.json                  # Workflow definitions
└── src/caal/
    ├── integrations/           # n8n MCP, web search
    ├── llm/                    # Gemini LLM integration
    ├── webhooks.py             # HTTP API endpoints
    └── utils/                  # Formatting helpers
```

## Troubleshooting

### Google Cloud Authentication Failed

**Symptom**: Agent logs show "Could not automatically determine credentials"

1. **Check credentials file exists**:
   ```bash
   ls -la credentials/gcp-service-account.json
   ```

2. **Verify file permissions**:
   ```bash
   chmod 600 credentials/gcp-service-account.json
   ```

3. **Test credentials locally**:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS=./credentials/gcp-service-account.json
   gcloud auth application-default print-access-token
   ```

### geminicli2api Not Responding

**Symptom**: Agent logs show connection errors to port 8888

1. **Check container is running**:
   ```bash
   docker compose logs geminicli2api
   ```

2. **Verify OAuth credentials**:
   ```bash
   ls -la credentials/gemini-oauth.json
   ```

3. **Re-authenticate if expired**:
   ```bash
   gemini auth login
   cp ~/.gemini/oauth_creds.json credentials/gemini-oauth.json
   docker compose restart geminicli2api
   ```

### WebRTC Not Connecting

**Symptom**: Frontend loads but voice doesn't work

1. **Check CAAL_HOST_IP** in `.env` - must match your network mode:
   - LAN HTTP/HTTPS: your LAN IP (e.g., `192.168.1.100`)
   - Tailscale: your Tailscale IP (`tailscale ip -4`)

2. **Check firewall** - these ports must be open:
   | Port | Protocol | Purpose |
   |------|----------|---------|
   | 3000 | TCP | Web UI |
   | 7880 | TCP | WebSocket signaling |
   | 7881 | TCP/UDP | WebRTC fallback |
   | 50000-50100 | UDP | WebRTC media |

3. **Check LiveKit logs**:
   ```bash
   docker compose logs livekit | grep -i "ice\|error"
   ```

### Agent Not Processing Voice

```bash
# Check agent logs
docker compose logs -f agent

# Verify all services are healthy
docker compose ps
```

### n8n Tools Not Loading

1. Verify `N8N_MCP_URL` and `N8N_MCP_TOKEN` in `.env`
2. Check n8n has MCP enabled (Settings > MCP Access)
3. Ensure workflows have webhook triggers and are active

## Production Hardening

### Generate Secure LiveKit Keys

```bash
# Generate new API keys
docker run --rm livekit/livekit-server generate-keys

# Update .env and livekit.yaml with generated values
```

### HTTPS

For HTTPS, see [Network Modes](#network-modes). Options:
- **LAN HTTPS (mkcert)**: Full voice from any device on your local network
- **Tailscale**: Full voice from anywhere via Tailscale network

Both use the same `--profile https` and nginx for TLS termination.

### Credential Security

- Never commit `credentials/` directory (already in `.gitignore`)
- Rotate GCP service account keys periodically
- Gemini OAuth tokens refresh automatically but may need re-authentication after 7 days

## Related Projects

- [LiveKit Agents](https://github.com/livekit/agents) - Voice agent framework
- [geminicli2api](https://github.com/gzzhongqi/geminicli2api) - Gemini to OpenAI API proxy
- [Google Cloud Speech-to-Text](https://cloud.google.com/speech-to-text) - STT API
- [Google Cloud Text-to-Speech](https://cloud.google.com/text-to-speech) - TTS API
- [n8n](https://n8n.io/) - Workflow automation
- [Picovoice Porcupine](https://picovoice.ai/platform/porcupine/) - Wake word engine

## License

MIT License - see [LICENSE](LICENSE) for details.
