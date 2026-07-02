# Whizzard — Known Issues, Deferred Work, and Tech Debt

A consolidated index of things known not to be ideal in the project right now.
Most entries link out to a canonical source (a decision in `docs/decisions.md`
or an architecture invariant) — the value of this doc is the *single cross-cutting
view*, not duplicate copy of those sources.

Categories:
- **Functional gaps** — works differently than designed/documented.
- **Deferred features** — known-deliberate "not yet" items.
- **Tech debt** — code/structure improvements desired.

**Terminology:** "sandbox" throughout this document refers to the hardened Docker container Whizzard launches each agent session inside.

---

## Functional gaps

### Windows support is unverified end-to-end (not yet run on a real Windows box)
The codebase was developed and tested on macOS, with Ubuntu + macOS CI.
Addressed on the `windows-portability` branch:
- **The two launch-time crashes are guarded** (`os.getuid` in the UID-parity
  path; `_is_pid_alive`'s POSIX signal-0 idiom) — both branch on
  `os.name == "nt"`, macOS/Linux untouched.
- **Safety blocklist now has a validated Windows set** (`safety._windows_exclusions`,
  merged when `os.name == "nt"`): `AppData` (the `~/Library` analog — browser
  creds, Credential Manager store, DPAPI master keys, gnupg, gcloud), `C:\Windows`,
  `C:\ProgramData`, the system-drive root, `~/.azure`/`~/.kube`, `Videos`, and cloud
  roots led by OneDrive (incl. the `OneDrive - <Company>` business-naming prefix
  match) + iCloudDrive. Unit-tested cross-platform via a simulated Windows HOME.

Remaining (genuinely open):
- **Not run end-to-end on a real Windows box.** The path-matching is unit-verified,
  but a live `whiz init` → `whiz r hermes` round-trip on Windows + Docker Desktop
  has not happened.
- **Bind-mount path translation untested.** `-v C:\Users\…:/container` relies on
  Docker Desktop's handling; the drive-letter colon vs the `-v` field separator
  is a known fragility, not yet exercised.
- **No Windows CI lane** — the unit suite has never run on Windows.
- The `\\.\pipe\docker_engine` Docker "socket" isn't `-v`-mountable like the Unix
  socket, so it's documented rather than path-blocked.
*Source:* portability review + validated exclusion research 2026-06; `windows-portability` branch.
*Disposition:* before any "Windows supported" claim — add a Windows CI lane and an
end-to-end launch verification on a real Windows box. The README's "pre-release
verification" wording stands until then.

### OneCLI integration is functionally inert
Whizzard integrates with OneCLI (a separate command-line credential vault) to
fetch secrets without writing them to disk. The integration's `fetch_secret`
helper calls `onecli secrets get`, which does not exist in the actual OneCLI
CLI surface; every invocation falls through to the env-var fallback. The
integration nominally exists but never does the OneCLI thing.
*Source:* `docs/decisions.md` §D-162 Notes.
*Disposition:* decide — fix to match the real OneCLI surface, or drop the
direct integration and leave only env-var-fallback.

### Hermes full-chat smoke needs HERMES_HOME setup
The Hermes integration smoke verifies the deployment + Ollama reachability +
that `hermes -z` is wired, but does not drive a real chat against Ollama.
`hermes -z PROMPT` requires a configured HERMES_HOME (`config.yaml` +
Hermes-state files); the smoke doesn't currently provision one.
*Source:* internal smoke notes.
*Disposition:* either bundle a smoke-test HERMES_HOME or document that the
heavier smoke needs the user's `~/.hermes-whizzard-sandbox`. Tracked as the
"next-level Hermes-integration smoke."

### Hermes `config.yaml` MCP auto-wiring is manual
The Hermes adapter sets the WHIZ_* env vars for the in-sandbox MCP server, but
the harness-side `config.yaml` MCP-client entry pointing at
`python /opt/whiz/mcp_server.py` is still a manual user step.
*Source:* maintainer working notes.
*Disposition:* add a `whiz hermes profile sync-mcp` verb or fold into
`whiz hermes profile create`.

### Maintainer's personal config predates schema additions
The maintainer's personal `~/.whizzard/config/profiles.json` predates several
schema additions (most recent: `idle_timeout_seconds` from the
duration-enforcement work). Bundled defaults updated; the personal file
needs syncing for the changes to take effect locally.
*Source:* maintainer working notes.
*Disposition:* a one-time `whiz profiles init --force` (or manual edit) when
convenient.

### In-cell first-run Hermes setup poisons the profile (conflicts with D-80)
When the cell's Hermes isn't configured, it offers a first-run setup wizard;
if the user authenticates there (e.g. Claude OAuth), Hermes writes `auth.lock`
(and credential state) into its `HERMES_HOME` — which is the *mounted* profile.
That write persists to the host profile, and D-80's mount-time preflight then
**refuses to mount a profile containing `auth.lock`** — bricking every
subsequent launch. So the "run setup inside the cell" first-run path (assumed
to be the desired UX) creates exactly the file D-80 forbids. The intended model
is creds-via-env (D-134/D-162); the cell should never authenticate into its
mounted profile. Surfaced on the Windows test 2026-06-04.
*Fix direction (pending the install-order decision):* the cleanest fix removes
the in-cell-setup path entirely — require a *configured* host Hermes before
`whiz init` and always clone it (auth excluded), so the cell never prompts for
setup. Couples to the open question of whether to make host-Hermes-first a hard
prerequisite (strengthening D-182) + a clean credential-via-env path
(`secrets:` injection, since the clone carries config but not credentials).
*Disposition:* **launch-blocker resolved** — D-182 makes host-Hermes-first the
model (a configured host profile is cloned with auth excluded), and D-184/D-187
mediation hands the cell a placeholder + broker URL so it never authenticates
into its mounted profile — the `auth.lock` poison path can't fire on the
documented flow. *Residual (post-launch hardening):* confirm/suppress the cell's
Hermes first-run setup wizard so a user can't manually trigger in-cell auth.

### Cell credential injection has no auto-wiring; OAuth path hides the token value
The cell gets LLM credentials via the harness config's `secrets:` block — env
injection sourced from OneCLI or a host env-var fallback (D-134/D-162). The
*mechanism* works (validated in M7 smoke), but there is **no auto-wiring**: the
user must manually add `"secrets": ["<VAR>"]` to `hermes-cell` and export the
matching env var. Worse on the OAuth/Claude-Max path — choosing "Claude Pro/Max
OAuth" in `hermes setup` stores the credential in *Claude Code's credential
store* (host), not in a file/env the cell can read (and the clone strips `.env`
per D-80 anyway). So there is **no token value to inject**: the user has to know
to run `claude setup-token` separately to mint an explicit `sk-ant-oat01-…` for
`CLAUDE_CODE_OAUTH_TOKEN`. Non-obvious, and each mint adds a 1-year token to the
account. Surfaced on the Windows fresh-install test 2026-06-04.
*Fix direction:* wizard auto-wiring — detect the configured provider/auth
method and wire the `secrets:` entry: for API-key providers, prompt for the key
+ env var; for the OAuth path, prompt to mint a token (`claude setup-token`) and
wire `CLAUDE_CODE_OAUTH_TOKEN`. Consider OneCLI/vault as the non-plaintext
default once OneCLI is real (it is currently inert).
*Provider-scale dimension (needs exploration — surfaced 2026-06-05):* Hermes
supports ~20 inference providers, and to be a real harness wrapper Whizzard must
support all of them — across **two** seams that both currently assume Anthropic:
(1) the **cell image bakes in `anthropic` only** (`Dockerfile.hermes` hardcodes
the SDK), so the provider SDK needs parameterizing (build `ARG` derived from the
configured provider, or bundle the common set) — fold into the version-bump
unit; (2) **credential injection per provider** — each provider has its own
key/env var, so the current "manually add a `secrets:` entry + `export` one env
var" path scales poorly to 20 providers (friction + error-prone, easy to set the
wrong var). This is the strongest argument to **make the OneCLI integration real
sooner rather than later**: a vault that resolves credentials by name removes the
manual-env-var sprawl entirely and is the clean substrate for multi-provider
support. Explore the full ramifications (which providers to bundle vs. install
on demand, how the wizard picks the provider, OneCLI rollout sequencing) before
committing to an approach.
*Cross-harness (maintainer note 2026-06-05):* credential handling is not a
Hermes problem — **every** harness Whizzard adds (Claude Code, Codex, NanoClaw,
…) brings its own provider/auth model and its own set of keys. So the real
deliverable is a **comprehensive, harness-neutral credential-handling plan** (a
credential layer the adapters plug into), not a per-harness patch. Treat this as
a first-class design workstream, not a Hermes footnote.
*Disposition:* **launch-blocking core RESOLVED** — Anthropic credential
onboarding is handled by D-185 (the `whiz init` credential step) + D-184 (bar-C
broker) + D-187 (onecli/hybrid), so a fresh user reaches a working, credential-
private cell without hand-editing config. *Residual (post-launch, not blocking —
Anthropic-first is the launch scope per D-183/184/185):* the provider-scale piece
(multi-provider SDK in `Dockerfile.hermes` + per-provider credential injection)
and the harness-neutral credential-layer plan remain their own design workstreams.

