# Warlock / Airlock MVP Build Plan v3

Date: 2026-05-08

## Purpose

Build a local-first agent permission manager for solo developers and AI power users.

The MVP should let a user launch an agent/Hermes session with explicit, temporary, human-readable permissions:

```zsh
warlock run --profile default --mount agentwork
warlock run --profile build --mount project-alpha
warlock run --dry-run --profile power --mount project-alpha
```

Core principle:

```text
The launcher controls what the agent can access.
The agent itself does not decide.
```

---

# Product Architecture

```text
Warlock = local CLI launcher / orchestrator
Airlock = permission and containment layer
Profiles = predefined permission envelopes
Mount Registry = human-readable folder capability map
Docker Cell = controlled execution environment
Session Log = audit record of granted capabilities
```

MVP architecture:

```text
Host Mac
  |
  | warlock CLI
  v
Airlock policy resolution
  |
  | profile + mounts + network + limits
  v
Docker execution cell
  |
  | mounted folders only
  v
Agent / Hermes / shell session
```

---

# MVP Definition

The MVP is operational when the system can:

1. Launch a generic Docker shell under a named profile.
2. Mount only registered folders.
3. Apply read-only and read-write mount modes.
4. Toggle network access by profile.
5. Reject obviously dangerous mounts.
6. Show a dry-run permission summary before launch.
7. Write a session log.
8. Run Hermes inside the controlled environment or provide a clear integration path.

---

# Explicit Build Order

This build order is important. Do not start with Hermes integration.

## Stage 1 — Generic Docker Shell Launch

Goal:
Prove that Warlock can launch a contained terminal session.

Deliverable:

```zsh
warlock run --profile default
```

Expected result:
- starts Docker container
- opens shell
- mounts only `/Users/Shared/AgentWork`
- uses non-root container user where practical
- applies baseline Docker restrictions

Reason:
This validates the core containment model before adding config complexity.

---

## Stage 2 — Mount Registry

Goal:
Add named, human-readable mount capabilities.

Deliverable:

```zsh
warlock mounts list
warlock run --profile default --mount agentwork
```

The system should resolve:

```json
{
  "agentwork": {
    "path": "/Users/Shared/AgentWork",
    "mode": "rw"
  }
}
```

into a Docker bind mount.

Rules:
- mounts must be registered
- arbitrary host paths should not be accepted by default
- each mount has a fixed default mode
- CLI may allow lowering permissions from `rw` to `ro`
- CLI should not allow raising a mount above registry permissions

---

## Stage 3 — Profiles

Goal:
Add capability presets.

Deliverable:

```zsh
warlock profiles list
warlock run --profile safe
warlock run --profile default
warlock run --profile build --mount project-alpha
```

Initial profiles:

| Profile | Purpose | Network | Default Mounts | Notes |
|---|---|---:|---|---|
| safe | lowest-risk local work | off | agentwork:rw | no internet |
| default | daily driver | on | agentwork:rw | safe enough to leave on |
| build | coding/package installs | on | agentwork:rw | project mounts allowed |
| power | trusted local automation | on | agentwork:rw | broader but still controlled |
| quarantine | unknown/sketchy code | off | agentwork:rw | future VM candidate |

Default profile:

```text
default = SAFE-NET
```

Meaning:
- network enabled
- shell enabled
- workspace write access
- no host home directory
- no Docker socket
- no browser profile
- no password manager
- no SSH keys
- no sudo

---

## Stage 4 — Dry Run

Goal:
Make permissions visible before execution.

Deliverable:

```zsh
warlock run --dry-run --profile build --mount project-alpha
```

Example output:

```text
Warlock Dry Run

Airlock Profile: build
Network: enabled
Docker Socket: disabled
Privileged: false
Read-only RootFS: true

Mounts:
- agentwork -> /workspace/agentwork (rw)
- project-alpha -> /workspace/project-alpha (rw)

Session logging: enabled

No container started.
```

