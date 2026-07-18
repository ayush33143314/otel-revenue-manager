"""Phase 2 tool property tests — covers published tool scenarios 1-6 and 8-12.

Run against the ETL-loaded Postgres (DATABASE_URL). These are property tests:
they assert structural invariants, not exact totals, so they hold for any
anchor date.
"""
import inspect
import pathlib

import pytest

from tools.rm_tools import (
    ALL_TOOLS,
    get_as_of_otb,
    get_block_vs_transient_mix,
    get_otb_summary,
    get_pickup_delta,
    get_segment_mix,
)

JULY, AUG, SEP = "2025-07", "2025-08", "2025-09"


def q1(db, sql):
    with db.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()[0]


@pytest.fixture(scope="module")
def months_with_data(db):
    with db.cursor() as cur:
        cur.execute(
            """select to_char(stay_date, 'YYYY-MM') as m, count(*)
               from public.vw_stay_night_base group by 1 order by 2 desc"""
        )
        return [m for m, _ in cur.fetchall()]


# Scenario 1 — Grain inequality
def test_grain_inequality(months_with_data):
    s = get_otb_summary(months_with_data[0], exclude_cancelled=True)
    assert s["reservation_count"] < s["row_count"] or s["reservation_count"] == s["row_count"] == 0
    assert s["room_nights"] >= s["reservation_count"]
    assert s["room_revenue"] <= s["total_revenue"]


# Scenario 2 — Cancellation filter changes counts
def test_cancellation_filter_shrinks_counts(db):
    with db.cursor() as cur:
        cur.execute(
            """select to_char(stay_date, 'YYYY-MM') from public.vw_stay_night_all
               where reservation_status = 'Cancelled' and financial_status = 'Posted'
               group by 1 order by count(*) desc limit 1"""
        )
        row = cur.fetchone()
    assert row, "dataset should contain cancelled Posted stay rows"
    month = row[0]
    incl = get_otb_summary(month, exclude_cancelled=False)
    excl = get_otb_summary(month, exclude_cancelled=True)
    assert excl["row_count"] < incl["row_count"]
    assert excl["reservation_count"] <= incl["reservation_count"]


# Scenario 3 — Segment shares sum to one
def test_segment_shares_sum_to_one(months_with_data):
    mix = get_segment_mix(months_with_data[0], macro_group=None)
    assert mix["segments"], "expected segments in busiest month"
    assert abs(sum(s["share_of_room_nights"] for s in mix["segments"]) - 1.0) < 1e-6
    assert abs(sum(s["share_of_revenue"] for s in mix["segments"]) - 1.0) < 1e-6
    for s in mix["segments"]:
        assert 0.0 <= s["share_of_room_nights"] <= 1.0
        assert 0.0 <= s["share_of_revenue"] <= 1.0


# Scenario 4 — Macro group filter narrows universe
def test_macro_group_filter_narrows(months_with_data):
    month = months_with_data[0]
    unfiltered = get_segment_mix(month, macro_group=None)
    filtered = get_segment_mix(month, macro_group="Retail")
    assert filtered["denominator_room_nights"] <= unfiltered["denominator_room_nights"]
    for s in filtered["segments"]:
        assert s["macro_group"] == "Retail"


# Scenario 5 — Pickup uses booking date, not stay date
def test_pickup_uses_booking_window(db):
    # create_datetime defines the booking window; stay_date only gates which
    # future stay rows count (documented behaviour under test).
    anchor = q1(db, "select min(stay_date)::text from public.vw_stay_night_base")
    wide = get_pickup_delta(booking_window_days=3650, future_stay_from=anchor)
    narrow = get_pickup_delta(booking_window_days=1, future_stay_from=anchor)
    assert narrow["new_reservations"] <= wide["new_reservations"]
    assert wide["new_reservations"] > 0, "10y window from first stay date must catch bookings"
    later = get_pickup_delta(booking_window_days=3650, future_stay_from="2099-01-01")
    assert later["new_room_nights"] == 0  # no stays that far out


# Scenario 6 — OTA segment exists (loud ETL canary)
def test_ota_segment_present(months_with_data):
    for month in months_with_data:
        mix = get_segment_mix(month, macro_group=None)
        ota = [s for s in mix["segments"] if s["market_code"] == "OTA"]
        if ota:
            assert 0.0 < ota[0]["share_of_revenue"] < 1.0
            return
    pytest.fail("no OTA segment in any month — broken ETL or wrong dataset")


