"""FastAPI server: basic-auth chat UI + SSE agent streaming + /health.

Endpoints:
  GET  /            — chat UI (static single page)
  GET  /health      — live DB fingerprint (unauthenticated: values are already
                      public in the repo's LOAD_PROOF.json)
  POST /api/chat    — {message, thread_id} -> SSE stream of agent events
  POST /api/resume  — {thread_id, decision} -> resume after a HITL interrupt

Every tool call and skill load streams to the UI as it happens (skill loads
are read_file calls under /skills/ — surfaced with their own event type).
"""
from __future__ import annotations

import app.config  # noqa: F401 — unpacks APP_SECRETS_JSON into env before any read

import hashlib
import json
import os
import pathlib
import secrets as pysecrets

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from langgraph.types import Command

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"

DATABASE_URL = os.environ["DATABASE_URL"]
BASIC_AUTH_USER = os.environ.get("BASIC_AUTH_USER", "")
BASIC_AUTH_PASS = os.environ.get("BASIC_AUTH_PASS", "")

app = FastAPI(title="Revenue Manager Agent")
security = HTTPBasic()

_agent = None
_agent_date = None
_persist = None


def get_agent():
    """Build the agent lazily; rebuild when the date rolls over so the
    system prompt's "today" (used to resolve bare month names) stays true."""
    global _agent, _agent_date, _persist
    import datetime
    today = datetime.date.today().isoformat()
    if _agent is None or _agent_date != today:
        from app.agent import build_agent
        if _persist is None:
            _persist = _persistence()
        checkpointer, store = _persist
        _agent = build_agent(checkpointer=checkpointer, store=store, today=today)
        _agent_date = today
    return _agent


_pool = None  # module-level: keeps checkpointer/store connections alive


def _persistence():
    """Postgres-backed checkpointer/store so conversations survive restarts."""
    global _pool
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from langgraph.store.postgres import PostgresStore
        from psycopg_pool import ConnectionPool

        _pool = ConnectionPool(
            DATABASE_URL, min_size=1, max_size=8,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )
        saver = PostgresSaver(_pool)
        saver.setup()
        store = PostgresStore(_pool)
        store.setup()
        return saver, store
    except Exception:  # noqa: BLE001 — fall back to in-memory (dev)
        return None, None


def check_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if not BASIC_AUTH_USER:  # auth not configured (local dev)
        return
    ok = pysecrets.compare_digest(credentials.username, BASIC_AUTH_USER) and (
        pysecrets.compare_digest(credentials.password, BASIC_AUTH_PASS)
    )
    if not ok:
        raise HTTPException(status_code=401, detail="Unauthorized",
                            headers={"WWW-Authenticate": "Basic"})


@app.get("/health")
def health():
    """Live DB fingerprint — must match the committed etl/LOAD_PROOF.json."""
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """select reservation_id, stay_date::text, financial_status
               from public.reservations_hackathon
               order by reservation_id, stay_date, financial_status"""
        )
        lines = [f"{a}|{b}|{c}" for a, b, c in cur.fetchall()]
        fingerprint = hashlib.sha256("\n".join(lines).encode()).hexdigest()
        cur.execute(
            """select dataset_revision, row_hash from public.load_manifest
               order by load_id desc limit 1"""
        )
        revision, row_hash = cur.fetchone() or (None, None)
        cur.execute(
            """select count(*) from public.reservations_hackathon
               where reservation_status <> 'Cancelled'
                 and financial_status = 'Posted'"""
        )
        posted_rows = cur.fetchone()[0]
    return {
        "db_fingerprint": fingerprint,
        "dataset_revision": revision,
        "row_hash": row_hash,
        "financial_status_posted_only_rows": posted_rows,
    }


