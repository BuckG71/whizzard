# Stage Validation Checklist

Manual validation steps for each MVP stage. Update this file as new stages land.

---

## Stage 1 — Generic Docker Shell Launch

### Setup

```sh
cd /Users/USER/ai-sandbox/airlock-warlock
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
whizzard image build
whizzard image status
```

Expected:
- Build completes without errors
- `image status` reports `whizzard-base:latest` is present

### Step 3: Launch a contained shell under the default profile

```sh
whizzard run --profile default
```

Expected: see `Airlock Profile: DEFAULT` banner followed by a bash prompt inside the container.

### Step 4: Verify containment from inside the container

Run these inside the container shell:

```sh
whoami                     # expected: whizzard
id                         # expected: uid=1000(whizzard) gid=1000(whizzard)
ls /Users 2>&1 | head -3   # expected: fail or empty — host home not mounted
ls / | head -20            # see contained rootfs
touch /testfile            # expected: fail — root fs is read-only
touch /tmp/testfile        # expected: succeed — /tmp is tmpfs
exit
```

### Step 5: Verify offline profile

```sh
whizzard run --profile safe
```

Inside the container:

```sh
curl -m 5 https://example.com   # expected: fail — network disabled
exit
```

### Step 6: CLI surface check

```sh
whizzard --help                  # shows command tree
whizzard profiles list           # displays all five profiles
whizzard run --profile build     # network on, rw allowed
whizzard run --profile power     # network on, allow_broad_mount=true
whizzard run --profile quarantine  # network off, ro only
```

### Pass criteria

All of the following must be true:

- [ ] All unit tests pass
- [ ] Image builds and shows in `image status`
- [ ] `whoami` inside container reports `whizzard`, not host user
- [ ] Host home directory inaccessible from inside container
- [ ] Root filesystem is read-only; `/tmp` is writable
- [ ] `safe` profile has network disabled (curl fails)
- [ ] `default` profile has network enabled (curl succeeds)
- [ ] `whizzard profiles list` shows all five profiles
- [ ] `whizzard --help` shows expected command tree

### Report any of these as bugs

- Container runs as root
- Any host path is accessible from inside container
- Network mode does not match profile
- Tests fail
- CLI commands error out unexpectedly
- macOS-specific Docker Desktop issues (UID mapping, volume mount errors)

---

## Stage 2 — Mount Registry

### Setup

Update the install (in-place editable install picks up new modules automatically, but pytest needs a fresh collect):

```sh
cd /Users/USER/ai-sandbox/airlock-warlock
source .venv/bin/activate
git pull
pytest -v
```

Expected: previous 13 tests still pass plus 19 new tests (14 in `test_mounts.py` plus 5 mount-aware tests in `test_docker_cmd.py`). 32 total green.

### Step 1: List mounts before any are registered

```sh
whizzard mounts list
```

Expected: yellow message saying no mounts are registered, with a pointer to `~/.whizzard/config/mounts.json` and `config/mounts.json.example`.

### Step 2: Register a couple of test mounts

```sh
mkdir -p ~/test-whizzard-rw ~/test-whizzard-ro
echo "writable test data" > ~/test-whizzard-rw/hello.txt
echo "read-only test data" > ~/test-whizzard-ro/hello.txt

# Ensure the whizzard config directory exists. (ensure_warlock_home()
# only runs on `whizzard run`, not on `mounts list`, so on a fresh
# install this directory may not exist yet.)
mkdir -p ~/.whizzard/config

cat > ~/.whizzard/config/mounts.json <<'JSON'
{
  "schema_version": 1,
  "mounts": {
    "rw-test": {
      "host_path": "~/test-whizzard-rw",
      "default_mode": "rw",
      "description": "writable test mount"
    },
    "ro-test": {
      "host_path": "~/test-whizzard-ro",
      "default_mode": "ro",
      "description": "read-only test mount"
    }
  }
}
JSON
```

### Step 3: Verify the registry is loaded

```sh
whizzard mounts list
```

Expected: a Rich table showing both `rw-test` and `ro-test` with their resolved host paths and modes.

### Step 4: Run with a single rw mount

```sh
whizzard run --profile build --mount rw-test
```

Banner should now include a `Mounts:` line. Inside the container:

```sh
ls /mounts/                       # expected: rw-test
cat /mounts/rw-test/hello.txt     # expected: writable test data
echo "agent wrote this" > /mounts/rw-test/agent-output.txt
exit
```

Then on the host:

