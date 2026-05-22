# Similar Tools Research

Landscape scan of existing tools that overlap with Whizzard's product space, run as input
for OSS-launch positioning. The question this answers: *does something already do what
Whizzard does, and if so, where exactly does Whizzard still have unoccupied ground?*

Written: 2026-05-22. Method: web search across five framings — Docker/sandbox isolation for
agents, local capability governance, harness-neutral wrappers, MCP gateways, and runtime
behavioral monitoring — followed by source fetches on the closest matches.

Companion to the existing competitive material: `vision_and_strategy.md` §"Competitive
Framing" (what Whizzard is *not* competing with) and the NanoClaw deep-dive in
`archive/nanoclaw_research.md` (the previously-identified closest analog).

---

## TL;DR

The space has gotten crowded since the NanoClaw review, but **nothing occupies Whizzard's
exact position**: a *local-first, harness-neutral capability-governance layer* whose
permission model is a human-readable mount list and whose roadmap includes behavior-aware
revocation.

The market has split into four clusters, none of which is the whole of Whizzard:

1. **Local harness-neutral sandbox wrappers** (`scode`, Anthropic `sandbox-runtime`,
   `dagger/container-use`) — closest neighbors. They isolate; they do not *govern*. No
   profiles, no human-readable capability surface as the primary affordance, no
   time-bounding, no behavioral layer.
