# MVP Build Plan: Local Agent Permission Manager

## Working Name

**Agent Permission Manager (APM)**

A local-first launcher and policy layer for running AI agents with explicit, temporary, human-readable capabilities.

---

## 1. Product Definition

### 1.1 Core Problem

AI agents become useful when they can:

- read and write files
- run shell commands
- install packages
- clone repositories
- access the internet
- call APIs
- use credentials
- execute generated code

But giving an agent unrestricted access to a personal computer creates unacceptable risk:

- exposure of home directory contents
- browser cookies and authenticated sessions
- SSH keys
- API keys
- password vault attack surface
- destructive filesystem writes
- uncontrolled network exfiltration
- package-install and supply-chain risk
- Docker socket / host escape risk

The MVP solves this by making agent access **explicit, temporary, visible, and logged**.

### 1.2 Product Thesis

The permission boundary should not live inside the agent. It should live in a separate launcher/policy layer controlled by the human operator.

### 1.3 MVP Goal

Create a local CLI tool that launches a Hermes or general AI-agent terminal session inside a constrained execution environment with:

- default safe-but-useful profile
- named permission profiles
- one-step dynamic folder mounting
- network mode control
- explicit read-only vs read-write mounts
- dangerous-path blocking
- session logging
- dry-run preview
- simple audit trail

### 1.4 Non-Goals for MVP

Do not build these in the first version:

- GUI
- cloud service
- enterprise admin console
- browser automation
- password manager integration
- full credential broker
- kernel-level security product
- multi-user policy server
- cross-platform Windows/Linux support
- automatic malware detection
- automatic command classification
- production notarized macOS app

The MVP should prove the workflow.

---

## 2. Competitive / Prior-Art Context

This concept is not appearing from nowhere. Several adjacent systems already exist:

- Claude Code supports sandboxing and permissions, including filesystem and network restrictions, plus allow/ask/deny rules.
- OpenAI Codex supports sandboxing, approvals, and permission switching, with default behavior that limits workspace access and often disables network access.
- Docker has launched Docker Sandboxes for coding agents, with disposable isolated sandboxes for agents including Claude Code, Gemini CLI, Copilot CLI, Codex, OpenCode, and Kiro.
- NanoClaw has been integrated with Docker Sandboxes for secure agent execution.
- Developers are already publishing personal setups that run agents inside devcontainers, Docker, or local sandboxes to reduce approval fatigue while limiting host exposure.

### 2.1 Implication

The broad need is validated.

### 2.2 Differentiation

The MVP should not be positioned as “just sandboxing.” That is becoming table stakes.

The stronger concept is:

> A local, human-readable, capability-based permission manager for AI agents.

The differentiator is the control plane:

- profiles
- mount registry
- temporary grants
- readable permission summaries
- logs
- consistent launcher UX
- agent-harness neutrality

---

## 3. Target User

### 3.1 Initial User

A technically capable local AI / coding-agent user who wants agent usefulness without exposing their entire machine.

Likely traits:

- uses macOS
- comfortable with Terminal
- uses Docker Desktop
- experiments with Claude Code, Codex, Hermes, NanoClaw, OpenCode, etc.
- wants agents to code, research, install packages, and run commands
- does not want the agent to access personal browser/session/password/SSH material

### 3.2 MVP User Story

> As a local AI-agent user, I want to launch an agent with a named permission profile and selected mounted folders so that the agent can do real work without receiving unrestricted access to my computer.

---

## 4. Security Model

### 4.1 Design Principles

1. **Default deny**
   - The agent receives access only to explicitly granted resources.

2. **Temporary capability grants**
   - Access exists for the session, not permanently.

3. **Human-readable permissions**
   - Before launch, the tool clearly states what will be exposed.

4. **No hidden privilege escalation**
   - No silent sudo, Docker socket, browser profile, password vault, or SSH-key exposure.

5. **Separation of control and execution**
   - The human-controlled launcher determines access.
   - The agent runs inside the constrained environment.

6. **Auditability**
   - Each session records what profile, mounts, network mode, and command were used.

7. **Pragmatic usefulness**
   - Default profile should be safe enough to leave on but useful enough that users do not bypass it.

### 4.2 Threats Addressed

The MVP reduces risk from:

- agent reading arbitrary host files
- agent modifying unrelated projects
- accidental deletion outside workspace
- package scripts affecting host filesystem
- malicious cloned repositories accessing secrets
- prompt-injected tool calls reaching sensitive directories
- accidental exposure of `.ssh`, browser profiles, Keychain files, cloud-drive data, or personal documents
- untracked agent sessions

### 4.3 Threats Not Fully Addressed

The MVP does not fully solve:

- Docker Desktop vulnerabilities
- kernel/container escape vulnerabilities
- malicious output files manually opened by the user
- network exfiltration when network is enabled
- malicious packages run inside the mounted workspace
- secrets intentionally mounted or entered by the user
- compromised base images
- side-channel attacks
- fully automated credential governance

