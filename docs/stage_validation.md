# Stage Validation Checklist

Manual validation steps for each MVP stage. Update this file as new stages land.

---

## Stage 1 — Generic Docker Shell Launch

### Setup

```sh
cd /Users/USER/ai-sandbox/whizzard
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

Expected: see `Whizzard Profile: DEFAULT` banner followed by a bash prompt inside the container.

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
cd /Users/USER/ai-sandbox/whizzard
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

# Ensure the whizzard config directory exists. (ensure_whizzard_home()
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
cd /Users/USER/ai-sandbox/whizzard
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
cd /Users/USER/ai-sandbox/whizzard
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
- The standard profile summary (Whizzard Profile, Network, Duration, Broad-mount override, Image, Mounts)
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
cd /Users/USER/ai-sandbox/whizzard
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

### Setup

```sh
cd /Users/USER/ai-sandbox/whizzard
source venv/bin/activate
pytest -v
```

Expected: 90 tests pass (73 prior − 3 removed Stage-2 sanity tests + 18 in `test_safety.py` + 1 in `test_session_log.py` + 1 typing adjustment).

### Step 1: Hard block — filesystem root

Add a fake registered mount that points at `/` and try to use it. We don't actually want the registry to reach `/`, so do this carefully:

```sh
# Temporarily corrupt the registry to point a mount at /
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / ".whizzard/config/mounts.json"
data = json.loads(p.read_text())
data["mounts"]["danger-root"] = {"host_path": "/", "default_mode": "ro"}
p.write_text(json.dumps(data))
PY

whizzard run --profile default --mount danger-root
```

Expected: red `safety policy: ... hard-blocked` error mentioning `/`. Exit code 2. No container launches.

```sh
whizzard run --profile power --mount danger-root --allow-broad-mount
```

Expected: STILL blocked. Hard blocks have no override.

Cleanup:

```sh
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / ".whizzard/config/mounts.json"
data = json.loads(p.read_text())
data["mounts"].pop("danger-root", None)
p.write_text(json.dumps(data))
PY
```

### Step 2: Hard block — `~/.ssh`

```sh
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / ".whizzard/config/mounts.json"
data = json.loads(p.read_text())
data["mounts"]["danger-ssh"] = {"host_path": "~/.ssh", "default_mode": "ro"}
p.write_text(json.dumps(data))
PY

whizzard run --profile default --mount danger-ssh
```

Expected: red `safety policy: ... hard-blocked` error mentioning `.ssh`. Even on the `power` profile with `--allow-broad-mount`, still blocked. Cleanup the registry entry afterwards.

### Step 3: Config write-protection

```sh
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / ".whizzard/config/mounts.json"
data = json.loads(p.read_text())
data["mounts"]["danger-whizzard"] = {"host_path": "~/.whizzard", "default_mode": "rw"}
p.write_text(json.dumps(data))
PY

whizzard run --profile power --mount danger-whizzard --allow-broad-mount
```

Expected: hard-blocked. The Whizzard config dir is non-overridable. Cleanup the registry entry afterwards.

### Step 4: Override-required — broad folder, strict profile

Set up a `~/Documents` mount (assuming you have that directory):

```sh
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / ".whizzard/config/mounts.json"
data = json.loads(p.read_text())
data["mounts"]["my-docs"] = {"host_path": "~/Documents", "default_mode": "ro"}
p.write_text(json.dumps(data))
PY

