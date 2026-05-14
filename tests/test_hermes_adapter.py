"""Hermes adapter tests — Stage 8.

Scope per build plan Action 1 (skeleton): the adapter exists, instantiates,
satisfies the HarnessAdapter Protocol, and is returned by `build_adapter`
for `type: "agent"`. Behavior tests (config.yaml reading, gateway.lock
check, --platforms restriction, wrap_up via /quit) arrive in subsequent
build-plan actions.
"""

import pytest

from whizzard.adapters import (
    HarnessAdapter,
    HermesAdapter,
    WrapUpStatus,
    build_adapter,
)


def test_build_adapter_returns_hermes_for_agent_type():
    adapter = build_adapter(
        "hermes", {"type": "agent", "start_command": "hermes gateway run"}
    )
    assert isinstance(adapter, HermesAdapter)
    assert adapter.name == "hermes"


def test_hermes_adapter_satisfies_protocol():
    assert isinstance(HermesAdapter(), HarnessAdapter)


def test_hermes_default_start_command_is_gateway_run():
    # D-88: gateway is the default mode for the Hermes adapter.
    assert HermesAdapter().start_command() == ["hermes", "gateway", "run"]


def test_hermes_start_command_can_be_overridden_via_config():
    adapter = HermesAdapter(config={"start_command": "hermes chat"})
    assert adapter.start_command() == ["hermes", "chat"]


def test_hermes_start_command_list_is_passed_through():
    adapter = HermesAdapter(config={"start_command": ["hermes", "chat", "-q", "hi"]})
    assert adapter.start_command() == ["hermes", "chat", "-q", "hi"]


def test_hermes_env_defaults_empty():
    # Skeleton behavior — Action 3 replaces this with config.yaml-driven env.
    assert HermesAdapter().container_env() == {}


def test_hermes_working_dir_defaults_none():
    assert HermesAdapter().working_dir() is None


def test_hermes_wrap_up_not_yet_implemented():
    # Real wrap_up via `docker exec /quit` lands in build-plan milestone 6.
    # Skeleton raises so end-to-end runs fail loudly rather than silently
    # mishandling shutdown.
    with pytest.raises(NotImplementedError, match="milestone 6"):
        HermesAdapter().wrap_up("container-id", grace_seconds=10)


def test_hermes_health_check_is_none():
    assert HermesAdapter().health_check_command() is None


def test_hermes_active_capabilities_returns_list_of_strings():
    # Skeleton: empty. Action 3 populates from config.yaml + approval mode.
    caps = HermesAdapter().active_capabilities()
    assert isinstance(caps, list)
    assert all(isinstance(c, str) for c in caps)