The MVP is a substantial reduction in practical exposure, not a formal high-assurance sandbox.

---

## 5. Recommended MVP Architecture

### 5.1 High-Level Architecture

```text
Human Operator
   |
   | agent-run --profile default --mount project-alpha
   v
Agent Permission Manager CLI
   |
   | validates profile + mounts + policy
   | prints permission summary
   | logs session metadata
   v
Docker Container / Agent Execution Cell
   |
   | sees only approved mounts
   | receives chosen network mode
   | runs Hermes / agent terminal
   v
Mounted Workspace / Outbox
```

### 5.2 Local Directory Layout

```text
~/agent-permission-manager/
  bin/
    agent-run
    agent-safe
    agent-net
    agent-build
    agent-power
    agent-quarantine

  config/
    profiles.json
    mounts.json
    policy.json

  docker/
    Dockerfile
    entrypoint.sh

  logs/
    sessions/

  examples/
    profiles.example.json
    mounts.example.json

  README.md
```

### 5.3 Host Workspace Layout

```text
/Users/Shared/AgentWork/
  inbox/
  workspace/
  outbox/
  logs/
```

The agent’s default writable location should be:

```text
/Users/Shared/AgentWork/workspace
```

Outputs intended for human review should go to:

```text
/Users/Shared/AgentWork/outbox
```

---

## 6. Profiles

### 6.1 Required Profiles

The MVP should include five profiles:

1. `default`
2. `safe`
3. `net`
4. `build`
5. `power`
6. `quarantine`

### 6.2 Default Profile

The default should be **SAFE-NET**, not fully offline.

Rationale:

- Fully offline is too frustrating.
- Many normal agent tasks need web/API/model access.
- The safe boundary should be filesystem isolation, not necessarily no internet.

#### Default Capabilities

Allowed:

- network access
- shell execution inside container
- read/write access to AgentWork
- selected extra mounts only
- package installs inside container
- git operations inside mounted workspace

Denied:

- host sudo
- Docker socket
- host home directory
- browser profile
- Keychain
- password vault
- SSH master keys
- arbitrary host filesystem
- host process namespace
- privileged container mode

### 6.3 Profile Matrix

| Profile | Purpose | Network | Shell | Default Mounts | Extra Mounts | Root FS | Docker Socket |
|---|---|---:|---:|---|---|---|---|
| `default` | normal useful agent work | on | yes | AgentWork rw | allowed | read-only | no |
| `safe` | low-risk local work | off | yes | AgentWork rw | allowed | read-only | no |
| `net` | research/API tasks | on | yes | AgentWork rw | ro preferred | read-only | no |
| `build` | coding/package installs | on | yes | AgentWork rw | rw allowed | writable or overlay | no |
| `power` | trusted local automation | on | yes | AgentWork rw | rw allowed | configurable | no by default |
| `quarantine` | unknown/sketchy repos | off default | yes | quarantine workspace | limited | read-only | no |

### 6.4 Example `profiles.json`

```json
{
  "default": {
    "description": "Safe but useful default. Network on, host filesystem constrained.",
    "network": "bridge",
    "allow_shell": true,
    "read_only_root": true,
    "tmpfs": ["/tmp"],
    "cap_drop": ["ALL"],
    "security_opt": ["no-new-privileges"],
    "pids_limit": 256,
    "memory": "4g",
    "cpus": "2",
    "allow_extra_mounts": true,
    "default_mounts": ["agentwork"],
    "allow_docker_socket": false,
    "confirm_before_launch": false
  },
  "safe": {
    "description": "Offline constrained local work.",
    "network": "none",
    "allow_shell": true,
    "read_only_root": true,
    "tmpfs": ["/tmp"],
    "cap_drop": ["ALL"],
    "security_opt": ["no-new-privileges"],
    "pids_limit": 128,
    "memory": "2g",
    "cpus": "1",
    "allow_extra_mounts": true,
    "default_mounts": ["agentwork"],
    "allow_docker_socket": false,
    "confirm_before_launch": false
  },
  "net": {
    "description": "Research and API mode with narrow filesystem access.",
    "network": "bridge",
    "allow_shell": true,
    "read_only_root": true,
    "tmpfs": ["/tmp"],
    "cap_drop": ["ALL"],
    "security_opt": ["no-new-privileges"],
    "pids_limit": 256,
    "memory": "4g",
    "cpus": "2",
    "allow_extra_mounts": true,
    "default_mounts": ["agentwork"],
    "allow_docker_socket": false,
    "confirm_before_launch": false
  },
  "build": {
    "description": "Coding and package-install mode.",
    "network": "bridge",
    "allow_shell": true,
    "read_only_root": false,
    "tmpfs": ["/tmp"],
    "cap_drop": ["ALL"],
    "security_opt": ["no-new-privileges"],
    "pids_limit": 512,
    "memory": "6g",
    "cpus": "4",
    "allow_extra_mounts": true,
    "default_mounts": ["agentwork"],
    "allow_docker_socket": false,
    "confirm_before_launch": true
  },
  "power": {
    "description": "Trusted automation mode. Broader project access, still no host secrets.",
    "network": "bridge",
    "allow_shell": true,
    "read_only_root": false,
    "tmpfs": ["/tmp"],
    "cap_drop": ["ALL"],
    "security_opt": ["no-new-privileges"],
    "pids_limit": 1024,
    "memory": "8g",
    "cpus": "4",
    "allow_extra_mounts": true,
    "default_mounts": ["agentwork"],
    "allow_docker_socket": false,
    "confirm_before_launch": true
  },
  "quarantine": {
    "description": "Unknown-code mode. Use for untrusted repositories.",
    "network": "none",
    "allow_shell": true,
    "read_only_root": true,
    "tmpfs": ["/tmp"],
    "cap_drop": ["ALL"],
    "security_opt": ["no-new-privileges"],
    "pids_limit": 128,
    "memory": "2g",
    "cpus": "1",
    "allow_extra_mounts": false,
    "default_mounts": ["quarantine"],
    "allow_docker_socket": false,
    "confirm_before_launch": true
  }
}
```