whizzard run --profile default --mount my-docs
```

Expected: red `safety policy:` error stating the path requires broad-mount override but profile `default` blocks it. Reason: `broad folder (~/Documents)`.

### Step 5: Override-required — broad folder, permissive profile, no flag

```sh
whizzard run --profile power --mount my-docs
```

Expected: red error saying the override flag is required: `pass --allow-broad-mount to opt in`. Reason: `broad folder`.

### Step 6: Override-required — both gates open → allowed

```sh
whizzard run --profile power --mount my-docs --allow-broad-mount
```

Expected:
- Banner shows `Broad-mount overrides applied:` in yellow with the reason
- Container launches normally
- Inside the container, `/mounts/my-docs/` shows your Documents directory contents

Exit the container and confirm the override was logged:

```sh
whizzard sessions tail -n 1
```

The most recent `session_start` should include an `overrides_used` array with the broad-folder reason.

Cleanup:

```sh
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / ".whizzard/config/mounts.json"
data = json.loads(p.read_text())
data["mounts"].pop("my-docs", None)
p.write_text(json.dumps(data))
PY
```

### Step 7: Parent-of-registered-mount detection

Set up a registered mount at a deep path, then try to mount its parent:

```sh
mkdir -p ~/test-parent/child
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / ".whizzard/config/mounts.json"
data = json.loads(p.read_text())
data["mounts"]["the-child"] = {"host_path": "~/test-parent/child", "default_mode": "rw"}
data["mounts"]["the-parent"] = {"host_path": "~/test-parent", "default_mode": "rw"}
p.write_text(json.dumps(data))
PY

whizzard run --profile power --mount the-parent
```

Expected: red error stating `the-parent` is a parent of registered mount `the-child`, requires override.

```sh
whizzard run --profile power --mount the-parent --allow-broad-mount
```

Expected: launches with override applied; banner shows the override; session log records it.

Cleanup:

```sh
rm -rf ~/test-parent
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / ".whizzard/config/mounts.json"
data = json.loads(p.read_text())
data["mounts"].pop("the-child", None)
data["mounts"].pop("the-parent", None)
p.write_text(json.dumps(data))
PY
```

### Step 8: Dry-run respects safety

```sh
# After re-creating ~/Documents mount as in Step 4
whizzard run --profile default --mount my-docs --dry-run
```

Expected: the dry-run still surfaces the safety error before printing any argv. Hard blocks and override-required violations are caught in the same code path as live runs.

### Step 9: Allowed paths are unaffected

```sh
whizzard run --profile build --mount rw-test
```

Expected: launches normally with no override banner. The `rw-test` mount is in `~/test-whizzard-rw` which doesn't intersect any block list.

### Pass criteria

- [ ] All 90 unit tests pass
- [ ] Mounting `/` is hard-blocked, no override possible
- [ ] Mounting `~/.ssh` is hard-blocked, no override possible
- [ ] Mounting `~/.whizzard` is hard-blocked, no override possible
- [ ] Mounting `~/Documents` is blocked on strict profile (no override)
- [ ] Mounting `~/Documents` on permissive profile without flag is blocked
- [ ] Mounting `~/Documents` on permissive profile WITH `--allow-broad-mount` succeeds
- [ ] Banner shows yellow override notice when overrides apply
- [ ] Session log records `overrides_used` for runs that used overrides
- [ ] Mounting a parent of a registered mount is override-required
- [ ] Dry-run catches the same safety violations as live runs
- [ ] Allowed paths (registered, outside all block lists) launch normally with no override

---

## Stage 7 — Generic Adapter

### Setup

```sh
cd /Users/USER/ai-sandbox/whizzard
source venv/bin/activate
pytest -v
```

Expected: 131 tests pass (90 prior + 16 in `test_adapters.py` + 13 in `test_harness_config.py` + 8 docker-cmd Stage 7 additions + 4 dry-run Stage 7 additions).

### Step 1: Default behavior unchanged

```sh
whizzard run --profile default --dry-run
```

Expected: banner now shows a `Harness: generic` line. The docker argv ends with `/bin/bash` and includes `--label whizzard.harness=generic`. Everything else is unchanged from Stage 6.

### Step 2: List the harness registry

```sh
whizzard harnesses list
```

Expected: a Rich table titled `Harnesses (bundled defaults)` showing the `generic` harness.

### Step 3: Seed user config from defaults

```sh
whizzard harnesses init
cat ~/.whizzard/config/harnesses.json
whizzard harnesses list
```

Expected: writes the defaults to `~/.whizzard/config/harnesses.json`. `harnesses list` now shows `Harnesses (user config)` in the title.

### Step 4: Add a custom shell harness

```sh
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / ".whizzard/config/harnesses.json"
data = json.loads(p.read_text())
data["harnesses"]["bash-login"] = {
    "type": "shell",
    "start_command": "/bin/bash -l",
    "working_dir": "/home/whizzard",
    "env": {"FOO": "bar"},
    "description": "login shell with example env"
}
p.write_text(json.dumps(data, indent=2))
PY

