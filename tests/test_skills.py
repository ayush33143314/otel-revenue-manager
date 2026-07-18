"""Phase 3 skill-pack structure tests — covers published skill scenarios 1-7.

Pure filesystem tests: no database, no LLM calls.
"""
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"

REQUIRED_TOOLS = [
    "get_otb_summary",
    "get_segment_mix",
    "get_pickup_delta",
    "get_as_of_otb",
    "get_block_vs_transient_mix",
]

# numeric threshold: percentages, comparisons, or "N points/days" style rules
THRESHOLD_RE = re.compile(
    r"(>=?|<=?|≤|≥|above|below|under|over|exceeds?)\s*~?\s*\d+(\.\d+)?\s*(%|percent|points?)?",
    re.IGNORECASE,
)
ACTION_RE = re.compile(
    r"recommend|close (OTA|discounted)|raise BAR|hold (BAR|transient)|open a promotional"
    r"|shift|re-pric|overbooking|deposit|fence|cap or close",
    re.IGNORECASE,
)


def load_skills() -> list[dict]:
    skills = []
    for path in sorted(SKILLS_DIR.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, flags=re.S)
        assert m, f"{path}: missing YAML frontmatter"
        front = yaml.safe_load(m.group(1))
        skills.append({"path": path, "front": front, "body": m.group(2)})
    return skills


# Scenario 1 — Pack version pin
def test_pack_version_pin():
    path = SKILLS_DIR / "CHALLENGE_SKILL.md"
    text = path.read_text(encoding="utf-8")  # raises if not valid UTF-8
    m = re.match(r"\A---\n(.*?)\n---", text, flags=re.S)
    front = yaml.safe_load(m.group(1))
    assert "otel-rm-v2" in front["description"]


# Scenario 2 — Minimum skill count with frontmatter
def test_minimum_skill_count():
    skills = load_skills()
    assert len(skills) >= 6
    for s in skills:
        assert s["front"].get("name"), f"{s['path']}: missing name"
        assert s["front"].get("description"), f"{s['path']}: missing description"


# Scenario 3 — Judgment skills: threshold + action + depth
def test_judgment_skills():
    judgment = []
    for s in load_skills():
        has_threshold = bool(THRESHOLD_RE.search(s["body"]))
        has_action = bool(ACTION_RE.search(s["body"]))
        word_count = len(s["body"].split())
        if has_threshold and has_action and word_count >= 80:
            judgment.append(s["front"]["name"])
    assert len(judgment) >= 3, f"only {judgment} qualify as judgment skills"


# Scenario 4 — Tool routing declared, no raw SQL
def test_tool_routing_declared():
    for s in load_skills():
        text = s["front"]["description"] + s["body"]
        assert any(t in text for t in REQUIRED_TOOLS), (
            f"{s['path']}: names no required tool"
        )
        assert "reservations_hackathon" not in text.lower().replace(
            "never write sql", ""
        ) or "never" in text.lower(), f"{s['path']}: routes to raw table"
        assert not re.search(r"\bselect\s+.*\bfrom\b", text, re.IGNORECASE), (
            f"{s['path']}: contains SQL instructions"
        )


# Scenario 5 — Distinct routing, coverage of core question types
def test_distinct_routing():
    skills = load_skills()
    names = [s["front"]["name"] for s in skills]
    assert len(names) == len(set(names)), "duplicate skill names"
    descs = [re.sub(r"\s+", " ", s["front"]["description"]).strip() for s in skills]
    assert len(descs) == len(set(descs)), "duplicate skill descriptions"
    all_text = " ".join(s["front"]["description"].lower() for s in skills)
    assert "pickup" in all_text or "pace" in all_text
    assert "mix" in all_text or "segment" in all_text
    assert "on the books" in all_text or "otb" in all_text or "books" in all_text


# Scenario 6 — Adversarial guardrail present
def test_adversarial_guardrail():
    bodies = " ".join(s["body"].lower() for s in load_skills())
    assert "stay rows" in bodies and ("never" in bodies or "trap" in bodies)
    assert "property_date" in bodies or "property date" in bodies
    assert "cancelled" in bodies and "provisional" in bodies


# Scenario 7 (bonus) — Concentration judgment references share semantics
def test_concentration_judgment():
    text = " ".join(s["body"] for s in load_skills())
    assert "share_of_revenue" in text
    assert "block_share_of_revenue" in text
