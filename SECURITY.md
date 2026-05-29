# Security Policy

## Reporting a vulnerability

If you believe you've found a security vulnerability in Whizzard, **please do not open a public issue or pull request**. Disclose it privately so we can investigate and ship a fix before details become public.

### Preferred channel: GitHub Private Vulnerability Reporting

Open the repository's **Security** tab and click **Report a vulnerability**. This routes the report directly to the maintainers through a private GitHub advisory, where we can triage, discuss, and coordinate a fix without the report being publicly visible.

### What to include

- A description of the vulnerability and the impact you believe it has
- The version, commit SHA, or release tag where you observed it
- Reproduction steps — minimal proof-of-concept, screenshots, or logs as relevant
- Whether you intend to publish your own write-up, and on what timeline

## Response expectations

- **Acknowledgement** within 5 business days of report
- **Initial assessment** (confirmed / not reproducible / out of scope) within 10 business days
- **Fix or mitigation plan** communicated for confirmed vulnerabilities; severity drives target timeline (critical issues prioritized over non-exploitable hardening)

These are best-effort timelines for a maintainer-driven open-source project, not a contractual SLA.

## Scope

(In this document, "sandbox" refers to the hardened Docker container Whizzard launches each agent session inside.)

In scope:

- The Whizzard Python package and CLI (`whizzard/`)
- The sandbox containment model: container hardening, mount policy, network policy, capability enforcement, credential handling
- The in-sandbox MCP surface and the agent-event channel
- Distributed Docker images published by this project
- Build, release, and CI workflows in `.github/workflows/`

Out of scope:

- Vulnerabilities in third-party agent harnesses themselves (Hermes, OpenClaw, NanoClaw, etc.) — please report those to their respective maintainers
- Vulnerabilities in Docker, the Linux kernel, or other dependencies — please report those upstream
- Issues that require an already-compromised host (Whizzard does not claim to defend against a host that is already controlled by an attacker)
- Theoretical capability bypasses that require user misconfiguration explicitly warned against in the docs

If you're unsure whether something is in scope, report it anyway and we'll discuss.

## Supported versions

Whizzard is pre-1.0; security fixes are applied to the current `main` branch and the most recent tagged release. Older tagged releases are not patched. Once 1.0 ships, this section will be updated with a clear supported-version policy.

## Disclosure policy

We follow a **coordinated disclosure** model:

- We will work with you on a fix and a disclosure timeline. Default target is 90 days from initial report to public disclosure, shorter for actively exploited issues, longer if a fix is genuinely complex.
- Credit is given to reporters in the published advisory unless you prefer to remain anonymous — please tell us your preference in the report.
- We ask that you do not publicly disclose details, share working exploits, or test against repositories you don't own until a fix is available.

## Acknowledgements

Reporters who have helped improve Whizzard's security will be listed here once advisories are published.