```sh
cat ~/test-whizzard-rw/agent-output.txt   # should show: agent wrote this
```

### Step 5: Run with a read-only mount

```sh
whizzard run --profile build --mount ro-test
```

Inside:

```sh
cat /mounts/ro-test/hello.txt     # expected: read-only test data
echo "should fail" > /mounts/ro-test/should-fail.txt   # expected: Read-only file system
exit
```

### Step 6: Verify the ro→rw cap

```sh
whizzard run --profile build --mount ro-test:rw
```

Expected: command fails with `mount 'ro-test' is registered as 'ro'; cannot request 'rw'`. Container is NOT launched.

### Step 7: Multiple mounts in one session

```sh
whizzard run --profile build --mount rw-test --mount ro-test
```

Inside:

```sh
ls /mounts/                       # expected: ro-test  rw-test
exit
```

### Step 8: Unknown mount is rejected

```sh
whizzard run --profile build --mount does-not-exist
```

Expected: `unknown mount 'does-not-exist'. Available: ro-test, rw-test`. Container is NOT launched.

### Step 9: Confirm Docker hint is suppressed

After any clean `whizzard run` exit, the misleading `What's next: Debug this container error with Gordon ...` line should NO LONGER appear.

### Cleanup

```sh
rm -rf ~/test-whizzard-rw ~/test-whizzard-ro
rm ~/.whizzard/config/mounts.json    # or keep it for future stages
```

### Pass criteria

- [ ] All 32 unit tests pass
- [ ] `whizzard mounts list` shows registered entries from `~/.whizzard/config/mounts.json`
- [ ] Mounts appear at `/mounts/<name>` inside the container
- [ ] `rw` mounts allow writes that persist on the host
- [ ] `ro` mounts reject writes
- [ ] Requesting `rw` against an `ro`-default mount is rejected before launch
- [ ] Unknown mount names are rejected before launch
- [ ] Multiple `--mount` flags work in a single invocation
- [ ] No more "Gordon" / "container error" hints from Docker

---

## Stage 3 — Profiles (JSON-driven)

### Setup

```sh
cd /Users/USER/ai-sandbox/airlock-warlock
source venv/bin/activate
git pull
pytest -v
```

Expected: 46 tests pass (32 prior + 14 new in `test_config.py`).

### Step 1: Confirm bundled defaults still work

With NO `~/.whizzard/config/profiles.json` present:

```sh
rm -f ~/.whizzard/config/profiles.json   # safe to run; -f swallows missing
whizzard profiles list
```

Expected: a Rich table titled `Profiles (bundled defaults: whizzard.config._DEFAULT_PROFILES)` showing all five profiles with their original values (default unlimited, power 60 min < build 120 min, etc.).

### Step 2: Seed user config from defaults

```sh
whizzard profiles init
```

Expected: writes `~/.whizzard/config/profiles.json` with the bundled defaults serialized as JSON. Prints a green `wrote ...` message and an instruction to edit.

```sh
cat ~/.whizzard/config/profiles.json
whizzard profiles list
```

Expected: same five profiles, but the table title now shows `Profiles (user config: /Users/USER/.whizzard/config/profiles.json)`.

### Step 3: Init refuses to clobber

```sh
whizzard profiles init
```

Expected: yellow warning that the file already exists, telling you to use `--force`. Exit code 1, file unchanged.

```sh
whizzard profiles init --force
```

Expected: overwrites silently with green `wrote ...` confirmation.

### Step 4: Edit the user config and verify it takes effect

```sh
# add a new custom profile via a quick Python edit
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / ".whizzard/config/profiles.json"
data = json.loads(p.read_text())
data["profiles"]["sandbox"] = {
    "network_enabled": False,
    "duration_seconds": 600,
    "allow_broad_mount": False,
    "description": "10-minute offline scratch session"
}
p.write_text(json.dumps(data, indent=2))
PY

whizzard profiles list
```

Expected: the new `sandbox` profile appears in the table with 10 min duration, network off.

```sh
whizzard run --profile sandbox
```

Inside the container:

```sh
curl -m 5 https://example.com   # expected: fail (no network)
exit
```

The banner should report `Duration: 10 min` and `Network: disabled`, confirming the user config was honored.

### Step 5: Malformed JSON is caught with a clear error

```sh
echo "not json" > ~/.whizzard/config/profiles.json
whizzard profiles list
```

Expected: red error message starting with `error loading profiles.json:` followed by the parse-error detail. Exit code 2. No traceback.

```sh
whizzard run --profile default
```

Expected: same red error from `run`, no container launched.