---

## Deferred features (planned, on the roadmap)

### Discord control plane (read-only, then write/approve)
Two-phase work: a read-only Discord surface for approval visibility, then
write/approve flow on top. Carries a design-pause requirement before any
coding — a UX-shaped change.
*Source:* roadmap (post-launch).

### Security review & hardening audit
Adversarial red-team suite expansion, a "does the system fail closed when
config is missing or corrupt?" audit, injection / command-construction
audit, credential-handling audit, supply-chain scan in CI, independent
reviewer pass. Pre-OSS-launch gate. The consolidated threat model at
`docs/threat_model.md` is the anchor.

### `ADAPTER_SPEC.md` (OSS-launch artifact)
Contributor-facing adapter Protocol artifact. Decided but not authored.

### Network allowlist must handle the hostname parser-differential class
ROADMAP goal 11's host-side egress proxy is the same shape as the
allowlist Claude Code shipped a CVE-class bypass against in
v2.0.24–v2.1.89: an attacker hostname `attacker.com\x00.google.com`
passed JS `endsWith()` (saw `.google.com`) while libc's `getaddrinfo()`
truncated at the null byte and resolved `attacker.com` — parser
differential between matcher and resolver. Implementation invariants for
our proxy:
- Normalize through a single parser before matching, or keep matcher and
  resolver in one language/stdlib end-to-end.
