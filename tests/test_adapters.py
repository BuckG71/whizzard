"""Stage 7: adapter interface and generic-shell adapter tests.

Hermes-adapter-specific tests live in `test_hermes_adapter.py`. This file
covers the Protocol contract, the generic shell adapter, and the factory
dispatch (`build_adapter`) for all currently-supported harness types.
"""

import pytest

from whizzard.adapters import (
    GenericShellAdapter,
    HarnessAdapter,
    HermesAdapter,
    UnknownHarnessTypeError,
    WrapUpResult,
    WrapUpStatus,
    build_adapter,
)


def test_generic_adapter_satisfies_protocol():
    """The generic adapter must structurally satisfy HarnessAdapter."""
    adapter = GenericShellAdapter()
    assert isinstance(adapter, HarnessAdapter)


def test_adapters_declare_their_required_image():
    """Harness↔image coupling: each adapter declares the image its binary
    lives in, so selecting a harness selects the right image when no
    explicit `--image` override is given. Hermes' `hermes` binary is only
    in the Hermes image — running it on the base image dies with
    `exec hermes: No such file or directory` (regression guard)."""
    from whizzard.images import WHIZZARD_HERMES_IMAGE, WHIZZARD_IMAGE

    assert GenericShellAdapter().default_image == WHIZZARD_IMAGE
    assert HermesAdapter().default_image == WHIZZARD_HERMES_IMAGE


def test_generic_default_start_command_is_bash():
    adapter = GenericShellAdapter()
    assert adapter.start_command() == ["/bin/bash"]


def test_generic_start_command_can_be_overridden_via_config():
    adapter = GenericShellAdapter(config={"start_command": "/bin/zsh"})
    assert adapter.start_command() == ["/bin/zsh"]


def test_generic_start_command_string_is_shlex_split():
    adapter = GenericShellAdapter(config={"start_command": "/bin/bash -l"})
    assert adapter.start_command() == ["/bin/bash", "-l"]


def test_generic_start_command_list_is_passed_through():
    adapter = GenericShellAdapter(config={"start_command": ["bash", "--noprofile"]})
    assert adapter.start_command() == ["bash", "--noprofile"]


def test_generic_env_defaults_empty():
    assert GenericShellAdapter().container_env() == {}


def test_generic_env_from_config_normalizes_to_strings():
    adapter = GenericShellAdapter(config={"env": {"X": 1, "Y": "two"}})
    assert adapter.container_env() == {"X": "1", "Y": "two"}


def test_generic_working_dir_defaults_none():
    assert GenericShellAdapter().working_dir() is None


def test_generic_working_dir_from_config():
    adapter = GenericShellAdapter(config={"working_dir": "/home/whizzard"})
    assert adapter.working_dir() == "/home/whizzard"


def test_generic_wrap_up_returns_no_op():
    result = GenericShellAdapter().wrap_up("container-id-123", grace_seconds=10)
    assert result.status == WrapUpStatus.NO_OP
    assert result.detail


def test_generic_health_check_is_none():
    assert GenericShellAdapter().health_check_command() is None


def test_generic_active_capabilities_is_empty():
    # Generic shell exposes no capability surface for the pre-launch banner.
    assert GenericShellAdapter().active_capabilities() == []


def test_generic_preflight_always_ok():
    result = GenericShellAdapter().preflight()
    assert result.ok is True
    assert result.reason == ""
    assert result.cleanup_note == ""


def test_generic_mcp_env_is_empty():
    # Generic shell has no agent; no MCP server to configure.
    assert GenericShellAdapter().mcp_env("any-session-id") == {}


def test_generic_container_mounts_is_empty():
    # Stage 8 M6: generic shell has no harness state to persist.
    assert GenericShellAdapter().container_mounts() == []


def test_build_adapter_returns_generic_for_shell_type():
    adapter = build_adapter("test", {"type": "shell", "start_command": "/bin/bash"})
    assert isinstance(adapter, GenericShellAdapter)
    assert adapter.name == "test"


def test_build_adapter_defaults_to_shell_when_type_missing():
    adapter = build_adapter("test", {"start_command": "/bin/bash"})
    assert isinstance(adapter, GenericShellAdapter)


def test_build_adapter_returns_hermes_for_agent_type():
    adapter = build_adapter(
        "hermes", {"type": "agent", "start_command": "hermes gateway run"}
    )
    assert isinstance(adapter, HermesAdapter)
    assert adapter.name == "hermes"


def test_build_adapter_rejects_unknown_type():
    with pytest.raises(UnknownHarnessTypeError, match="unknown type"):
        build_adapter("weird", {"type": "alien", "start_command": "x"})


def test_wrap_up_result_is_frozen():
    import dataclasses
    r = WrapUpResult(status=WrapUpStatus.SUCCESS, detail="done")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.detail = "tampered"  # type: ignore[misc]
