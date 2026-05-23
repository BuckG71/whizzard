"""Stage 8 contained-Hermes — integration smoke.

Verifies the foundational pieces of the Stage 8 deployment without the full
Hermes-setup chain (which is the next-level heavier test):

- the `hermes` binary is installed in the cell;
- Ollama is reachable from the cell via `host.docker.internal:11434` and
  returns a structured model-list response;
- Hermes's `-z` one-shot mode is wired — running it without a configured
  HERMES_HOME errors graciously with a recognizable "no LLM provider"
  message, not a crash.

The full chat-against-Ollama smoke (M7-style) needs a configured HERMES_HOME
(see `docs/examples/hermes/config.yaml.snippet`) and is the heavier
follow-up. Auto-wiring that into the test harness is tracked separately.
"""

from __future__ import annotations

import json
import subprocess

import pytest

pytestmark = pytest.mark.integration


def test_hermes_binary_present_in_cell(whizzard_hermes_image: str) -> None:
    """The Hermes CLI is installed in the cell — the foundational
    Dockerfile.hermes outcome."""
    result = subprocess.run(
        ["docker", "run", "--rm", whizzard_hermes_image, "hermes", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    # `-z PROMPT` is Hermes's one-shot mode — it's what the heavier
    # chat-against-Ollama smoke would invoke.
    assert "-z" in result.stdout, "hermes --help missing -z one-shot mode"


def test_ollama_reachable_from_cell(
    whizzard_hermes_image: str, ollama_reachable: bool
) -> None:
    """The cell can reach Ollama at host.docker.internal:11434 and the API
    returns a well-formed model-list response. Skipped when Ollama isn't up."""
    result = subprocess.run(
        ["docker", "run", "--rm",
         "--add-host=host.docker.internal:host-gateway",
         whizzard_hermes_image,
         "curl", "-s", "--max-time", "5",
         "http://host.docker.internal:11434/api/tags"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "models" in payload, f"unexpected /api/tags shape: {payload!r}"


def test_hermes_oneshot_errors_graciously_without_config(
    whizzard_hermes_image: str,
) -> None:
    """`hermes -z` without a configured HERMES_HOME hits the documented
    "No LLM provider configured" error path — verifies Hermes's setup
    detection is wired, the entrypoint hasn't drifted, and the failure is
    well-formed (not a silent miss or hang)."""
    result = subprocess.run(
        ["docker", "run", "--rm", whizzard_hermes_image,
         "hermes", "-z", "say hi"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0, (
        "hermes -z exited 0 without config — setup detection drifted?"
    )
    combined = (result.stdout + result.stderr).lower()
    # Tolerant of upstream wording — Hermes phrases this as "no inference
    # provider", "no llm provider", or points at `hermes model` / `hermes
    # setup` / an API-key env var, depending on which code path resolves
    # the missing config. Any of those = the error is well-formed.
    expected = ("no inference provider", "no llm provider",
                "hermes model", "hermes setup", "api key")
    assert any(s in combined for s in expected), (
        f"unexpected hermes error path:\nstdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