---

## 7. Mount Registry

### 7.1 Concept

The mount registry maps friendly names to approved host folders.

Instead of letting the user pass arbitrary host paths every time, the MVP should encourage named mounts.

Example:

```zsh
agent-run --profile power --mount project-alpha
```

This is safer than:

```zsh
docker run -v ~/Projects/project-alpha:/workspace/project-alpha
```

because the registry can enforce:

- path validation
- read-only/read-write mode
- dangerous-path blocking
- friendly labels
- logging
- future policy controls

### 7.2 Example `mounts.json`

```json
{
  "agentwork": {
    "label": "AgentWork",
    "path": "/Users/Shared/AgentWork",
    "container_path": "/workspace/agentwork",
    "mode": "rw",
    "required": true
  },
  "quarantine": {
    "label": "Quarantine Workspace",
    "path": "/Users/Shared/AgentWork/quarantine",
    "container_path": "/workspace/quarantine",
    "mode": "rw",
    "required": false
  },
  "project-alpha": {
    "label": "Project Alpha",
    "path": "/Users/bryan/Projects/project-alpha",
    "container_path": "/workspace/project-alpha",
    "mode": "rw",
    "required": false
  },
  "research": {
    "label": "Research Documents",
    "path": "/Users/bryan/Documents/Research",
    "container_path": "/workspace/research",
    "mode": "ro",
    "required": false
  }
}
```

### 7.3 Mount Mode Override

Support explicit mode overrides:

```zsh
agent-run --mount research:ro
agent-run --mount project-alpha:rw
```

Rules:

- User may downgrade `rw` to `ro`.
- User may not upgrade a registry-defined `ro` mount to `rw` unless `allow_mode_upgrade` is true.
- Default should be to reject mode upgrades.

### 7.4 Arbitrary Path Mounts

For MVP, arbitrary paths should be disabled by default.

Optional later:

```zsh
agent-run --path /Users/bryan/Projects/foo:rw
```

If enabled, it should require confirmation and pass the same dangerous-path checks.

---

## 8. Policy Rules

### 8.1 Dangerous Paths to Block

The launcher should refuse to mount:

```text
/
~
/Users
/Users/bryan
/Users/bryan/.ssh
/Users/bryan/.gnupg
/Users/bryan/.aws
/Users/bryan/.config
/Users/bryan/Library
/Users/bryan/Library/Application Support
/Users/bryan/Library/Keychains
/Users/bryan/Library/Cookies
/Users/bryan/Library/Group Containers
/Users/bryan/Library/Mobile Documents
/Users/bryan/Library/CloudStorage
/Users/bryan/Library/Safari
/Users/bryan/Library/Messages
/Users/bryan/Library/Mail
/Users/bryan/Library/Containers
/Users/bryan/Library/Application Support/Google
/Users/bryan/Library/Application Support/BraveSoftware
/Users/bryan/Library/Application Support/Firefox
/Users/bryan/Library/Application Support/1Password
/Users/bryan/Library/Application Support/Bitwarden
/Users/bryan/Library/Application Support/Apple
```

The exact username should be configurable or detected dynamically.

### 8.2 Suspicious Path Warnings

Warn but do not necessarily block:

```text
~/Desktop
~/Downloads
~/Documents
~/Dropbox
~/OneDrive
~/Google Drive
~/Library/Mobile Documents
```

For MVP, broad personal folders should require confirmation or be blocked unless explicitly registered.

### 8.3 Docker Socket Ban

Always block this mount unless an advanced override is explicitly added later:

```text
/var/run/docker.sock
```

Rationale:

Docker socket access can effectively become host-level control.

### 8.4 Symlink Resolution

Before mounting any path:

1. expand `~`
2. resolve symlinks
3. compute real absolute path
4. compare against blocklist
5. check parent path risk
6. verify path exists
7. verify it is a directory unless file mounts are later supported

