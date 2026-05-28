# Whizzard

Local capability governance for AI agents. Run powerful agent harnesses inside explicit, temporary, human-readable permission boundaries.

> **Status:** MVP under construction. Stages 1–15.5 shipped. See [ROADMAP.md](ROADMAP.md) for what's next.

> **Naming:** "Whizzard" is a working name. The project may rename before OSS launch. See [docs/decisions.md](docs/decisions.md) D-144.

---

## What this is

See [docs/vision_and_strategy.md](docs/vision_and_strategy.md). In one sentence: Whizzard wraps an agent harness in a hardened, scoped, time-bounded execution cell with auditable capability grants.

The core invariant:

```
Whizzard controls capabilities.
Agents request capabilities.
Agents do not grant themselves capabilities.
```

## Scope and limitations

Whizzard sits at the runtime layer of the agent lifecycle: while an agent is executing, Whizzard *bounds what it can reach* — what filesystem paths are visible, what network destinations are reachable, what capabilities the container holds. The product's value rests on those boundaries holding.

It is deliberately not a complete security solution. The list below names what Whizzard does and does not address in `v0.1.0`, with mitigation pointers where applicable.

### What Whizzard *does* address

- **Filesystem capability boundaries.** An agent reaches only the paths you explicitly mounted into the cell. Your SSH keys, your browser cookies, your other projects, your password manager, your cloud-credentials directory — none of these are reachable unless you declared them. The mount list *is* the permission model (no implicit access via parent traversal, symlink, or "the agent figured out my home directory"). This closes the entire class of "an agent ran `find ~ -name '*.pem'` and found everything I have."

- **Network capability boundaries.** Per-profile network policy constrains outbound destinations: `off` means no network at all; `allowlist` means only the destinations you declared (your model endpoint, the package index, etc.). This closes the easy data-exfiltration path — an agent can't `curl evil.example.com` to a destination you didn't approve. Combined with the filesystem boundary above, it closes the "read sensitive data then send it somewhere" loop.

- **Privilege containment.** The agent runs as a non-root user inside the container, with dropped Linux capabilities, a read-only container root filesystem, `no-new-privileges` set, and the Docker socket unreachable. A vulnerability in any tool the agent invokes doesn't get root, can't load kernel modules, can't write outside declared writable mounts, can't escalate via `setuid` binaries, and can't reach back to the host Docker daemon to spawn unconstrained containers.

- **Credential isolation.** Whizzard's own configuration (including the platform-integration `auth.json`) is structurally unreachable from the cell — no symlink, no parent-mount, no traversal trick, no rglob bypass reaches it. The cell can't read or modify the credentials that govern *future* Whizzard sessions. This closes the "compromise one session, persist via Whizzard's own config" path.

- **One-way capability flow.** Permissions only get narrower, not broader, after a session launches. An agent that needs more access than its profile allows must surface a request to the operator — it cannot grant itself broader permissions, cannot re-launch itself with new flags, cannot escape its profile by editing config. The escalation path is one-way and requires explicit operator approval. There is no "the agent quietly upgraded itself to root" path.

- **Time-bounded sessions.** Every session carries an explicit duration cap and an idle-timeout cap. When the cap fires, the container is stopped. This closes the "long-running agent gradually accumulates failed attempts until something works" pattern and limits the blast radius of any compromise to the declared session window.

- **Append-only audit visibility.** Every session emits a structured, append-only audit log: what was launched, with what profile and mounts, what the agent requested mid-session, how requests were resolved, when the session ended and why. The log is the post-hoc detection surface; even a sophisticated attack has to operate within recorded scope. Tampering with the log requires reaching the config directory, which the cell can't do (see credential isolation above).

- **Operator-in-the-loop on escalation.** When an agent needs something beyond its profile (a broader mount, a network destination not on the allowlist, a longer session), the request lands in a file-mailbox the operator monitors. The operator approves or denies; the agent does not get the permission without explicit grant. No silent escalation, no implicit consent.

### What Whizzard *does not* address in v0.1.0

- **Deferred-execution attacks via writable mounts.** An agent with write access to a project mount can plant files that execute later on the host — `.git/hooks/pre-commit`, poisoned `package.json` post-install scripts, source backdoors, or pinned-bad dependencies in lockfiles. Whizzard's containment holds while the agent is running, but writes are visible to the host immediately and may execute later when the user resumes normal work.
  **Mitigation roadmap:** v1.0 introduces an opt-in `--strict-overlay` mode that quarantines writable-mount writes behind a `whiz merge` review gate (see [ROADMAP.md](ROADMAP.md), goal 10). Until then: review diffs before commit, especially for sensitive paths (`.git/hooks/`, build configs, lockfiles).

- **DNS-based exfiltration.** When network access is allowed, an agent can encode data in DNS lookups even to hostnames not in the allowlist. Whizzard constrains *HTTP* destinations but does not gate DNS by default.
  **Mitigation roadmap:** per-profile constrained-DNS option under consideration; not v1.0-blocking. For high-stakes work today: use the `off` network profile, which blocks everything including DNS.

