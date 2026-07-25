# Session Handoff Log

## 2026-07-25T15:31Z — Wizard web-search UX + 3-profile redesign (2 decisions pending) · alignment fixes · Phase C awaiting smoke

### Goal
Get Whizzard to `v0.1.0` soft-launch. Immediate threads: (1) finish web-search Phase C, (2) reconcile all doc↔code alignment gaps before launch (user confirmed ALL must land pre-launch), (3) redesign the setup-wizard web-search flow + collapse the profile model 5→3.

### Where we are (active task)
Mid design-discussion on the **setup-wizard web-search UX pass**, which expanded into a **profile-model redesign**. Two user decisions are pending before any implementation. Do NOT implement the redesign or the D-196 posture fixes until the user answers Decisions 1 & 2 below — they are posture/UX calls.

### OPEN DESIGN QUESTIONS (capture-in-full — user may forget details)

**The 3-profile model (user's proposal, agreed in principle).** Collapse the current 5 bundled profiles (safe/default/build/power/quarantine) → **3**: `default` (balanced security+usability), `strict` (high security — exact config TBD, "we can discuss"), `open` (low-friction, quick/easy; still a net gain vs bare Hermes). Search maps onto them: `default`→**firecrawl** (contained) if a key is available; `open`→**ddgs** (keyless, low-friction); `strict`→**no search** (search = attack surface).

- **DECISION 1 (PENDING) — the keyless default.** ddgs requires `open` egress (un-brokerable), so a credential-private (mediated) profile cannot run ddgs. For a user with **no Firecrawl key**, what does `whiz r` (default) launch?
  - **(A)** `default` stays mediated always; keyless users get search only by launching the `open` profile → default has NO search for them (contradicts "search on default for ~everyone").
  - **(B)** the wizard's security-vs-convenience choice PICKS which profile `whiz r` targets; a keyless/low-friction user's default IS the `open` profile (open+ddgs) → everyone gets search on their default, honestly labeled; cost = keyless user's default is the open posture (model key not brokered).
  - **Claude recommended (B).** Rationale: "search for ~everyone" + "low-friction-or-they-abandon" (matches the user's dep-hygiene/"Whiz must be easier than yolo" principle).

- **DECISION 2 (PENDING) — fold D-196 into this redesign?** D-196 (open) = the `default`/`build` intended posture. Since we're reworking profiles anyway, decide the posture here rather than separately. **Claude recommended: yes, fold it in.**

**ddgs is REQUIRED as the keyless fallback (user was firm).** User rejected Claude's "firecrawl-only in wizard" suggestion: low-friction path is essential or users abandon; whizzard+ddgs > bare Hermes. ddgs lives on the `open` profile (needs open egress). Must "account for how the fallback fits into profiles/config" → the 3-profile model does this.

**OneCLI housing the Firecrawl token (user's idea — sound, agreed).** In onecli/hybrid mode the OneCLI gateway could inject `FIRECRAWL_API_KEY` for `api.firecrawl.dev`, so firecrawl works under onecli with only a placeholder in the cell — dissolving the "firecrawl needs mediated/hybrid" coupling (would then work across all 3 credential modes). TWO caveats: (a) **OneCLI is currently INERT** in Whizzard (`known_issues.md` — `fetch_secret`'s `onecli` subcommand doesn't exist; always falls back to host env), so this is design-correct but non-functional until fixed; (b) **works-today alternative**: let the dedicated search-broker join the *onecli* internal net (`start_search_broker` already takes an internal-network arg; `_launch.py` validation just doesn't allow firecrawl+onecli yet). **Claude leans: search-broker-on-onecli-net first (works now), gateway-injection later.**

**Provisional (revisit during the wizard walkthrough test — user said may change mind):**
- **Search-image build conditional** (only when web search enabled), built in **Step 2** (after Step 1's hermes build; the search image is `FROM` hermes) — avoids reordering Step 1 and dodges `test_init_step_1_invokes_four_builds_in_order` (asserts exactly 4 builds).
- **Firecrawl key = probe-and-warn** at the Done summary (mirror the existing `ANTHROPIC_API_KEY` probe in `_print_credential_privacy_summary`); Whizzard persists no secrets by design, so instruct-only (`export FIRECRAWL_API_KEY=…` or OneCLI vault; free key at firecrawl.dev).

**Confirmed:** web-search prompt lives **in Step 2, right after `_prompt_credential_mode`** (hard dependency on the credential-mode value).

### Wizard hook-points (from the code-mapping agent — `whizzard/init_wizard.py`)
- Step 1 `step_1_image` (~:237): 4 docker builds (base :336 / hermes :352 / broker :367 / onecli-shim :380). Add the 5th (search) build **in Step 2**, conditional.
- Step 2 `step_2_profiles` (:527): `_prompt_credential_mode` (:451, choices→mediated/onecli/hybrid). Writers `_write_default_profiles` (:1743) & `_write_profiles_subset` (:617) set `network_mode` ONLY for `default` and emit NO `web_search` key. Add `web_search` emission + the redesign here.
- Harnesses `_write_wizard_harnesses` (:1298) carries `model_credential` (so mediated works OOTB).
- Tests: `tests/test_init_wizard.py` full-flow tests drive the wizard via an `input=` newline string encoding every prompt — a new prompt inserts a line into ALL of them; `:165` asserts 4 builds.

### Alignment gaps (all must land before launch — user confirmed) — see `docs/known_issues.md` "Doc↔code alignment gaps"
- **Findings 3–5 DONE** → **PR #39** (`docs-credential-alignment`, open): README credential over-claim softened + threat_model §4.2/§4.3 refreshed. Awaiting user review of the exact flagship-claim wording.
- **Finding 6 DONE** → on **PR #38** (README web-search "contained" caveat).
- **Finding 1 (bundled `default`→`mediated`, fail-safe) — PENDING**, part of D-196 (needs Decision 2). Also updates `test_config.py::test_network_mode_derives_from_network_enabled` (asserts bundled default == `open`).
- **Finding 2 (`build` posture) — PENDING**, D-196.

### Phase C status (web search) — **PR #38** (`websearch-firecrawl`)
Code-complete: firecrawl-broker launch integration, ddgs open-rung, launch notices, README, `whiz hermes image build --search`. **All CI green** (877 tests). The new CodeQL alert (#3, `clear-text-storage` on `search_broker.py:77`) was DISMISSED as by-design false-positive — byte-for-byte the model broker's `_write_key_file` pattern (twin alert #2 already dismissed). **Remaining before merge: live smoke with a real `FIRECRAWL_API_KEY`** (confirms Hermes actually reads `FIRECRAWL_API_URL`/`_KEY` — the one thing unit tests can't cover), then squash-merge.

### Branches / PRs in flight
- **PR #38** `websearch-firecrawl` — Phase C. Green. → live smoke → squash-merge.
- **PR #39** `docs-credential-alignment` — findings 3–5. → user reviews wording → merge.
- **main** — already has the network-egress design docs (see below), pushed directly *before* the doc-PR rule (that push logged a branch-protection bypass).
- This handoff is on `chore/session-handoff-2` (off `websearch-firecrawl`) → PR.

### Reference already written (on main)
- `docs/network_egress_design.md` — the **`allowlist` network mode** (middle ground), allowlist-proxy design (reuse internal-net + HTTP(S)_PROXY sidecar, CONNECT-host filter, no TLS termination, proxy resolves DNS → closes DNS-exfil), adoptable dev bundles + learn mode (Harden-Runner audit→enforce prior art), Firecrawl-vs-allowlist + safety comparison, and the **egress × credential-handling bifurcation** (D-195). All v1.0/future.
- **D-195** (bifurcate egress from credential handling — open), **D-196** (default/build posture — open). ROADMAP goal 11 points to the design doc.

### Process notes
- **Doc changes now go through PRs** (branch protection is on main; user wants consistency) — memory updated. Don't push docs straight to main anymore.
- **No HTML deliverables right now** — user reported HTML docs weren't downloading; deliver plain text until they say otherwise.

### Tried & rejected (this session)
- **Firecrawl-only in the wizard** — user rejected; ddgs keyless fallback is required (low-friction).
- **A credential-private profile running ddgs** — impossible; ddgs needs open egress.

### Resume protocol
1. Get the user's **Decision 1** (keyless default: A vs B — Claude leans B) and **Decision 2** (fold D-196 into the 3-profile redesign — Claude leans yes).
2. Design the concrete **3-profile model** (default/strict/open exact configs, incl. `strict`'s posture which the user wants to discuss) — this resolves D-196 and the ddgs-placement question together.
3. Implement: wizard Step-2 web-search prompt; conditional search-image build in Step 2; key probe-and-warn at Done; profile-model change in `_DEFAULT_PROFILES` (5→3) + `test_config.py` + README profiles table; update `test_init_wizard.py` input sequences.
4. For firecrawl under onecli: attach the search-broker to the onecli internal net (works today); OneCLI-gateway injection is a later item (OneCLI is inert).
5. **Live smoke PR #38** (needs the user's real `FIRECRAWL_API_KEY`) → squash-merge. Review/merge **PR #39**.
6. Then **Phase D — launch** (tag `v0.1.0` → soft-launch → Show HN). A reminder is scheduled for **Monday 2026-07-27 12:00 CT**.

Don't implement the 3-profile redesign or the D-196 code fixes until Decisions 1 & 2 are answered — they change security-default behavior and are the user's call.

---

## 2026-07-25T01:44Z — Whizzard web-search build, Phase C (launch integration next)

### Goal
Ship model/provider-agnostic web search in Whizzard cells (build plan A–D) so it's a genuinely useful tool, then tag `v0.1.0` → soft-launch → Show HN. Contained keyed backend (Firecrawl) = default; keyless `ddgs` = easy alt.

### Active task
Phase C **launch integration**: wire `start_search_broker()` into `_perform_launch` — start it after the model broker when `prof.web_search=="firecrawl"`; set the cell's `FIRECRAWL_API_URL` → search broker + placeholder key (via `HermesAdapter.container_env`); validate `web_search=firecrawl` requires a mediated/hybrid `network_mode`; tear the search broker down **before** the model broker in the `finally`.

### Tried & rejected
- **Anthropic server-side "free piggyback"**: doesn't exist in Hermes — `web_search` is always a client tool needing a configured backend, not model-dependent.
- **Dual-upstream broker proxy**: adds host-routing to the security-critical single-upstream proxy; chose a 2nd broker instance instead.
- **ddgs as contained default**: multi-host fan-out + `primp` TLS-impersonation, un-allowlistable; open-rung only.
- **pyyaml dep**: avoided — JSON is valid YAML, use stdlib `json`. And `python3` (not `python`) in mcp_servers — cell has only python3.

### Resume protocol
1. Branch `websearch-firecrawl` (= main@`8162fa3` + 3 C commits @`67a2ae2`). Read D-194 in `docs/decisions.md` + memory `project-websearch-model-agnostic`.
2. Launch integration (above): mirror the hybrid onecli-shim wiring in `whizzard/cli/_launch.py` (~L455–530). Search broker joins `broker_handle.internal_network`; teardown before `stop_broker`.
3. Then: `ddgs` open-rung + add `"ddgs"` to `WEB_SEARCH_MODES`; the two notices (key-required / expanded-surface) + README; squash-merge C as one PR.
4. Live smoke needs a real `FIRECRAWL_API_KEY` (user provides after build); keep `test_redteam_network` green + assert key absent from cell.
5. **Post-C (separate UX pass — design before coding):** revise the `whiz init` setup wizard for web search. 3 touchpoints: build/offer the search image; ask to enable `web_search` on a profile; prompt for + capture the Firecrawl key. Separable, not blocking; UX-shaped so design it with the user first.

Don't rush the launch-integration network topology — a containment bug there defeats the point.
