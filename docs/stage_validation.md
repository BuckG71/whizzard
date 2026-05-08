# Stage Validation Checklist

Manual validation steps for each MVP stage. Update this file as new stages land.

---

## Stage 1 — Generic Docker Shell Launch

### Setup

```sh
cd /Users/bg1971/ai-sandbox/airlock-warlock
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest
```

### Step 1: Run unit tests (no Docker required)

```sh
pytest -v
```

Expected: all tests in `tests/test_config.py` and `tests/test_docker_cmd.py` pass.

### Step 2: Build the execution image

```sh
warlock image build
warlock image status
```

Expected:
- Build completes without errors
- `image status` reports `warlock-base:latest` is present

### Step 3: Launch a contained shell under the default profile

```sh
warlock run --profile default
```

Expected: see `Airlock Profile: DEFAULT` banner followed by a bash prompt inside the container.

### Step 4: Verify containment from inside the container

Run these inside the container shell:

```sh
whoami                     # expected: warlock
id                         # expected: uid=1000(warlock) gid=1000(warlock)
ls /Users 2>&1 | head -3   # expected: fail or empty — host home not mounted
ls / | head -20            # see contained rootfs
touch /testfile            # expected: fail — root fs is read-only
touch /tmp/testfile        # expected: succeed — /tmp is tmpfs
exit
```

### Step 5: Verify offline profile

```sh
warlock run --profile safe
```

Inside the container:

```sh
curl -m 5 https://example.com   # expected: fail — network disabled
exit
```

### Step 6: CLI surface check

```sh
warlock --help                  # shows command tree
warlock profiles list           # displays all five profiles
warlock run --profile build     # network on, rw allowed
warlock run --profile power     # network on, allow_broad_mount=true
warlock run --profile quarantine  # network off, ro only
```

### Pass criteria

All of the following must be true:

- [ ] All unit tests pass
- [ ] Image builds and shows in `image status`
- [ ] `whoami` inside container reports `warlock`, not host user
- [ ] Host home directory inaccessible from inside container
- [ ] Root filesystem is read-only; `/tmp` is writable
- [ ] `safe` profile has network disabled (curl fails)
- [ ] `default` profile has network enabled (curl succeeds)
- [ ] `warlock profiles list` shows all five profiles
- [ ] `warlock --help` shows expected command tree

### Report any of these as bugs

- Container runs as root
- Any host path is accessible from inside container
- Network mode does not match profile
- Tests fail
- CLI commands error out unexpectedly
- macOS-specific Docker Desktop issues (UID mapping, volume mount errors)

---

## Stage 2 — Mount Registry

*(To be added once Stage 2 lands.)*

---

## Stage 3 — Profiles (JSON-driven)

*(To be added once Stage 3 lands.)*

---

## Stage 4 — Dry Run

*(To be added once Stage 4 lands.)*

---

## Stage 5 — Session Logging

*(To be added once Stage 5 lands.)*

---

## Stage 6 — Safety Validation

*(To be added once Stage 6 lands.)*

---

## Stage 7 — Generic Adapter

*(To be added once Stage 7 lands.)*

---

## Stage 8 — Hermes Integration

*(To be added once Stage 8 lands.)*

---

## Stage 9 — Image Management

*(To be added once Stage 9 lands.)*