Reason:
Dry-run output becomes both a safety feature and a UX primitive.

---

## Stage 5 — Session Logging

Goal:
Create an audit trail of what permissions were granted.

Deliverable:
Every session writes a log file.

Example path:

```text
~/.warlock/logs/session-2026-05-08-231500.log
```

Log fields:
- timestamp
- command
- profile
- network mode
- mounts
- Docker image
- Docker container name/id
- start time
- end time
- exit code

Do not log:
- secrets
- environment variable values that may contain credentials
- full command output initially

---

## Stage 6 — Safety Checks

Goal:
Block the most dangerous user mistakes.

Deliverable:
Warlock refuses dangerous mounts unless a future explicit override mechanism is added.

Denylist examples:
- `/`
- `$HOME`
- `~/.ssh`
- `~/Library`
- `~/Library/Keychains`
- `~/Library/Application Support`
- browser profile directories
- password manager directories
- Docker socket
- system directories

Warning examples:
- `~/Documents`
- `~/Desktop`
- cloud sync roots
- broad project parent folders

MVP behavior:
- hard block critical paths
- warn on broad paths
- require named registry entries for all mounts

---

## Stage 7 — Convenience Wrappers

Goal:
Make secure operation low friction.

Deliverables:

```zsh
warlock-default
warlock-safe
warlock-build project-alpha
warlock-power project-alpha
```

These wrappers should call the main CLI internally.

Reason:
The safe path must be the easy path.

---

## Stage 8 — Hermes Integration

Goal:
Run Hermes through the Warlock/Airlock permission system.

Only start this stage after generic Docker shell launch, mounts, profiles, dry-run, and logging work.

Potential integration paths:

### Option A — Hermes Inside Container

Build a Docker image containing:
- Hermes
- Python
- Node
- git
- jq
- required runtime dependencies

Pros:
- cleaner containment
- reproducible runtime
- fewer host dependencies

Cons:
- Hermes install/config may require iteration
- persistence must be explicitly mounted

### Option B — Host Hermes, Container Terminal

Use Hermes on host but route terminal/tool execution into Docker.

Pros:
- less disruption to existing Hermes setup
- easier initial testing

Cons:
- weaker isolation if Hermes itself has broad host access
- more dependent on Hermes configuration

### Recommended MVP Path

Start with Option A if practical.

If Hermes install becomes a blocker, use Option B temporarily while preserving the core Airlock model.

---

# Suggested Initial Repository Structure

```text
warlock-airlock/
  README.md
  pyproject.toml
  warlock/
    __init__.py
    cli.py
    config.py
    docker_cmd.py
    safety.py
    logging.py
  config/
    profiles.json
    mounts.json
  docker/
    Dockerfile
  scripts/
    install.sh
    warlock-safe
    warlock-default
    warlock-build
    warlock-power
  tests/
    test_config.py
    test_safety.py
    test_docker_cmd.py
```

Recommendation:
Use Python for the CLI rather than zsh.

Reason:
- easier argument parsing
- easier config parsing
- easier tests
- cleaner future expansion

---

# Initial Config Files

## profiles.json

```json
{
  "safe": {
    "network": "none",
    "default_mounts": ["agentwork"],
    "read_only_rootfs": true,
    "cap_drop_all": true,
    "no_new_privileges": true,
    "memory": "4g",
    "cpus": "2"
  },
  "default": {
    "network": "bridge",
    "default_mounts": ["agentwork"],
    "read_only_rootfs": true,
    "cap_drop_all": true,
    "no_new_privileges": true,
    "memory": "4g",
    "cpus": "2"
  },
  "build": {
    "network": "bridge",
    "default_mounts": ["agentwork"],
    "read_only_rootfs": false,
    "cap_drop_all": true,
    "no_new_privileges": true,
    "memory": "6g",
    "cpus": "4"
  },
  "power": {
    "network": "bridge",
    "default_mounts": ["agentwork"],
    "read_only_rootfs": false,
    "cap_drop_all": true,
    "no_new_privileges": true,
    "memory": "8g",
    "cpus": "4"
  },
  "quarantine": {
    "network": "none",
    "default_mounts": ["agentwork"],
    "read_only_rootfs": true,
    "cap_drop_all": true,
    "no_new_privileges": true,
    "memory": "4g",
    "cpus": "2"
  }
}
```

