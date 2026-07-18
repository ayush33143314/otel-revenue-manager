"""Revenue Manager Deep Agent — assembly of the required building blocks.

Building blocks (brief §0.3) and why each is here:
  Tools      — the five tested tools from tools/rm_tools.py; no raw SQL surface.
  Skills     — skills/ SKILL.md pack, loaded via progressive disclosure so
               judgment heuristics never bloat the system prompt.
  Subagent   — 'revenue-analyst' (a ROLE, not a topic): investigates and
               diagnoses a scope, and — the real payoff — fans out one-per-month
               in PARALLEL for a whole-book question, which a single context
               cannot do. Kept lean (judgment in its prompt) so it stays
               responsive; the chair owns the full skill pack. Topic-split
               subagents (one per tool) and an adversarial 'challenger' subagent
               were both built and rejected: topic-split was redundant with the
               skills, and the challenger added a runaway reasoning loop that
               broke live responsiveness (its check now lives as a self-check in
               the forecast skill). The value of a subagent is an isolated
               reasoning loop whose payoff beats its latency.
  Planning   — Deep Agents' built-in todo tooling decomposes composite GM
               questions before tool calls (enabled by default).
  Memory     — a store-backed filesystem persists notes across turns/threads;
               checkpointer keeps multi-turn GM conversation state.
  HITL       — get_as_of_otb (expensive point-in-time rebuild) requires
               approval; kept at MAIN-AGENT level only (never inside a
               subagent) so the approval interrupt stays simple and correct.
"""
from __future__ import annotations

import pathlib