### Step 6: Schema violation is caught

```sh
cat > ~/.whizzard/config/profiles.json <<'JSON'
{
  "schema_version": 1,
  "profiles": {
    "broken": {
      "network_enabled": "maybe",
      "duration_seconds": -1
    }
  }
}
JSON

whizzard profiles list
```

Expected: red error like `profile 'broken': network_enabled must be true/false`. (Specific field that fails first depends on parse order, but it must be a clear schema-violation message rather than a Python traceback.)

### Step 7: Empty profiles object is rejected

```sh
echo '{"schema_version": 1, "profiles": {}}' > ~/.whizzard/config/profiles.json
whizzard profiles list
```

Expected: red error mentioning "at least one profile is required."

### Cleanup

```sh
# Restore a known-good config from bundled defaults
whizzard profiles init --force
# Or remove entirely to fall back to defaults
# rm ~/.whizzard/config/profiles.json
```

### Pass criteria

- [ ] All 46 tests pass
- [ ] `whizzard profiles list` works with no user config (bundled defaults)
- [ ] `whizzard profiles init` writes a JSON file matching the defaults
- [ ] `whizzard profiles init` without `--force` refuses to clobber
- [ ] `whizzard profiles init --force` overwrites
- [ ] Adding a custom profile in JSON makes it appear in `profiles list` and usable in `whizzard run`
- [ ] Invalid JSON produces a clean error message, no traceback
- [ ] Schema violations (wrong type, missing field, bad value) produce clean errors
- [ ] Empty profiles object is rejected with a helpful message

---

## Stage 4 — Dry Run

### Setup

```sh
cd /Users/USER/ai-sandbox/airlock-warlock
source venv/bin/activate
pytest -v
```

Expected: 55 tests pass (46 prior + 9 new in `test_cli_dry_run.py`).

### Step 1: Basic dry-run

```sh
whizzard run --profile default --dry-run
```

Expected:
- Yellow `DRY RUN — no container will be launched.` banner at the top
- The standard profile summary (Airlock Profile, Network, Duration, Broad-mount override, Image, Mounts)
- A `docker invocation that would run:` block showing the full docker command, copy-pasteable
- Exits cleanly with code 0
- **No container launches** — your shell prompt returns immediately, no bash session inside

### Step 2: Dry-run with a mount

Assuming you still have `rw-test` registered from Stage 2:

```sh
whizzard run --profile build --mount rw-test --dry-run
```

Expected:
- Mounts section shows `rw-test (rw): /Users/USER/test-whizzard-rw → /mounts/rw-test`
- The docker argv includes `-v '/Users/USER/test-whizzard-rw:/mounts/rw-test:rw'`
- Still no container launched

### Step 3: Dry-run surfaces all profiles

Run dry-run for each profile and confirm the duration / network / broad-mount fields update accordingly:

```sh
whizzard run --profile safe --dry-run        # Network: disabled, Duration: 30 min
whizzard run --profile default --dry-run     # Network: enabled, Duration: unlimited
whizzard run --profile build --dry-run       # Network: enabled, Duration: 120 min
whizzard run --profile power --dry-run       # Broad-mount override: allowed
whizzard run --profile quarantine --dry-run  # Network: disabled
```

Each should produce a complete preview without launching anything.

### Step 4: Dry-run errors are still caught

```sh
whizzard run --profile nope --dry-run
```

Expected: red `Unknown profile: 'nope'` error, exit code 2. No banner printed.

```sh
whizzard run --profile default --mount does-not-exist --dry-run
```

Expected: red `unknown mount 'does-not-exist'` error, exit code 2.

### Step 5: Image existence is NOT checked in dry-run

Dry-run shows intent regardless of whether the image is built:

```sh
whizzard run --profile default --image bogus-image:does-not-exist --dry-run
```

Expected: full preview prints, including `Image: bogus-image:does-not-exist` in the summary and in the docker argv. Exit code 0. Without `--dry-run`, the same command would fail with an "image not found" error — but dry-run is for previewing intent, so it doesn't gate on the image.

### Step 6: Sanity — without dry-run, container still launches

```sh
whizzard run --profile default
```

Inside the container:

```sh
exit
```

Expected: container actually runs, prompt returns. Confirms dry-run flag wasn't accidentally stuck on.

### Pass criteria

