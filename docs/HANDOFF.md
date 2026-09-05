# Session Handoff Log

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