whizzard harnesses list
```

Expected: `bash-login` row appears in the list with the right values.

### Step 5: Use the custom harness in dry-run

```sh
whizzard run --profile default --harness bash-login --dry-run
```

Expected:
- Banner shows `Harness: bash-login`
- argv ends with `/bin/bash -l`
- argv includes `-e FOO=bar`
- argv includes `-w /home/whizzard`
- argv includes `--label whizzard.harness=bash-login`

### Step 6: Use the custom harness for real

```sh
whizzard run --profile default --harness bash-login
```

Expected: a login bash session inside the container. Inside, `echo $FOO` should print `bar`. Confirms env injection through the adapter is working.

```sh
exit
whizzard sessions tail -n 1
```

The session_start record's `argv` field should reflect the custom start_command and env.

### Step 7: Unknown harness produces a clean error

```sh
whizzard run --profile default --harness nope --dry-run
```

Expected: red `unknown harness: 'nope'. Available: ...` error, exit code 2.

### Step 8: Agent-type harness rejected until Stage 8

```sh
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / ".whizzard/config/harnesses.json"
data = json.loads(p.read_text())
data["harnesses"]["fake-agent"] = {
    "type": "agent",
    "start_command": "echo nope"
}
p.write_text(json.dumps(data, indent=2))
PY