- Reject `\x00`, `%`, CRLF, anything outside DNS-allowed characters
  before matching.
- Cap input length.
- Adversarial test corpus: null injection, URL-encoded bypasses, IDN
  lookalikes, trailing-dot quirks, SOCKS5 `DOMAINNAME` edge cases.
*Source:* silent fix in Claude Code v2.1.90 / `sandbox-runtime 0.0.43`
(2026-04-01); researcher Aonan Guan, HackerOne #3646509.
*Disposition:* design constraint for goal 11 implementation; not
actionable until that work begins.

---

## Tech debt

### In-sandbox `snapshot.json` is writable by the agent
The per-session `/run/whiz` mount is `:rw` because the sandbox legitimately writes
`events.jsonl` and `requests/*.json` there. `snapshot.json` (the agent's
launch-time capability view, written by Whizzard for the agent to read) lives
in the same dir, so the sandbox can overwrite it. The host-side audit log
(mounted `:ro`) is still the source of truth — containment is intact — but the
cooperation-layer "honest self-reflection" guarantee leaks: a compromised
harness could lie to itself about its own permissions via `whiz_status`.
*Source:* internal code review.
*Fix shape:* split `/run/whiz` into a `:ro` snapshot mount and a `:rw`
events/requests mount, OR expose the snapshot through the in-sandbox MCP server
instead of as a file. Either way it amends the existing in-sandbox-MCP
decision (D-156).
*Disposition:* security-review backlog, or a decision-needed item earlier
if it bothers us.