- [ ] All 55 unit tests pass
- [ ] `--dry-run` prints the DRY RUN banner and full profile/mount summary
- [ ] `--dry-run` prints the full docker argv that *would* run
- [ ] `--dry-run` does NOT launch a container (no shell prompt inside one)
- [ ] Mounts in the summary match `-v` lines in the argv
- [ ] Profile resolution errors still produce clean messages under `--dry-run`
- [ ] Mount registry errors still produce clean messages under `--dry-run`
- [ ] Image absence is NOT a dry-run failure
- [ ] Without `--dry-run`, `whizzard run` still launches normally

---

## Stage 5 — Session Logging

### Setup

```sh
cd /Users/USER/ai-sandbox/airlock-warlock
source venv/bin/activate
pytest -v
```

Expected: 73 tests pass (55 prior + 9 in `test_session_log.py` + 4 docker-cmd Stage 5 additions + 5 dry-run / pre-flight error tests).

### Step 1: Banner shows session ID

```sh
whizzard run --profile default --dry-run
```

Expected: a new line `Session ID: <uuid>` in the banner. The docker argv includes `--label whizzard.session_id=<same uuid>`. No file is written for dry-run.

```sh
whizzard sessions tail
```

Expected: yellow `no session log yet` message at `~/.whizzard/logs/sessions.jsonl` (file shouldn't exist after only dry-runs).

### Step 2: Real run writes start AND end records

```sh
whizzard run --profile default
# inside container:
exit
```

Then on the host:

```sh
whizzard sessions tail
```

Expected: TWO JSONL lines, one with `"event":"session_start"` and one with `"event":"session_end"`, sharing the same `session_id`. The `start` record includes profile, mounts, network_enabled, image_tag, image_id (sha256:...), and the full argv. The `end` record includes container_id (sha256-style hex) and exit_status (0 for clean exit).

### Step 3: Container ID is captured

The `container_id` field in the session_end record should be a 64-char hex string (or shorter — depends on docker version). It's the actual ID of the container that ran, captured via `--cidfile`.

To verify, while a session is running, check from another terminal:

```sh
# in another terminal:
docker ps --filter label=whizzard.session_id=<the uuid you saw>
```

Expected: shows the container with that label. The `CONTAINER ID` here matches what ends up in the log.

### Step 4: Image ID is recorded

The session_start record's `image_id` should be a `sha256:...` digest. Verify it matches:

```sh
docker image inspect --format '{{.Id}}' whizzard-base:latest
```

This sha256 should equal the `image_id` field in the most recent session_start log entry.

### Step 5: Duration tracking

Run a session, wait a few seconds, exit:

```sh
whizzard run --profile default
sleep 3
exit
```

`whizzard sessions tail` — the session_end record's `duration_seconds` should be roughly the time you spent in the container (somewhere around 3 plus your exit-typing time).

### Step 6: Mount metadata in start record

```sh
whizzard run --profile build --mount rw-test
exit
```

The session_start record's `mounts` array should contain one object:
```json
{"name":"rw-test","mode":"rw","host_path":"/Users/USER/test-whizzard-rw","container_path":"/mounts/rw-test"}
```

### Step 7: Failed pre-flight does NOT write session log

```sh
whizzard run --profile nope
```

Expected: red error, exit code 2, NO new lines in the session log (run_shell never gets called).

```sh
whizzard run --profile default --image bogus:nonexistent
```

Expected: red `image not found` error, exit code 125, NO new session log entries (run_shell does the image-existence check before writing the start event).

### Step 8: Sessions log path command

```sh
whizzard sessions path
```

Expected: prints `/Users/USER/.whizzard/logs/sessions.jsonl` (the absolute path).

### Step 9: JSONL format is parseable

```sh
cat ~/.whizzard/logs/sessions.jsonl | tail -2 | python3 -c "import json,sys; [print(json.dumps(json.loads(l), indent=2)) for l in sys.stdin]"
```

Expected: pretty-printed JSON for the last two lines, no parse errors.

### Pass criteria

- [ ] All 71 unit tests pass
- [ ] Banner shows `Session ID: <uuid>`
- [ ] Real `whizzard run` writes one `session_start` and one `session_end` per session
- [ ] start and end records share the same `session_id`
- [ ] `container_id` in session_end matches the actual docker container ID
- [ ] `image_id` in session_start matches `docker image inspect`
- [ ] `duration_seconds` in session_end is a sane number reflecting wall time
- [ ] Mount details appear in session_start when `--mount` is used
- [ ] Pre-flight failures (bad profile, missing image) do NOT add log entries
- [ ] `whizzard sessions tail` and `whizzard sessions path` work
- [ ] Each line of the log parses cleanly as JSON

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