from deepagents import create_deep_agent
from deepagents.backends import (
    CompositeBackend,
    FilesystemBackend,
    StateBackend,
    StoreBackend,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from tools.rm_tools import (
    get_as_of_otb,
    get_block_vs_transient_mix,
    get_otb_summary,
    get_pickup_delta,
    get_segment_mix,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILLS_HOST_DIR = ROOT / "skills"     # on-disk skill pack
SKILLS_VIRTUAL_PATH = "/skills"       # where the agent's backend mounts it

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT_TEMPLATE = """You are the hotel's Revenue Manager, briefing the
General Manager. Your job is commercial: help the GM MAKE more money (price to
demand) and AVOID SURPRISES (spot soft months and wash risk early). You answer
from the reservation database through your tools — never from guesses, never
with SQL.

Today's date is {today}. The database is forward-looking from today AND holds a
same-time-last-year (STLY) block one year back — the single most important
benchmark in revenue management. When the GM names a month without a year,
ALWAYS resolve it to the next FUTURE occurrence. Use the prior-year month for
STLY pacing comparisons, labelled as last year's actuals — never as business
"on the books".

Close the commercial loop, in order: (1) the number that matters (room nights,
reservations = distinct bookings, revenue — never stay rows as bookings);
(2) the benchmark — good or bad vs STLY/pace (a number with no benchmark is not
an answer); (3) the money at stake; (4) the recommended lever (rate, channel,
block, policy) per the loaded skill's thresholds; (5) the risk/caveat. Keep it
TIGHT — headline first, then short bullets, no filler; match depth to the
question (a quick lookup gets a quick answer, not a full work-up).

Working rules:
- Default universe is posted, non-cancelled; state any assumption on an
  ambiguous question.
- Be ECONOMICAL — each extra skill load and tool call is a slow round-trip.
  Load only the one or two most relevant skills and call only the tools THIS
  question needs. Do NOT expand a simple "how is <month>" into a
  forecast+segment+block+pickup sweep — answer with get_otb_summary (+ STLY if
  a benchmark helps) and OFFER deeper analysis instead of running it unprompted.
- Follow the loaded skill's thresholds and actions. Plan multi-part questions
  with your todo tools first.
- CAPABILITY LIMIT: you have NO room-type and NO booking-channel
  (WEB/REC/EMA/WAL/direct) breakdown. For a room-type or channel question, say
  plainly you don't have that breakdown — never present market-segment mix as a
  channel split. "OTA" is a market segment, not a channel; the other segments
  are not "direct".
- If a question about the book names no month, cover the whole future book (or
  ask) — don't scope to a month carried over from earlier in the chat.
You chair the revenue review. Use subagents only where they earn it — most
questions you answer yourself, fast, with your own skills and tools:
- A single-month or single-topic question ("what's driving September?", "OTA
  dependency?", "pace this week?") you answer DIRECTLY — load the relevant
  skill, call the tools, brief the GM. Do not dispatch a subagent for these.
- A WHOLE-BOOK or multi-month question ("brief me on the rest of the year")
  is where the revenue-analyst earns its place: dispatch one PER MONTH in
  parallel, then synthesise the portfolio view.
- FORECASTING and pacing-vs-last-year you run yourself (load the
  pace-vs-last-year skill): reconstruct last year's booking curve with
  get_as_of_otb, project where the month lands, run the skill's self-check
  before you commit, and say whether pickup will close the gap. CALL
  get_as_of_otb DIRECTLY — it is gated, so calling it shows the GM an
  Approve/Deny card, which is the approval; do NOT ask "shall I proceed?" in
  prose first. Never hand get_as_of_otb to a subagent.
"""

# Subagents are split by ROLE in a revenue review, not by data dimension. They
# are kept LEAN — the diagnostic method is baked concisely into each prompt
# rather than loaded skill-by-skill (progressive disclosure inside a subagent
# adds a model round-trip per skill and made answers unacceptably slow). The
# full skill pack stays on the chair (main agent), which owns the deep playbook
# and synthesis. Neither subagent gets get_as_of_otb — the forecast /
# point-in-time rebuild is HITL-gated and stays with the chair.
_READ_TOOLS = [
    get_otb_summary,
    get_segment_mix,
    get_block_vs_transient_mix,
    get_pickup_delta,
]

REVENUE_ANALYST = {
    "name": "revenue-analyst",
    "description": (
        "Investigator for a stay month or a specific question: assesses the "
        "numbers AND diagnoses the drivers (segment/channel mix, block/company "
        "concentration, recent pickup). Best used for a deep single-scope "
        "investigation, or fanned out one-per-month for a whole-book question "
        "so the chair can build the portfolio view in parallel."
    ),
    "system_prompt": (
        "You are a hotel revenue analyst. Investigate and DIAGNOSE the scope — "
        "do not just dump numbers, and work efficiently. Method: get_otb_summary "
        "for month size; get_segment_mix for who is driving it (read revenue "
        "share vs room-night share — revenue>nights = rate-accretive, "
        "nights>revenue = dilutive volume; the macro_group filter is "
        "stay-date-effective); get_block_vs_transient_mix for group/company "
        "concentration (flag block revenue share >40% or top-3 company share "
        ">30%); get_pickup_delta for recent booking velocity. Room nights are "
        "sum(number_of_spaces); reservations are distinct reservation_id — never "
        "row counts. Return a tight finding: the headline number, the top 2-3 "
        "drivers with BOTH revenue and room-night shares, any concentration "
        "breach, and the recommended lever. You do NOT have the forecast / "
        "point-in-time tool — that is the chair's job."
    ),
    "tools": _READ_TOOLS,
}

# NOTE: an adversarial "challenger" SUBAGENT was built and measured, then
# deliberately removed. As a subagent it added a full extra reasoning loop, the
# chair re-dispatched it repeatedly (observed 6x on one forecast → ~8 min), and
# long single-request answers are fragile over SSE — it broke the brief's
# "live and responsive" bar. Its value (stress-testing a forecast against the
# data traps) is preserved as a bounded SELF-CHECK inside the pace-vs-last-year
# skill: one extra reasoning step by the chair, no loop, no added round-trips.
# Lesson: a subagent must buy an isolated reasoning loop with a payoff that
# beats its latency; adversarial review here did not, a self-check did.


def build_agent(checkpointer=None, store=None, today: str | None = None):
    """Assemble the Revenue Manager deep agent. Import-safe: no server, no DB."""
    from datetime import date

    store = store if store is not None else InMemoryStore()
    checkpointer = checkpointer if checkpointer is not None else InMemorySaver()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        today=today or date.today().isoformat()
    )
    return create_deep_agent(
        model=MODEL,
        tools=[
            get_otb_summary,
            get_segment_mix,
            get_pickup_delta,
            get_as_of_otb,
            get_block_vs_transient_mix,
        ],
        system_prompt=system_prompt,
        skills=[SKILLS_VIRTUAL_PATH],
        subagents=[REVENUE_ANALYST],
        # Composite backend (route prefixes MUST be '/x/'-style):
        #   /skills/   -> read-only view of the on-disk skill pack
        #   /memories/ -> store-backed, survives across threads
        #   everything else -> graph-state scratch files
        backend=lambda rt: CompositeBackend(
            default=StateBackend(rt),
            routes={
                "/memories/": StoreBackend(rt),
                "/skills/": FilesystemBackend(
                    root_dir=SKILLS_HOST_DIR, virtual_mode=True
                ),
            },
        ),
        interrupt_on={
            # Point-in-time rebuild is expensive and easy to misread — GM
            # must approve each call (brief Phase 3 requirement).
            "get_as_of_otb": True,
        },
        checkpointer=checkpointer,
        store=store,
        name="revenue-manager",
    )


agent = build_agent()
