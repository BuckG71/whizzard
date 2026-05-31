"""S20.5 / D-134: credential values must not persist plaintext in the
audit log.

The host's docker argv has ``-e KEY=VALUE`` pairs for every env var
injected into the cell. When the adapter resolved KEY from OneCLI or
the host-env fallback, VALUE is the plaintext secret. Whizzard scrubs
those pairs via ``_argv_for_log`` before handing argv to
``log_session_start``.

These tests lock down both halves:
  * the scrub function replaces VALUE with ``***`` for credential keys
    and leaves non-credential pairs untouched
  * the integration of the scrub into the run_shell logging path is
    actually wired (a credential adapter logs a scrubbed argv)
"""

from __future__ import annotations

from whizzard.docker_cmd import _argv_for_log


def test_scrub_replaces_credential_value_with_stars():
    argv = [
        "docker", "run", "--rm",
        "-e", "ANTHROPIC_API_KEY=sk-secret-value-xyz",
        "-e", "HERMES_MODE=contained",
        "whizzard-base:latest",
    ]
    scrubbed = _argv_for_log(argv, {"ANTHROPIC_API_KEY"})
    assert "ANTHROPIC_API_KEY=***" in scrubbed
    assert "sk-secret-value-xyz" not in " ".join(scrubbed)
    # Non-credential env unchanged.
    assert "HERMES_MODE=contained" in scrubbed


def test_scrub_leaves_argv_untouched_when_no_credentials():
    argv = ["docker", "run", "-e", "FOO=bar", "image"]
    assert _argv_for_log(argv, set()) == argv


def test_scrub_handles_multiple_credentials():
    argv = [
        "docker", "run",
        "-e", "ANTHROPIC_API_KEY=sk-a",
        "-e", "DISCORD_BOT_TOKEN=mfa.xyz",
        "-e", "PUBLIC_VAR=visible",
        "image",
    ]
    scrubbed = _argv_for_log(
        argv, {"ANTHROPIC_API_KEY", "DISCORD_BOT_TOKEN"}
    )
    joined = " ".join(scrubbed)
    assert "sk-a" not in joined
    assert "mfa.xyz" not in joined
    assert "visible" in joined  # non-credential survives
    assert "ANTHROPIC_API_KEY=***" in scrubbed
    assert "DISCORD_BOT_TOKEN=***" in scrubbed


def test_scrub_does_not_match_partial_key_names():
    """A credential key 'TOKEN' must not scrub a non-credential key
    'TOKEN_PUBLIC' that just contains the same substring."""
    argv = [
        "docker", "run",
        "-e", "TOKEN=secret",
        "-e", "TOKEN_PUBLIC=visible-prefix-value",
        "image",
    ]
    scrubbed = _argv_for_log(argv, {"TOKEN"})
    assert "TOKEN=***" in scrubbed
    assert "TOKEN_PUBLIC=visible-prefix-value" in scrubbed
    assert "secret" not in " ".join(scrubbed)


def test_scrub_ignores_e_without_following_pair():
    """A bare `-e` at the end of argv (malformed but not crashable) is
    handled defensively without raising."""
    argv = ["docker", "run", "-e"]
    scrubbed = _argv_for_log(argv, {"FOO"})
    assert scrubbed == argv


def test_scrub_handles_e_value_without_equals():
    """`-e VAR` (env var without value, inherits from host) has no
    value to scrub; pass through untouched."""
    argv = ["docker", "run", "-e", "BAREVAR", "image"]
    scrubbed = _argv_for_log(argv, {"BAREVAR"})
    assert scrubbed == argv


def test_default_adapter_returns_no_credential_keys():
    """The base HarnessAdapter and the generic shell adapter expose no
    credentials; credential_env_keys() returns empty set."""
    from whizzard.adapters import GenericShellAdapter

    adapter = GenericShellAdapter()
    assert adapter.credential_env_keys() == set()


def test_hermes_adapter_returns_resolved_credential_keys(
    monkeypatch, tmp_path,
):
    """The Hermes adapter tracks resolved credentials in
    _credential_sources; credential_env_keys() returns the env-var
    names (NOT platform names — see test_platforms_credential_keys_use_env_var_names
    below for the S20.7 regression that this distinction caused)."""
    from whizzard.adapters import _credentials
    from whizzard.adapters import hermes as hermes_module
    from whizzard.adapters._credentials import SecretFetchResult
    from whizzard.adapters.hermes import HermesAdapter

    monkeypatch.setattr(
        _credentials, "fetch_secret",
        lambda n: SecretFetchResult(value=f"value-{n}", source="onecli"),
    )
    monkeypatch.setattr(
        hermes_module, "fetch_secret",
        lambda n: SecretFetchResult(value=f"value-{n}", source="onecli"),
    )

    adapter = HermesAdapter(
        name="hermes-test",
        config={
            "type": "agent",
            "start_command": "hermes start",
            "platforms": ["discord"],          # production-shape (lowercase platform)
            "secrets": ["ANTHROPIC_API_KEY"],
            "hermes_home": str(tmp_path),
        },
    )
    # Trigger credential resolution.
    adapter.container_env()
    keys = adapter.credential_env_keys()
    # platform "discord" must resolve to env var "DISCORD_BOT_TOKEN" in
    # the returned set so the audit-log scrubber matches the argv pair.
    assert "DISCORD_BOT_TOKEN" in keys
    assert "ANTHROPIC_API_KEY" in keys


def test_platforms_credential_keys_use_env_var_names_not_platform_names(
    monkeypatch, tmp_path,
):
    """S20.7 regression: the independent security review caught that
    _populate_credential_sources keyed the dict on platform names
    (e.g., "discord"), while the actual argv has -e DISCORD_BOT_TOKEN=
    pairs. credential_env_keys() advertised a set the scrubber could
    never match against — plaintext bot tokens leaked into the audit
    log for every platforms-using harness.

    Production-shape end-to-end test: lowercase platform name in
    config → resolved env var in the returned credential set →
    _argv_for_log actually scrubs the argv produced by build_run_argv."""
    from whizzard.adapters import hermes as hermes_module
    from whizzard.adapters._credentials import SecretFetchResult
    from whizzard.adapters.hermes import HermesAdapter
    from whizzard.config import get_profile
    from whizzard.docker_cmd import _argv_for_log, build_run_argv

    monkeypatch.setattr(
        hermes_module, "fetch_secret",
        lambda n: SecretFetchResult(
            value=f"plaintext-secret-for-{n}", source="onecli",
        ),
    )

    adapter = HermesAdapter(
        name="hermes-prod",
        config={
            "type": "agent",
            "start_command": "hermes start",
            "platforms": ["discord"],   # lowercase platform name (production shape)
            "hermes_home": str(tmp_path),
        },
    )

    argv = build_run_argv(
        get_profile("default"),
        image="whizzard-hermes:latest",
        session_id="s20-7-regression",
        adapter=adapter,
    )
    scrubbed = _argv_for_log(argv, adapter.credential_env_keys())

    # The plaintext token MUST NOT appear in the scrubbed argv —
    # otherwise it lands in ~/.whizzard/logs/sessions.jsonl.
    joined = " ".join(scrubbed)
    assert "plaintext-secret-for-DISCORD_BOT_TOKEN" not in joined, (
        f"S20.7 regression: platform-sourced credential leaked into "
        f"audit-log argv. credential_env_keys()={adapter.credential_env_keys()!r}, "
        f"scrubbed argv slice={[a for a in scrubbed if 'DISCORD' in a]!r}"
    )
    assert "DISCORD_BOT_TOKEN=***" in scrubbed
