# otel-revenue-agent

Revenue Manager Agent for a hotel GM — solution to the
[otel build challenge](https://github.com/otel-ai/otel-build-challenge).

## Layout

- `etl/` — Playwright scrape → transform → idempotent Postgres load →
  `/verify` reconciliation (+ `SCRAPE_MANIFEST.json`, `LOAD_PROOF.json`)
- `sql/` — schema + semantic views (the only surface tools query)
- `tools/` — the five required tools + `METRIC_DEFINITIONS.md`
- `skills/` — Deep Agents skill pack `otel-rm-v2` (8 runtime skills — 4 with
  judgment thresholds — plus the `CHALLENGE_SKILL.md` pack manifest)
- `app/` — `create_deep_agent()` assembly: subagent, HITL, memory, planning
- `tests/` — ETL / tool / skill / agent test suites (30 tests, no LLM calls)

## Run locally

```bash
docker compose up -d                       # empty Postgres with schema
python -m venv .venv && .venv/bin/pip install -e . --group dev
.venv/bin/playwright install chromium

.venv/bin/python etl/extract.py            # scrape the data site
.venv/bin/python etl/transform.py          # type + grain-check
.venv/bin/python etl/load.py               # truncate-and-reload + manifest
.venv/bin/python etl/reconcile.py          # 13-point /verify gate
docker exec -i hackathon-postgres psql -U hackathon -d hotel_hackathon < sql/views.sql
python scripts/compute_load_fingerprint.py --manifest etl/SCRAPE_MANIFEST.json --output etl/LOAD_PROOF.json

.venv/bin/python -m pytest                 # full suite
```

Scrape, load, and reconcile on the same calendar day — the dataset regenerates
from each day's anchor date.
