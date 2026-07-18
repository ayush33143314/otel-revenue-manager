"""Phase 3 agent wiring tests — covers published agent scenarios 1-3, 5, 6.

Graph introspection only: the agent is compiled but never invoked, so no LLM
API calls happen in CI. Scenario 4 (multi-tool decomposition) is covered by
the live smoke run documented in ARCHITECTURE.md; scenario 3 is satisfied via
the SUBAGENT pattern (segment/mix work delegated to 'mix-analyst').
"""
import gc

import pytest

REQUIRED = {
    "get_otb_summary",
    "get_segment_mix",
    "get_pickup_delta",
    "get_as_of_otb",
    "get_block_vs_transient_mix",
}

FRAMEWORK_TOOLS = {
    "ls", "read_file", "write_file", "edit_file", "glob", "grep", "execute",
    "task", "write_todos",
}


@pytest.fixture(scope="module")
def agent():
    # Importable without any HTTP server (scenario 1 requirement).
    from app.agent import build_agent
    return build_agent()


def tool_registry(agent) -> dict:
    node = agent.nodes["tools"].node
    for step in getattr(node, "steps", []):
        if hasattr(step, "tools_by_name"):
            return step.tools_by_name
    raise AssertionError("no ToolNode found in compiled graph")


# Scenario 1 — Tool surface is fixed: exactly the five domain tools, no SQL tool
def test_tool_surface_fixed(agent):
    tools = tool_registry(agent)
    domain_tools = set(tools) - FRAMEWORK_TOOLS
    assert domain_tools == REQUIRED
    assert not any("sql" in name.lower() for name in tools)
    for name in REQUIRED:
        params = tools[name].args if hasattr(tools[name], "args") else {}
        assert not any("sql" in p.lower() for p in params), f"{name} takes SQL"


# Scenario 2 — get_as_of_otb is human-gated
def test_hitl_on_get_as_of_otb(agent):
    assert "HumanInTheLoopMiddleware.after_model" in agent.nodes
    from langchain.agents.middleware.human_in_the_loop import (
        HumanInTheLoopMiddleware,
    )
    configs = [
        obj.interrupt_on
        for obj in gc.get_objects()
        if isinstance(obj, HumanInTheLoopMiddleware)
    ]
    assert any("get_as_of_otb" in cfg for cfg in configs), (
        "no HITL interrupt registered for get_as_of_otb"
    )


# Scenario 3 — Segment work is isolated (SUBAGENT pattern chosen)
def test_segment_subagent_registered(agent):
    # Segment/block mix work is isolated in the revenue-analyst subagent; the
    # task tool advertises it to the model.
    tools = tool_registry(agent)
    assert "task" in tools, "subagent task tool missing"
    desc = tools["task"].description
    assert "revenue-analyst" in desc
    from app.agent import REVENUE_ANALYST
    analyst_tools = {t.__name__ for t in REVENUE_ANALYST["tools"]}
    assert {"get_segment_mix", "get_block_vs_transient_mix"} <= analyst_tools


# Scenario 3 (cont.) — the revenue-analyst is a role subagent, restricted: it
# may not run the HITL point-in-time tool (that stays with the chair), and it is
# kept lean (no per-subagent skill pack — the chair owns the skills).
def test_role_subagent_restricted(agent):
    from app.agent import REVENUE_ANALYST
    analyst = {t.__name__ for t in REVENUE_ANALYST["tools"]}
    assert "get_as_of_otb" not in analyst
    assert "skills" not in REVENUE_ANALYST


# Scenario 5 — Skills are filesystem-backed, on-demand (not one giant prompt)
def test_skills_on_demand(agent):
    assert "SkillsMiddleware.before_agent" in agent.nodes
    from app.agent import (
        SKILLS_HOST_DIR,
        SKILLS_VIRTUAL_PATH,
        SYSTEM_PROMPT_TEMPLATE as SYSTEM_PROMPT,
    )
    import pathlib
    skill_files = list(pathlib.Path(SKILLS_HOST_DIR).rglob("*.md"))
    assert len(skill_files) >= 6
    # The middleware must point at the virtual mount, not a host path the
    # state backend can't see.
    from deepagents.middleware.skills import SkillsMiddleware
    mws = [o for o in gc.get_objects() if isinstance(o, SkillsMiddleware)]
    assert any(mw.sources == [SKILLS_VIRTUAL_PATH] for mw in mws)
    # Heuristic bodies live in skills, not the system prompt: no judgment
    # threshold text baked into the prompt itself.
    assert "35%" not in SYSTEM_PROMPT and "> 40%" not in SYSTEM_PROMPT
    assert len(SYSTEM_PROMPT) < 3000


# Scenario 5 (cont.) — Runtime discovery: every skill is reachable through the
# same backend mechanics the middleware uses (subdir/SKILL.md via the mounted
# FilesystemBackend). Guards against skills existing on disk but being
# invisible to the agent.
def test_skills_discoverable_through_backend():
    from app.agent import SKILLS_HOST_DIR
    from deepagents.backends import FilesystemBackend

    fb = FilesystemBackend(root_dir=SKILLS_HOST_DIR, virtual_mode=True)
    listing = fb.ls("/")
    assert listing.error is None
    subdirs = [e["path"] for e in listing.entries if e["is_dir"]]
    discovered = []
    for d in subdirs:
        content = fb.read(f"{d}SKILL.md")
        assert content.error is None, f"{d}: SKILL.md unreadable"
        discovered.append(d.strip("/"))
    assert len(discovered) >= 6
    assert "challenge-skill" in discovered  # operating rules reach the runtime


# Scenario 6 — Memory / filesystem configured for multi-turn use
def test_memory_and_checkpointer(agent):
    assert agent.checkpointer is not None, "no checkpointer: stateless chat"
    assert agent.store is not None, "no store: no long-term memory backend"
    registry = tool_registry(agent)
    assert {"write_file", "read_file"} <= set(registry), "no filesystem tools"


# Scenario 7 (bonus) — Refusal on bad instruction is encoded in the skill pack
def test_filter_policy_guardrail_exists():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    challenge = (root / "skills" / "challenge-skill" / "SKILL.md").read_text()
    assert "no caveats" in challenge or "asked to ignore" in challenge.lower()


# Scenario 4 — Multi-tool decomposition (recorded trace from the live smoke
# run: composite question answered with pickup + OTB + segment tools and the
# mix-analyst subagent — no live LLM call needed here)
def test_multi_tool_decomposition_trace():
    import json
    import pathlib
    fixture = pathlib.Path(__file__).parent / "fixtures" / "composite_trace.json"
    trace = json.loads(fixture.read_text())
    tools_used = {tc["name"] for tc in trace["tool_calls"]}
    domain_used = tools_used & REQUIRED
    assert len(domain_used) >= 2, f"expected >=2 required tools, got {domain_used}"
    assert "task" in tools_used, "subagent (task tool) not used in composite trace"
    # The revenue-analyst was fanned out for a whole-book decomposition.
    # (Skill loading is covered separately by test_skills_on_demand and
    # test_skills_discoverable_through_backend.)
    assert "revenue-analyst" in set(trace.get("subagents_invoked", []))