### No test for agent-event merge ordering vs `session_end`
`run_shell` documents in code that agent events MUST be merged into the
audit log before the `session_end` event so the log is temporally
ordered. No unit test populates `event_log_path(session_id)` then asserts
the merged events appear between `session_start` and `session_end`.
Integration smokes would catch a real ordering bug, but fast unit coverage
is missing.
*Source:* internal code review.
*Disposition:* track for the session-lifecycle / audit review pass —
that area's review already touches the audit-log assertion machinery.

### CLI flag parsing accepts empty strings for `--harness` / `--profile` / `--mount`
Typer does not validate string-typed options as non-empty by default.
Examples like `whiz run --harness ""` or `whiz run --mount ""` pass an
empty string through to the registry lookup, which then errors with
`unknown harness ''` or `mount spec '' not registered`. Errors are
technically clear but the empty-string case would be cheaper to
reject earlier with a flag-specific message ("--harness requires a
non-empty name"). Shell-quoting accidents (`--harness ""` in a script)
surface as registry errors instead of arg-parsing errors.
*Source:* internal code review.
*Disposition:* defer — UX polish, not a correctness bug; cheap to
add when next touching the CLI flag layer.

### `whiz status` reads the entire sessions.jsonl every invocation
`_read_session_events` does `SESSIONS_LOG.read_text().splitlines()`
and parses every entry. No rotation, no head/tail bound. `whiz`
(bare) and `whiz status` invoke it on every CLI launch. After months
of daily use the file grows linearly and status will perceptibly
stall. Parallel to the in-sandbox finding below (`whiz_audit_self` slurps the
whole log too). Both want the same eventual fix: audit-log rotation
+ streaming reads with optional `since=<ts>`.
*Source:* internal code review.
*Disposition:* defer — quality improvement when audit-log rotation
lands OR security-review backlog.

### Wake selection-rule doc and code use different phrasings
The decision record (D-169) describes the wake-eligibility rule as
"most-recent session with `expiry_reason: idle` AND no subsequent
`session_start` for that sid". The implementation tracks `session_woken`
events instead and excludes sids that appear as `superseded_session_id`
in such events. The two are behaviorally equivalent today (every adjust
and wake mints a new sid), so this is purely a doc/code drift — no
behavior change required. Cleanest fix: reconcile the decision text with
the actual implementation (or add a code comment in
`wake._build_index` pointing to the decision's phrasing as an alternative
invariant).
*Source:* internal code review.
*Disposition:* defer — doc reconciliation, no behavior change.

### Unlimited-profile enforcer can hang forever if `docker run` client wedges
When both `duration_seconds` and `idle_timeout_seconds` are `None`,
`monitor_and_enforce` calls `proc.wait()` with no timeout — this is the
pre-existing behavior from before duration/idle enforcement landed, not
a regression. If the docker-run client process wedges
while the container stays alive (rare; bad-virtio-state class of bug),
the enforcer hangs the host indefinitely. With duration/idle now
first-class capabilities, the unlimited-profile case is precisely the
one that wants a watchdog the most. Fix is a periodic liveness probe
on the unlimited path — bigger than a one-line patch, overlaps with
the security-review backlog.
*Source:* internal code review.
*Disposition:* defer — enforcement-watchdog design pass or the security review.

### Sub-agent permission scoping — none today
Whizzard's containment boundary is the docker container. Every process
inside the sandbox — the parent agent, Hermes-spawned workers, tool
subprocesses — shares the parent's full permission set: mount list,
network, time budget, credentials, request-channel access. A buggy or
compromised sub-agent has the same blast radius as the parent. Adequate
under the project's current single-trusted-user threshold; becomes a real
defense-in-depth question for OSS launch when users may run third-party
agent code. The path forward is sub-sandboxes via host request (one
Whizzard sandbox per scoped sub-agent), which preserves the one-way
capability-flow and no-docker-socket invariants.
*Source:* D-171 (open); internal code review.
*Disposition:* defer to OSS-launch milestone planning.

### `whiz_audit_self` reads the entire host audit log per call
The in-sandbox MCP tool `tool_whiz_audit_self` loads the full audit log
with `read_text().splitlines()`, then filters in Python. The log is
append-only and accumulates entries across every session for the
lifetime of the install — no rotation. An agent polling
`whiz_audit_self` on a long-lived install pays O(total-log-bytes) RAM
per call. A prior internal-review fix applied streaming to
`merge_agent_events` on the host side for the same reason; the
sandbox-side read deserves the same treatment plus an optional
`since=<ts>` argument so the agent can ask for incremental tail.
*Source:* internal code review.
*Disposition:* defer — quality improvement when audit-log rotation
lands OR security-review backlog; no current install long-lived enough
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
*Source:* internal code review.
*Disposition:* defer — fix when adding the first Linux-specific path to
`_BROAD_FOLDERS` or `_CLOUD_SYNC_ROOTS`.

### Per-session directories under `~/.whizzard/sessions/` never cleaned up
Each launch creates `~/.whizzard/sessions/<sid>/` with snapshot.json,
events.jsonl, and request/resolution dirs. Nothing in the codebase ever
removes them; long-running installs accumulate one dir per session. Each
dir is small (KB) so urgency is low; the fix needs a retention policy
(N days? referenced-by-audit-log? `whiz sessions clear`?) that's a design
call, not a one-line change.
*Source:* internal code review.
*Disposition:* defer — natural home is a dedicated retention-policy feature
(the image-management work chose not to absorb it; the design call — N days?
referenced-by-log? `whiz sessions clear`? — is bigger than image management
cleanly carries).

### Hermes adapter `parent_dir` parameter has no input validation
`create_hermes_profile` validates the `name` argument (no slashes, no
leading dots, no reserved values) but accepts `parent_dir` as-is. Production
callers (`whiz hermes profile create`) pass `parent_dir=None` so the live
attack surface is zero; the gap only matters if a future `--profile-dir`
CLI flag or programmatic caller wires user input through. Treat as a
review requirement: any new caller that exposes `parent_dir` must
validate it.
*Source:* internal code review.
*Disposition:* defer — defensive hardening with no current path; would
add at the point a user-facing profile-dir option is introduced.

### Hermes image carries unused vestigial config
`harnesses.json` schema and the bundled `_DEFAULT_HARNESSES['hermes']` retain
`wrap_up_command: "/quit"` — the field is unused (the adapter performs
graceful shutdown via `docker stop` instead), and architecture.md now flags
it as vestigial.
*Disposition:* prune the field from the schema + bundled config when the
harness-config schema next gets a touch.

### Idle-detection signal set is fixed-coded
`enforcement.py`'s hybrid-idle signals (CPU + net/block I/O + event-file +
request-channel mtimes) and CPU threshold are hard-coded constants. For a
v1.0 / the security review pass, may want to make these configurable per-profile.
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
*Source:* internal code review.
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

