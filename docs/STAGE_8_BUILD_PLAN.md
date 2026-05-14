# Plan: Stage 8 — Hermes Adapter Implementation

## Goal
Whizzard launches Hermes inside a contained cell via `whiz hermes <profile>` end-to-end — profile creation, concurrency guards, capability visibility, gateway-mode default and interactive opt-in all working per D-86–D-90.

## Success criteria
- `whiz hermes <profile>` starts a containerized Hermes gateway, with the pre-launch banner showing active platforms + approval mode (D-89, D-90), and exits cleanly via `wrap_up()` calling `/quit` over `docker exec`.
- `whiz hermes profile create <name>` with `--clone-from default` (default) and `--no-clone` works for the three migration shapes (D-86); `auth.json` is verifiably never copied.
- Concurrent same-profile launches are blocked via `gateway.lock` pre-check with stale-pid auto-recovery (D-87); the error names the profile + conflicting pid.
- Smoke + unit tests pass in CI; one integration smoke test launches a real Hermes container in interactive mode and exits cleanly.

## Milestones
1. Adapter skeleton landed — `whizzard/adapters/hermes.py` exists with all `HarnessAdapter` Protocol methods (D-28) stubbed; `adapters/__init__.py` returns `HermesAdapter` for `type: "agent"` instead of raising `UnknownHarnessTypeError`; harnesses.json schema accepts a Hermes entry; existing tests still pass.
2. Adapter Protocol extended for capability visibility — `active_capabilities() -> list[str]` added to `adapters/base.py` (D-89, D-90); `GenericShellAdapter` returns `[]`; `HermesAdapter` stub returns placeholder list; pre-launch banner machinery in core wired to call it.
3. Hermes-config reading complete — `HermesAdapter.container_env()` reads `<HERMES_HOME>/config.yaml`, identifies active platforms, looks up host env vars (`DISCORD_BOT_TOKEN`, etc.), returns the dict; `--platforms` flag restricts the set (D-89); missing-credential and `manual`-mode-in-gateway warnings fire pre-launch (D-89, D-90).
4. Concurrency guard wired in — `gateway.lock` + `gateway.pid` pre-check with pid liveness probe and stale-lock auto-recovery (D-87); error UX names profile + pid + remediation paths.
5. Profile-creation verb shipped — `whiz hermes profile create <name>` subcommand with `--clone-from <name>` / `--no-clone` flags and the bare-command graceful-degrade logic (D-86); `auth.json` exclusion enforced in code and verified by test.
6. End-to-end interactive launch validated — `whiz hermes <profile> --interactive` starts a real Hermes container, runs `hermes chat -q "say hi"`, captures the response, and shuts down cleanly. Gateway-mode end-to-end is manual smoke by Bryan.
7. Packaging and validation closed out — `pyproject.toml` declares `[project.optional-dependencies] hermes = [...]` (per D-131 notes); test files (`test_hermes_adapter.py`, `test_hermes_integration.py`) follow the flat-tests convention with `pytest.importorskip` gating the integration tier; `docs/STAGE_VALIDATION.md` Stage 8 section written (currently placeholder at line 1027); `HANDOFF.md` updated.

## Next 3 actions
1. Create `whizzard/adapters/hermes.py` with a `HermesAdapter` class implementing every method of the `HarnessAdapter` Protocol as a stub that returns a placeholder of the right shape (or raises `NotImplementedError` with a tracking comment). Update `whizzard/adapters/__init__.py` so `build_adapter("agent", config)` returns `HermesAdapter(config)` instead of raising. Add `tests/test_hermes_adapter.py` with one passing test: `build_adapter` returns a `HermesAdapter` instance for a minimal agent-type harness config.
2. Add `active_capabilities() -> list[str]` to the `HarnessAdapter` Protocol in `whizzard/adapters/base.py`. Implement it in `GenericShellAdapter` (returns `[]`) and stub it in `HermesAdapter` (returns `["placeholder"]` for now). Add Protocol-shape unit tests in `tests/test_adapters.py` covering both adapters.
3. Implement `HermesAdapter.container_env()` reading `<HERMES_HOME>/config.yaml` for the platform list and mapping each to its conventional env var (`DISCORD_BOT_TOKEN`, etc., pulled from the host environment). Add unit tests using fixture HERMES_HOME directories with known `config.yaml` shapes — happy path, empty-platforms, missing-credential, and unreadable-config cases.

## Open questions
- Hermes upstream version to pin in `pyproject.toml` extras: floor and ceiling for the initial supported range. Reasonable default: pin to the version Bryan currently runs, with `< next-major` as the ceiling.
- Integration test platform: interactive-mode end-to-end is straightforward (no platform creds needed); gateway-mode end-to-end against a real Discord workspace vs. deferring to a mock-platform substrate post-Stage 8. Plan currently assumes interactive is the only CI integration test; gateway is manual smoke.

## Risks
- **Hermes upstream churn during the build.** D-154's pipeline isn't running yet, so a breaking Hermes release mid-build could derail testing. Mitigation: pin to a known-good Hermes version in `pyproject.toml` for the duration of the build; widen the range after Stage 8 ships.
- **Adapter-vs-core boundary erosion under deadline pressure.** Tempting to "just read `config.yaml` from core, we only have Hermes anyway." Mitigation: D-153 is captured; treat any Hermes-specific identifier appearing outside `adapters/hermes.py` or the `whiz hermes` subcommand surface as a code-review finding.
- **Gateway-mode end-to-end is hard to automate cleanly.** Real platform credentials in CI are a non-starter; mock platform servers are a real chunk of work. Mitigation: scope CI integration test to interactive mode (cheap, no creds); gateway-mode smoke is manual until a mock substrate justifies the build cost — explicitly out of Stage 8.
- **`wrap_up()` via `docker exec /quit` may not work uniformly across Hermes modes.** Per `docs/archive/hermes_research.md` L208–209, `/quit` is confirmed for chat mode but only assumed for gateway mode. Mitigation: validate the gateway shutdown path early (during milestone 6 or earlier) and fall back to SIGTERM + drain timeout if needed; this is implementation discovery, not new design.

## Where to resume
You stopped immediately after closing the Stage 8 Hermes design slate. The five Stage 8 questions (D-86 through D-90) are all resolved and committed (88b7e3e, 24ddf07, c45ebfd, 00e98b9), plus D-153 (adapter-isolation rule) and D-154 (upstream-change pipeline) were captured along the way. No Stage 8 *code* has been written yet — `whizzard/adapters/__init__.py` still raises `UnknownHarnessTypeError` for `type: "agent"`. The first concrete code action is to land the adapter skeleton (Next Action 1) and remove that raise. All design decisions are in `docs/decisions.md` §10 — reference by ID, do not re-derive.