whizzard run --profile default --harness fake-agent --dry-run
```

Expected: red error stating `harness 'fake-agent' has type 'agent' but no agent adapter is implemented yet (lands in Stage 8 with the Hermes adapter)`.

### Step 9: Schema violations are caught

```sh
echo '{"schema_version": 1, "harnesses": {"bad": {"type": "alien", "start_command": "x"}}}' > ~/.whizzard/config/harnesses.json
whizzard harnesses list
```

Expected: red `error loading harnesses.json: harness 'bad': type must be 'shell' or 'agent', got 'alien'`. Exit code 2.

### Step 10: Init refuses to clobber

```sh
whizzard harnesses init
```

Expected: yellow "already exists, use --force" message. Exit code 1.

```sh
whizzard harnesses init --force
```

Expected: overwrites silently with the green confirmation.

### Cleanup

```sh
# Remove custom entries from harnesses.json
whizzard harnesses init --force
```

### Pass criteria

- [ ] All 131 unit tests pass
- [ ] `whizzard run` still works as before, defaulting to the generic harness
- [ ] Banner shows `Harness: <name>`
- [ ] docker argv includes `--label whizzard.harness=<name>`
- [ ] Custom shell harnesses (start_command, env, working_dir) work end-to-end
- [ ] `whizzard harnesses list` and `whizzard harnesses init` work
- [ ] Unknown harness produces clean red error, no traceback
- [ ] Agent-type harnesses are explicitly rejected with a Stage-8 message
- [ ] Schema violations produce clean errors
- [ ] `init` refuses to clobber without `--force`

---

## Stage 8 — Hermes Integration

The Hermes adapter and supporting plumbing land in **eight milestones** — six code milestones (M1–M6) validated by the unit test suite, plus the live end-to-end check (M7 manual smoke, requires built image + Hermes install) and the packaging closeout (M8). All eight are shipped as of 2026-05-19. The original sequence (M1–M5 + M6 wrap_up + M7 packaging) was renumbered when the HERMES_HOME wiring gap was identified mid-build (see `STAGE_8_BUILD_PLAN.md`).

### Unit-test-validated milestones (run `make test` or `pytest tests/`)

- [x] **M1**: `HermesAdapter` exists, satisfies the `HarnessAdapter` Protocol, and is returned by `build_adapter("agent", ...)` instead of `UnknownHarnessTypeError`. (`test_hermes_adapter.py`, `test_adapters.py`)
- [x] **M2**: `active_capabilities() -> list[str]` is on the Protocol; `GenericShellAdapter` returns `[]`; `HermesAdapter` returns declared platforms + MCP availability + credential-source warnings (D-89, D-90). (`test_adapters.py`, `test_hermes_adapter.py`)
- [x] **M3**: `HermesAdapter.container_env()` reads `self.config["platforms"]` (declared in `harnesses.json` per D-89 amended), fetches each platform's credential via the shared `fetch_secret` utility (OneCLI first per D-134; env-var fallback), returns the env dict. D-162's `secrets:` field handles arbitrary LLM-provider credentials via the same mechanism. (`test_hermes_adapter.py`)
- [x] **M4**: `preflight()` checks `<HERMES_HOME>/gateway.lock`. Live pid → block with profile + pid + remediation message. Dead pid → cleared, proceed with `cleanup_note`. Missing or malformed lock → proceed. (`test_hermes_adapter.py`)
- [x] **M5**: `whiz hermes profile create <name>` creates `~/.hermes-<name>/`. Bare clones from default (or degrades to empty); `--clone-from <src>` selects source; `--no-clone` forces empty. `auth.json` and per-instance runtime state are excluded from clones (D-80). Reserved/invalid names refused. Existing targets refused. (`test_hermes_adapter.py`)
- [x] **M6**: HERMES_HOME mount + env-var wiring (D-79). `HarnessAdapter` Protocol extended with `container_mounts() -> list[ContainerMount]`; `HermesAdapter` returns the HERMES_HOME mount with `uid_parity=True` per D-56; `docker_cmd.build_run_argv` emits the `-v` flags and overrides `--user` to host UID/GID when uid_parity is requested. Wrap-up (`HermesAdapter.wrap_up()`) uses `docker stop --time=<grace>` + container exit-code inspection: clean SIGTERM exit → SUCCESS; SIGKILL exit code 137 → TIMEOUT; docker missing or stop fails → ERROR. (`test_hermes_adapter.py`, `test_docker_cmd.py`)
- [x] **CLI surface**: `whiz hermes profile create --help` shows the subcommand tree; `--clone-from` / `--no-clone` mutual-exclusion fires; success message names the created path and announces clone source (if any).
- [x] **`harnesses.json` validation**: `platforms` is an optional list of strings; `secrets` is an optional list of valid env-var names (D-162). Non-list / non-string entries / plaintext-value smuggling (`=` in name) produce clean errors with no traceback. (`test_harness_config.py`)

### Manual end-to-end smoke (M7, requires built image + Hermes)

These are the steps that prove the adapter drives a real Hermes container. They are NOT part of the automated suite — run them manually once the prerequisites are in place. **M7 ran successfully 2026-05-19 against `whizzard-hermes:latest` (derived from `whizzard-base:latest` via `docker/Dockerfile.hermes`, Hermes 0.12.0 pip-installed from `github.com/NousResearch/hermes-agent`) with mistral-nemo via Mac Studio Ollama as the LLM provider.** See `STAGE_8_BUILD_PLAN.md` §M7 Runbook for the full procedure.

Prerequisites:
- `whizzard-base:latest` built (`docker build -t whizzard-base:latest docker/`).
- Derived Hermes image built (`docker build -f docker/Dockerfile.hermes -t whizzard-hermes:latest .`).
- A cloned Hermes profile at `~/.hermes-<name>/`, created via `whiz hermes profile create <name> --clone-from default`.
- A `harnesses.json` entry of `type: "agent"` declaring `hermes_home`; for gateway mode, `platforms: [...]` with the corresponding `<PLATFORM>_BOT_TOKEN` in OneCLI or host env. For LLM provider credentials, declare via D-162 `secrets: [ANTHROPIC_API_KEY, ...]`.

Steps:

```sh
# Interactive mode — cheapest smoke, no platform creds needed.
WHIZZARD_IMAGE=whizzard-hermes:latest whiz run --harness <hermes-harness-name>
# Expected: container starts, Hermes interactive prompt appears,
# `/quit` (typed into Hermes) exits cleanly. Session state at
# ~/.hermes-<name>/sessions/ survives container termination.

