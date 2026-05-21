# Home-Lab Deployment Reference

**Status:** Reference doc, not active deployment plan. Intended for execution *after* MVP is operational, after the local Hermes→OIQ-wrapped migration is debugged on the Mac Studio (per D-86 Migrate path), and after the Whizzard→Osmotiq rename (D-158). Captured here so the architecture survives compaction and is available when execution begins.

**Captured:** 2026-05-19

---

## TL;DR

A four-machine Tailscale-meshed topology for self-hosting an always-on autonomous agent setup with capability containment and bring-your-own local inference. All four machines are already owned and Tailscale + Ollama are already provisioned on three of them; the only net-new work is wiping the 2015 MBP and installing Linux on it.

| Role | Machine | Status |
|------|---------|--------|
| Workstation | Mac Studio (M-series) | In place; Tailscale + Ollama already running |
| Always-on agent host | 2015 MacBook Pro 15" (Linux, post-wipe) | Hardware in place; OS install + Tailscale join required |
| Local inference (always-on tier) | Gaming PC (NVIDIA, ~8 GB VRAM) | In place; Tailscale + Ollama already running |
| Local inference (higher-quality tier) | Mac Studio Ollama (shared with workstation role) | In place |
| Production agent host *(eventual)* | Cloud VM (Linux, Tailscale-joined) | Not provisioned; deferred until Linux-on-MBP step is debugged |

---

## Architectural shape

The topology is hub-and-spoke over Tailscale; no machine exposes services to the public internet. All inter-machine traffic goes over the private tailnet.

```
                  +--------------------+
                  |   Android phone    |
                  |  (Tailscale)       |
                  +---------+----------+
                            | (Discord control,
                            |  ad-hoc remote)
                            v
+---------------+    +------+------+    +----------------+
|  Mac Studio   |<-->|             |<-->|  Gaming PC     |
|  (workstation |    |  Tailscale  |    |  (NVIDIA GPU)  |
|   + Ollama)   |    |   mesh      |    |  (Ollama, WoL) |
+-------+-------+    |             |    +-------+--------+
        |            +------+------+            |
        | dev work          |                   | inference
        | git push          |                   | API
        |                   v                   |
        |          +----------------+           |
        +--------> |  2015 MBP      | <---------+
                   |  (Linux)       |
                   |  OIQ + Docker  |
                   |  + Hermes cell |
                   +----------------+
                            |
                            | (eventually replaced by)
                            v
                   +----------------+
                   |  Cloud VM      |
                   |  (Linux,       |
                   |   Tailscale)   |
                   +----------------+
```

## Why this shape

**Threat-model alignment.** The autonomous agent (Hermes) lives on its own host, not on the workstation that holds development files and primary credentials. The agent is wrapped in OIQ cells, so even within its host, capabilities are explicit and per-session. This combines perimeter isolation (separate machine) with per-cell isolation (OIQ) — two boundaries instead of one. Aligns with the dep-careful + harness-yolo split threat model in `memory/user_dep_hygiene.md`.

**Separation of concerns.** Each machine has one job:
- Mac Studio = workstation + ad-hoc heavy-model inference.
- MBP = always-on agent host (and Linux-deployment validation environment for the eventual cloud VM).
- Gaming PC = dedicated GPU inference, doesn't disturb workstation responsiveness, can be powered down when unused (Wake-on-LAN brings it up on demand).
- Cloud VM (later) = production replacement for the MBP, when the MBP role is well-understood and OIQ-on-Linux is debugged.

**Tailscale as the bus.** MagicDNS lets the agent call `http://gaming-pc.tailnet:11434/v1/...` by name. No public ports, no public DNS, no NAT punching. The private mesh is the entire networking story.

**OIQ stays inference-endpoint-agnostic.** The Hermes adapter doesn't dictate which model endpoint is called; that's harness config. OIQ's containment posture works identically whether the agent calls api.anthropic.com or `http://gaming-pc.tailnet:11434/v1`. No special OIQ code is needed to support this topology — it just works.

## Inference tiering

Three tiers, used by the agent on the MBP based on model-class requirements:

1. **Always-on tier — Gaming PC Ollama (8 GB VRAM).** Llama 3.1 8B class, Qwen 2.5 7B class, DeepSeek-Coder small variants, Phi-3.5 Mini, etc. Curated set Bryan has already validated for performance on this hardware. Convenience tier — picks up routine queries without disturbing the workstation. Can be powered down and woken via WoL over Tailscale to avoid idle-power tax.

2. **Higher-quality tier — Mac Studio Ollama.** Apple Silicon unified memory means materially larger models (per actual RAM config). Used when the agent needs something bigger than the gaming PC can host, and the workstation is on anyway because Bryan is working.

3. **Frontier tier — Cloud APIs.** Anthropic / OpenAI / OpenRouter / etc. for queries that need frontier-quality reasoning that no local model can match. OneCLI-mediated credentials per D-134.

The Hermes-side config decides which endpoint to call; routing logic lives in Hermes (or in a future routing skill), not in OIQ.

## What's already in place