This prevents:

```text
~/Projects/innocent-link -> ~/.ssh
```

from bypassing the policy.

---

## 9. CLI Specification

### 9.1 Required Commands

```zsh
agent-run
agent-run --profile default
agent-run --profile safe
agent-run --profile net --mount research
agent-run --profile build --mount project-alpha
agent-run --profile power --mount project-alpha --mount research:ro
agent-run --profile quarantine
agent-run --list-profiles
agent-run --list-mounts
agent-run --dry-run --profile power --mount project-alpha
agent-run --version
```

### 9.2 Convenience Wrappers

```zsh
agent-safe
agent-net
agent-build project-alpha
agent-power project-alpha
agent-quarantine
```

These should call `agent-run`.

Example:

```zsh
agent-power project-alpha
```

maps to:

```zsh
agent-run --profile power --mount project-alpha
```

### 9.3 CLI Output Before Launch

Before starting the container, print:

```text
Agent Permission Manager

Profile: default
Description: Safe but useful default. Network on, host filesystem constrained.

Network: ON
Shell: ON
Docker socket: OFF
Privileged container: OFF
Container root filesystem: read-only
Capabilities: drop ALL
No-new-privileges: ON
CPU: 2
Memory: 4g
PID limit: 256

Mounted folders:
- AgentWork
  Host: /Users/Shared/AgentWork
  Container: /workspace/agentwork
  Mode: rw

Session log:
- /Users/bryan/agent-permission-manager/logs/sessions/2026-05-07T231500-default.log
```

### 9.4 Confirmation Behavior

No confirmation:

- `default`
- `safe`
- `net`

Confirmation required:

- `build`
- `power`
- `quarantine`

Example:

```text
This profile allows package installs and writable project access.
Continue? [y/N]
```

### 9.5 Dry Run

Dry run should print:

- resolved profile
- resolved mounts
- security settings
- final Docker command
- log path

But not start the agent.

---

## 10. Docker Image

### 10.1 Base Image

Start with:

```Dockerfile
FROM python:3.11-slim
```

Alternative later:

```Dockerfile
FROM node:22-bookworm-slim
```

depending on Hermes requirements.

### 10.2 Installed Tools

MVP image should include:

- bash
- zsh
- git
- curl
- wget
- jq
- ca-certificates
- python3/pip
- node/npm if needed
- ripgrep
- fd
- unzip
- less
- nano or vim

Avoid overbuilding the image. More tools mean more capability and more attack surface.

### 10.3 Non-Root User

Create non-root user:

```Dockerfile
RUN useradd -m -u 1000 agent
USER agent
WORKDIR /workspace
```

### 10.4 Entrypoint

Use a minimal entrypoint:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /workspace/agentwork/workspace 2>/dev/null || cd /workspace
exec "$@"
```

### 10.5 Default Command

For first build:

```Dockerfile
CMD ["/bin/bash"]
```

Later replace with Hermes start command or make it configurable.

---

## 11. Launcher Implementation Plan

### 11.1 Language Choice

For the MVP, use Python rather than zsh.

Reason:

- safer argument parsing
- JSON parsing built in
- path resolution easier
- logging easier
- unit tests easier
- fewer shell injection mistakes

Use only Python standard library at first.

### 11.2 Script Location

```text
~/agent-permission-manager/bin/agent-run
```

Add executable shebang:

```python
#!/usr/bin/env python3
```

### 11.3 Python Modules Needed

Use standard library:

```python
argparse
json
os
pathlib
subprocess
datetime
shlex
sys
uuid
```

### 11.4 Main Functions

Implement:

```python
load_json(path)
resolve_profile(name)
resolve_mount(name_or_spec)
validate_mount_path(path)
build_docker_command(profile, mounts, command)
print_summary(profile, mounts, command)
write_session_log(metadata)
run_container(command)
```

### 11.5 Argument Parsing

Support:

```python
--profile
--mount
--dry-run
--list-profiles
--list-mounts
--command
--version
```

Default:

```python
profile = "default"
mounts = []
command = ["/bin/bash"]
```

### 11.6 Docker Command Construction

Build command as a list, not as a shell string.

Example:

```python
cmd = [
  "docker", "run", "--rm", "-it",
  "--name", container_name,
  "--network", profile["network"],
  "--cap-drop", "ALL",
  "--security-opt", "no-new-privileges",
  "--pids-limit", str(profile["pids_limit"]),
  "--memory", profile["memory"],
  "--cpus", profile["cpus"]
]
```

Add:

```python
if profile["read_only_root"]:
    cmd.append("--read-only")
```

Add tmpfs:

```python
for tmp in profile["tmpfs"]:
    cmd.extend(["--tmpfs", tmp])
