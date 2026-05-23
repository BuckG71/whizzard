# Whizzard — Known Issues, Deferred Work, Tech Debt, and Process Risks

A consolidated index of things known not to be ideal in the project right now.
Most entries link out to a canonical source (decision, build plan stage,
handoff section) — the value of this doc is the *single cross-cutting view*,
not duplicate copy of those sources.

Categories:
- **Functional gaps** — works differently than designed/documented.
- **Deferred features** — known-deliberate "not yet" items.
- **Tech debt** — code/structure improvements desired.
- **Process risks** — workflow-level risks.

---

## Functional gaps

### OneCLI integration is functionally inert
The Stage 12 OneCLI credential utility (`fetch_secret`) calls
`onecli secrets get`, which does not exist in the actual OneCLI CLI surface;
every invocation falls through to the env-var fallback. The integration
nominally exists but never does the OneCLI thing.
*Source:* `docs/decisions.md` §D-162 Notes.
*Disposition:* decide — fix to match the real OneCLI surface, or drop the
direct integration and leave only env-var-fallback.

### Hermes full-chat smoke needs HERMES_HOME setup
The Stage 8 integration smoke verifies the deployment + Ollama reachability +
that `hermes -z` is wired, but does not drive a real chat against Ollama.
`hermes -z PROMPT` requires a configured HERMES_HOME (`config.yaml` +
Hermes-state files); the smoke doesn't currently provision one.
*Source:* commit `aeaddb0` (Stage 8 smoke).
*Disposition:* either bundle a smoke-test HERMES_HOME or document that the
heavier smoke needs the user's `~/.hermes-whizzard-cell`. Tracked as the
"next-level Hermes-integration smoke."

### Hermes `config.yaml` MCP auto-wiring is manual
The Hermes adapter sets the WHIZ_* env vars for the in-cell MCP server, but
the harness-side `config.yaml` MCP-client entry pointing at
`python /opt/whiz/mcp_server.py` is still a manual user step.
*Source:* `docs/HANDOFF.md` "What's next".
*Disposition:* Stage 9 follow-up — add an `oiq hermes profile sync-mcp`
verb or fold into `oiq hermes profile create`.

### D-157 user-config drift
The maintainer's personal `~/.whizzard/config/profiles.json` predates several
schema additions (`allow_broad_mount` default per D-157, now
`idle_timeout_seconds` per Stage 15). Bundled defaults updated; the personal
file needs syncing for the changes to take effect locally.
*Source:* `docs/HANDOFF.md` "What's next".
*Disposition:* a one-time `whiz profiles init --force` (or manual edit) when
convenient.

---

## Deferred features (planned, on the roadmap)

### Stage 15.5 — Hot-restart of idle-ended sessions
Spec in the build plan; not implemented. `whiz resume <sid>` verb (+ bare
`whiz r` resuming the most-recent idle-ended session). Restricted to
`expiry_reason == idle` so duration caps can't be circumvented.
*Source:* `docs/mvp_build_plan.md` §Stage 15.5.

### Stages 16–17 — Discord control plane
Read-only (16) then write/approve (17). Both carry a D-148 design pause
requirement before any coding.
*Source:* `docs/mvp_build_plan.md` §Stages 16, 17.

### Stage 18 — Image management
Image build / digest pinning / audit. Autonomous-able when scheduled.
*Source:* `docs/mvp_build_plan.md` §Stage 18.

### MVP+ Stage 19 — Packaging & Install
Published Python distribution, execution-image distribution, clean-machine
install verification, first-run config init. Pre-OSS-launch gate.
*Source:* `docs/mvp_build_plan.md` §Stage 19.

### MVP+ Stage 20 — Security review & hardening audit
Consolidated threat model (`docs/threat_model.md`, not yet written),
adversarial red-team suite (partially started — see Process risks below),
fail-closed audit closing D-133, injection / command-construction audit,
credential-handling audit, supply-chain scan in CI, independent reviewer
pass. Pre-OSS-launch gate.
*Source:* `docs/mvp_build_plan.md` §Stage 20; closes D-131 / D-133.