## mounts.json

```json
{
  "agentwork": {
    "path": "/Users/Shared/AgentWork",
    "mode": "rw",
    "description": "Default shared agent workspace"
  },
  "project-alpha": {
    "path": "/Users/bryan/Projects/project-alpha",
    "mode": "rw",
    "description": "Example project folder"
  },
  "research": {
    "path": "/Users/bryan/Documents/Research",
    "mode": "ro",
    "description": "Read-only research folder"
  }
}
```

---

# Docker Command Target

The CLI should generate commands equivalent to:

```zsh
docker run --rm -it \
  --name warlock-session-$(date +%s) \
  --network bridge \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 256 \
  --memory 4g \
  --cpus 2 \
  --read-only \
  --tmpfs /tmp \
  -v /Users/Shared/AgentWork:/workspace/agentwork:rw \
  warlock-agent:local
```

When network is disabled:

```zsh
--network none
```

Important:
Do not mount:
- host Docker socket
- host home directory
- SSH keys
- browser profiles
- Keychain directories

---

# Implementation Steps

## Step 1 — Create Project Directory

```zsh
mkdir -p ~/Projects/warlock-airlock
cd ~/Projects/warlock-airlock
```

## Step 2 — Initialize Repo

```zsh
git init
mkdir -p warlock config docker scripts tests
touch README.md pyproject.toml
touch warlock/__init__.py
touch warlock/cli.py warlock/config.py warlock/docker_cmd.py warlock/safety.py warlock/logging.py
touch config/profiles.json config/mounts.json
```

## Step 3 — Create Baseline Dockerfile

```Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    git \
    curl \
    jq \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 agent

WORKDIR /workspace

USER agent

CMD ["/bin/bash"]
```

## Step 4 — Build Docker Image

```zsh
docker build -t warlock-agent:local docker/
```

## Step 5 — Manually Validate Docker Cell

```zsh
docker run --rm -it \
  --network none \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 256 \
  --memory 4g \
  --cpus 2 \
  --read-only \
  --tmpfs /tmp \
  -v /Users/Shared/AgentWork:/workspace/agentwork:rw \
  warlock-agent:local
```

Inside container:

```bash
whoami
pwd
ls /workspace
```

Expected:
- user is `agent`
- only mounted workspace is visible
- no host home directory is mounted
- shell works

## Step 6 — Add CLI Argument Parsing

Minimum command support:

```zsh
python -m warlock.cli run --profile default
python -m warlock.cli run --profile default --mount agentwork
python -m warlock.cli run --dry-run --profile build --mount project-alpha
python -m warlock.cli profiles list
python -m warlock.cli mounts list
```

## Step 7 — Load Config

`config.py` should:
- load `profiles.json`
- load `mounts.json`
- validate requested profile exists
- validate requested mounts exist
- merge default profile mounts with CLI mounts
- de-duplicate mounts

## Step 8 — Add Safety Validation

`safety.py` should:
- expand paths
- reject dangerous paths
- reject missing paths unless explicitly creating AgentWork
- reject symlinks that resolve into dangerous paths
- warn on broad paths

Critical check:
Use resolved absolute paths, not raw strings.

## Step 9 — Generate Docker Command

`docker_cmd.py` should:
- convert profile + mounts into Docker arguments
- add network mode
- add resource limits
- add security flags
- add mount flags
- add image
- add command

## Step 10 — Implement Dry Run

Dry run should:
- print resolved profile
- print resolved mounts
- print network mode
- print Docker image
- print whether rootfs is read-only
- print generated Docker command
- not start Docker

