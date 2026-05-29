# Hermes adapter setup — full recipe

This is the production-grade Hermes adapter setup, used for daily autonomous Hermes via Discord and validated end-to-end against a real Mac Studio Ollama backend on 2026-05-19.

Hermes is [`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent) — a self-improving agent harness with platform connectors (Discord, Slack, WhatsApp), cron scheduling, kanban, and a curator for ongoing skill maintenance.

## What this recipe gives you

A Hermes instance running inside an OIQ-governed sandbox with:
- **State persistence:** Hermes's profile (skills, memories, sessions, kanban) lives in a host directory bind-mounted as `HERMES_HOME`. State survives container termination per D-79.
- **No identity-credential leak:** `auth.json` (Hermes's master credential store) is explicitly excluded from the cloned profile per D-80. The sandbox never sees the host Hermes's authentication tokens.
- **Scoped per-sandbox credentials:** LLM and platform credentials inject into the sandbox via the harness config's `secrets:` / `platforms:` fields (D-162, D-89-amended). OneCLI delivers values; env-var fallback if OneCLI isn't configured.
- **Hardened sandbox:** `--cap-drop=ALL`, `--security-opt no-new-privileges`, `--read-only` rootfs, tmpfs scratch, host-UID parity on the HERMES_HOME mount (D-56).

## Prerequisites

- OIQ installed (`pip install -e .` from the repo).
- Docker Desktop or equivalent.
- An existing host-side Hermes install at `~/.hermes/` (used as the clone source). If you don't have one, `hermes setup` from upstream creates one.
- *(Optional)* OneCLI installed with provider credentials (`Anthropic`, `Discord`, etc.). Without OneCLI, OIQ's adapter falls back to host env vars.

## Step-by-step

### 1. Build the Hermes-extended image

The base `whizzard-base:latest` is a minimal Debian image with no Hermes. The included `docker/Dockerfile.hermes` layers Python + Hermes on top, pinned to a specific upstream commit.

```sh
docker build -f docker/Dockerfile.hermes -t whizzard-hermes:latest .
```

Bump `HERMES_REF` in `docker/Dockerfile.hermes` to update the pinned version.

### 2. Clone a Hermes profile for the sandbox

This creates a *sibling* of your existing `~/.hermes/`, excluding `auth.json` (D-80) and per-instance runtime state.

```sh
whiz hermes profile create whizzard-sandbox --clone-from default
```

Creates `~/.hermes-whizzard-sandbox/` (~10-50 MB depending on profile content). Your daily-driver host Hermes is untouched.

### 3. Add the harness to `~/.whizzard/config/harnesses.json`

See [`harnesses.json.example`](harnesses.json.example) for the full snippet. The bundled `hermes-sandbox` entry uses gateway mode with Discord; the `hermes-sandbox-smoke` variant uses interactive chat mode with no platform credentials (good for first-launch validation).

### 4. Configure the sandbox's LLM provider

OIQ doesn't touch the sandbox's `~/.hermes-whizzard-sandbox/config.yaml` — you edit it directly to choose a provider.

**Option A: Local LLM via Ollama** (validates Hermes integration without external credentials):

```yaml
model:
  api_key: ollama
  default: mistral-nemo:latest
  provider: ollama-launch
providers:
  ollama-launch:
    api: http://host.docker.internal:11434/v1
    base_url: http://host.docker.internal:11434/v1
    api_key: ollama
    default_model: mistral-nemo:latest
    # ...
```

The `host.docker.internal` hostname routes from the sandbox to the host's Ollama. See [`../home_lab_deployment.md`](../../home_lab_deployment.md) for the broader Tailscale-meshed inference architecture.

**Option B: Cloud provider via the `secrets:` field** (D-162):

In `harnesses.json`, declare:

```json
"hermes-sandbox": {
    ...
    "secrets": ["ANTHROPIC_API_KEY"]
}
```

Then either store `ANTHROPIC_API_KEY` in OneCLI (recommended) or export it in the shell that launches OIQ. The adapter injects it into the sandbox at launch; the value never appears in any file on disk.

**Never put plaintext credential values directly in `harnesses.json` or `config.yaml`.** D-80 + D-162 are explicit on this.

### 5. Launch

```sh
WHIZZARD_IMAGE=whizzard-hermes:latest whiz r hermes-sandbox-smoke
```

Or for the gateway-mode production setup:

```sh
WHIZZARD_IMAGE=whizzard-hermes:latest whiz r hermes-sandbox
```

The launch banner shows the active capabilities; Hermes initializes inside the sandbox; you can interact with it normally. `/quit` (Hermes's chat-mode exit) or SIGTERM via wrap_up triggers a clean shutdown — Hermes drains active turns, writes final state, exits with code 0.

### 6. Verify state persistence

After the sandbox exits, your session state lives on the host:

```sh
ls -la ~/.hermes-whizzard-sandbox/sessions/    # should show the session you just had
ls -la ~/.hermes-whizzard-sandbox/memories/    # any memories Hermes wrote during the session
```

A subsequent `whiz r hermes-sandbox-smoke` launch sees the previous state and continues from there.

## Common follow-ups

- **Different LLM provider** — edit `config.yaml`, update the `secrets:` list in `harnesses.json` if it's a new credential.
- **Run autonomously / always-on** — switch the harness from `hermes-sandbox-smoke` (chat mode) to `hermes-sandbox` (gateway mode) once you've validated the setup.
- **Move to a cloud VM or secondary host** — see [`../../home_lab_deployment.md`](../../home_lab_deployment.md).

## Troubleshooting

- **`Permission denied` writing under `/home/whizzard/.hermes` inside the sandbox** — `uid_parity=True` should prevent this on macOS Docker Desktop and Linux. If you see it, file an issue with your `docker info` output and host UID/GID.
- **Sandbox launches but Hermes errors with "no provider configured"** — `config.yaml` provider isn't matching a `providers:` block, or the `api_key` field is missing. Cross-check the YAML against [Step 4](#4-configure-the-sandboxes-llm-provider).
- **`host.docker.internal` doesn't resolve** — only works on Docker Desktop (macOS / Windows). On native Linux, use the host's actual IP (`172.17.0.1` is the default Docker bridge gateway), or run Ollama in a sibling container.
- **OneCLI not found / "fetch failed"** — OIQ's `fetch_secret` calls `onecli secrets get` which doesn't exist in current OneCLI; falls through to env-var fallback. Set the env var directly until the OneCLI integration is realigned. Tracked in D-162 Notes.

## Files in this directory

- [`README.md`](README.md) — this file
- [`harnesses.json.example`](harnesses.json.example) — `hermes-sandbox` + `hermes-sandbox-smoke` harness entries
- [`config.yaml.snippet`](config.yaml.snippet) — Ollama provider configuration block for the sandbox's `config.yaml`