```

Add mounts:

```python
cmd.extend(["-v", f"{host}:{container}:{mode}"])
```

Add image and command:

```python
cmd.append("agent-permission-manager:local")
cmd.extend(command)
```

### 11.7 Shell Injection Avoidance

Never use:

```python
subprocess.run(" ".join(cmd), shell=True)
```

Use:

```python
subprocess.run(cmd)
```

---

## 12. Logging

### 12.1 Session Log Fields

Each run should create a JSON log:

```json
{
  "session_id": "2026-05-07T231500Z-a1b2c3",
  "timestamp_start": "2026-05-07T23:15:00-05:00",
  "profile": "default",
  "network": "bridge",
  "mounts": [
    {
      "name": "agentwork",
      "host_path": "/Users/Shared/AgentWork",
      "container_path": "/workspace/agentwork",
      "mode": "rw"
    }
  ],
  "docker_image": "agent-permission-manager:local",
  "container_name": "agent-session-a1b2c3",
  "docker_command": ["docker", "run", "..."],
  "exit_code": 0,
  "timestamp_end": "2026-05-07T23:40:00-05:00"
}
```

### 12.2 Do Not Log

Do not log:

- raw secrets
- environment variable values marked secret
- full contents of files
- command output by default

For MVP, only log metadata.

### 12.3 Optional Terminal Transcript

Do not implement transcript capture in the first build unless needed.

Later option:

```zsh
script logs/transcripts/session.log
```

But transcript logging can accidentally capture secrets.

---

## 13. Environment Variables

### 13.1 Dynamic Mount Environment Variable

Support:

```zsh
AGENT_MOUNTS="project-alpha,research:ro" agent-run --profile power
```

This should be equivalent to:

```zsh
agent-run --profile power --mount project-alpha --mount research:ro
```

### 13.2 Precedence

Order of mount resolution:

1. profile default mounts
2. `AGENT_MOUNTS`
3. explicit `--mount` flags

If duplicates occur:

- explicit CLI flags override environment variable
- environment variable overrides profile only when same mount name appears
- mode upgrades are still blocked unless allowed

### 13.3 Environment Variable Safety

Do not allow raw arbitrary Docker arguments through environment variables in MVP.

Do not support:

```zsh
AGENT_DOCKER_ARGS="..."
```

That creates a policy bypass.

---

## 14. Credentials

### 14.1 MVP Rule

No credential injection in MVP.

This includes:

- no SSH key mounting
- no API key mounting
- no password manager integration
- no browser cookie sharing
- no GitHub token injection

### 14.2 Manual Workaround

For MVP, users may manually paste temporary tokens into the container session when needed.

### 14.3 Future Credential Broker

Later support:

```zsh
agent-run --credential github-readonly
agent-run --credential openai-api-limited
```

But this needs careful design.

Credential rules should include:

- scope
- expiration
- visible summary
- redacted logging
- revocation guidance
- no persistence inside mounted workspace

---

## 15. Network Policy

### 15.1 MVP Network Modes

Support:

```text
none
bridge
```

Map:

```json
"network": "none"
```

to:

```zsh
--network none
```

Map:

```json
"network": "bridge"
```

to:

```zsh
--network bridge
```

### 15.2 Future Network Allowlisting

Do not implement allowlisted domains in MVP unless using a proxy.

Future:

```yaml
network:
  mode: allowlist
  domains:
    - github.com
    - pypi.org
    - npmjs.com
```

Implementation would likely require a local proxy or firewall layer.

---

## 16. Build Steps

## Phase 0 — Prepare Host

### Step 0.1: Confirm Docker Desktop

Run:

```zsh
docker version
docker ps
```

Expected:

- Docker daemon reachable
- no permission errors

### Step 0.2: Create Project Folder

```zsh
mkdir -p ~/agent-permission-manager/{bin,config,docker,logs/sessions,examples}
cd ~/agent-permission-manager
```

### Step 0.3: Create AgentWork Folder

```zsh
sudo mkdir -p /Users/Shared/AgentWork/{inbox,workspace,outbox,logs,quarantine}
sudo chown -R "$USER":staff /Users/Shared/AgentWork
chmod -R 755 /Users/Shared/AgentWork
```

Later this can be tightened, but MVP should start simple.

---

## Phase 1 — Create Config Files

### Step 1.1: Create `config/profiles.json`

Use the profile JSON from Section 6.4.

### Step 1.2: Create `config/mounts.json`

Start with:

```json
{
  "agentwork": {
    "label": "AgentWork",
    "path": "/Users/Shared/AgentWork",
    "container_path": "/workspace/agentwork",
    "mode": "rw",
    "required": true
  },
  "quarantine": {
    "label": "Quarantine Workspace",
    "path": "/Users/Shared/AgentWork/quarantine",
    "container_path": "/workspace/quarantine",
    "mode": "rw",
    "required": false
  }
}
```

Add project-specific mounts later.

### Step 1.3: Create `config/policy.json`

```json
{
  "blocked_paths": [
    "/",
    "~",
    "~/Library",
    "~/Library/Keychains",
    "~/Library/Application Support",
    "~/Library/Cookies",
    "~/Library/Group Containers",
    "~/Library/Safari",
    "~/.ssh",
    "~/.aws",
    "~/.gnupg",
    "~/.config"
  ],
  "blocked_exact_paths": [
    "/var/run/docker.sock"
  ],
  "warn_paths": [
    "~/Desktop",
    "~/Downloads",
    "~/Documents"
  ],
  "allow_arbitrary_paths": false,
  "allow_mode_upgrade": false
}
```

The launcher must expand `~` before validating.

---

## Phase 2 — Build Docker Image

### Step 2.1: Create `docker/Dockerfile`

```Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends     bash     zsh     git     curl     wget     jq     ca-certificates     ripgrep     fd-find     unzip     less     nano   && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 agent