- **Behavioral analysis of the agent.** Whizzard is a containment layer, not a behavioral controller. It does not detect or prevent sophisticated refusal patterns, hidden communication channels in tool outputs, or steganography in agent writes. Those are different problem classes handled by different tools (behavioral testing, audit-log analysis); Whizzard's value is that *whatever the agent does, it can only do it within the declared capability surface*.

- **Container escape.** Whizzard relies on Docker / OCI runtime boundaries. A kernel-level container escape (a CVE in the runtime itself) is out of scope; the project tracks runtime security advisories but does not invent novel sandboxing primitives.

- **Supply-chain attacks on Whizzard itself.** The repo applies industry-standard hardening (branch protection, signed releases, pinned dependencies) but is not third-party audited. Use the pinned-version install path for sensitive work; review pull requests before merging.

This list is not exhaustive. It names the gaps most likely to surprise a user who assumes a Docker wrapper fully isolates the agent's effect. If you find a gap not listed, please open an issue.

## Prerequisites

- macOS or Linux
- Python 3.11+
- Docker Desktop (or any Docker daemon) running

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

Individual targets: `make test`, `make lint`, `make fmt` (auto-fix), `make typecheck`, `make validate-decisions`, `make dx ARGS='D-158'`. Configs for all three tools live in `pyproject.toml`.

Pre-commit hooks for the same checks: `pip install pre-commit && pre-commit install`. CI (GitHub Actions, `.github/workflows/ci.yml`) runs the same set on push and PR.

## First run

Build the execution image:

```sh
whizzard image build
whizzard image status
```

Launch a contained shell under the default profile:

```sh
whizzard run --profile default
```

You should see a `Whizzard Profile: DEFAULT` banner followed by a bash prompt inside the container. Confirm containment by trying to access the host home directory:

```sh
ls /Users/$USER   # should fail or show nothing — host home is not mounted
whoami            # should print "whizzard", not your host user
```

Exit with `exit` or `Ctrl-D`.

## Optional: Hermes adapter

Whizzard ships a generic shell adapter (above) plus an optional Hermes adapter for the [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) harness. The Hermes adapter is bundled in the Python package — no separate `pip install` step — but the execution image needs Hermes layered on top of the base image:

```sh
docker build -f docker/Dockerfile.hermes -t whizzard-hermes:latest .
```

That image pins Hermes to a specific upstream commit; bump `HERMES_REF` in `docker/Dockerfile.hermes` to update.

Then point Whizzard at the Hermes image and a harness entry:

```sh
# 1. Clone a Hermes profile into a sibling directory (auth.json + runtime state excluded).
whiz hermes profile create whizzard-cell --clone-from default

# 2. Configure ~/.whizzard/config/harnesses.json with a `hermes-cell` entry — see config/harnesses.json.example.

# 3. Launch.
WHIZZARD_IMAGE=whizzard-hermes:latest whiz run --harness hermes-cell
```

For non-Ollama providers (Anthropic, OpenAI, etc.), declare credential env-var names in the harness's `secrets:` field; values resolve from OneCLI or host env at launch (D-162). Never put plaintext credential values in `harnesses.json`.

## Using OIQ inside your agent harness

The OIQ CLI is the harness-neutral integration surface. Any agent harness that can shell out can wrap `oiq r`, `oiq s`, etc. — no harness-specific runtime lives in OIQ core.

Copy-paste integration recipes live in **[`docs/examples/`](docs/examples/)**:

- **[`docs/examples/claude_code/`](docs/examples/claude_code/)** — Claude Code skill files (`/oiq-launch`, `/oiq-status`, `/oiq-presets`, `/oiq-sessions-tail`). Drop into `~/.claude/skills/` to install.
- **[`docs/examples/hermes/`](docs/examples/hermes/)** — Hermes adapter setup recipe (image build, profile clone, harness config, provider config).
- Other harnesses welcome via PR — see [`docs/examples/README.md`](docs/examples/README.md) for contribution guidance.

The design choice to ship integration as docs rather than as harness-specific code in OIQ core is captured in [`decisions.md`](docs/decisions.md) D-161.

## Available profiles

```sh
whizzard profiles list
```

Profiles available in Stage 1: `safe`, `default`, `build`, `power`, `quarantine`. The `default` profile is the always-on baseline (network enabled, no mounts, no expiry); other profiles add or remove capabilities.

## Repository layout

```
whizzard/
  whizzard/        # Python package
  docker/          # execution image
  config/          # JSON configs (populated in later stages)
  scripts/         # profile wrapper scripts (populated in later stages)
  docs/            # design docs (vision, architecture, build plans, decisions)
  tests/           # tests
  README.md
  pyproject.toml
```

## Documentation

- [docs/vision_and_strategy.md](docs/vision_and_strategy.md) — what this is, who it's for, where it's going
- [docs/architecture.md](docs/architecture.md) — system structure, safety policy, adapter contract, control layering
- [ROADMAP.md](ROADMAP.md) — v1.0 primary goals + post-launch sequencing
- [docs/decisions.md](docs/decisions.md) — append-only decisions index
