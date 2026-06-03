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

### Wizard Docker preflight checks PATH only, not daemon reachability
`whiz init`'s only Docker check is `docker_available()` —
`shutil.which("docker") is not None` (binary on PATH). It then
unconditionally prints "✓ Docker is running". With Docker installed but
the daemon down (the common Docker-Desktop-not-started state — surfaced
live during the Windows clean-install test 2026-06-03), this asserts a
green state it never verified, then fails confusingly at `docker build`.
Violates fail-closed (D-133). Git needs no check (not a runtime dep);
Python's floor is pip-enforced via `requires-python`.
*Fix:* real preflight reusing the daemon-down detection that already
exists in `adjust.py` / `image_exists()` (`DockerDaemonError`, F-B-01 /
F-G-10). Four states: binary-missing → install hint; daemon-unreachable
→ "start Docker Desktop and re-run" (OS-aware); Windows-containers mode
→ "switch to Linux containers"; daemon-up-Linux → proceed. Folds in the
previously-deferred "daemon-down message clarity" item. Optionally expose
as `whiz doctor` (one preflight fn, two callers).
*Rendering (surfaced 2026-06-03):* Step 1 lists the Windows Linux-backend
requirement as a dim `›` advisory styled inline with two green `✓` checks,
so it reads as a pending/grayed checklist item that never resolves — users
assume it turns green after the build; it doesn't (it's a static print).
Redesign so every prerequisite line is a *verified* state: daemon
reachable ✓, Linux backend ✓ (or ✗ + abort on Windows-container mode),
recipe found ✓ — no advisory-dressed-as-check; non-Windows hosts skip the
backend line entirely rather than show a grayed item.
*Disposition:* fix before launch; UX-shaped, so design noted here first.

### Wizard Hermes-not-installed branch links the repo but gives no install steps
Step 1b Branch B (`init_wizard.py:1228-1230`) prints "Install Hermes on
your computer" + the bare `github.com/NousResearch/hermes-agent` URL —
no command, no steps. The README claims it "prints install instructions";
it only links. Surfaced during the Windows clean-install test 2026-06-03.
*Fix (near-term — behavior decided 2026-06-03):* replace the bare URL with
an explicit y/N "Install Hermes now?" prompt. On **yes**:
- if `pipx` is present → Whizzard runs `pipx install hermes-agent`
  (isolated CLI env; never touches Whizzard's own venv — the dep-hygiene
  property, enforced by construction; [[user_dep_hygiene]]). Hermes is an
  application you run, not a library Whizzard imports, so pipx is the
  idiomatic mechanism.
