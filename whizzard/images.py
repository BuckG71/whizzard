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
# Credential-broker sidecar image (bar C / D-184).
WHIZZARD_BROKER_IMAGE = os.environ.get(
    "WHIZZARD_BROKER_IMAGE", "whizzard-broker:latest"
)
