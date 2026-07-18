#!/usr/bin/env bash
# Load the hosted database from the local scrape artifacts (or a fresh scrape).
#
# Usage:
#   DATABASE_URL=postgresql://... ./scripts/load_hosted_db.sh          # reuse today's scrape
#   DATABASE_URL=postgresql://... ./scripts/load_hosted_db.sh --scrape # scrape fresh first
#
# Applies schema + views, loads, reconciles against /verify, regenerates proofs.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${DATABASE_URL:?set DATABASE_URL to the hosted Postgres connection string}"
PY=.venv/bin/python

if [[ "${1:-}" == "--scrape" ]]; then
  echo "== extract (fresh scrape) =="
  time $PY etl/extract.py
fi

echo "== schema + views =="
$PY - <<'EOF'
import os, pathlib, psycopg
with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
    cur.execute(pathlib.Path("sql/schema.sql").read_text())
    cur.execute(pathlib.Path("sql/views.sql").read_text())
    conn.commit()
print("schema + views applied")
EOF

echo "== transform + load =="
$PY etl/transform.py
$PY etl/load.py

echo "== reconcile against /verify =="
$PY etl/reconcile.py

echo "== regenerate LOAD_PROOF =="
$PY scripts/compute_load_fingerprint.py \
  --database-url "$DATABASE_URL" \
  --manifest etl/SCRAPE_MANIFEST.json \
  --output etl/LOAD_PROOF.json
echo "done — commit etl/SCRAPE_MANIFEST.json and etl/LOAD_PROOF.json"