# Gateway mode — verifies platform connection.
WHIZZARD_IMAGE=whizzard-hermes:latest whiz run --harness <hermes-harness-name>
# Expected: container starts in gateway mode, Hermes connects to declared
# platforms, env vars populated from OneCLI / host env. wrap_up via
# Whizzard's stop path drains turns and exits within grace.

# Concurrency guard — D-87.
# 1. Launch the same harness twice; second launch refused with profile + pid + remediation.
# 2. Kill the first container; gateway.lock points to dead pid; next launch announces
#    "Cleared stale gateway.lock" and proceeds.
```

### Stage-8 closeout (M8) — SHIPPED 2026-05-19

- [x] **`pyproject.toml` Hermes extras** — closeout reframed: OIQ host-side imports zero Hermes-specific Python modules, so no `[project.optional-dependencies] hermes = [...]` extras block is needed; the install path is the Docker image built from `docker/Dockerfile.hermes`. Explanatory comment block in `pyproject.toml` documents this; README "Optional: Hermes adapter" section walks users through the two-step setup (image build + profile clone + harness config).
- [x] **`whiz hermes <profile>` direct-launch sugar** — left unimplemented; `whiz r hermes` and `whiz run --harness hermes-cell` cover the same use case. Equivalent functionality; not a closeout blocker.

---

## Stage 9 — Whiz MCP Server (Read-Only Subset)

Stage 9 ships an in-cell MCP server that exposes four read-only tools to
the contained agent for introspection of Whizzard-imposed constraints
(D-25, D-156). Architecture: in-cell Python child process, launch-time
state snapshot, mounted live audit log, event-file write-back merged into
the host log at session_end.

### Unit-test-validated milestones (run `pytest tests/`)

- [ ] M1: `whizzard/mcp_server.py` exists with four tool functions:
  `tool_whiz_status`, `tool_whiz_audit_self`, `tool_whiz_emit_event`,
  `tool_whiz_list_presets`. Tools read env vars (`WHIZ_SNAPSHOT_PATH`,
  `WHIZ_AUDIT_LOG_PATH`, `WHIZ_EVENT_LOG_PATH`, `WHIZ_SESSION_ID`) for
  paths. `main()` lazily imports the `mcp` SDK so tests don't need it.
  (`test_mcp_server.py`)
- [ ] M2: `whizzard/snapshot.py` writes per-session state to
  `<WHIZZARD_HOME>/sessions/<session_id>/snapshot.json` at launch.
  Snapshot includes session_id, profile, mounts, harness, timestamp.
  Helper functions for `session_dir`, `snapshot_path`, `event_log_path`.
  (`test_snapshot.py`)
- [ ] M3: Adapter Protocol has `mcp_env(session_id) -> dict[str, str]`.
  Generic shell returns `{}`. Hermes returns the four WHIZ_* env vars
  pointing at the conventional in-cell `/run/whiz/` paths. Hermes's
  `active_capabilities` mentions MCP availability. (`test_adapters.py`,
  `test_hermes_adapter.py`)
- [ ] M4: `session_log.merge_agent_events(session_id, event_log_path,
  target_log)` reads the per-session event file and appends entries to
  the audit log. Defensive: missing-file returns 0, wrong session_id
  skipped, malformed lines skipped, `origin: agent` marker enforced.
  Called from `docker_cmd.run_shell` before `log_session_end`.
  (`test_session_log.py`)
- [ ] M5: `whizzard/cli.py` calls `write_snapshot` before launch.
  `docker_cmd.build_run_argv` adds `-v <host_session_dir>:/run/whiz:rw`
  and `-v <audit_log>:/run/whiz/audit.jsonl:ro` only when adapter's
  `mcp_env` is non-empty and `session_id` is present. `pyproject.toml`
  declares `mcp>=1.0` as a core dep. (`test_docker_cmd.py`)

### Manual end-to-end smoke (requires built image + Hermes + mcp SDK in cell)

These steps prove the MCP server actually serves the agent inside the
cell. They are NOT part of the automated suite.

Prerequisites:
- Whizzard execution image has `mcp` SDK installed (add to `docker/Dockerfile`).
- Hermes is configured with the Whiz MCP server entry. Per D-156, the
  user adds an entry to their Hermes profile's `config.yaml` pointing
  Hermes's MCP client at the in-cell Whiz server (auto-wiring is a
  follow-up):

```yaml
# In <HERMES_HOME>/config.yaml
mcp_servers:
  whiz:
    command: ["python", "-m", "whizzard.mcp_server"]