### Wizard Hermes-not-installed branch links the repo but gives no install steps
Step 1b Branch B printed "Install Hermes on your computer" + the bare
`github.com/NousResearch/hermes-agent` URL — no steps, no necessity framing.
The README overclaimed it "prints install instructions". Surfaced during the
Windows clean-install test 2026-06-03.
*Resolved 2026-06-03 (D-182):* the harness is **user-supplied** — Whizzard
does not install it. An earlier plan to have the wizard run `pipx install
hermes-agent` (with a separate-terminal fallback) was **superseded**: the
user must run Hermes' interactive config to produce a usable `~/.hermes/`
regardless, so an inline install removes only one of two out-of-Whizzard
steps while adding harness-specific install knowledge to a harness-neutral
core (D-10). Branch B is now informational: necessity-first framing → the
three setup steps (install per Nous' instructions → configure → `whiz hermes
profile create main`) → the "you can finish init now" reassurance. The README
gained a "install a supported harness first" prerequisite. Still rejected:
synthesizing a minimal `~/.hermes/` (a profile the user didn't create would
shadow/conflict with a real install; we'd own a config format we don't
control — the host profile must come from Hermes itself).
*Remaining (separate unit):* declare the tested Hermes version in the
compatibility matrix + add host-version detect-and-warn at init/profile-create,
keyed off the cell's pinned version (couples to the `Dockerfile.hermes`
0.12→0.14 pin-bump, which needs an M7 smoke re-run). See D-182.

### onecli/hybrid: model-key placeholder is hardcoded to `ANTHROPIC_API_KEY`
In onecli/hybrid mode the adapter strips all fetched secrets and sets only
`ANTHROPIC_API_KEY=<placeholder>` so the client initializes. Correct for the
only shipped harness (Anthropic `hermes-cell`), but a non-Anthropic model whose
key env var differs would be stripped with no placeholder under its real name,
so that client fails to init even though OneCLI would inject the header.
*Source:* D-187 onecli review (2026-07-01), angles A/B/altitude.
*Disposition:* defer — single-provider scope today; thread the model-secret
name through `OneCLIContext` when the first non-Anthropic harness lands.

### onecli_gateway.py duplicates broker.py session-net helpers
`_docker`, `_slug`, `_older_than_grace`, `_reap_orphans`, and `_REAP_GRACE_S`
are copied from `broker.py` (now consistent, but two copies that can drift).
The `mediated_network` build_run_argv param is also overloaded to carry the
onecli/hybrid net (misleading name).
*Source:* D-187 onecli review (2026-07-01), altitude/cleanup angles.
*Disposition:* defer — extract shared session-net helpers (and rename the
param to `cell_network`) as a deliberate refactor, not under launch pressure.

### onecli/hybrid: watch-items (defensive)
`NO_PROXY` is set host-only (no `:port`) — fine for httpx/Hermes and the broker
still injects even if routed via OneCLI, but a strict client could differ; the
proxy-parse regex assumes `user:token@host:port` (fails closed on other shapes);
`onecli_gateway_available()` + `resolve_onecli_wiring()` do overlapping probes;
container_env's mode blocks are order-coupled (documented). All verified-working
against the current OneCLI.
*Source:* D-187 onecli review (2026-07-01), angles A/C/cleanup.
*Disposition:* defer — revisit if OneCLI's proxy shape changes or a non-httpx
harness is added.

### Dockerfile.hermes has mutable build inputs (supply-chain determinism)
The base and broker images are digest-pinned, but `Dockerfile.hermes` uses
`FROM whizzard-base:latest`, a short Hermes ref (`HERMES_REF=e8b9369a9`), and
open-ended `pip install "anthropic>=0.39.0"` / `mcp`. Less deterministic than
the surrounding security story.
*Source:* Codex security review (2026-07-01), finding #7.
*Disposition:* defer — full-SHA the Hermes ref + pin anthropic/mcp versions
(cheap) and pass the exact base digest into the Hermes build; batch into a
supply-chain pass rather than the launch critical path.

### OneCLI proxy-auth token lives in the cell env (delegated capability)
onecli/hybrid mode puts the gateway's basic-auth token in the cell's
`HTTP(S)_PROXY` (scrubbed from the audit log, but visible to the cell process).
A compromised cell could drive the gateway for anything its policy allows.
*Source:* Codex review (2026-07-01) #4, corroborating the D-187 onecli review.
*Disposition:* defer — inherent to an authenticating proxy; document the token's
scope/lifetime and, if OneCLI supports it, move to a per-session-scoped token or
per-attached-network gateway policy. See D-187 Notes.

## How to keep this doc useful

Add an entry when:
- a bug-find surfaces a durable lesson (link the commit or decision).
- a tech-debt item gets identified during real work (don't lose it in
  conversation).

Remove an entry (move to `git log` history) when:
- the underlying issue is resolved.
- the deferred feature ships.

Aim to keep entries short; this is an index, not a discussion forum. The
doc earns its keep by being scannable.

*Last reviewed: 2026-06-20.*