COPY entrypoint.sh /usr/local/bin/agent-entrypoint
RUN chmod +x /usr/local/bin/agent-entrypoint

USER agent
WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/agent-entrypoint"]
CMD ["/bin/bash"]
```

### Step 2.2: Create `docker/entrypoint.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

if [ -d /workspace/agentwork/workspace ]; then
  cd /workspace/agentwork/workspace
elif [ -d /workspace ]; then
  cd /workspace
fi

exec "$@"
```

### Step 2.3: Build Image

```zsh
docker build -t agent-permission-manager:local ./docker
```

### Step 2.4: Test Image

```zsh
docker run --rm -it agent-permission-manager:local echo "container works"
```

Expected:

```text
container works
```

---

## Phase 3 — Build `agent-run`

### Step 3.1: Create `bin/agent-run`

Implement Python script with:

- argument parsing
- config loading
- profile resolution
- mount resolution
- path validation
- Docker command generation
- dry-run support
- session logging
- container execution

### Step 3.2: Make Executable

```zsh
chmod +x ~/agent-permission-manager/bin/agent-run
```

### Step 3.3: Add to PATH

Add to `~/.zshrc`:

```zsh
export PATH="$HOME/agent-permission-manager/bin:$PATH"
```

Reload:

```zsh
source ~/.zshrc
```

### Step 3.4: Test CLI Discovery

```zsh
agent-run --version
agent-run --list-profiles
agent-run --list-mounts
```

---

## Phase 4 — Implement Path Validation

### Step 4.1: Expand Paths

For every configured path:

```python
Path(path).expanduser().resolve()
```

### Step 4.2: Reject Nonexistent Paths

If path does not exist:

```text
ERROR: Mount path does not exist
```

### Step 4.3: Reject Non-Directories

For MVP, require directories.

### Step 4.4: Block Exact Dangerous Paths

Reject exact matches:

```text
/
~/.ssh
~/Library
```

### Step 4.5: Block Children of Dangerous Paths

Reject:

```text
~/Library/Application Support/Google/Chrome
```

because it is inside:

```text
~/Library/Application Support
```

### Step 4.6: Resolve Symlink Bypass

If:

```text
~/Projects/foo -> ~/.ssh
```

then `.resolve()` should reveal the real path and block it.

---

## Phase 5 — Implement Dry Run

### Step 5.1: Basic Dry Run

```zsh
agent-run --dry-run
```

Should show:

- profile
- mounts
- network
- Docker security settings
- Docker command
- log path

### Step 5.2: Dry Run With Mount

```zsh
agent-run --dry-run --profile power --mount project-alpha
```

### Step 5.3: Dry Run Should Not Create Container

Verify:

```zsh
docker ps -a
```

No new container should appear.

---

## Phase 6 — Implement Session Logging

### Step 6.1: Create Session ID

Format:

```text
YYYYMMDD-HHMMSS-profile-shortuuid
```

Example:

```text
20260507-231500-default-a1b2c3
```

### Step 6.2: Write Start Log

Before launch, write session metadata with:

```json
"status": "started"
```

### Step 6.3: Update End Log

After container exits, update:

```json
"status": "complete"
"exit_code": 0
"timestamp_end": "..."
```

### Step 6.4: Handle Failure

If Docker fails, log:

```json
"status": "error"
"exit_code": 125
```

---

## Phase 7 — Implement Environment Variable Mounts

### Step 7.1: Parse `AGENT_MOUNTS`

Support comma-separated:

```zsh
AGENT_MOUNTS="project-alpha,research:ro" agent-run --profile power
```

### Step 7.2: Merge With CLI Mounts

Final mount list:

1. profile default mounts
2. environment mounts
3. CLI mounts

### Step 7.3: De-Duplicate

If the same mount appears twice, use the later specification.

### Step 7.4: Preserve Safety Rules

Even environment mounts must be registry-defined and policy-validated.

---

## Phase 8 — Add Convenience Wrappers

### Step 8.1: Create `bin/agent-safe`

```zsh
#!/bin/zsh
exec agent-run --profile safe "$@"
```

### Step 8.2: Create `bin/agent-net`

```zsh
#!/bin/zsh
exec agent-run --profile net "$@"
```

### Step 8.3: Create `bin/agent-build`

```zsh
#!/bin/zsh
if [ "$#" -ge 1 ]; then
  exec agent-run --profile build --mount "$1" "${@:2}"