- if `pipx` is absent → do **not** silently fall back to `pip` (that would
  pollute Whizzard's venv). Instead print clear, complete instructions to
  run **in a separate terminal window** (keeping the wizard session
  intact): install pipx (`py -m pip install --user pipx` then
  `py -m pipx ensurepath`), then `pipx install hermes-agent`, then return
  and run `whiz hermes profile create whizz`.
Rejected plain auto-`pip install` (commingles Hermes' deps into Whizzard's
venv). "Easier than yolo" without silent shared-env pulls.
*Also (UX, surfaced 2026-06-03):* reorder Branch B — lead with why a
harness is required ("Whizzard runs an agent harness in the sandbox; it
needs at least one installed and configured to do its job"), then the
"you can finish init now, but nothing launches until it's done"
reassurance (currently buried at the bottom and worded to undersell the
necessity). The y/N install prompt must carry this context so declining
is an informed choice.
*Considered and rejected:* having Whizzard generate a minimal `~/.hermes/`
profile to drop the host-Hermes prerequisite. A synthesized profile the
user didn't create would shadow or conflict with a real Hermes install
later, with unclear provenance/authority — and we'd own a config format we
don't control. The host profile must come from Hermes itself.
*Disposition:* near-term fix (real command + opt-in + reorder) before launch.

### BUG: `_prompt_numeric_choice` silently drops its question (wizard-wide)
`init_wizard._prompt_numeric_choice(message, options)` accepts a `message`
(the question) but never prints it — it renders the numbered options then
`choose:`, discarding the question. Every numbered prompt in `whiz init`
(network, time limit, idle limit, mounts, presets…) is therefore missing
its question. Surfaced at the mount step during the Windows test
2026-06-03: the prompt read as a bare "1) Yes  2) No  choose:" with no
indication of what was being chosen.
*Fix:* one line — print `message` (styled) above the options loop. Verify
every call site reads sensibly once the question is shown. High impact,
trivial fix.
*Disposition:* fix before launch (bug, not polish).

### Mount step has no directory-creation affordance + no early path validation
Step 3's mount loop (`step_3_mounts`) stores the typed path verbatim
(`host_path: path_raw`) without checking it exists, and offers no way to
create a folder for users who don't already have one. Surfaced Windows
test 2026-06-03.
*Fix:* after the path is entered, resolve and check existence; if missing,
offer to create it (`mkdir parents=True`) or re-enter. Critically, run the
path through `safety.check_mount_path` *before* creating/registering, so
the wizard never `mkdir`s (then mounts) a hard-blocked location — early
validation also catches denylisted paths at wizard time instead of
deferring the failure to launch.
*Disposition:* fix before launch (bug + small feature).

### CLI help legibility + the `whiz`/`whizz` naming collision
Cluster surfaced during the Windows test 2026-06-03 (`whiz --help` review):
- **Command ordering:** top-level commands render in an arbitrary order with
  shortcuts interleaved. Regroup into function panels via Typer
  `rich_help_panel` (one-line per command): Setup (init, image) · Launch
  (run, preset, hermes) · Control a running session (status, adjust, wake,
  requests) · Inspect (profiles, mounts, harnesses, sessions) · Shortcuts.
  Alphabetical within each panel. (Grouping shape pending maintainer confirm.)
- **`whiz` prefix + flag discovery not obvious:** bare command names don't
  signal they're invoked as `whiz <command>`, nor that per-command flags are
  found via `--help`. Add a Typer `epilog=` footer to `whiz --help`, rendered
  below the panels: "Run any command as `whiz <command>`. See a command's
  flags with `whiz <command> --help`." (Maintainer specifically wants the
  flag-discovery line surfaced on the top-level help.)
- **Shortcuts need descriptions:** `r/s/p/m/pr` listed bare are unguessable.
  Their panel must annotate each (r → run/preset, s → status, p → preset
  list/show, m → mounts list, pr → profiles list).
- **Nested-command discoverability:** the wizard hands users the 4-deep
  `whiz hermes profile create <name>`, which (correctly, per Typer) doesn't
  appear in top-level help. Cross-reference `whiz hermes --help` in the
  wizard's completion summary so the path is findable.
- **`whiz` vs `whizz` collision (real bug):** the example/default Hermes
  profile name `whizz` differs from the `whiz` command by one letter and sits
  adjacent in `whiz hermes profile create whizz` — reads as a typo, obscures
  which token is verb vs argument. Rename to a *role* name (proposed `main`
  → `~/.hermes-main`); the token also lives in the bundled preset's
  `hermes_home` (`~/.hermes-whizz`), so move both together. Not fixable by
  the Whizzard→Osmotiq rename alone — `oiq … create oiq` would collide the
  other way (command == argument), so a role name is correct regardless.
- **Internal refs leaking into user-facing help:** `Stage N` / `D-NN`
  tokens appear in command `help=` strings and command-function docstrings
  (which Typer renders as help): `hermes` "(Stage 8)", `preset` "(Stage 10)",
  `requests` "(Stage 14)", `adjust` docstring "per D-79", `adjust`
  `--allow-broad-mount` help "(D-46 first gate)", `hermes profile create`
  docstring "(D-80, D-86)", `requests approve` docstring "Stage 13". Scrub
  these. Scope is help OUTPUT only — module docstrings and `#` comments
  carry the same tokens as legit internal traceability and must be left
  intact (~25 such, not user-facing).
- **Profile name decided:** `whizz` → `main` (`~/.hermes-main`); update the
  bundled preset `hermes_home` in lockstep.
- **Grouping confirmed:** the five-panel shape is approved as-is.
*Disposition:* fix before launch as one CLI-help + wizard-copy polish pass.

### `whiz run` defaults to an unregistered `generic` harness → confusing failure
`run_cmd`'s `--harness` defaults to `"generic"`, but the wizard registers
only `hermes-cell` (the generic shell is internal-only per
[[feedback_no_shell_harness_in_user_surfaces]]). So a bare `whiz run`
fails with "unknown harness: 'generic'. Available: hermes-cell" — and the
`--harness` help text advertises "default: generic shell", which both
surfaces the internal shell *and* names a default that doesn't work.
Surfaced during the Windows cell-launch test 2026-06-03.
*Fix options:* (a) make the default harness the registered one / derive it
from harnesses.json rather than hardcoding `generic`; or (b) if `whiz run`
stays an internal/dev entry point, scrub the "generic shell" mention from
help and make the error actionable ("no harness specified — try
`whiz r hermes` or `--harness hermes-cell`"). Decide which `whiz run` is.
*Disposition:* fix before launch (confusing first-touch error).

### BUG (OS-agnostic, likely launch-blocking): harness not coupled to its image
`_perform_launch` uses the passed `image` param directly in
`build_run_argv(image=image, ...)`; there is **no harness→image
resolution**, and neither the harness config nor the adapter carries an
image. Both `run_cmd` and `preset_launch_cmd` default `image` to
`WHIZZARD_IMAGE` (the base). So launching the `hermes-cell` harness keeps
the *base* image (which has no `hermes` binary) and dies inside the
container with `[FATAL tini] exec hermes failed: No such file or
directory`. Surfaced on the Windows live launch 2026-06-03, but it is
**not Windows-specific** — it reproduces on any OS.
Critically, `preset.<x>` carries `.harness` but no image, and
`preset_launch_cmd` also defaults to base — so **`whiz r hermes` (the
command the wizard's "first commands to try" advertises) appears to fail
the same way** unless `--image whizzard-hermes:latest` is passed. (Confirm
by running `whiz r hermes` bare.) Workaround: explicit
`--image whizzard-hermes:latest`.
*Fix:* derive the image from the harness (the harness/adapter should
declare its required image — e.g. Hermes → `WHIZZARD_HERMES_IMAGE`), or
let a preset carry an image, so the headline launch path selects the
correct image without the user knowing image names. Also add a fail-fast
check: if the harness's expected binary isn't in the chosen image, error
at the whiz layer rather than as a cryptic in-container tini failure.
*Disposition:* fix before launch — this blocks the primary documented
launch command. How did this pass the M7 smoke? (M7 likely ran with an
explicit hermes image; worth confirming the smoke covers the bare
preset path.)

### Hermes default start command is gateway-mode, not interactive terminal
`HermesAdapter._DEFAULT_START_COMMAND = ["hermes", "gateway", "run"]`
(hermes.py:57) hardcodes the **gateway daemon** as the cell's command. The
gateway is a messaging-platform listener (Discord/Telegram/etc.) — it
requires platform config and is *not* interactive, so a default launch
just idles ("No messaging platforms enabled") and ignores stdin. Surfaced
on the Windows launch 2026-06-03: the maintainer notes interactive
**terminal mode should be the default**, with gateway as an explicit
opt-in the user selects and configures.
*Fix (command confirmed 2026-06-03):* default the cell command to bare
`hermes` (the interactive terminal/chat mode — maintainer-confirmed; the
cell already passes `-it`, so it gives a real in-terminal session).
Change `_DEFAULT_START_COMMAND = ["hermes", "gateway", "run"]` →
`["hermes"]`; this also revisits D-88 (which set gateway as the default
invocation). Gateway mode is **not** a Whizzard flag — per the maintainer,
the user starts gateway from within their Hermes session if they want it
(keeps Whizzard harness-neutral; no harness-specific flag on `whiz`).
Touches the adapter start command, the wizard's Hermes setup, and the
preset/use-flow docs.
*Open question:* the correct interactive Hermes command + how the user
opts into gateway (preset field? `whiz run --gateway`? wizard choice?).
*Disposition:* fix before launch — the default launch UX is currently a
dead-end idle daemon.

### Daemon-down detection is implemented three ways across two modules
`_DAEMON_DOWN_INDICATORS` + `_looks_like_daemon_error` live in
`docker_cmd.py`; `adjust.py:56-60` carries a **verbatim copy** (with a
drifted comment); and `docker_daemon_status()` now reuses the matcher but
the duplication remains. Surfaced by the #3 code review 2026-06-03. Risk:
Docker changes its unreachable-stderr wording (it has historically), a
maintainer updates the `docker_cmd` tuple + tests green, and `adjust.py`'s
copy silently goes stale — regressing the F-G-10 "daemon down vs no match"
fix in `whiz adjust` with nothing failing CI.
*Fix:* have `adjust.py` import `_DAEMON_DOWN_INDICATORS` /
`_looks_like_daemon_error` from `docker_cmd` (single source). Optional:
fold init's `docker_daemon_status` and adjust's probe onto one classifier.
*Disposition:* cleanup — fold into the launch-fixes batch's #6 (the
"centralize" pass), not merge-blocking.

### Flaky integration test: `test_docker_label_lookup_finds_running_cell`
`tests/integration/test_adjust_smoke.py::test_docker_label_lookup_finds_running_cell`
intermittently fails with "expected exactly one match, got []" on the
Ubuntu integration runner (passed on every re-run; flaked ≥3× across this
session's CI). Race: the test launches a cell (`sleep 3600`), waits for the
**cidfile**, then does a single-shot `docker ps` label lookup — but the
container's label can lag the cidfile write, so the lookup occasionally
sees nothing. Image-independent (uses base image + sleep), so unrelated to
the launch-fixes changes it keeps blocking.
*Fix:* poll the label lookup with a short deadline (mirror
`_await_container_id`'s retry loop) instead of one shot, so it tolerates
the start-up lag. Small, contained test-only change.
*Disposition:* fix soon — it's costing a CI re-run on nearly every
launch-fixes push.

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

*Last reviewed: 2026-05-22.*
