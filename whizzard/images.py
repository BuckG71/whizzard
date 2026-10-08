"""Execution-cell container image names.

Kept in a dependency-free module so both ``docker_cmd`` and the harness
adapters can reference them without an import cycle (``docker_cmd`` imports
``adapters``, so the adapters can't import ``docker_cmd``). Each adapter
declares its ``default_image`` from here, which the launch path uses when no
explicit ``--image`` override was passed (closes the harness↔image coupling
gap where ``whiz r hermes`` ran the base image and failed to exec ``hermes``).
"""

from __future__ import annotations

import os

WHIZZARD_IMAGE = os.environ.get("WHIZZARD_IMAGE", "whizzard-base:latest")
WHIZZARD_HERMES_IMAGE = os.environ.get(
    "WHIZZARD_HERMES_IMAGE", "whizzard-hermes:latest"
)
# Search-enabled Hermes cell (D-194 web_search; Phase C). Derived FROM the
# hermes image with web-search client libs baked in (firecrawl-py + ddgs) —
# an opt-in layer used only when a profile enables web search, so non-search
# cells stay lean. See whizzard/_dockerfiles/Dockerfile.hermes-search.
WHIZZARD_HERMES_SEARCH_IMAGE = os.environ.get(
    "WHIZZARD_HERMES_SEARCH_IMAGE", "whizzard-hermes-search:latest"
)
# Credential-broker sidecar image (bar C / D-184).
WHIZZARD_BROKER_IMAGE = os.environ.get(
    "WHIZZARD_BROKER_IMAGE", "whizzard-broker:latest"
)
# OneCLI forwarder-shim image (D-188). Isolates the cell from the OneCLI
# gateway's management port by relaying only the proxy port.
WHIZZARD_ONECLI_SHIM_IMAGE = os.environ.get(
    "WHIZZARD_ONECLI_SHIM_IMAGE", "whizzard-onecli-shim:latest"
)
