# ARCHITECTURE.md

## 1. ETL boundary
**Extract** (`etl/extract.py`): Playwright walks the "Page X of Y" list
(100/page), opens all detail pages (fields + per-night stay rows), scrapes the
five `/reference` tabs and the `/verify` JSON. Selector-based waits, retries
with fresh pages, resumable within an anchor/revision; any missing page raises.
**Transform** (`etl/transform.py`): enforces reservation × stay_date grain
(stay-row count == nights, duplicates rejected), types all columns,
FK-validates room/market/channel. *Rate-code decision:* detail pages publish
raw channel rate codes (`OCHEARLY`, `EXPBARH`, …) absent from the 8-row
published `rate_plan_lookup`, with no alias mapping on the site — we keep
source fidelity (raw code in fact table, published lookup unchanged, FK
dropped, LEFT joins for plan family). No required tool reads rate plans.
**Load** (`etl/load.py`): truncate-and-reload in one transaction +
`load_manifest` row (`row_hash` = sha256 of sorted
`reservation_id|stay_date|financial_status`). Idempotent: re-runs reproduce
hash `ff8716…`. **Verify** (`etl/reconcile.py`): 13 checks vs `/verify` — all
passing for anchor 2026-07-17; `LOAD_PROOF.json` cross-checked against
`SCRAPE_MANIFEST.json`.

## 2. Database and views
Neon Postgres (deploy) / docker-compose (dev). `sql/views.sql`:
`vw_stay_night_base` (Posted, non-cancelled), `vw_segment_stay_night`
(stay-date-effective macro group), `vw_stay_night_all` (unfiltered, so the
as-of rebuild also never touches the raw table).

## 3. Tool layer (`tools/rm_tools.py`)
`get_otb_summary`→base (all-Posted when `exclude_cancelled=False`) ·
`get_segment_mix`→segment · `get_pickup_delta`→base+segment (London-midnight
window on `create_datetime`, UTC-compared) · `get_as_of_otb`→all ·
`get_block_vs_transient_mix`→base. Defaults live in the base view; deviations
are explicit arguments echoed in payloads. No tool accepts SQL — grain, filters
and date semantics are tested code (`tools/METRIC_DEFINITIONS.md`).

## 4. Deep Agents wiring (`app/agent.py`)
| Building block | Use |
|---|---|
| Tools | The five named tools — no `run_sql` |
| Skills | 9 runtime skills (`skills/*/SKILL.md`) via `/skills` filesystem mount; pack manifest `skills/CHALLENGE_SKILL.md` (otel-rm-v2) |
| Subagent | **revenue-analyst** (a role, not a topic): investigates + diagnoses a scope, and fans out one-per-month in **parallel** for whole-book questions — the payoff a single context can't give. Lean (judgment in its prompt) so it stays responsive; the chair owns the full skill pack, answers everyday questions directly, and synthesises. It does not get `get_as_of_otb` — HITL forecast stays with the chair. Forecast stress-testing is a self-check in the pace-vs-last-year skill |
| Planning | Built-in todo middleware for composite GM questions |
| Memory / filesystem | Composite backend: `/skills/`→read-only pack, `/memories/`→store (cross-thread), else graph-state scratch; checkpointer for multi-turn chat |
| HITL | `interrupt_on={"get_as_of_otb": True}` — approval per point-in-time rebuild |
| Model & prompt | Revenue-manager briefing persona (brief §12); heuristics live in skills, not the prompt |

## 5. Skill → tool routing matrix
| Skill | Primary tool(s) | Subagent | Judgment? |
|---|---|---|---|
| challenge-skill | all five (routing + trap guardrails) | — | N |
| otb-summary | get_otb_summary | — | N |
| segment-mix | get_segment_mix | mix-analyst | N |
| pickup-pace | get_pickup_delta | pace-analyst | **Y** (<3%/>10% pace share → actions) |
| pace-vs-last-year | get_otb_summary (this yr + STLY) | pace-analyst | **Y** (±10% STLY variance → price/stimulate) |
| ota-concentration | get_segment_mix | mix-analyst | **Y** (20%/35% revenue share → actions) |
| block-concentration | get_block_vs_transient_mix | mix-analyst | **Y** (40% block / 30% top-3 / 10-pt dilution → actions) |
| cancellation-risk | get_otb_summary, get_as_of_otb | — | **Y** (25%/40% cancelled share → actions) |
| as-of-comparison | get_as_of_otb | — | N (documents the HITL gate) |

OTB → otb-summary; pace/pickup/STLY → pickup-pace + pace-vs-last-year
(pace-analyst); mix/OTA → segment-mix / ota-concentration; block/company →
block-concentration (mix-analyst).

**Business framing.** Every skill leads with the commercial *why* (money at
stake, not just the metric), and the system prompt enforces a
number → benchmark (STLY/pace) → money → action → risk loop on every answer.

**Subagent doctrine (earn the latency, or don't spawn).** A subagent earns its
place only when an isolated reasoning loop buys a payoff bigger than its
latency: context isolation, capability restriction, distinct reasoning, or
parallel decomposition. We kept **revenue-analyst** because its payoff is real —
fanning out one investigation per month in **parallel** is something a single
context cannot do. We rejected two others *after building and measuring them*:
(1) topic-split subagents (one per tool) — redundant with the skills, no
isolated reasoning; (2) an adversarial **challenger** subagent for forecasts —
it looked great in principle but the chair re-dispatched it in a loop (~8 min
answers), breaking the "live and responsive" bar, so its trap-check became a
bounded self-check inside the forecast skill. Also declined: an orchestrator
(the chair already orchestrates). The lesson — *when NOT to use a subagent* — is
the point: a self-check beat a subagent for adversarial review here.

## 6. Agent tests
`tests/test_agent.py`: compiled-graph introspection, no LLM calls — exactly
five domain tools (no SQL tool); HITL middleware targets `get_as_of_otb`;
mix-analyst advertised with exactly the two mix tools; skills mounted at
`/skills` **and** discoverable through the same backend mechanics the
middleware uses; checkpointer + store present. `tests/test_skills.py`:
version pin, ≥3 judgment skills (threshold+action regex, ≥80 words), routing,
guardrails — filesystem only.

## 7. Deployment topology
Neon Postgres (loaded by this ETL) → LangGraph server → Agent Chat UI
streaming tool/skill calls, behind basic auth. `GET /health` reads
`db_fingerprint`, `dataset_revision`, `row_hash`,
`financial_status_posted_only_rows` live from the DB. API keys are deployment
env vars, never in git.

## 8. Out of scope
MCP (optional in brief) — no correctness gain over the five tools. Rate-plan
alias inference — deliberately not fabricated (§1).