## Step 11 — Implement Run

Run should:
- create session id
- generate Docker command
- write pre-run log
- launch Docker
- capture exit code
- write post-run log

## Step 12 — Add Session Logging

`logging.py` should write structured JSONL or plain text logs.

Recommended:
Use JSONL initially.

Example:

```json
{
  "session_id": "20260508-231500",
  "profile": "default",
  "network": "bridge",
  "mounts": [
    {"name": "agentwork", "host": "/Users/Shared/AgentWork", "container": "/workspace/agentwork", "mode": "rw"}
  ],
  "image": "warlock-agent:local",
  "started_at": "2026-05-08T23:15:00",
  "exit_code": 0
}
```

## Step 13 — Add Convenience Scripts

Example:

```zsh
#!/bin/zsh
python -m warlock.cli run --profile default "$@"
```

Scripts:
- `warlock-safe`
- `warlock-default`
- `warlock-build`
- `warlock-power`

## Step 14 — Add Basic Tests

Tests:
- unknown profile rejected
- unknown mount rejected
- dangerous path rejected
- read-only mount generated correctly
- network none generated correctly
- dry-run does not execute Docker

## Step 15 — Test With a Fake Project

Create:

```zsh
mkdir -p /Users/Shared/AgentWork
mkdir -p ~/Projects/warlock-test-project
echo "hello" > ~/Projects/warlock-test-project/hello.txt
```

Add mount registry entry.

Run:

```zsh
python -m warlock.cli run --dry-run --profile build --mount warlock-test-project
python -m warlock.cli run --profile build --mount warlock-test-project
```

Inside container:
- read project file
- write test output to mounted workspace
- confirm no host home access

## Step 16 — Hermes Integration Attempt

Only after Stages 1–7 are working.

Try:
- install Hermes into Docker image
- run Hermes inside container
- persist only required Hermes config through explicit mount
- avoid mounting host home

If Hermes requires host-level integration:
- document limitation
- use host Hermes with Docker terminal mode temporarily
- keep Warlock as permission-controlled terminal/runtime layer

---

# First Operational MVP Acceptance Test

The MVP passes if all of the following work:

```zsh
warlock run --dry-run --profile default
warlock run --profile safe
warlock run --profile default
warlock run --profile build --mount warlock-test-project
warlock mounts list
warlock profiles list
```

And:
- dangerous mounts are rejected
- logs are written
- Docker network mode changes by profile
- read-only mounts cannot be written inside the container
- no host home directory is mounted
- Docker socket is not mounted

---

# Non-MVP Features

Do not build these initially:
- GUI
- cloud backend
- enterprise policy system
- AI risk scoring
- shadow home / decoy environment
- browser automation governance
- credential broker
- real-time breaker engine
- VM orchestration

These remain valuable roadmap items, but adding them now will slow the MVP.

---

# Practical Confidence Assessment

Confidence for generic MVP:
High.

Expected difficulty:
- low to moderate

Main risk:
Hermes-specific integration details.

Recommended approach:
Build Warlock/Airlock as a generic local permission launcher first, then integrate Hermes.

This keeps the project useful even if Hermes integration requires extra iteration.

---

# Build Partner Workflow

When building interactively, use one step at a time.

The recommended sequence is:

```text
1. Create repo/files
2. Build Docker image
3. Prove manual Docker launch
4. Implement CLI skeleton
5. Implement config loading
6. Implement safety checks
7. Implement Docker command generation
8. Implement dry-run
9. Implement real run
10. Implement logging
11. Add convenience scripts
12. Add tests
13. Attempt Hermes integration
```

At each step:
- run one command
- inspect output
- fix before moving on

---

# Final MVP Thesis

This project is not merely an agent sandbox.

It is a local-first capability governance layer for solo AI power users.

The narrow MVP should prove:

```text
Useful agent execution can coexist with explicit, temporary, human-readable permission boundaries.
```
