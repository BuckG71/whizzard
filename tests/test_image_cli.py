"""Stage 18: `whiz image status` enrichment, `whiz image check`, and
parse_dockerfile_base_pin."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from textwrap import dedent

import pytest
from typer.testing import CliRunner

from whizzard.cli import app
from whizzard.docker_cmd import ImageMeta, parse_dockerfile_base_pin

runner = CliRunner()


# ---------- parse_dockerfile_base_pin ----------


def test_parse_dockerfile_returns_digest_when_pinned(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text(
        "# header comment\n"
        "FROM debian:12-slim@sha256:0104b334637a5f19aa9c983a91b54c89887c0984081f2068983107a6f6c21eeb\n"
        "RUN echo ok\n"
    )
    assert parse_dockerfile_base_pin(df) == (
        "sha256:0104b334637a5f19aa9c983a91b54c89887c0984081f2068983107a6f6c21eeb"
    )


def test_parse_dockerfile_returns_none_when_not_pinned(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text("FROM debian:12-slim\nRUN echo ok\n")
    assert parse_dockerfile_base_pin(df) is None


def test_parse_dockerfile_returns_none_when_missing(tmp_path: Path):
    assert parse_dockerfile_base_pin(tmp_path / "nope") is None


def test_parse_dockerfile_skips_comments_and_blanks(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text(
        dedent(
            """
            # comment first

            FROM debian:12-slim@sha256:abcdef0123456789
            """
        )
    )
    assert parse_dockerfile_base_pin(df) == "sha256:abcdef0123456789"


def test_parse_dockerfile_returns_none_for_non_sha256_digest(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text("FROM debian:12-slim@sha512:notreal\n")
    assert parse_dockerfile_base_pin(df) is None


# ---------- whiz image status ----------


def _patch_docker_available(monkeypatch, value: bool = True) -> None:
    from whizzard.cli import image as cli_image

    monkeypatch.setattr(cli_image, "docker_available", lambda: value)


def test_image_status_no_docker(monkeypatch: pytest.MonkeyPatch):
    _patch_docker_available(monkeypatch, False)
    result = runner.invoke(app, ["image", "status"])
    assert result.exit_code == 127
    assert "docker not found" in result.stdout.lower()


def test_image_status_image_missing(monkeypatch: pytest.MonkeyPatch):
    from whizzard.cli import image as cli_image

    _patch_docker_available(monkeypatch, True)
    monkeypatch.setattr(cli_image, "image_exists", lambda image: False)

    result = runner.invoke(app, ["image", "status"])
    assert result.exit_code == 0
    assert "NOT present" in result.stdout
    assert "whiz image build" in result.stdout


def test_image_status_renders_id_built_and_base(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from whizzard.cli import image as cli_image

    df = tmp_path / "Dockerfile"
    df.write_text(
        "FROM debian:12-slim@sha256:0104b334637a5f19aa9c983a91b54c89887c0984081f2068983107a6f6c21eeb\n"
    )

    built = datetime.now(UTC) - timedelta(days=3, hours=4)
    meta = ImageMeta(id="sha256:deadbeefcafe", created=built)

    _patch_docker_available(monkeypatch, True)
    monkeypatch.setattr(cli_image, "image_exists", lambda image: True)
    monkeypatch.setattr(cli_image, "image_inspect", lambda image: meta)
    monkeypatch.setattr(cli_image, "_dockerfile_path", lambda: df)

    result = runner.invoke(app, ["image", "status"])
    assert result.exit_code == 0
    assert "is present" in result.stdout
    assert "sha256:deadbeefcafe" in result.stdout
    assert "3d" in result.stdout
    assert "ago" in result.stdout
    assert (
        "sha256:0104b334637a5f19aa9c983a91b54c89887c0984081f2068983107a6f6c21eeb"
        in result.stdout
    )


def test_image_status_warns_when_dockerfile_not_pinned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from whizzard.cli import image as cli_image

    df = tmp_path / "Dockerfile"
    df.write_text("FROM debian:12-slim\n")

    built = datetime.now(UTC) - timedelta(days=1)
    meta = ImageMeta(id="sha256:abc", created=built)

    _patch_docker_available(monkeypatch, True)
    monkeypatch.setattr(cli_image, "image_exists", lambda image: True)
    monkeypatch.setattr(cli_image, "image_inspect", lambda image: meta)
    monkeypatch.setattr(cli_image, "_dockerfile_path", lambda: df)

    result = runner.invoke(app, ["image", "status"])
    assert result.exit_code == 0
    assert "not digest-pinned" in result.stdout


def test_image_status_daemon_unreachable(monkeypatch: pytest.MonkeyPatch):
    from whizzard.cli import image as cli_image

    # Use cli_image.DockerDaemonError (not a fresh import from
    # whizzard.docker_cmd) — test_docker_cmd reloads docker_cmd, leaving
    # cli_image's bound DockerDaemonError class different-identity from
    # a fresh re-import. The except clause checks identity.
    def _raise(image):
        raise cli_image.DockerDaemonError("daemon down")

    _patch_docker_available(monkeypatch, True)
    monkeypatch.setattr(cli_image, "image_exists", _raise)

    result = runner.invoke(app, ["image", "status"])
    assert result.exit_code == 125
    assert "daemon down" in result.stdout


# ---------- whiz image check ----------


def test_image_check_fresh(monkeypatch: pytest.MonkeyPatch):
    from whizzard.cli import image as cli_image

    built = datetime.now(UTC) - timedelta(days=10)
    meta = ImageMeta(id="sha256:fresh", created=built)

    _patch_docker_available(monkeypatch, True)
    monkeypatch.setattr(cli_image, "image_inspect", lambda image: meta)

    result = runner.invoke(app, ["image", "check"])
    assert result.exit_code == 0
    assert "fresh" in result.stdout
    assert "10d" in result.stdout


def test_image_check_stale(monkeypatch: pytest.MonkeyPatch):
    from whizzard.cli import image as cli_image

    built = datetime.now(UTC) - timedelta(days=45)
    meta = ImageMeta(id="sha256:stale", created=built)

    _patch_docker_available(monkeypatch, True)
    monkeypatch.setattr(cli_image, "image_inspect", lambda image: meta)

    result = runner.invoke(app, ["image", "check"])
    assert result.exit_code == 1
    assert "stale" in result.stdout
    assert "45d" in result.stdout
    assert "threshold 30d" in result.stdout


def test_image_check_custom_threshold(monkeypatch: pytest.MonkeyPatch):
    from whizzard.cli import image as cli_image

    built = datetime.now(UTC) - timedelta(days=10)
    meta = ImageMeta(id="sha256:x", created=built)

    _patch_docker_available(monkeypatch, True)
    monkeypatch.setattr(cli_image, "image_inspect", lambda image: meta)

    # Same 10-day-old image is fresh at 30d (default) but stale at 7d.
    result = runner.invoke(app, ["image", "check", "--threshold-days", "7"])
    assert result.exit_code == 1
    assert "stale" in result.stdout


def test_image_check_not_built(monkeypatch: pytest.MonkeyPatch):
    from whizzard.cli import image as cli_image

    _patch_docker_available(monkeypatch, True)
    monkeypatch.setattr(cli_image, "image_inspect", lambda image: None)

    result = runner.invoke(app, ["image", "check"])
    assert result.exit_code == 2
    assert "NOT built" in result.stdout


def test_image_check_no_docker(monkeypatch: pytest.MonkeyPatch):
    _patch_docker_available(monkeypatch, False)
    result = runner.invoke(app, ["image", "check"])
    assert result.exit_code == 127


def test_image_check_daemon_unreachable(monkeypatch: pytest.MonkeyPatch):
    from whizzard.cli import image as cli_image

    def _raise(image):
        raise cli_image.DockerDaemonError("daemon down")

    _patch_docker_available(monkeypatch, True)
    monkeypatch.setattr(cli_image, "image_inspect", _raise)

    result = runner.invoke(app, ["image", "check"])
    assert result.exit_code == 125


# ---------- Stage 18: digest-pin in our bundled Dockerfile ----------


def test_bundled_dockerfile_is_digest_pinned():
    """Stage 18: the project's Dockerfile must FROM a digest-pinned base."""
    from whizzard.cli.image import _dockerfile_path

    digest = parse_dockerfile_base_pin(_dockerfile_path())
    assert digest is not None, "Dockerfile must pin its base image by digest"
    assert digest.startswith("sha256:")
    assert len(digest) >= len("sha256:") + 32  # at least 32-char digest
