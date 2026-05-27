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

### `mark_resolved` audit-log race — denial can vanish on cell-mirror write failure
`mark_resolved` writes the authoritative resolution to the host-only
store FIRST, then mirrors to the cell file, THEN emits the F-D-03
`session_request_resolved` audit-log event for denied/error
outcomes. If the cell-mirror write (`tmp.write_text` / `tmp.replace`)
fails — disk-full, the cell removed its requests/ dir mid-flight,
permission flake — the exception propagates and the `append_event`
call never runs. The host store has the truth but `sessions.jsonl`
shows no record of the denial.
*Source:* catch-up review pass 2 finding B4.
*Disposition:* defer — design call on write ordering. Cleanest fix:
emit the audit-log event BEFORE the cell-mirror write, OR wrap the
mirror write in try/except so the audit log still gets the entry on
mirror failure. Either order has trade-offs (audit-before-mirror: log
claims a resolution that may not be visible to the cell yet;
mirror-before-audit-with-try: audit lands even if mirror fails but the
operator's at-the-moment "denial confirmed" view diverges from
durable state).

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

### CLI flag parsing accepts empty strings for `--harness` / `--profile` / `--mount`
Typer does not validate string-typed options as non-empty by default.
Examples like `whiz run --harness ""` or `whiz run --mount ""` pass an
empty string through to the registry lookup, which then errors with
`unknown harness ''` or `mount spec '' not registered`. Errors are
technically clear but the empty-string case would be cheaper to
reject earlier with a flag-specific message ("--harness requires a
non-empty name"). Shell-quoting accidents (`--harness ""` in a script)
surface as registry errors instead of arg-parsing errors.
*Source:* catch-up review 2026-05-23 finding F-H-04.
*Disposition:* defer — UX polish, not a correctness bug; cheap to
add when next touching the CLI flag layer.

### `whiz status` reads the entire sessions.jsonl every invocation
`_read_session_events` does `SESSIONS_LOG.read_text().splitlines()`
and parses every entry. No rotation, no head/tail bound. `whiz`
(bare) and `whiz status` invoke it on every CLI launch. After months
of daily use the file grows linearly and status will perceptibly
stall. Parallel to F-E-05 (in-cell `whiz_audit_self` slurps the
whole log too). Both want the same eventual fix: audit-log rotation
+ streaming reads with optional `since=<ts>`.
*Source:* catch-up review 2026-05-23 finding F-H-06.
*Disposition:* defer — quality improvement when audit-log rotation
lands OR Stage 20 hardening pass.

### Wake selection-rule doc and code use different phrasings
D-169 describes the wake-eligibility rule as "most-recent session with
`expiry_reason: idle` AND no subsequent `session_start` for that sid".
The implementation tracks `session_woken` events instead and excludes
sids that appear as `superseded_session_id` in such events. The two are
behaviorally equivalent today (every adjust and wake mints a new sid),
so this is purely a doc/code drift — no behavior change required.
Cleanest fix: reconcile the D-169 text with the actual implementation
(or, equivalently, add a code comment in `wake._build_index` pointing
to the D-169 phrasing as an alternative invariant).
*Source:* catch-up review 2026-05-23 finding F-G-13.
*Disposition:* defer — doc reconciliation, no behavior change.

### Unlimited-profile enforcer can hang forever if `docker run` client wedges
When both `duration_seconds` and `idle_timeout_seconds` are `None`,
`monitor_and_enforce` calls `proc.wait()` with no timeout — pre-Stage-15
behavior, not a regression. If the docker-run client process wedges
while the container stays alive (rare; bad-virtio-state class of bug),
the enforcer hangs the host indefinitely. With duration/idle now
first-class capabilities, the unlimited-profile case is precisely the
one that wants a watchdog the most. Fix is a periodic liveness probe
on the unlimited path — bigger than a one-line patch, overlaps with
the Stage 20 hardening pass.
*Source:* catch-up review 2026-05-23 finding F-F-05.
*Disposition:* defer — enforcement-watchdog design pass or Stage 20.

### Sub-agent permission scoping — none today
Whizzard's containment boundary is the docker container. Every process
inside the cell — the parent agent, Hermes-spawned workers, tool
subprocesses — shares the parent's full permission set: mount list,
network, time budget, credentials, request-channel access. A buggy or
compromised sub-agent has the same blast radius as the parent. Adequate
for the MVP threshold (D-101: single trusted user); becomes a real
defense-in-depth question for OSS launch when users may run third-party
agent code. The path forward is sub-cells via host request (one
Whizzard cell per scoped sub-agent), which keeps D-9 and D-164 intact.
*Source:* D-171 (open); catch-up review 2026-05-23 Chunk E discussion.
*Disposition:* defer to OSS-launch milestone planning (D-131).

### `whiz_audit_self` reads the entire host audit log per call
The in-cell MCP tool `tool_whiz_audit_self` loads the full audit log
with `read_text().splitlines()`, then filters in Python. The log is
append-only and accumulates entries across every session for the
lifetime of the install — no rotation. An agent polling
`whiz_audit_self` on a long-lived install pays O(total-log-bytes) RAM
per call. The Chunk D F-D-04 fix applied streaming to
`merge_agent_events` on the host side for the same reason; the
cell-side read deserves the same treatment plus an optional
`since=<ts>` argument so the agent can ask for incremental tail.
*Source:* catch-up review 2026-05-23 finding F-E-05.
*Disposition:* defer — quality improvement when audit-log rotation
lands OR Stage 20 hardening pass; no current install long-lived enough
for it to bite.

### Safety policy two-way intersection check applies only to deep hard-blocks
`safety.py`'s module docstring promises a "two-way intersection check" for
all blocked-path tiers, but only `_DEEP_HARD_BLOCKS` actually uses
`_intersects`. `_BROAD_FOLDERS` and `_CLOUD_SYNC_ROOTS` are checked one-way
(`p inside b`). Currently unreachable on macOS because the broader parents
that would trigger two-way matching (`$HOME`, `/`) are already Tier-1a
hard-blocked. Becomes relevant when Linux paths land — e.g., a deeper sync
root like `/srv/cloud-sync/<user>/Dropbox` would not be caught if a user
mounted `/srv/cloud-sync/<user>`.
*Source:* catch-up review 2026-05-23 finding F-D-07.
*Disposition:* defer — fix when adding the first Linux-specific path to
`_BROAD_FOLDERS` or `_CLOUD_SYNC_ROOTS`.

### Per-session directories under `~/.whizzard/sessions/` never cleaned up
Each launch creates `~/.whizzard/sessions/<sid>/` with snapshot.json,
events.jsonl, and request/resolution dirs. Nothing in the codebase ever
removes them; long-running installs accumulate one dir per session. Each
dir is small (KB) so urgency is low; the fix needs a retention policy
(N days? referenced-by-audit-log? `whiz sessions clear`?) that's a design
call, not a one-line change.
*Source:* catch-up review 2026-05-23 finding F-D-09.
*Disposition:* defer — natural home is Stage 18 (image management) or a
dedicated retention-policy feature.

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

### CHANGELOG format reframe pre-OSS-launch
The current `CHANGELOG.md` is engineering-tone — long bullets with
decision IDs (D-46 etc.), internal terminology, retrospective context.
That's appropriate for the MVP-internal phase but not what an OSS
audience expects from a CHANGELOG. Maintainer plan: at OSS launch,
move the existing CHANGELOG.md to `docs/engineering_log.md` (still in
the repo, signaled-as-internal via the filename) and start a fresh
user-facing `CHANGELOG.md` with the typical one-line-per-entry shape.
Stays a deferred decision until the OSS-launch milestone (D-131).
*Source:* catch-up review 2026-05-23 conversation about CHANGELOG
detail level matching the project's actual audience.
*Disposition:* defer — execute alongside Stage 19/20 OSS-launch prep.

### Pre-OSS-launch PII / history scrub — MUST run before going public
Catch-up review of 2026-05-23 scanned tracked files for sensitive
content. Concrete disclosures found in the live tree:

1. **`docs/session_handoff.md:13`** — full PII paragraph: "**Bryan
   Garrett** (`<redacted>`, `BuckG71` on GitHub)". Full
   name + personal email + GitHub handle in one line.
2. **`/Users/USER/...` paths in 15 places across 3 files** — mostly
   in `docs/stage_validation.md` (12 occurrences, real `cd` commands
   captured during testing), plus `docs/decisions.md` (2x) and
   `docs/session_handoff.md` (1x). Reveals the maintainer's macOS
   username + local directory layout.
3. **Personal email `<redacted>`** in
   `docs/session_handoff.md` — single occurrence; LICENSE +
   `pyproject.toml` use the bare name (no email), which is fine.
4. **`<host>.tailnet` hostname** in
   `docs/home_lab_deployment.md:70-72` — reveals home-lab device
   naming + that the maintainer runs a tailnet.

**Why this needs explicit tracking:** editing the files only adds new
state. Old commits remain reachable via `git log -p`, `git show
<old-commit>`, or GitHub's file-history UI. The ONLY way to actually
scrub history is `git filter-repo` (the modern replacement for
`git filter-branch`), which rewrites every commit that touched the
sensitive content and changes every commit SHA.

**Window:** the repo is currently private — that's the only clean
moment to rewrite history. Once public, forks/clones spread the old
state, GitHub's reflog retains rewritten history for ~90 days, and
search engines may have indexed file contents. Effectively impossible
to fully recall post-launch.

**Going forward (maintainer plan):** to prevent re-capture of the
macOS username (`USER`) into future paths/output, move dev into a
containerized environment (option (c) from the 2026-05-23 discussion).
Mitigations (a) "manual sanitization before commit" and (b) "rename
the macOS user" are inferior — (a) requires constant discipline,
(b) is a large user-account migration.

*Source:* catch-up review 2026-05-23; D-173 deliverable (f);
`docs/mvp_build_plan.md` Stage 20 deliverable 8.
*Disposition:* **OSS-launch blocker.** Schedule the `git filter-repo`
pass + verification (`git log -p | grep` returns nothing for the four
strings above) into Stage 20 (Security Review & Hardening Audit).
Containerized-dev-environment setup is parallel work, separate from
the history scrub itself.

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