# Scenario 8 — Provisional excluded from default OTB
def test_provisional_excluded_by_default(db, load_proof):
    assert load_proof["aggregates"]["provisional_row_count"] > 0
    with db.cursor() as cur:
        cur.execute(
            """select to_char(stay_date, 'YYYY-MM') from public.vw_stay_night_all
               where financial_status = 'Provisional' and reservation_status <> 'Cancelled'
               group by 1 order by count(*) desc limit 1"""
        )
        month = cur.fetchone()[0]
    default_otb = get_otb_summary(month)["row_count"]
    cancelled_only_excluded = q1(
        db,
        f"""select count(*) from public.vw_stay_night_all
            where reservation_status <> 'Cancelled'
              and to_char(stay_date, 'YYYY-MM') = '{month}'""",
    )
    assert default_otb < cancelled_only_excluded


# Scenario 9 — As-of snapshot: bookings after as_of excluded, cancellations
# before as_of excluded, not-yet-cancelled included
def test_as_of_snapshot(db):
    def expected_rows(month, ts):
        # independent re-derivation of the as-of inclusion rule
        return q1(
            db,
            f"""select count(*) from public.vw_stay_night_all
                where to_char(stay_date, 'YYYY-MM') = '{month}'
                  and financial_status = 'Posted'
                  and create_datetime <= timestamptz '{ts}'
                  and (reservation_status <> 'Cancelled'
                       or cancellation_datetime > timestamptz '{ts}')""",
        )

    with db.cursor() as cur:
        cur.execute(
            """select to_char(stay_date, 'YYYY-MM'),
                      (min(cancellation_datetime) - interval '1 second')::text,
                      (max(cancellation_datetime) + interval '1 second')::text
               from public.vw_stay_night_all
               where cancellation_datetime is not null and financial_status = 'Posted'
               group by 1 order by count(*) desc limit 1"""
        )
        month, before_all, after_all = cur.fetchone()

    otb_before = get_as_of_otb(month, before_all)
    otb_after = get_as_of_otb(month, after_all)
    current = get_otb_summary(month)

    # Tool matches the independently derived inclusion rule at both instants.
    assert otb_before["row_count"] == expected_rows(month, before_all)
    assert otb_after["row_count"] == expected_rows(month, after_all)
    # As of after-all-cancellations, cancelled rows are all excluded and rows
    # created later are missing, so the snapshot is a subset of current OTB.
    assert otb_after["row_count"] <= current["row_count"]
    # A reservation cancelled later but already booked at before_all is
    # included then and gone after.
    cancelled_included_early = q1(
        db,
        f"""select count(*) from public.vw_stay_night_all
            where reservation_status = 'Cancelled' and financial_status = 'Posted'
              and create_datetime <= timestamptz '{before_all}'
              and to_char(stay_date, 'YYYY-MM') = '{month}'""",
    )
    if cancelled_included_early:
        assert otb_before["row_count"] >= cancelled_included_early


# Scenario 10 — Tools use stay_date, not property_date
def test_property_date_mismatch_documented(db, load_proof):
    mismatches = q1(
        db,
        "select count(*) from public.vw_stay_night_all where property_date <> stay_date",
    )
    assert load_proof["aggregates"]["property_date_mismatch_count"] == mismatches
    assert "stay_date" in inspect.getsource(get_otb_summary)


# Scenario 11 — Block vs transient mix reconciles
def test_block_transient_reconciles(months_with_data):
    month = months_with_data[0]
    mix = get_block_vs_transient_mix(month)
    otb = get_otb_summary(month)
    assert mix["block_room_nights"] + mix["transient_room_nights"] == otb["room_nights"]
    assert 0.0 <= mix["block_share_of_room_nights"] <= 1.0
    assert 0.0 <= mix["block_share_of_revenue"] <= 1.0
    assert mix["top3_company_revenue_share"] <= 1.0
    assert len(mix["top_companies"]) <= 3
    revenues = [c["total_revenue"] for c in mix["top_companies"]]
    assert revenues == sorted(revenues, reverse=True)


# Scenario 12 — Tool layer isolation
def test_tool_isolation_no_sql_params():
    assert len(ALL_TOOLS) == 5
    for tool in ALL_TOOLS:
        sig = inspect.signature(tool)
        for name in sig.parameters:
            assert "sql" not in name.lower(), f"{tool.__name__} exposes SQL param"
        doc = tool.__doc__ or ""
        assert "grain" in doc.lower(), f"{tool.__name__} docstring must state grain"


def test_tools_importable_without_server():
    # Importing tools.rm_tools in a fresh interpreter must not pull in the
    # agent app or any HTTP server (subprocess: immune to pytest-session
    # import pollution from test_agent.py).
    import subprocess
    import sys
    code = (
        "import sys, tools.rm_tools;"
        "bad = [m for m in sys.modules if m == 'app' or m.startswith(('app.', 'fastapi', 'uvicorn', 'langgraph_api'))];"
        "sys.exit(1 if bad else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=str(pathlib.Path(__file__).resolve().parents[1]))
    assert result.returncode == 0
