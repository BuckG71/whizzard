"""Search-broker unit tests (D-194 Phase C) — docker mocked.

Verifies the contained-web-search broker is a correctly-parameterized second
instance of the model broker: pinned to api.firecrawl.dev, bearer_plain auth,
joins the cell's internal net, its own egress, fail-closed on a missing key,
and clean teardown ordering.
"""

from __future__ import annotations

import types

import pytest

from whizzard import search_broker as sb
from whizzard.broker import BrokerError


def _fake_docker_ok():
    """A _docker stub that records calls and always succeeds."""
    calls: list[list[str]] = []

    def fake(args, **kw):
        calls.append(args)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    return calls, fake


@pytest.fixture
def isolated_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "_SEARCH_KEY_ROOT", tmp_path / "search-keys")
    # health-check does a real `docker exec` probe — no-op it under mocks
    monkeypatch.setattr(sb, "_await_broker_ready", lambda c: None)
    # a resolvable Firecrawl key
    monkeypatch.setattr(
        sb, "fetch_secret",
        lambda name: types.SimpleNamespace(value="fc-real-key", source="host-env"),
    )


def test_start_pins_firecrawl_and_joins_the_cell_net(isolated_keys, monkeypatch):
    calls, fake = _fake_docker_ok()
    monkeypatch.setattr(sb, "_docker", fake)

    h = sb.start_search_broker("sid-abc", "whiz-int-sid-abc")
    joined = [" ".join(c) for c in calls]

    # single-upstream pinned to Firecrawl + bearer_plain (no Anthropic beta)
    run = next(c for c in calls if c[:2] == ["run", "-d"])
    assert "BROKER_UPSTREAM_HOST=api.firecrawl.dev" in run
    assert "BROKER_AUTH_SCHEME=bearer_plain" in run
    # joins the CELL's existing internal net (created by the model broker)
    assert "--network" in run and "whiz-int-sid-abc" in run
    # its own egress net, created + connected
    assert any("network create whiz-search-egress-sid-abc" in j for j in joined)
    assert any("network connect whiz-search-egress-sid-abc" in j for j in joined)
    # key bind-mounted read-only
    assert any(":/run/broker/key:ro" in tok for tok in run)
    assert h.base_url == "http://whiz-search-broker-sid-abc:8080"


def test_key_is_written_and_never_a_run_arg(isolated_keys, monkeypatch):
    """The real key goes to a host file mounted ro — it must never appear as a
    docker run argument (which would leak into `docker inspect` / ps)."""
    calls, fake = _fake_docker_ok()
    monkeypatch.setattr(sb, "_docker", fake)
    sb.start_search_broker("sid-x", "whiz-int-sid-x")
    all_args = [tok for c in calls for tok in c]
    assert "fc-real-key" not in all_args


def test_missing_key_fails_closed(isolated_keys, monkeypatch):
    calls, fake = _fake_docker_ok()
    monkeypatch.setattr(sb, "_docker", fake)

    def missing(name):
        from whizzard.adapters._credentials import CredentialUnavailableError
        raise CredentialUnavailableError(name)

    monkeypatch.setattr(sb, "fetch_secret", missing)
    with pytest.raises(BrokerError) as e:
        sb.start_search_broker("sid-y", "whiz-int-sid-y")
    assert "FIRECRAWL_API_KEY" in str(e.value)
    # nothing was created (no docker calls past the failed credential resolve)
    assert calls == []


def test_start_rolls_back_on_container_failure(isolated_keys, monkeypatch):
    """If the container fails to start, the egress net + key dir are cleaned up
    (fail-closed, no orphans)."""
    calls: list[list[str]] = []

    def fake(args, **kw):
        calls.append(args)
        rc = 1 if args[:2] == ["run", "-d"] else 0
        return types.SimpleNamespace(returncode=rc, stdout="", stderr="boom")

    monkeypatch.setattr(sb, "_docker", fake)
    with pytest.raises(BrokerError):
        sb.start_search_broker("sid-z", "whiz-int-sid-z")
    joined = [" ".join(c) for c in calls]
    # egress net was created then removed on rollback
    assert any("network create whiz-search-egress-sid-z" in j for j in joined)
    assert any("network rm whiz-search-egress-sid-z" in j for j in joined)


def test_stop_removes_container_and_egress_not_internal(isolated_keys, monkeypatch, tmp_path):
    calls, fake = _fake_docker_ok()
    monkeypatch.setattr(sb, "_docker", fake)
    kd = tmp_path / "kd"
    kd.mkdir()
    handle = sb.SearchBrokerHandle(
        egress_network="whiz-search-egress-s",
        container_name="whiz-search-broker-s",
        base_url="http://whiz-search-broker-s:8080",
        _key_dir=str(kd),
    )
    sb.stop_search_broker(handle)
    joined = [" ".join(c) for c in calls]
    assert any("rm -f whiz-search-broker-s" in j for j in joined)
    assert any("network rm whiz-search-egress-s" in j for j in joined)
    # must NOT remove the internal net — the model broker owns it
    assert not any("whiz-int" in j for j in joined)
    assert not kd.exists()  # key dir reaped