else
  exec agent-run --profile build "$@"
fi
```

### Step 8.4: Create `bin/agent-power`

```zsh
#!/bin/zsh
if [ "$#" -ge 1 ]; then
  exec agent-run --profile power --mount "$1" "${@:2}"
else
  exec agent-run --profile power "$@"
fi
```

### Step 8.5: Create `bin/agent-quarantine`

```zsh
#!/bin/zsh
exec agent-run --profile quarantine "$@"
```

### Step 8.6: Make Wrappers Executable

```zsh
chmod +x ~/agent-permission-manager/bin/agent-*
```

---

## Phase 9 — Add Project Mounts

### Step 9.1: Add Mount Manually

Edit:

```text
config/mounts.json
```

Add:

```json
"some-project": {
  "label": "Some Project",
  "path": "/Users/bryan/Projects/some-project",
  "container_path": "/workspace/some-project",
  "mode": "rw",
  "required": false
}
```

### Step 9.2: Test List

```zsh
agent-run --list-mounts
```

### Step 9.3: Dry Run

```zsh
agent-run --dry-run --profile power --mount some-project
```

### Step 9.4: Launch

```zsh
agent-power some-project
```

---

## Phase 10 — Test Matrix

### Step 10.1: Default Launch

```zsh
agent-run
```

Expected:

- starts container
- AgentWork mounted rw
- network on
- no host home access

Inside container:

```bash
pwd
ls /workspace
```

### Step 10.2: Safe Offline Launch

```zsh
agent-safe
```

Inside container:

```bash
curl https://example.com
```

Expected:

- network failure

### Step 10.3: Net Launch

```zsh
agent-net
```

Inside container:

```bash
curl https://example.com
```

Expected:

- network works

### Step 10.4: Blocked Mount Test

Add a mount pointing to:

```text
/Users/bryan/.ssh
```

Run:

```zsh
agent-run --dry-run --mount ssh-test
```

Expected:

- rejected

### Step 10.5: Symlink Test

Create:

```zsh
ln -s ~/.ssh /Users/Shared/AgentWork/workspace/fake-project
```

Add mount to `fake-project`.

Expected:

- rejected after real path resolution

### Step 10.6: Read-Only Test

Mount a folder as `ro`.

Inside container:

```bash
touch /workspace/research/test.txt
```

Expected:

- write fails

### Step 10.7: Read-Write Test

Mount a project as `rw`.

Inside container:

```bash
touch /workspace/project-alpha/agent-test.txt
```

Expected:

- write succeeds

### Step 10.8: Log Test

After exit:

```zsh
ls ~/agent-permission-manager/logs/sessions
cat ~/agent-permission-manager/logs/sessions/<latest>.json
```

Expected:

- profile recorded
- mounts recorded
- network recorded
- exit code recorded

---

## Phase 11 — Hermes Integration

### Step 11.1: Determine Hermes Launch Command

Identify the command currently used to start Hermes.

Possible examples:

```zsh
hermes
hermes-agent
npx hermes
python -m hermes
```

### Step 11.2: Add Command Support

Support:

```zsh
agent-run --profile default --command hermes
```

or config-based default:

```json
"agent_command": ["hermes"]
```

### Step 11.3: Install Hermes Inside Docker Image

If Hermes can be installed via npm/pip/binary, add it to Dockerfile.

Examples:

```Dockerfile
RUN pip install hermes-agent
```

or:

```Dockerfile
RUN npm install -g hermes-agent
```

Use the actual Hermes install mechanism.

### Step 11.4: Rebuild Image

```zsh
docker build -t agent-permission-manager:local ./docker
```

### Step 11.5: Test Hermes

```zsh
agent-run --profile default --command hermes
```

### Step 11.6: Persist Hermes Config Carefully

If Hermes needs config persistence, create a dedicated mount:

```text
/Users/Shared/AgentWork/hermes-config
```

Mount it inside container:

```text
/workspace/hermes-config
```

Do not mount host `~/.hermes` unless reviewed.

---

## Phase 12 — Documentation

### Step 12.1: README Sections

Write:

1. What this does
2. What this does not do
3. Security model
4. Install steps
5. Profiles
6. Mount registry
7. Examples
8. Dangerous paths
9. Logs
10. Troubleshooting
11. Future roadmap

### Step 12.2: Example Use Cases

Include:

```zsh
agent-run
agent-safe
agent-net --mount research
agent-build project-alpha
AGENT_MOUNTS="project-alpha,research:ro" agent-power
```

### Step 12.3: Warning Section

Include:

```text
Do not mount:
- your home directory
- browser profile
- password manager data
- SSH keys
- Docker socket
- Keychain folders
```

---

## Phase 13 — MVP Acceptance Criteria

The MVP is complete when:

1. `agent-run` launches a containerized agent shell.
2. `default` profile works without flags.
3. At least five profiles exist.
4. Mounts are selected by friendly names.
5. Mounts can be read-only or read-write.
6. Dangerous mounts are blocked.
7. Symlink bypasses are blocked.
8. Network can be enabled or disabled by profile.
9. Dry run prints the full permission summary.
10. Session logs are written.
11. Convenience wrappers work.
12. Hermes can run inside the environment or the tool can launch a generic shell pending Hermes integration.
13. The user can complete a real coding/research task without exposing the full host filesystem.

---

## 17. Suggested Development Sequence If I Build It

If you decide to have me build this, the cleanest sequence is:

### Build Pass 1

Create:

- project skeleton
- Dockerfile
- entrypoint
- profiles.json
- mounts.json
- policy.json
- first version of `agent-run`
- README draft

### Build Pass 2

Add:

- full path validation
- dry-run
- logging
- environment variable mounts
- convenience wrappers

### Build Pass 3

Test locally with:

- default profile
- safe profile
- net profile
- blocked path examples
- read-only mount
- read-write mount

### Build Pass 4

Integrate Hermes-specific launch command.

### Build Pass 5

Refine README and add user-facing install instructions.

---

## 18. Future Roadmap

### 18.1 Version 0.2

- profile inheritance
- temporary session duration
- command transcript option
- one-command mount registration
- `agent-mount add project-alpha /path/to/project --mode rw`
- config validation command
- shell completions

### 18.2 Version 0.3

- credential broker
- one-time token injection
- GitHub read-only token profile
- OpenAI/Anthropic API profile
- secret redaction in logs

### 18.3 Version 0.4

- network allowlisting via proxy
- domain-level permissions
- package-source allowlisting
- npm/pip install auditing

### 18.4 Version 0.5

- GUI permission prompt
- menu bar app
- launch profiles from UI
- visual session history

### 18.5 Version 1.0

- multi-agent support
- Claude Code / Codex / Hermes / OpenCode adapters
- reusable agent profiles
- policy export/import
- signed releases
- macOS notarization
- enterprise policy mode

---

## 19. Key Product Insight

The MVP should not feel like a security appliance.

It should feel like:

> “I can safely share exactly the right folders and powers with my agent for this task.”

The safe path must also be the easy path.

That is the main reason the default profile matters.

---

## 20. First Build Recommendation

Start with:

```text
CLI-first
macOS-first
Docker-backed
JSON-configured
Hermes-compatible
profile-driven
mount-registry-based
logs-on-by-default
```

This is enough to validate the product idea without overbuilding.


---

# Branding / Product Roadmap Notes (v2 Addendum)

## Working Product Architecture

```text
Warlock = agent runtime/orchestrator
Airlock = permission/governance layer
Breaker = runtime behavioral interruption engine
Quarantine = high-risk execution mode
```

Core framing:

```text
Warlock operates.
Airlock governs.
```

or:

```text
Warlock executes inside Airlock.
```

---

## Conceptual Product Positioning

This project should NOT be positioned merely as:
- a Docker wrapper
- an AI sandbox
- a security utility

The stronger positioning is:

```text
Local Agent Capability Governance
```

or:

```text
Agent Permission Management Infrastructure
```

Core value proposition:

```text
Useful autonomous agents without unrestricted machine access.
```

---

## Future Product Direction

### Phase 1 (MVP)
Focus:
- profiles
- scoped mounts
- Docker isolation
- session logging
- explicit permission grants
- temporary capability exposure

Do NOT add:
- autonomous AI risk scoring
- shadow home simulation
- enterprise policy orchestration
- browser automation governance

Goal:
Validate the capability-governance workflow.

---

## Phase 2 (Advanced Safety Features)

### Breaker System

The Breaker system dynamically revokes permissions or pauses execution when suspicious or unexpected behavior occurs.

Core concept:

```text
Permissions are dynamically revocable based on runtime behavior.
```

Potential triggers:
- access to unexpected filesystem locations
- broad filesystem scans
- attempts to access credentials
- suspicious networking behavior
- unexpected sudo requests
- destructive shell commands
- privilege escalation attempts

Potential responses:
- revoke mounts
- disable network
- pause container
- require manual approval
- terminate session

Initial implementation recommendation:
- rule-based heuristics only
- no AI-driven behavioral analysis in MVP

---

## Phase 3 (Shadow Home / Decoy Environment)

Advanced optional safety layer:

```text
Shadow Home
```

Concept:
The agent first executes potentially risky tasks against a fake mirrored environment containing:
- decoy files
- fake credentials
- synthetic projects
- simulated browser/session artifacts

Purpose:
Observe agent behavior before exposing the real environment.

This feature is intentionally deferred beyond MVP due to:
- complexity
- execution latency
- infrastructure overhead

However, it could become a significant differentiator long term.

---

## Long-Term Strategic Observation

Most current agent systems focus on:
- static sandboxing
- permission prompts
- container isolation

This project instead focuses on:

```text
dynamic capability governance
```

That distinction may become increasingly important as autonomous agents become more capable and are granted broader local system access.
