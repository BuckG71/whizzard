# Network egress & credential-handling — design

**Status:** design / not yet implemented. Captures the target model for
ROADMAP goal 11 (per-destination allowlist) plus a proposed refactor
(bifurcating egress from credential handling). Nothing here ships yet; this is
the reference to implement against at the appropriate time. See open decisions
D-195 (bifurcation) and D-196 (default/build posture).

Cross-refs: D-184 (credential broker), D-187/D-188 (OneCLI gateway / hybrid),
D-194 (managed scope + Firecrawl web search), `docs/threat_model.md`,
`docs/known_issues.md` (the alignment gaps this design resolves).

---

## 1. Current model (as shipped)

Egress is governed by one field, `network_mode` ∈
`{none, open, mediated, onecli, hybrid}` (`config.py: NETWORK_MODES`). If a
profile omits it, it derives from `network_enabled` (`False → none`,
`True → open`). The three credential-private modes put the cell on a per-session
`--internal` network whose only peers are proxy sidecars.

The problem: this **one field fuses two independent concerns** — *how much of
the internet the cell can reach* and *how credentials are kept out of the cell*.
That fusion is why there is no profile that gives broad egress **and** a private
model key without OneCLI (see §2), and it is the root of the dev-profile
ambiguity in D-196.

---

## 2. Target: two independent axes

Split the single enum into two orthogonal fields:

- **Egress** — *where can the cell reach?* `none` · `allowlist` · `open`
  (and, via a proxy, `proxied-broad`).
- **Credential handling** — *how do keys stay out of the cell?* `raw/none`
  (key absent, or injected raw via `secrets:`) · `broker` (model key host-side,
  D-184) · `onecli` (all creds host-side) · `broker + onecli`.

|                    | raw / none            | broker (model)                | onecli (all)      | broker + onecli |
|--------------------|-----------------------|-------------------------------|-------------------|-----------------|
| **none** (offline) | `safe` / `quarantine` | —                             | —                 | —               |
| **open**           | `open` / `power` / `build` | ★ **NEW** broad egress + model key private, no OneCLI | (egress is proxied) `onecli` | (proxied) `hybrid` |
| **allowlist** (new)| new                   | new — named hosts + key private | new             | new             |

The **★ cell is the payoff**: keeping the model key out of the cell does *not*
depend on egress being narrow — the key simply is never injected; it lives on
the broker and is attached only on the outbound model hop. So "open egress to
the world **and** model calls routed through the broker" is coherent and needs
no OneCLI. That is the broad-egress-but-key-private dev profile the current
fused enum cannot express (today you would reach for `hybrid`, which drags in
OneCLI).

**The one honest coupling.** The axes are independent for the *model* key, but
*service tokens* are not: the only no-OneCLI way to give the cell a service
token today is to inject it `raw` (the `secrets:` path). So "broad egress +
*service* tokens also private" still requires OneCLI. Bifurcation cleanly
separates egress from *model*-credential handling; fully separating
*service*-credential handling too means OneCLI or a per-service broker (larger
scope) — an explicit later-scope call.

**Compatibility.** The current five mode names become **presets** over the two
axes (e.g. `native` = `egress: broker-only + credentials: broker`), so existing
profiles keep working.

---

## 3. Network config modes (with the new `allowlist`)

