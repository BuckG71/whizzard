# Whizzard

Local capability governance for AI agents. Run powerful agent harnesses inside explicit, temporary, human-readable permission boundaries.

> **Status:** v0.1.0 OSS launch in preparation. Pre-release reviewers welcome — see [Install](#install) below.

---

## What this is

In one sentence: Whizzard wraps an *agent harness* — a tool that drives an LLM through coding or agent tasks, e.g. Hermes, Claude Code, Cursor — in a hardened, scoped, time-bounded Docker container (hereafter "sandbox") with auditable capability grants. See [docs/vision_and_strategy.md](docs/vision_and_strategy.md) for more detail.

The core invariant:

```
Whizzard controls capabilities.
Agents request capabilities.
Agents do not grant themselves capabilities.
```

## Concepts at a glance

- **Sandbox** — the hardened Docker container Whizzard launches each agent session inside.
- **Profile** — a named bundle of capability defaults (network policy, time limits, image, hardening flags). You launch a session by picking a profile.
- **Mount** — an explicit path you grant the sandbox visibility into. The set of mounts *is* the agent's filesystem permission.

## Scope and limitations

Whizzard sits at the runtime layer of the agent lifecycle: while an agent is executing, Whizzard *bounds what it can reach* — what filesystem paths are visible, what network destinations are reachable, what capabilities the sandbox holds. The product's value rests on those boundaries holding.

Whizzard does not claim to be a complete security solution. The list below names what Whizzard does and does not address in `v0.1.0`, with mitigation pointers where applicable.

### What Whizzard *does* address

- **Filesystem capability boundaries.** An agent reaches only the paths you explicitly mounted into the sandbox. Your SSH keys, your browser cookies, your other projects, your password manager, your cloud-credentials directory — none of these are reachable unless you declared them. The mount list *is* the permission model (no implicit access via parent traversal, symlink, or "the agent figured out my home directory"). This closes the entire class of "an agent ran `find ~ -name '*.pem'` and found everything I have."

- **Network capability boundaries.** Per-profile network policy: `off` means no network at all (no DNS, no outbound HTTP, nothing); `on` means full outbound access. The `off` posture closes data exfiltration entirely — combined with the filesystem boundary above, it closes the "read sensitive data then send it somewhere" loop. The `default` Whizzard profile sets network `on` to minimize friction for everyday use; profiles like `safe` and `quarantine` ship with network `off` for untrusted work. **Per-destination allowlist mode is tagged for v1.0** — see [ROADMAP.md](ROADMAP.md), goal 11. Until then, the on/off boolean is the available granularity.

- **Privilege containment.** The agent runs as a non-root user inside the sandbox, with dropped Linux capabilities, a read-only container root filesystem, `no-new-privileges` set, and the Docker socket unreachable. A vulnerability in any tool the agent invokes doesn't get root, can't load kernel modules, can't write outside declared writable mounts, can't escalate via `setuid` binaries, and can't reach back to the host Docker daemon to spawn unconstrained containers.

- **Credential isolation.** Whizzard's own configuration directory — including any credential files belonging to harnesses Whizzard launches — is structurally unreachable from the sandbox: no symlink, no parent-mount, no traversal trick, no rglob bypass reaches it. The sandbox can't read or modify the credentials that govern *future* Whizzard sessions. This closes the "compromise one session, persist via Whizzard's own config" path.

- **One-way capability flow.** Permissions only get narrower, not broader, after a session launches. An agent that needs more access than its profile allows must surface a request to the operator — it cannot grant itself broader permissions, cannot re-launch itself with new flags, cannot escape its profile by editing config. The escalation path is one-way and requires explicit operator approval. There is no "the agent quietly upgraded itself to root" path.

- **Time-bounded sessions.** Every session carries an explicit duration cap and an idle-timeout cap. When the cap fires, the container is stopped. This closes the "long-running agent gradually accumulates failed attempts until something works" pattern and limits the blast radius of any compromise to the declared session window.

- **Append-only audit visibility.** Every session emits a structured, append-only audit log: what was launched, with what profile and mounts, what the agent requested mid-session, how requests were resolved, when the session ended and why. The log is the post-hoc detection surface; even a sophisticated attack has to operate within recorded scope. Tampering with the log requires reaching the config directory, which the sandbox can't do (see credential isolation above).

- **Operator-in-the-loop on escalation.** When an agent needs something beyond its profile (a broader mount, network access when the profile has it off, a longer session), the request lands in a file-mailbox the operator monitors. The operator approves or denies; the agent does not get the permission without explicit grant. No silent escalation, no implicit consent.

### What Whizzard *does not* address in v0.1.0

- **Deferred-execution attacks via writable mounts.** An agent with write access to a project mount can plant files that execute later on the host — `.git/hooks/pre-commit`, poisoned `package.json` post-install scripts, source backdoors, or pinned-bad dependencies in lockfiles. Whizzard's containment holds while the agent is running, but writes are visible to the host immediately and may execute later when the user resumes normal work.
  **Mitigation roadmap:** v1.0 introduces an opt-in `--strict-overlay` mode that quarantines writable-mount writes behind a `whiz merge` review gate (see [ROADMAP.md](ROADMAP.md), goal 10). Until then: review diffs before commit, especially for sensitive paths (`.git/hooks/`, build configs, lockfiles).

- **DNS-based exfiltration.** When network access is on, an agent can encode data in DNS lookups. Whizzard does not currently gate DNS independently of the on/off boolean.
  **Mitigation roadmap:** per-profile constrained-DNS option under consideration as a sub-track of the v1.0 network-allowlist work (see [ROADMAP.md](ROADMAP.md) goal 11). For high-stakes work today: use the `off` network profile (or `safe` / `quarantine`), which blocks everything including DNS.

- **Behavioral analysis of the agent.** Whizzard is a containment layer, not a behavioral controller. It does not detect or prevent sophisticated refusal patterns, hidden communication channels in tool outputs, or steganography in agent writes. Those are different problem classes handled by different tools (behavioral testing, audit-log analysis); Whizzard's value is that *whatever the agent does, it can only do it within the declared capability surface*.

- **Container escape.** Whizzard relies on Docker / OCI runtime boundaries. A kernel-level container escape (a CVE in the runtime itself) is out of scope; the project tracks runtime security advisories but does not invent novel sandboxing primitives.

- **Supply-chain attacks on Whizzard itself.** The repo applies industry-standard hardening (branch protection, signed releases, pinned dependencies) but is not third-party audited. Use the pinned-version install path for sensitive work; review pull requests before merging.

This list is not exhaustive. It names the gaps most likely to surprise a user who assumes a Docker wrapper fully isolates the agent's effect. If you find a gap not listed, please open an issue.

## Prerequisites

- macOS, Linux, or Windows (Windows is in pre-release verification for v0.1.0)
- Python 3.11+
- Docker Desktop (or any Docker daemon) running

## Install

### Pre-release (v0.1.0 reviewers)

```sh
pip install whizzard==0.1.0rc1
whiz init
```

That's the entire flow. `whiz init` walks you through five short configuration steps, builds the execution container (about 2 minutes the first time), and sets up the configuration files at `~/.whizzard/config/`. Setup takes about five minutes total.

### Hermes setup

Whizzard currently supports the [Hermes Agent harness by Nous Research](https://github.com/NousResearch/hermes-agent) — an open-source autonomous-agent harness with platform connectors (Discord, Slack), cron scheduling, and skill management. Additional harnesses are planned for future releases.

`whiz init` detects whether you already have Hermes installed on your machine (`~/.hermes/`) and branches into one of two flows:

- **If you have Hermes**: the wizard copies your existing setup into a Whizzard profile (`~/.hermes-whizz/`). Your existing Hermes setup on the host is not changed — Whizzard only reads from it. The bundled `hermes` preset is ready to launch.
- **If you don't have Hermes**: the wizard prints install instructions and completes setup without it. To finish, install [Hermes from NousResearch](https://github.com/NousResearch/hermes-agent), then run `whiz hermes profile create whizz` to copy your fresh Hermes setup into `~/.hermes-whizz/`.

### First session

After `whiz init` completes:

```sh
whiz                  # show what's running and what you have set up
whiz r hermes         # launch a Hermes session
whiz --help           # list every command
```

## Install (development)

```sh
git clone <this-repo>
cd whizzard
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"     # includes pytest, ruff, mypy
```

### Dev workflow

One-command lint + typecheck + test:

```sh
make check
```

Individual targets: `make test`, `make lint`, `make fmt` (auto-fix), `make typecheck`, `make validate-decisions`, `make dx ARGS='<decision-id>'` (browse a decision record from `docs/decisions.md`). Configs for all three tools live in `pyproject.toml`.

Pre-commit hooks for the same checks: `pip install pre-commit && pre-commit install`. CI (GitHub Actions, `.github/workflows/ci.yml`) runs the same set on push and PR.

## Available profiles

```sh
whiz profiles list
```

Bundled profiles: `default` (network on, no time limit, no idle limit — everyday baseline), `safe` (network off, 30 min limit), `build` (network on, 2 hour limit), `power` (network on, 1 hour limit, broad access), `quarantine` (network off, 30 min limit, read-only folders only). `whiz init` writes the full five by default; you can customize during setup or edit `~/.whizzard/config/profiles.json` after.

## Repository layout

```
whizzard/
  whizzard/                # Python package
    _dockerfiles/          # bundled Dockerfile + Dockerfile.hermes (package data)
    adapters/              # harness adapters (Hermes + generic Protocol reference)
    cli/                   # per-subcommand CLI modules
    init_wizard.py         # `whiz init` orchestration
  config/                  # example JSON configs (user copies into ~/.whizzard/config/)
  scripts/                 # maintenance tooling (decisions validator, dx lookup)
  docs/                    # vision, architecture, decisions, examples
  tests/                   # unit + integration tests
  README.md
  pyproject.toml
```

## Documentation

- [docs/vision_and_strategy.md](docs/vision_and_strategy.md) — what this is, who it's for, where it's going
- [docs/architecture.md](docs/architecture.md) — system structure, safety policy, adapter contract, control layering
- [ROADMAP.md](ROADMAP.md) — v1.0 primary goals + post-launch sequencing
- [docs/decisions.md](docs/decisions.md) — append-only decisions index

## A note on naming

"Whizzard" is a working name. The project may rename before broader release; the CLI verb may change accordingly.