```

Steps:

```sh
# Launch a Hermes session with MCP wiring active
whizzard run --harness <hermes-harness-name>

# Inside the agent's session, the agent should be able to call:
#   whiz_status — returns the cell's profile, mounts, harness, session id
#   whiz_audit_self — returns this session's audit-log entries
#   whiz_emit_event(event_type, detail) — agent records a note
#   whiz_list_presets — returns empty list (Stage 10 dependency)

# After session exits, check that agent-emitted events are merged
# into the host audit log with `origin: agent`:
cat ~/.whizzard/logs/sessions.jsonl | grep '"origin":"agent"'
```

### Outstanding for full closeout

- [ ] Docker image build: install `mcp` in the cell image (probably part
  of Stage 18 image management when the Dockerfile gets its full overhaul).
- [ ] Auto-wire Hermes's `config.yaml` MCP server entry (currently
  manual). Could be a `whiz hermes profile create` flag or a separate
  command.

---

## Stage 10 — Presets and CLI Ergonomics

Shipped 2026-05-16 (commits 51a236c, 97a1bc5, 4f1eaf6, fd7014d). Design
conversation per D-148 resolved four items across 2026-05-15/16:
preset slate, CLI shortcut shape, smart defaults, preset config schema.

### Unit-test-validated milestones (run `pytest tests/`)

- [ ] **#1 hermes preset + default profile change (D-157).** `default`
  profile's `allow_broad_mount` flips to `true` to support broad-mount
  presets (D-157 supersedes D-38 on this field). Bundled `claude-projects`
  and `ai-sandbox` mounts added. (`test_config.py`, `test_mounts.py`)
- [ ] **#2 preset machinery.** `whizzard/preset_config.py` with
  `Preset` dataclass, omit-to-inherit override semantics, bundled
  `_DEFAULT_PRESETS` (`hermes` + `shell`), strict `validate_references()`
  against profile/harness/mount/platform-ceiling. (`test_preset_config.py`)
- [ ] **#3 preset CLI subapp.** `whiz preset list | show | init |
  launch`. Bundled `hermes-cell` harness so `hermes` preset validates
  out of the box. Preset launch passes `allow_broad_mount=True` to
  `_perform_launch` as the user's persistent intent declaration; profile
  gate (first gate per D-46) is the referenced profile's setting.
  Platforms field on the preset restricts the harness's ceiling
  (D-89 amended). (`test_preset_cli.py`)
- [ ] **#4 CLI brevity + smart defaults.** `whiz r/s/p/m/pr` shortcuts.
  Bare `whiz` → status (rather than help; `whiz --help` is the explicit
  help path). Bare `whiz r` → launch most-recent preset (parsed from
  sessions.jsonl `preset` field; `log_session_start` gains the field).
  `whiz r --profile X` → `whiz run --profile X`. Positional + run-flags
  mix errors. (`test_cli_brevity_and_status.py`)
- [ ] **#5 status command + `whiz` script alias.** Active sessions list
  with running indicator + active-session count + last-10 history table.
  Harness name extracted from `session_start` argv label. `pyproject.toml`
  adds `whiz = "whizzard.cli:app"` script entry alongside `whizzard`.
  (`test_cli_brevity_and_status.py`)

### Manual end-to-end smoke

These verify the launch ergonomics with a real container. Require the
prerequisites already noted in Stage 8 / Stage 9 (built image, OneCLI,
HERMES_HOME wiring per the still-outstanding Stage 8 M6).

```sh
# Initialize bundled config (one-time, if not already done)
whiz preset init           # writes ~/.whizzard/config/presets.json
whiz mounts list           # confirm claude-projects + ai-sandbox visible
whiz pr                    # profiles list — confirm default has allow_broad_mount on