### Whizzard → Osmotiq rename
Triggered after MVP operational, before Hermes migration. CLI becomes `oiq`;
`osmotiq.ai` owned.
*Source:* D-158.

### `ADAPTER_SPEC.md` (OSS-launch artifact)
Contributor-facing adapter Protocol artifact. Decided but not authored.
*Source:* D-160.

---

## Tech debt

### `STAGE_8_BUILD_PLAN.md` is closed but not archived
A stage-specific build plan that's fully shipped. Lives as cruft in `docs/`.
*Disposition:* archive to `docs/archive/` when next touching that area.

### In-cell `snapshot.json` is writable by the agent
The per-session `/run/whiz` mount is `:rw` because the cell legitimately writes
`events.jsonl` and `requests/*.json` there. `snapshot.json` (the agent's
launch-time capability view, per D-156) lives in the same dir, so the cell
can overwrite it. The host-side audit log (mounted `:ro`) is still the source
of truth — containment is intact — but the cooperation-layer "honest
self-reflection" guarantee leaks: a compromised harness could lie to itself
about its own permissions via `whiz_status`.
*Source:* catch-up review 2026-05-23 finding F-B-05.
*Fix shape:* split `/run/whiz` into a `:ro` snapshot mount and a `:rw`
events/requests mount, OR expose the snapshot through the in-cell MCP server
instead of as a file. Either is a D-156 amendment.
*Disposition:* Stage 20 security review, or a decision-needed item earlier
if it bothers us.

### No env-name denylist on adapter-supplied `container_env`
`docker_cmd.build_run_argv` passes the adapter's `container_env()` and
`mcp_env()` into `-e K=V` flags without filtering names. A user-edited
`harnesses.json` could include `LD_PRELOAD`, `PATH`, `HOME`, etc. and the
values would land verbatim in the cell. Not a containment escape (the cell
is the cell), but a footgun for misconfig. Adapter code is core-trusted (D-10)
and `harnesses.json` is a Whizzard-owned surface (D-153) so no current path
exercises this; the denylist is defensive hardening.
*Source:* catch-up review 2026-05-23 finding F-B-07.
*Disposition:* Stage 20 hardening audit.

### `cidfile` orphans in STATE_DIR on a mid-launch crash
`run_shell` clears `cidfile` before `Popen`, populates it during the run,
and unlinks it at the end. If an unhandled exception fires between the
Popen and the final unlink (KeyboardInterrupt during `monitor_and_enforce`,
etc.), the cidfile is left behind. Each orphan is a few bytes; impact is
slow STATE_DIR growth. Fix is a `try/finally` wrap of a sizable block;
natural home is the Stage 18 (image management) work that already touches
this area.
*Source:* catch-up review 2026-05-23 finding F-B-09.
*Disposition:* Stage 18.

### No test for agent-event merge ordering vs `session_end`
`run_shell` documents in code that agent events MUST be merged into the
audit log before the `session_end` event so the log is temporally
ordered. No unit test populates `event_log_path(session_id)` then asserts
the merged events appear between `session_start` and `session_end`.
Integration smokes would catch a real ordering bug, but fast unit coverage
is missing.
*Source:* catch-up review 2026-05-23 finding F-B-10.
*Disposition:* Chunk D of the catch-up review (session lifecycle + audit) —
that chunk's review already touches the audit-log assertion machinery.

### Hermes adapter `parent_dir` parameter has no input validation
`create_hermes_profile` validates the `name` argument (no slashes, no
leading dots, no reserved values) but accepts `parent_dir` as-is. Production
callers (`whiz hermes profile create`) pass `parent_dir=None` so the live
attack surface is zero; the gap only matters if a future `--profile-dir`
CLI flag or programmatic caller wires user input through. Treat as a
review requirement: any new caller that exposes `parent_dir` must
validate it.
*Source:* catch-up review 2026-05-23 finding F-C-06.
*Disposition:* defer — defensive hardening with no current path; would
add at the point a user-facing profile-dir option is introduced.