- **Tailscale**: Mac Studio, Gaming PC, Android phone — all joined.
- **Ollama on Mac Studio**: installed, models curated and validated.
- **Ollama on Gaming PC**: installed, models curated and validated.
- **OneCLI**: configured on Mac Studio with platform credentials.
- **OIQ + Hermes integration**: in development on Mac Studio (the MVP work). Will be validated locally before any deployment migration.
- **2015 MacBook Pro 15"**: hardware in hand, brand-new battery (recall replacement, ~1 year old), needs OS wipe and Linux install.

## What's required to execute (post-MVP)

The actual delta from current state to the four-machine topology is small:

1. **Verify the MBP boots and check RAM** (16 GB ideal; 8 GB workable but tight for Docker + Hermes).
2. **Install Ubuntu 24.04 LTS or Debian 12** on the MBP. Both have solid 2015 MBP hardware support; Wi-Fi may need a non-free Broadcom driver (installer handles it).
3. **Configure clamshell mode**: set `systemd-logind` so closing the lid doesn't suspend; keep on permanent power.
4. **Join Tailscale**: `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`. Note the MagicDNS hostname.
5. **Install Docker** (standard Linux Docker, not Docker Desktop).
6. **Install OIQ** (the renamed package, post-D-158).
7. **Migrate Hermes profile** from Mac Studio to MBP per the planned D-86 Migrate path — clone `~/.hermes-whizzard-cell` to the MBP via scp / git / rsync; update the harness config's `hermes_home`.
8. **Configure Hermes** to point at local Ollama endpoints over Tailscale for the model calls that should route locally.
9. **Wake-on-LAN setup** on the Gaming PC: enable WoL in BIOS + NIC settings; configure a small script that sends the magic packet when the agent on the MBP needs inference and the Gaming PC is asleep; auto-shutdown after N minutes idle.
10. **Validate end-to-end**: start a Hermes session on the MBP, issue a Discord command, confirm Tailscale-routed inference works, confirm state persists across container restarts via the HERMES_HOME mount (M6 wiring).

Total estimate: one focused weekend.

## Honest constraints worth knowing

**Thermal management on the MBP.** Intel 2015 MBPs throttle under sustained load and have a decade of thermal-paste degradation. If the autonomous Hermes idles 99% of the time and spikes only on Discord commands, thermals are mostly a non-issue. A cooling pad ($20–30) is cheap insurance for sustained-load periods.

**Disk mortality on the MBP.** 10-year-old SSD; treat state on it as disposable. Tailscale + git push back to Mac Studio + periodic snapshots of `~/.hermes-whizzard-cell` to a NAS or to the Mac Studio = adequate recovery path. Don't store anything load-bearing only on the MBP.

**Power draw on the Gaming PC.** Idle 50–100W; under inference, 200–400W. If always-on, this is real money. The WoL-on-demand pattern eliminates the always-on tax: gaming PC stays off until the agent on the MBP needs it; wakes, serves the inference, idles for N minutes, shuts down.

**Local inference quality ceiling.** An 8 GB-VRAM gaming PC can't run frontier models. The 7B-class models that do fit are fine for routing/classification/summarization/boilerplate but weaker for complex agentic reasoning. Mac Studio Ollama covers the middle ground; cloud APIs cover the top. The agent harness has to route appropriately — local-only deployments will feel the quality difference vs. cloud-API agents.

**Cloud VM trust-chain (eventual step).** When the production-host role moves from MBP to a cloud VM, the cloud provider enters the trust chain. The MBP-as-Linux step is partly a buffer that validates the deployment on hardware Bryan fully controls before introducing the cloud dependency.

**Always-on assumes the home network is up.** ISP, router, and power are all single points of failure for the MBP-based deployment. The MBP's new battery acts as a built-in UPS for short flickers, but a multi-hour outage takes the agent down. The eventual cloud VM step is the answer to this — but until then, the MBP role is "always-on except when the house has a problem."

## OSS-launch positioning notes

This topology is reproducible by any user with similar hardware. Three open-source tools (OIQ, Tailscale, Ollama) + three commonly-owned machine classes (workstation, secondary box, gaming/AI PC) + one weekend = a self-hosted agent stack with capability containment, private inference, and no cloud trust chain. Worth mentioning as a recommended deployment pattern in the OSS README and `docs/examples/` — likely as `docs/examples/deployments/home_lab/` with a copy-paste setup walkthrough.

The narrative angle to lean into: "you already own most of this." Not "buy a Mac mini" or "rent a VM" — *use what's on your desk*. The differentiator from existing self-hosted-agent stories is OIQ's per-cell containment layer turning the hand-rolled isolation checklist (Docker, mounts, network policy, credential scoping, audit logs) into a single opinion-having tool.

## Open questions to revisit at execution time

- **MBP RAM verification.** Need to confirm 16 GB vs 8 GB before committing. 8 GB will be tight under load.
- **Power tradeoff for Gaming PC always-on vs. WoL.** Depends on actual idle-frequency usage patterns once the autonomous agent is running. Easier to measure after a few weeks of operation than to predict.
- **Hermes config for tiered model routing.** Hermes's existing config supports endpoint configuration per-model; need to validate the multi-endpoint routing pattern works cleanly with the harness when we get there.
- **Sequencing of MBP-vs-Cloud-VM transition.** Worth revisiting after MBP role is stable — at that point may decide cloud VM is overkill (MBP is sufficient) or essential (need cloud-grade uptime).