2. **Harness-native sandboxing** (Claude Code's sandboxed Bash/network) — single-harness,
   and the layer Whizzard explicitly does *not* recreate (D-24, architecture.md behavioral
   layer).
3. **Cloud code-execution sandboxes** (E2B, Daytona, Modal, Northflank, Vercel Sandbox) —
   different axis entirely: cloud infra for AI *products*, not local governance for a
   user's *own* agents.
4. **Enterprise agent governance / MCP gateways** (Permit.io, Kong, Gravitee, Cerbos,
   Permiso, Microsoft Agent Governance Toolkit) — explicitly *not* Whizzard's v1 audience
   (vision_and_strategy.md §"Intended Audience").

The genuine threat is cluster 1, and `scode` in particular is conceptually very close.
The genuine moat is the combination Whizzard alone assembles: **mount-list-as-permission +
profiles + time-bounding + the cooperation (MCP) layer + the planned Breaker** — see
§"Gap Analysis".

---

## Tier 1 — Direct comparables (local, agent-focused containment)

These share Whizzard's axis: a thing you run locally that puts a boundary around a coding
agent. They are the tools a prospective Whizzard user would realistically already have.

### scode — `bindsch/scode`

The closest single match to Whizzard's *positioning sentence*. scode wraps AI coding tools
(Claude, Codex, OpenCode, Goose, Gemini, etc.) in an OS-level sandbox that blocks access to
personal files, credentials, and sensitive directories. Explicitly harness-agnostic: "one
config and one set of rules, consistent across Claude, Codex, OpenCode, Goose, Gemini, or
anything else you run."

| Dimension            | scode                                          | Whizzard                                              |
|----------------------|------------------------------------------------|-------------------------------------------------------|
| Isolation mechanism  | OS-native (`sandbox-exec`/Seatbelt, `bubblewrap`) | Docker execution cell; backend abstracted (D-19)     |
| Footprint            | Single bash script, ~10ms overhead, no daemon  | Python package + daemon + container image            |
| Permission model     | `blocked:`/`allowed:` path lists in YAML; allow-default or deny-default mode | Mount list + profile toggles, shown pre-launch as *the* permission surface |
| Profiles             | Two modes (allow-default / strict)             | Named profiles (safe/default/build/power/quarantine) |
| Time-bounding        | None — sandbox lives for command duration      | First-class: duration is an enforced capability primitive |
| Audit                | `--log` denials, `scode audit`, `--watch`      | Structured session log, dry-run preview              |
| Cooperation layer    | None                                           | In-cell MCP surface (status/self-audit/requests)     |
| Behavioral layer     | None                                           | Breaker planned (Phase 3)                             |

**Read:** scode is the "good enough for most people" tool in this niche. It wins on
zero-friction install and near-zero overhead. Whizzard's differentiation has to be the
*governance* framing — visible/named/temporary capability grants, profiles as a shared
vocabulary, and the cooperation + behavioral layers — not "we also sandbox."

### Anthropic `sandbox-runtime` — `@anthropic-ai/sandbox-runtime`

The official, open-source primitive. `npx @anthropic-ai/sandbox-runtime <command>`
sandboxes arbitrary programs, including MCP servers, using OS-level mechanisms. This is the
*building block* a competitor (or Whizzard) could sit on, not a governance product itself:
no profiles, no audit story, no harness lifecycle management. Its existence matters mostly
as a signal — Anthropic is normalizing "sandbox the agent locally," which validates the
category while raising the floor.

### container-use — `dagger/container-use`

An MCP server that gives each coding agent its own isolated Docker container + git branch,
so multiple agents run in parallel without conflicts. Works with Claude Code, Cursor, and
other MCP clients. Provides command-history visibility ("see what agents actually did, not
what they claim") and a "drop into the terminal" escape hatch.

Overlaps Whizzard on: local, Docker-based, multi-harness reach, execution visibility.
Differs on: it is framed as *parallel-work isolation and dev environments*, not capability
governance. The permission model is "a fresh container," not an explicit mount list the
user reads and trusts. No profiles, no time-bounding, no behavioral revocation. It attaches
*as an MCP server the agent calls*, whereas Whizzard *wraps the harness from outside* — a
meaningful trust-model difference (the agent can choose not to call an MCP tool; it cannot
opt out of the cell).

### sandbox-agent — `rivet-dev/sandbox-agent`

Runs coding agents (Claude Code, Codex, OpenCode, Amp, Cursor, Pi) inside a sandbox and
exposes an HTTP/SSE API to control them remotely. Harness-neutral on the *control* axis,
but the product is remote orchestration, not local capability governance. Closest to
Whizzard's *post-MVP* Discord/mobile control-plane direction — worth watching as that phase
approaches, not as an MVP competitor.

### Docker Sandboxes (Docker, March 2026)

Runs each agent in a lightweight microVM with its own kernel rather than a shared-kernel
container. An isolation-strength play from the Docker org. It is infrastructure Whizzard
could *target as a backend* (the D-19 backend abstraction explicitly anticipates
Firecracker/VM backends), not a governance competitor.

---

## Tier 2 — Harness-native sandboxing (the layer Whizzard does NOT recreate)

Claude Code now ships its own sandboxed Bash tool and a network sandbox. Codex and others
are converging on the same. This is exactly the "Product Category Observation" in
vision_and_strategy.md: *harness providers will absorb basic sandboxing and command
approval.* It is also the **behavioral layer** in architecture.md's control-layering model
— harness-owned, intent-time, and explicitly out of scope for Whizzard core (D-24).

Notably, in May 2026 a Claude Code network-sandbox bypass was disclosed and quietly patched
(The Register, SecurityWeek, multiple outlets). The takeaway for positioning: single-harness
sandboxing is real but fragile, and a harness-neutral *enforcement* layer underneath it
(kernel/Docker-enforced, not harness-enforced) is the durable complement — which is precisely
Whizzard's outer layer. This is launch-narrative material alongside the existing
"crypto-swarm via published skills" anecdote in vision_and_strategy.md §"Real-World
Validation."

---

## Tier 3 — Cloud code-execution sandboxes (adjacent, different axis)

E2B, Daytona, Modal, Northflank, Vercel Sandbox, Morph, Beam — a large, well-funded cluster.
They run agent-generated code in cloud sandboxes (Daytona: Docker, sub-90ms cold start;
E2B: Firecracker microVMs, ~150ms). They differ from Whizzard on the load-bearing axis:

- **Cloud-first vs local-first.** Whizzard governs the agents on *your* machine touching
  *your* filesystem. These provision disposable cloud VMs.
- **Infra for products vs tool for a person.** Their buyer is an engineer embedding code
  execution into an AI product. Whizzard's user is the solo developer running their own
  agent (vision_and_strategy.md §"Intended Audience").
- **Isolation vs governance.** They sell isolation strength and cold-start latency. None
  sells a *human-readable, temporary capability grant* as the primary affordance.

Not competitors for the MVP. Relevant only as possible future execution backends.

---

## Tier 4 — MCP gateways & enterprise agent governance (adjacent, wrong audience)

A dense cluster: Permit.io MCP Gateway, Kong, Gravitee, Cerbos, MCP Manager (per-tool /
per-resource authorization at the MCP layer); Permiso, BeyondTrust, WorkOS, Microsoft's
open-source Agent Governance Toolkit, Databricks Unity AI Gateway, NVIDIA Verified Agent
Skills (identity, least-privilege, runtime attribution, signed-skill verification).

This cluster uses Whizzard's vocabulary — "capability governance," "least privilege,"
"default deny," "time-bounded access" — which is worth knowing so launch copy doesn't read
as derivative. But it is **explicitly not Whizzard's v1 space**: vision_and_strategy.md
rules out enterprise IAM, SOC2, and centralized corporate governance as the initial
audience. These tools govern *fleets of service-account agents inside an org's network*;
Whizzard governs *one developer's agents on one laptop*. The gateway model also governs at
the tool-call boundary (the agent must route through the gateway); Whizzard governs at the
*execution-cell* boundary (the agent cannot route around the kernel). Different grain,
different enforcement, different buyer.

One item to track: NVIDIA's "Verified Agent Skills" and signed-skill marketplaces are a
direct response to the same skill/plugin attack surface vision_and_strategy.md cites. They
attack it at the *distribution* layer (vet the skill); Whizzard attacks it at the
*execution* layer (contain whatever the skill does). Complementary, not competing — and a
useful contrast to draw explicitly.

---

## Tier 5 — Runtime behavioral monitoring (maps to the Breaker, Phase 3)

The closest prior art for Whizzard's Phase 3 Breaker concept lives here. ARMO markets "AI
agent sandboxing & progressive enforcement" with *behavioral baselines* — "every
container's actual runtime behavior becomes the foundation for anomaly detection and
enforcement, instead of declaring what an agent should do in a config file." Permiso adds
runtime identity attribution and "kill switches that revoke an agent's access at machine
speed when behavior crosses a threshold."

This validates the Breaker thesis (permissions dynamically revocable on observed behavior)
and confirms it is a real, defensible category. Two caveats for Whizzard:

- These are **enterprise, cloud, identity-layer** products. The Breaker as specced is
  local, deterministic-heuristic-first, and explicitly *not* autonomous AI scoring at the
  start (vision_and_strategy.md Phase 3). That restraint is a feature — it stays debuggable
  and trustworthy for the solo-dev audience.
- "Behavioral baseline" (learn normal, flag deviation) vs Whizzard's framing ("expected
  capability envelope *for the declared task*, flag deviation") is a subtle but real
  distinction. Whizzard's is task-scoped and legible; the enterprise version is
  statistical. Keep the task-envelope framing — it is the more honest claim.

No local, single-developer behavioral-revocation tool surfaced. Phase 3 ground appears
unoccupied at Whizzard's audience tier.

---

## Building blocks (not competitors)

For completeness — the isolation primitives everything above is built on, any of which
Whizzard could adopt as a backend under the D-19 abstraction: Firecracker (AWS microVM),
Kata Containers, gVisor (user-space kernel), bubblewrap (what scode uses on Linux), and the
Seatbelt/`sandbox-exec` framework on macOS. These are substrate, not products in
Whizzard's category.

---

## Gap Analysis — where Whizzard still has unoccupied ground

No surveyed tool combines all of the following. This intersection *is* the product:

1. **Local-first AND harness-neutral.** scode is both; container-use is both. But neither
   adds governance on top — see points 2–5. Cloud sandboxes and enterprise gateways fail
   "local-first." Harness-native sandboxes fail "harness-neutral."
2. **Mount-list-as-permission-model.** The defining affordance (D-11): the user reads their
   exact capability grant as a short, named list *before* launch. scode's path lists are
   the nearest thing, but they are config files, not a pre-launch "this is what you are
   granting" surface. Nobody else makes the permission set the primary, human-facing object.
3. **Profiles as a shared vocabulary.** Named, composable capability bundles
   (safe/default/build/power/quarantine). scode has two modes; the rest have none. Profiles
   are how a non-expert reasons about "how much am I trusting this run."
4. **Time-bounding as an enforced primitive.** Sessions expire; duration is a capability,
   not a setting. No Tier 1 tool does this. Only enterprise credential-vault products do,
   and only for cloud credentials.
5. **The cooperation layer.** An in-cell MCP surface that lets the agent introspect its own
   constraints, write audit entries, and *request* capability changes that the host
   mediates via stop+restart. container-use exposes MCP tools *to do work*; nobody exposes
   MCP tools *for the agent to negotiate its own envelope*. This is genuinely novel.
6. **The Breaker (Phase 3).** Local, deterministic, task-scoped behavioral revocation.
   Enterprise tools (ARMO, Permiso) prove the category; none serves the solo-dev tier.

**Honest risks:**

- **scode can move toward governance faster than Whizzard can move toward zero-friction.**
  A bash script with 10ms overhead is a hard install story to beat. Whizzard's answer is
  not "be lighter" — it is to make the governance value (profiles, audit, cooperation,
  Breaker) obviously worth a daemon and an image.
- **The category vocabulary is now contested.** "Capability governance," "least
  privilege," "default deny" are in enterprise marketing copy. Launch positioning should
  lean on the concrete, ownable phrases — *mount list IS the permission model*, *execution
  cell*, *Breaker* — not the generic governance lexicon.
- **Harness vendors keep absorbing the floor.** Each harness shipping its own sandbox
  shrinks the "I have no protection" gap. The durable framing remains the one already in
  vision_and_strategy.md: harness-neutral, below-the-skill, kernel-enforced — the layer no
  single harness can own.

---

## Recommended follow-ups

Not decisions — candidate items for the maintainer to weigh:

- Consider a short, named comparison ("Whizzard vs scode vs container-use") in the OSS
  README. The honest, specific contrast reads as confident; omitting it reads as unaware.
- The May-2026 Claude Code sandbox-bypass disclosure is concrete launch-narrative evidence
  for the harness-neutral-enforcement-layer argument. Consider adding it to
  vision_and_strategy.md §"Real-World Validation" alongside the crypto-swarm anecdote.
- Watch `bindsch/scode` (closest neighbor) and `dagger/container-use` (closest on the
  containment+visibility axis) for roadmap moves toward profiles or behavioral monitoring —
  those would be the first real encroachment on Whizzard's gap.

## Sources

- [scode — Safe sandbox wrapper for AI coding harnesses (GitHub)](https://github.com/bindsch/scode)
- [Configure the sandboxed Bash tool — Claude Code Docs](https://code.claude.com/docs/en/sandboxing)
- [dagger/container-use — Development environments for coding agents](https://github.com/dagger/container-use)
- [rivet-dev/sandbox-agent — Run coding agents in sandboxes](https://github.com/rivet-dev/sandbox-agent)
- [Even Claude agrees: hole in its sandbox was real and dangerous — The Register](https://www.theregister.com/security/2026/05/20/even-claude-agrees-hole-in-its-sandbox-was-real-and-dangerous/5243662)
- [Anthropic Silently Patches Claude Code Sandbox Bypass — SecurityWeek](https://www.securityweek.com/anthropic-silently-patches-claude-code-sandbox-bypass/)
- [How to sandbox AI agents in 2026: MicroVMs, gVisor & isolation strategies — Northflank](https://northflank.com/blog/how-to-sandbox-ai-agents)
- [Docker Sandbox: Running AI Agents in Isolated Docker Environments — Morph](https://www.morphllm.com/docker-sandbox)
- [Daytona vs E2B in 2026: which sandbox for AI code execution? — Northflank](https://northflank.com/blog/daytona-vs-e2b-ai-code-execution-sandboxes)
- [AI Code Sandbox Benchmark 2026 — Modal vs E2B vs Daytona — Superagent](https://www.superagent.sh/blog/ai-code-sandbox-benchmark-2026)
- [Best MCP Gateways and AI Agent Security Tools (2026) — Integrate.io](https://www.integrate.io/blog/best-mcp-gateways-and-ai-agent-security-tools/)
- [Getting Started with Permit MCP Gateway — Permit.io](https://docs.permit.io/permit-mcp-gateway/guide/)
- [MCP Permissions: Securing AI Agent Access to Tools — Cerbos](https://www.cerbos.dev/blog/mcp-permissions-securing-ai-agent-access-to-tools)
- [Introducing the Agent Governance Toolkit: Open-source runtime security for AI agents — Microsoft](https://opensource.microsoft.com/blog/2026/04/02/introducing-the-agent-governance-toolkit-open-source-runtime-security-for-ai-agents/)
- [NVIDIA-Verified Agent Skills Provide Capability Governance for AI Agents — NVIDIA](https://developer.nvidia.com/blog/nvidia-verified-agent-skills-provide-capability-governance-for-ai-agents/)
- [AI Agent Sandboxing & Progressive Enforcement: The Complete Guide — ARMO](https://www.armosec.io/blog/ai-agent-sandboxing-progressive-enforcement-guide/)
- [Permiso Brings Identity Runtime Attribution to AI Agents](https://permiso.io/blog/ai-agent-runtime-security)
- [The best authorization platforms for managing AI agent permissions in 2026 — WorkOS](https://workos.com/blog/best-authorization-platforms-ai-agent-permissions-2026)