# The shell is public (contains no data); every data endpoint stays behind
# basic auth. The shell renders a login screen that validates credentials
# against /api/thread. This is the brief's allowed "simple login screen".
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _stream_agent(payload, config):
    """Run the agent, yielding SSE events. Two LangGraph stream modes at once:
    'updates' → tool calls / skill loads / results / interrupt; 'messages' →
    the final answer token-by-token so it types out live. Token streaming works
    because the model has extended thinking disabled (see app.agent._model)."""
    agent = get_agent()
    final_text = ""
    seen_tool_calls: set[str] = set()
    try:
        for chunk in agent.stream(payload, config=config,
                                  stream_mode=["updates", "messages"],
                                  subgraphs=True):
            # subgraphs=True + multi-mode → (namespace, mode, data)
            if isinstance(chunk, tuple) and len(chunk) == 3:
                ns, mode, data = chunk
            elif isinstance(chunk, tuple) and len(chunk) == 2:
                ns, mode, data = (), chunk[0], chunk[1]
            else:
                continue

            if mode == "messages":
                # live answer tokens — top-level assistant text only (ns empty);
                # subagent chatter and empty tool-deciding turns are skipped
                msg = data[0] if isinstance(data, tuple) else data
                if not ns and type(msg).__name__ in ("AIMessageChunk", "AIMessage"):
                    delta = _text_of(getattr(msg, "content", ""))
                    if delta:
                        yield _sse({"type": "token", "text": delta})
                continue

            # mode == "updates"
            for node, out in (data or {}).items():
                if node == "__interrupt__":
                    for intr in out:
                        yield _sse({"type": "interrupt",
                                    "value": _jsonable(intr.value)})
                    return
                for msg in (out or {}).get("messages", []):
                    for tc in (getattr(msg, "tool_calls", None) or []):
                        if tc.get("id") in seen_tool_calls:
                            continue
                        seen_tool_calls.add(tc.get("id"))
                        ev = {"type": "tool_call", "name": tc["name"],
                              "args": tc["args"]}
                        path = str(tc["args"].get("path", "") or tc["args"].get("file_path", ""))
                        if tc["name"] == "read_file" and "/skills/" in path:
                            ev = {"type": "skill_load",
                                  "skill": path.split("/skills/")[-1].split("/")[0]}
                        yield _sse(ev)
                    if type(msg).__name__ == "ToolMessage":
                        yield _sse({"type": "tool_result",
                                    "name": getattr(msg, "name", ""),
                                    "preview": str(msg.content)[:400]})
                    elif getattr(msg, "content", None) and type(msg).__name__ == "AIMessage" and not ns:
                        final_text = _text_of(msg.content)  # authoritative full text
        # final: clean markdown render replaces the streamed tokens
        yield _sse({"type": "answer", "content": final_text})
    except Exception as exc:  # noqa: BLE001
        yield _sse({"type": "error", "message": str(exc)[:500]})
    yield _sse({"type": "done"})


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


def _jsonable(v):
    try:
        json.dumps(v)
        return v
    except TypeError:
        return str(v)


@app.post("/api/chat", dependencies=[Depends(check_auth)])
async def chat(request: Request):
    body = await request.json()
    thread_id = body.get("thread_id") or pysecrets.token_hex(8)
    config = {"configurable": {"thread_id": thread_id}}
    payload = {"messages": [{"role": "user", "content": body["message"]}]}
    return StreamingResponse(_stream_agent(payload, config),
                             media_type="text/event-stream",
                             headers={"X-Thread-Id": thread_id})


def _pending_decision_count(config) -> int:
    """How many tool calls are held at the current interrupt. The agent can
    request several gated calls at once (e.g. this-year AND last-year as-of for
    a forecast); the resume must supply one decision per held call, or LangGraph
    raises 'decisions != hanging tool calls'."""
    try:
        snapshot = get_agent().get_state(config)
        total = 0
        for task in getattr(snapshot, "tasks", []):
            for intr in getattr(task, "interrupts", []):
                value = getattr(intr, "value", None)
                reqs = value.get("action_requests") if isinstance(value, dict) else None
                total += len(reqs) if isinstance(reqs, list) and reqs else 1
        return max(total, 1)
    except Exception:  # noqa: BLE001 — fall back to a single decision
        return 1


@app.post("/api/resume", dependencies=[Depends(check_auth)])
async def resume(request: Request):
    body = await request.json()
    config = {"configurable": {"thread_id": body["thread_id"]}}
    decision = body.get("decision", "reject")
    # Apply the GM's one Approve/Deny to every held call in this interrupt.
    n = _pending_decision_count(config)
    cmd = Command(resume={"decisions": [{"type": decision} for _ in range(n)]})
    return StreamingResponse(_stream_agent(cmd, config),
                             media_type="text/event-stream")


@app.get("/api/thread", dependencies=[Depends(check_auth)])
def new_thread():
    return JSONResponse({"thread_id": pysecrets.token_hex(8)})
