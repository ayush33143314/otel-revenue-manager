---
name: challenge-skill-pack
description: "Pack manifest for otel-rm-v2: index of the Revenue Manager skill set, listing every skill, its judgment status, and its tool routing (get_otb_summary, get_segment_mix, get_pickup_delta, get_as_of_otb, get_block_vs_transient_mix)."
---

# Skill pack manifest — otel-rm-v2

This file pins the pack version and indexes the runtime skills, which live as
`<skill-name>/SKILL.md` directories alongside it (the format Deep Agents
discovers). The agent's core operating rules are in
[challenge-skill/SKILL.md](challenge-skill/SKILL.md).

| Skill | Primary tool(s) | Judgment |
|-------|-----------------|----------|
| challenge-skill | all five (routing + guardrails) | — |
| otb-summary | get_otb_summary | — |
| segment-mix | get_segment_mix | — |
| pickup-pace | get_pickup_delta | thresholds + actions |
| pace-vs-last-year | get_otb_summary + get_as_of_otb (forecast) | thresholds + actions |
| ota-concentration | get_segment_mix | thresholds + actions |
| block-concentration | get_block_vs_transient_mix | thresholds + actions |
| cancellation-risk | get_otb_summary, get_as_of_otb | thresholds + actions |
| as-of-comparison | get_as_of_otb (HITL-gated) | — |

The **revenue-analyst** subagent (a role, not a topic) investigates + diagnoses
a scope and fans out one-per-month in parallel for whole-book questions — kept
lean for responsiveness (judgment in its prompt) while the chair (main agent)
owns this full skill pack and answers everyday questions directly. Forecast
stress-testing is a self-check inside pace-vs-last-year (an adversarial
challenger subagent was measured and rejected for latency; see ARCHITECTURE).
No skill may instruct SQL or direct fact-table access; every metric flows
through the five tools above.