### Hermes image carries unused vestigial config
`harnesses.json` schema and the bundled `_DEFAULT_HARNESSES['hermes']` retain
`wrap_up_command: "/quit"` — the field is unused (per D-88 the adapter does
`docker stop` instead), and architecture.md now flags it as vestigial.
*Disposition:* prune the field from the schema + bundled config when the
harness-config schema next gets a touch.

### Idle-detection signal set is fixed-coded
`enforcement.py`'s hybrid-idle signals (CPU + net/block I/O + event-file +
request-channel mtimes) and CPU threshold are hard-coded constants. For a
v1.0 / Stage 20 pass, may want to make these configurable per-profile.
*Source:* D-166 / `whizzard/enforcement.py`.
*Disposition:* defer to v1.0 / OSS-launch.

### Config loaders re-read JSON on every call; no caching
`config.load_profiles()`, `harness_config.load_harnesses()`,
`preset_config.load_presets()`, and `mounts.load_mounts()` re-read and
re-validate the JSON file every time they're invoked. A single CLI run
often calls them several times (completion, launch, snapshot writer). Not
a correctness bug today, but the "this file is read once per session"
mental model is wrong, and a malformed-after-launch config could raise
mid-session in unexpected places.
*Source:* catch-up review 2026-05-23 finding F-A-08.
*Disposition:* defer to v1.0 / OSS-launch.

### Integration test fixture: image-staleness detection
`whizzard_hermes_image` fixture currently checks only that the image exists,
not that it's current relative to `Dockerfile.hermes`. A stale image (built
before a Dockerfile change) would silently pass the existence check and
fail downstream smokes mysteriously. Acceptable for the maintainer-on-Mac
workflow today; needs hardening for CI.
*Disposition:* defer; revisit if it bites.

---

## Process risks

### Pace + no formal review-gate combination
The maintainer + AI-pair workflow can land a large volume of code in one
session without an explicit second-pair-of-eyes review. The integration
smoke harness catches *wiring* bugs (the MCP `tool_*` registration bug is
the proof); it does not catch *design-level* issues (API choice, abstraction
quality, security trade-offs).
*Mitigation:* the `work-wrap-up` skill surfaces `/ultrareview` as the
recommended review checkpoint at `/wrap-up stage`. Build the habit of
running it at meaningful milestones.

### Lightweight post-mortem discipline (now codified)
When a real bug surfaces (M7 nested-mount, MCP `tool_*` registration),
lessons were discussed implicitly but not always codified. A
durable-lesson rule is now captured as `feedback_postmortem_pattern` in
project memory — when a real bug surfaces, capture *what got missed* and
*what would have caught it earlier* as a small feedback memory or
known-issues entry.

### Documentation drift between architecture / build plan / decisions
Architecture.md, the build plan, and decisions.md can drift relative to
each other and the code (the 2026-05-22 cross-check found 8 issues, all
docs-lagging-code). The full cross-check is a periodic-judgment-pass
discipline; the `work-wrap-up` skill's quick alignment check catches the
common cases per-boundary.
*Mitigation:* lightweight check on every wrap-up; full cross-check every
~10 stages or every ~6 weeks.

### Solo code-review until OSS-launch
Beyond the maintainer + Claude, no second pair of human eyes on changes.
External reviewers are planned for Stage 20.
*Mitigation:* `/ultrareview` (via the wrap-up skill) for now;
external-reviewer pass at OSS-launch.

---

## How to keep this doc useful

Add an entry when:
- a bug-find surfaces a durable lesson (link the commit or decision).
- a tech-debt item gets identified during real work (don't lose it in
  conversation).
- a known process gap is identified (mitigation goes here, the *rule*
  goes in a feedback memory).

Remove an entry (move to `git log` history) when:
- the underlying issue is resolved.
- the deferred feature ships.

Aim to keep entries short; this is an index, not a discussion forum. Per
`feedback_decisions_succinct` — the doc earns its keep by being scannable.

*Last reviewed: 2026-05-22.*
