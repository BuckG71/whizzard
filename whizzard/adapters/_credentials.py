"""Credential fetching utility for adapter modules.

Centralizes the OneCLI-shell-out logic (introduced for Hermes in Stage 8 per
D-134) and adds an env-var fallback path (Stage 12 generalization). Adapter
modules consume `fetch_secret(name)` to retrieve a credential value from the
best available source. The caller stays adapter-private; this module is
underscored to signal "adapter-private, not for core consumption" per D-153.

Fetch order:
  1. OneCLI vault (preferred per D-91, D-134)
  2. Host environment variable named identically (fallback)
  3. Raise `CredentialUnavailableError` if neither has it

The fallback emits no in-process side effect; the caller is responsible for
surfacing the fact that a credential came from the host env rather than the
vault (e.g., via `active_capabilities()` on the adapter). This module's
responsibility ends at "fetch the value and report the source."
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

_ONECLI_TIMEOUT_SECONDS = 30


class OneCLINotInstalledError(Exception):
    """`onecli` is not on PATH. The fetch path falls back to host env."""


class OneCLISecretMissingError(Exception):
    """OneCLI returned non-zero — usually a not-registered secret."""


class OneCLITimeoutError(Exception):
    """OneCLI exceeded the fetch timeout — vault locked or daemon stuck.

    Distinct from ``OneCLISecretMissingError`` because the host-env fallback
    is unsafe on timeout (we don't know what OneCLI would have said). D-134
    "fail loud, do not launch" applies (F-B-03).
    """


class CredentialUnavailableError(Exception):
    """Neither OneCLI nor host env has the requested secret."""


@dataclass(frozen=True)
class SecretFetchResult:
    """Outcome of `fetch_secret`. `source` is `"onecli"` or `"host-env"`."""

    value: str
    source: str


def _fetch_via_onecli(name: str) -> str:
    """Fetch `name` from OneCLI's vault. Raises on missing binary or non-zero.

    Tests monkeypatch this function (or `subprocess.run`) to avoid invoking
    a real OneCLI install.
    """
    try:
        result = subprocess.run(
            ["onecli", "secrets", "get", name],
            capture_output=True,
            text=True,
            timeout=_ONECLI_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as e:
        raise OneCLINotInstalledError(
            "`onecli` not found on PATH; falling back to host env."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise OneCLITimeoutError(
            f"OneCLI timed out after {_ONECLI_TIMEOUT_SECONDS}s fetching "
            f"secret {name!r}. Your vault may be locked, or the OneCLI "
            f"daemon may be stuck. Try `onecli auth status` and unlock "
            f"the vault before relaunching."
        ) from e

    if result.returncode != 0:
        raise OneCLISecretMissingError(
            f"OneCLI failed to fetch secret {name!r} "
            f"(exit code {result.returncode}). "
            f"stderr: {result.stderr.strip() or '(empty)'}."
        )

    return result.stdout.rstrip("\n")


def fetch_secret(name: str) -> SecretFetchResult:
    """Fetch a credential by name. Tries OneCLI first, falls back to host env.

    Raises `CredentialUnavailableError` if neither source has the value.

    Raises `OneCLITimeoutError` if OneCLI hung — there is no fallback in
    that case because we don't know whether the vault has the secret or
    not (F-B-03, D-134 "fail loud" intent).

    The fallback is silent at this layer — the caller surfaces "came from
    host env" via its own capability-banner mechanism (e.g.,
    `active_capabilities()`).
    """
    try:
        return SecretFetchResult(value=_fetch_via_onecli(name), source="onecli")
    except OneCLINotInstalledError:
        host_value = os.environ.get(name)
        if host_value is None:
            raise CredentialUnavailableError(
                f"Secret {name!r} unavailable: OneCLI not installed and "
                f"env var {name} not set on host. "
                f"Install OneCLI (recommended) or export {name}."
            ) from None
        return SecretFetchResult(value=host_value, source="host-env")
    except OneCLISecretMissingError:
        host_value = os.environ.get(name)
        if host_value is None:
            raise CredentialUnavailableError(
                f"Secret {name!r} unavailable: not in OneCLI vault and "
                f"env var {name} not set on host. "
                f"Register via `onecli secrets create {name}` or export {name}."
            ) from None
        return SecretFetchResult(value=host_value, source="host-env")