# Daily-driver launch
whiz r hermes              # or just `whiz r` if hermes was the last preset

# Status check
whiz                       # bare: status output
whiz s                     # alias: same

# Inspect a preset
whiz p hermes              # show details
whiz p                     # list all
```

### Outstanding for full closeout

- [ ] **Stage 10 launch validates end-to-end only after Stage 8 M6 lands**
  (HERMES_HOME mount + env-var wiring per the prior handoff entry). Until
  M6, `whiz r hermes` will launch a container but Hermes inside won't have
  its profile mounted.
- [ ] Personal-config path: user updates `~/.whizzard/config/profiles.json`
  to pick up D-157's `allow_broad_mount: true` on `default` (either by
  manual edit or `whiz profiles init --force`).

---

## Stage 14 — Whiz MCP Server (Request-Side Tools)

Design: D-165. Agent-initiated capability requests via the in-cell MCP
request tools + the operator-invoked `whiz requests` command.

### Automated coverage

`tests/test_mcp_server.py` (request/check tools), `tests/test_requests.py`
(host-side reader, validator, `process_request`), `tests/test_requests_cli.py`
(`whiz requests` list/approve/deny + status count). 407 unit tests pass; 85%
coverage. Run: `make check && make coverage`.

### Manual end-to-end smoke (blocked on the same infra as Stage 9)

Requires a real Hermes container with the `mcp` SDK and the Whiz MCP server
wired into the harness's `config.yaml` — same prerequisite as the Stage 9
smoke. Once that lands:

```sh
# 1. Launch a Hermes session; note the session id from the banner.
whiz r hermes

# 2. Inside the cell, have the agent call the MCP tool:
#      whiz_request_mount(name="documents", reason="need the docs")
#    It returns {"status": "pending", "request_id": "..."}.

# 3. On the host, in another terminal:
whiz requests                      # pending request is listed
whiz requests approve <request-id> # shows diff, [y/N], stop+restart

# 4. Back in the cell, the agent polls:
#      whiz_check_request("<request-id>")  -> status "applied"
#      whiz_status()                       -> "documents" now in mounts

# Negative paths to exercise:
whiz requests deny <request-id>          # decline without applying
#   whiz_request_mount("unregistered")   -> request auto-denied (pre-flight)
```

### Outstanding for full closeout

- [ ] Manual smoke above — blocked on the Stage 9 / Stage 8-M6 end-to-end
  infra (cell image with `mcp` SDK + `config.yaml` MCP server entry).
- [ ] v1.0 revisit (D-165): host-side MCP server for synchronous round-trip
  request tools.

---

## Stage 18 — Image Management

*(To be added once Stage 18 lands. This section previously sat at "Stage 9 — Image Management" before the renumbering per D-76 → D-143, which moved image management from Stage 9 to Stage 11 to Stage 18.)*
