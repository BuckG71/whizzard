# Whizzard — Known Issues, Deferred Work, and Tech Debt

A consolidated index of things known not to be ideal in the project right now.
Most entries link out to a canonical source (decision, build plan stage) — the
value of this doc is the *single cross-cutting view*, not duplicate copy of
those sources.

Categories:
- **Functional gaps** — works differently than designed/documented.
- **Deferred features** — known-deliberate "not yet" items.
- **Tech debt** — code/structure improvements desired.

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
*Source:* maintainer working notes.
*Disposition:* Stage 9 follow-up — add an `oiq hermes profile sync-mcp`
verb or fold into `oiq hermes profile create`.

### D-157 user-config drift
The maintainer's personal `~/.whizzard/config/profiles.json` predates several
schema additions (`allow_broad_mount` default per D-157, now
`idle_timeout_seconds` per Stage 15). Bundled defaults updated; the personal
file needs syncing for the changes to take effect locally.
*Source:* maintainer working notes.
*Disposition:* a one-time `whiz profiles init --force` (or manual edit) when
convenient.

---

## Deferred features (planned, on the roadmap)

### Stage 15.5 — Hot-restart of idle-ended sessions
Spec in the build plan; not implemented. `whiz resume <sid>` verb (+ bare
`whiz r` resuming the most-recent idle-ended session). Restricted to
`expiry_reason == idle` so duration caps can't be circumvented.
*Source:* roadmap §Stage 15.5.

### Stages 16–17 — Discord control plane
Read-only (16) then write/approve (17). Both carry a D-148 design pause
requirement before any coding.
*Source:* roadmap §Stages 16, 17.

### MVP+ Stage 19 — Packaging & Install
Published Python distribution, execution-image distribution, clean-machine
install verification, first-run config init. Pre-OSS-launch gate.
*Source:* roadmap §Stage 19.

### MVP+ Stage 20 — Security review & hardening audit
Consolidated threat model (`docs/threat_model.md`, not yet written),
adversarial red-team suite (partially started),
fail-closed audit closing D-133, injection / command-construction audit,
credential-handling audit, supply-chain scan in CI, independent reviewer
pass. Pre-OSS-launch gate.
*Source:* roadmap §Stage 20; closes D-131 / D-133.

### Whizzard → Osmotiq rename
Triggered after MVP operational, before Hermes migration. CLI becomes `oiq`;
`osmotiq.ai` owned. **Wizard rename ripple:** `whiz init`'s detect-and-clone
flow creates `~/.hermes-whizz/` as the Hermes profile target; when the
product name changes, that path needs to rename in lockstep (likely
`~/.hermes-oiq/` or whatever the final CLI name becomes). User-facing
migration: `mv ~/.hermes-whizz ~/.hermes-oiq` + update any presets that
reference it.
*Source:* D-158.

### `ADAPTER_SPEC.md` (OSS-launch artifact)
Contributor-facing adapter Protocol artifact. Decided but not authored.
*Source:* D-160.

---

## Tech debt

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
*Disposition:* defer — natural home is a dedicated retention-policy feature
(Stage 18 chose not to absorb it; the design call — N days? referenced-by-log?
`whiz sessions clear`? — is bigger than image management cleanly carries).

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

### GitHub Actions: Node.js 20 deprecation in release workflow
`.github/workflows/release.yml` uses `actions/checkout@v4`,
`actions/setup-python@v5`, and `actions/upload-artifact@v4` — each
still on the Node.js 20 runtime. GitHub flagged these as deprecated
during the v0.1.0rc1 publish run on 2026-05-29. Node 20 is removed
from GitHub-hosted runners on 2026-09-16; Node 24 becomes the default
on 2026-06-16. The same deprecation applies to `.github/workflows/ci.yml`.
*Disposition:* defer until an upstream version of each action ships
Node-24-native (most likely well before September). Bump action
versions in one maintenance commit; no functional change expected.

## How to keep this doc useful

Add an entry when:
- a bug-find surfaces a durable lesson (link the commit or decision).
- a tech-debt item gets identified during real work (don't lose it in
  conversation).

Remove an entry (move to `git log` history) when:
- the underlying issue is resolved.
- the deferred feature ships.

Aim to keep entries short; this is an index, not a discussion forum. Per
`feedback_decisions_succinct` — the doc earns its keep by being scannable.

*Last reviewed: 2026-05-22.*
