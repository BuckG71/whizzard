# Changelog

All notable changes to Whizzard will land here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project will follow [Semantic Versioning](https://semver.org/) once the public API stabilizes at v1.0.

Stage references map to milestones in [`docs/mvp_build_plan.md`](docs/mvp_build_plan.md). Decision references map to entries in [`docs/decisions.md`](docs/decisions.md).

## [Unreleased]

### Added
- **Stage 8 — Hermes adapter** (M1–M8 all shipped). Full end-to-end: adapter Protocol implementation, `active_capabilities()` surface (D-89, D-90), OneCLI-mediated credential injection with env-var fallback (D-134), `gateway.lock` preflight with stale-pid auto-recovery (D-87), `whiz hermes profile create` verb with `--clone-from` / `--no-clone` and `auth.json` exclusion (D-80, D-86), SIGTERM-based `wrap_up()` via `docker stop --time=<grace>`, HERMES_HOME bind mount with scoped UID parity (D-56, D-79), `docker/Dockerfile.hermes` derived image, manual smoke validation against Mac Studio Ollama via `host.docker.internal:11434`.
- **Stage 9 — in-cell MCP server (read-only subset).** `whiz_status`, `whiz_audit_self`, `whiz_emit_event`, `whiz_list_presets` (D-25, D-156). Launch-time snapshot + event-file write-back pattern; merged into host audit log at session_end.
- **Stage 10 — presets and CLI ergonomics.** Schema-versioned `presets.json` with omit-to-inherit override semantics (D-148 design pass). Brevity aliases (`whiz r`/`s`/`p`/`m`/`pr`) and smart defaults: bare `whiz` shows status, bare `whiz r` launches the most-recent preset. Bundled `hermes` and `shell` presets (D-101 personal-MVP defaults).
- **Stage 12 — cross-adapter credential utility.** `whizzard/adapters/_credentials.py` with `fetch_secret(name)`: OneCLI first (D-134), host-env fallback. Credential source surfaced via `active_capabilities`.
- **D-162 — declarative `secrets:` field** in harness config for LLM-provider credentials; uses the same fetch_secret delivery as platform tokens. Plaintext credential values prohibited in harness configs.
- **Decisions log infrastructure.** Flat+tags schema (Type / Tags / Door Type / Decision / Rationale / Source / Status), curated canonical tag vocabulary, `scripts/validate_decisions.py` for schema + tag + reference integrity, `scripts/dx.py` lookup CLI.
- **Dev tooling.** `pyproject.toml` configs for ruff (lint + import order + modernization) and mypy (phased adoption); `Makefile` shortcuts (`make check`, `make test`, etc.); `.pre-commit-config.yaml` running validate-decisions + ruff + mypy; GitHub Actions CI workflow (`.github/workflows/ci.yml`) running lint + typecheck + test matrix (Python 3.11, 3.12) + decisions-validation on push and PR.
- **Documentation.** `docs/vision_and_strategy.md` (positioning + real-world threat-model validation), `docs/architecture.md`, `docs/mvp_build_plan.md` (18-stage plan with shipped markers), `docs/post_mvp_spec.md` (v1.0 spec), `docs/control_surface.md`, `docs/stage_validation.md` (per-stage manual validation checklists), `docs/decisions.md` (162 captured decisions), `docs/home_lab_deployment.md` (four-machine Tailscale-meshed reference deployment), `docs/STAGE_8_BUILD_PLAN.md` with M7 runbook, `docs/HANDOFF.md` (append-only session log + mutable Current State header).

### Notes
- Status: MVP under construction; stages 1–10 + 12 shipped. Outstanding: Stage 11 (`docs/examples/<harness>/` recipes), stages 13–18, OSS-launch readiness gaps.
- Naming: "Whizzard" is a working name; product will rename to "Osmotiq" before OSS launch (D-158) — CLI binary `oiq`, domain `osmotiq.ai` already owned.
