#!/usr/bin/env python3
"""Reconcile the loaded database against the /verify targets captured at scrape time.

Exits non-zero on any mismatch. Run this after load.py; it is the Phase 1 gate.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://hackathon:hackathon@localhost:5432/hotel_hackathon"
)


def main() -> int:
    verify = json.loads((ROOT / "data" / "raw" / "verify.json").read_text())
    checks: list[tuple[str, object, object]] = []

    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        def one(sql: str):
            cur.execute(sql)
            return cur.fetchone()[0]

        checks.append((
            "total_reservations", verify["total_reservations"],
            one("select count(distinct reservation_id) from reservations_hackathon"),
        ))
        checks.append((
            "total_stay_rows", verify["total_stay_rows"],
            one("select count(*) from reservations_hackathon"),
        ))
        checks.append((
            "cancelled_reservations", verify["cancelled_reservations"],
            one("select count(distinct reservation_id) from reservations_hackathon "
                "where reservation_status = 'Cancelled'"),
        ))
        checks.append((
            "provisional_row_count", verify["provisional_row_count"],
            one("select count(*) from reservations_hackathon "
                "where financial_status = 'Provisional'"),
        ))
        checks.append((
            "property_date_mismatch_count", verify["property_date_mismatch_count"],
            one("select count(*) from reservations_hackathon "
                "where property_date <> stay_date"),
        ))
        checks.append((
            "rate_plan_lookup_rows", verify["rate_plan_lookup_rows"],
            one("select count(*) from rate_plan_lookup"),
        ))
        checks.append((
            "market_macro_group_history_rows", verify["market_macro_group_history_rows"],
            one("select count(*) from market_macro_group_history"),
        ))
        anchor = verify["anchor_date"]
        checks.append((
            "posted_stay_rows", verify["posted_stay_rows"],
            one("select count(*) from reservations_hackathon "
                "where reservation_status <> 'Cancelled' and financial_status = 'Posted' "
                f"and stay_date >= date '{anchor}'"),
        ))
        checks.append((
            "posted_otb_room_nights", verify["posted_otb_room_nights"],
            one("select coalesce(sum(number_of_spaces),0) from reservations_hackathon "
                "where reservation_status <> 'Cancelled' and financial_status = 'Posted' "
                f"and stay_date >= date '{anchor}'"),
        ))
        checks.append((
            "posted_room_revenue_before_tax", float(verify["posted_room_revenue_before_tax"]),
            float(one("select coalesce(sum(daily_room_revenue_before_tax),0) from reservations_hackathon "
                      "where reservation_status <> 'Cancelled' and financial_status = 'Posted' "
                      f"and stay_date >= date '{anchor}'")),
        ))
        checks.append((
            "posted_total_revenue_before_tax", float(verify["posted_total_revenue_before_tax"]),
            float(one("select coalesce(sum(daily_total_revenue_before_tax),0) from reservations_hackathon "
                      "where reservation_status <> 'Cancelled' and financial_status = 'Posted' "
                      f"and stay_date >= date '{anchor}'")),
        ))
        cur.execute(
            """select string_agg(line, E'\n' order by line) from (
                 select reservation_id || '|' || stay_date::text || '|' || financial_status as line
                 from reservations_hackathon) t"""
        )
        import hashlib
        payload = (cur.fetchone()[0] or "").encode("utf-8")
        checks.append((
            "reservation_stay_status_sha256", verify["reservation_stay_status_sha256"],
            hashlib.sha256(payload).hexdigest(),
        ))
        checks.append((
            "dataset_revision (load_manifest)", verify["dataset_revision"],
            one("select dataset_revision from load_manifest order by load_id desc limit 1"),
        ))

    failed = 0
    for name, expected, actual in checks:
        ok = expected == actual
        failed += (not ok)
        print(f"{'OK  ' if ok else 'FAIL'} {name}: expected={expected} actual={actual}")
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed "
          f"(anchor_date={verify['anchor_date']})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