| Mode | Docker layer | Egress permitted | Credential posture | Needs OneCLI |
|---|---|---|---|---|
| `none` | `--network none` | Nothing — no route, no DNS. | N/A | No |
| `mediated` ("native") | per-session `--internal` net; sole peer is the broker | **Model API endpoint only** (broker pinned to one host). +firecrawl broker if `web_search: firecrawl`. | Model key never in cell (placeholder + broker URL). | No |
| **`allowlist` (new)** | per-session `--internal` net; sole peer is an **allowlist proxy** sidecar; `HTTP(S)_PROXY` set in cell | **A named set of hosts** (the profile's `egress_allowlist`) and nothing else. | Composes with any credential handling (esp. `broker`). | No |
| `onecli` | isolated net; OneCLI gateway is the proxy peer | Broad, but proxied through the gateway. | Every credential injected host-side; cell holds none. | Yes |
| `hybrid` | broker + OneCLI gateway both on the isolated net | Broad (proxied); model endpoint via broker. | Model via broker + services via OneCLI. | Yes |
| `open` | default Docker bridge (no isolation flag) | **Everything** — unrestricted direct egress, DNS on. | No mediation; **no model key injected** (needs `secrets:` → raw in cell). | No |

`allowlist` slots in as the **middle ground between `mediated` (one pinned host)
and `open` (the whole internet)**: multi-host, but exactly the declared set.

---

## 4. The allowlist proxy — design & implementation

### Topology (reuse what `onecli` already proves)

```
   cell (agent)                allowlist proxy            the internet
   HTTP(S)_PROXY  ──internal──▶  host ∈ list?  ──egress──▶  ✔ pypi.org
   (no direct route)            ✔ allow → tunnel            ✔ github.com
                                ✘ deny  → 403               ✘ evil.com (refused)
```

- **Reused as-is:** the per-session `--internal` net (no NAT; the cell can't
  route out on its own), the sidecar lifecycle (`broker.py`-style
  start/teardown/reaper), and the `HTTP(S)_PROXY` + `NO_PROXY` env wiring in the
  Hermes adapter (the `onecli`/`hybrid` path).
- **New:** a small **forward CONNECT proxy** that permits a request only if the
  target host matches the profile's allowlist. For HTTPS it filters on the
  `CONNECT` target host and then tunnels — **no TLS termination**, so no CA
  plumbing and the proxy never sees payloads. For plain HTTP it filters the
  `Host` header.
- **New:** a per-profile field, e.g.
  `egress_allowlist: ["pypi.org", "*.pythonhosted.org", "github.com"]`, or a
  named bundle reference (§5).

### Two properties that fall out for free

- **DNS-exfil closes for this mode.** The *proxy* resolves names, not the cell,
  so the cell needs no resolver and the DNS-tunnel gap `open` has is not
  reachable. (This answers the ROADMAP goal 11 "DNS gating" sub-track: DNS is
  handled by the proxy, not the cell.)
- **Non-HTTP egress stays blocked.** The cell has no route except the HTTP(S)
  proxy, so raw sockets / odd protocols go nowhere.

### Caveats (keep honest)

- **Only proxy-honoring tools get out.** `pip`, `npm`, `git-https`, `curl`
  honor `HTTP(S)_PROXY`; a tool that ignores it reaches nothing (fail-closed).
- **CONNECT-host filtering can't see inside TLS.** A determined agent could
  domain-front (connect to an allowed host, present a different inner SNI) — a
  theoretical residual. Adequate for "contain my own agent," not a
  nation-state egress boundary. Closing it fully means MITM + SNI inspection
  (CA plumbing), which we deliberately avoid.
- **Hostname, not IP.** Filtering is by hostname (stable) rather than IP
  (churns constantly across CDNs).

### Implementation notes

- Proxy candidates, dep-hygiene first: a minimal self-written asyncio CONNECT
  proxy (single responsibility, matches the existing `broker/proxy.py` style),
  or a Debian-packaged option (e.g. tinyproxy with a filter list) baked into the
  broker image. No PyPI in the security sidecar.
- Launch wiring mirrors the `onecli` shim path in `whizzard/cli/_launch.py`
  (start sidecar on the cell's internal net; set `HTTP(S)_PROXY`; teardown
  before the net is removed).
- No new trust boundary — same "cell's only peer is a Whizzard sidecar" model,
  just a policy that permits N hosts instead of 1.

---

## 5. Pre-configured allowlist bundles

Coding/dev allowlists cleanly — package registries and forges are a finite,
published host set. **Research does not** allowlist (the open web is the target
by definition) — route research reads through Firecrawl (§6), not an allowlist.

### Starting host sets (curated defaults users can extend)

| Bundle | Hosts | Covers |
|---|---|---|
| `python` | `pypi.org`, `files.pythonhosted.org` | `pip install`, build deps |
| `node` | `registry.npmjs.org`, `registry.yarnpkg.com` | npm / yarn / pnpm |
| `rust` | `crates.io`, `static.crates.io`, `index.crates.io` | cargo |
| `go` | `proxy.golang.org`, `sum.golang.org`, `storage.googleapis.com` | go mod |
| `github` | `github.com`, `api.github.com`, `codeload.github.com`, `*.githubusercontent.com`, `ghcr.io` | clone / push / releases / GHCR |
| `os-debian` | `deb.debian.org`, `security.debian.org` | apt (base is Debian) |
| `docker` | `registry-1.docker.io`, `auth.docker.io`, `production.cloudflare.docker.com` | Docker Hub pulls |
| `llm-apis` | `api.anthropic.com`, `api.openai.com` | direct model calls (if not brokered) |

**Composed presets:** `coding-python` = `python + github + os-debian`;
`coding-fullstack` = `python + node + github + os-debian`. A profile names the
bundle(s).

### Learn mode (the feature that makes this usable)

The allowlist proxy sees every `CONNECT`, so offer **observe-only "learn"
sessions**: run a task once with egress logged-but-not-blocked; the proxy
proposes a tightened allowlist from what the workload actually hit. Ship the
curated bundles as the starting point, and let learn mode close the gap for a
specific repo/toolchain. This sidesteps the static-list maintenance problem.

### Prior art worth adopting, not reinventing

- **StepSecurity Harden-Runner** — egress filtering for GitHub Actions with a
  maintained "known destinations" DB and an **audit→enforce** flow (observe,
  then generate the allowlist). The pattern to copy.
- **`api.github.com/meta`** — authoritative live feed of GitHub host/IP ranges,
  so the `github` bundle can be refreshed from source.
- **Artifact-proxy vendor docs** (Artifactory / Nexus / Chainguard) publish
  upstream host lists for these ecosystems — a cross-check.

### Caveats

- Lists drift (CDNs, mirrors); wildcards (`*.githubusercontent.com`) + the
  `/meta` feed + learn mode keep them current.
- Research is the exception — use Firecrawl, keep the allowlist for tools.

---

## 6. Relationship to Firecrawl web search

Firecrawl (D-194) and the allowlist proxy both sit between the cell and the
internet but **narrow different things**:

- **Firecrawl broker = delegated-fetch relay.** One pinned network host
  (`api.firecrawl.dev`), but that host fetches the whole web for you →
  **narrow network, broad (read-only) content**, a third party (Firecrawl SaaS)
  in the loop, needs a key.
- **Allowlist proxy = direct-connection gate.** N hosts reached directly, and
  only those → **broader network, narrow content** (exactly the list), full
  interaction, no third party, no key.

So "one host" is tighter on *network surface* but looser on *content reach* —
that one host is a fetch-anything relay. They are **complementary**: a
research+dev profile could run both (`egress: allowlist[pypi,github]` +
`web_search: firecrawl` + `credentials: broker`) — three narrow doors instead
of one open one.

**Is Firecrawl materially safer than `open`?** Yes on the network-containment
axis (no SSRF to metadata/LAN, no arbitrary C2, no port scans, DNS-exfil closed,
read-only, server-side fetch) — this is the pivot class that broke the OpenAI →
Hugging Face escape, and Firecrawl makes it structurally impossible. **No** on
exfiltration (arbitrary-URL fetch is itself a leak channel — narrower/logged,
not closed) and prompt injection (untrusted web text still enters the model).
Slightly worse on third-party exposure. The exfil gap is best closed by the
credential axis + minimal mounts (leave little worth exfiltrating), not by
Firecrawl.

---

## 7. Open decisions

- **D-195** — adopt the egress × credential-handling bifurcation (§2)?
- **D-196** — the intended posture for `default` and `build` (see
  `known_issues.md`: `default` is credential-private only after `whiz init`;
  `build` is `open` in every install despite the README calling it "native").
