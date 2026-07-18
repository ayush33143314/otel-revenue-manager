"""Phase 1 ETL property tests — covers published ETL scenarios 1-4.

Assumes a completed scrape -> transform -> load against DATABASE_URL.
"""
import hashlib


def q1(db, sql):
    with db.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()[0]


# Scenario 1 — Lookup row counts
def test_lookup_row_counts(db):
    expected = {
        "room_type_lookup": 3,
        "rate_plan_lookup": 8,
        "market_code_lookup": 10,
        "market_macro_group_history": 11,
        "channel_code_lookup": 4,
    }
    for table, count in expected.items():
        assert q1(db, f"select count(*) from public.{table}") == count, table


# Scenario 2 — Fact-table grain uniqueness
def test_grain_uniqueness(db):
    dupes = q1(
        db,
        """select count(*) from (
             select reservation_id, stay_date
             from public.reservations_hackathon
             group by 1, 2 having count(*) > 1) d""",
    )
    assert dupes == 0


# Scenario 3 — Manifest and DB reconciliation
def test_manifest_matches_db(db, scrape_manifest):
    db_count = q1(
        db, "select count(distinct reservation_id) from public.reservations_hackathon"
    )
    assert scrape_manifest["reservation_ids_count"] == db_count

    with db.cursor() as cur:
        cur.execute(
            "select distinct reservation_id from public.reservations_hackathon order by 1"
        )
        ids = [r[0] for r in cur.fetchall()]
    db_hash = hashlib.sha256("\n".join(ids).encode()).hexdigest()
    assert scrape_manifest["reservation_ids_sha256"] == db_hash


# Scenario 3 — total_stay_rows and reservation ids reconcile with LOAD_PROOF
def test_row_counts_match_load_proof(db, load_proof, scrape_manifest):
    total_stay_rows = q1(db, "select count(*) from public.reservations_hackathon")
    assert load_proof["row_counts"]["reservations_hackathon"] == total_stay_rows
    check = load_proof["scrape_manifest_check"]
    assert check["manifest_valid"] is True and not check["manifest_errors"]
    assert check["db_reservation_ids_count"] == scrape_manifest["reservation_ids_count"]


# Scenario 3 — LOAD_PROOF fingerprint matches DB and load_manifest
def test_load_proof_matches_db(db, load_proof):
    with db.cursor() as cur:
        cur.execute(
            """select reservation_id, stay_date::text, financial_status
               from public.reservations_hackathon
               order by reservation_id, stay_date, financial_status"""
        )
        lines = [f"{a}|{b}|{c}" for a, b, c in cur.fetchall()]
    pair_hash = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    assert load_proof["reservation_stay_status_sha256"] == pair_hash
    assert load_proof["load_manifest_row_hash"] == pair_hash

    manifest_revision = q1(
        db, "select dataset_revision from public.load_manifest order by load_id desc limit 1"
    )
    assert load_proof["dataset_revision"] == manifest_revision
    assert q1(db, "select count(*) from public.load_manifest") >= 1


# Scenario 4 (bonus) — Stay row expansion matches nights
def test_stay_row_expansion(db):
    with db.cursor() as cur:
        cur.execute(
            """select reservation_id, max(nights) as nights, count(*) as rows
               from public.reservations_hackathon
               group by reservation_id
               having max(nights) > 1"""
        )
        multi = cur.fetchall()
    assert multi, "expected at least one multi-night reservation"
    for rid, nights, rows in multi:
        assert nights == rows, f"{rid}: nights={nights} stay_rows={rows}"
