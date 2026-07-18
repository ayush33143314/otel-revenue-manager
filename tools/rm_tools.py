"""Required tool layer (Phase 2) — the five agent-facing revenue tools.

Every tool queries the semantic views (vw_stay_night_base, vw_segment_stay_night,
vw_stay_night_all), never reservations_hackathon directly, and none accepts SQL.
Grain vocabulary used throughout (see tools/METRIC_DEFINITIONS.md):

  stay row          — one reservation x stay_date row (the fact grain)
  reservation count — count(distinct reservation_id) within the filtered scope
  room nights       — sum(number_of_spaces) over stay rows in scope

Default OTB universe = vw_stay_night_base: reservation_status <> 'Cancelled'
AND financial_status = 'Posted'.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from psycopg_pool import ConnectionPool

DEFAULT_DATABASE_URL = "postgresql://hackathon:hackathon@localhost:5432/hotel_hackathon"
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)

LONDON = ZoneInfo("Europe/London")

# Lazy, process-wide connection pool. `check` recycles connections the server
# dropped while idle (RDS closes idle connections) instead of failing a query;
# created on first use so importing this module never opens a connection.
_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            min_size=1,
            max_size=8,
            check=ConnectionPool.check_connection,
            kwargs={"connect_timeout": 10},
            open=True,
        )
    return _pool


def _month_bounds(stay_month: str) -> tuple[str, str]:
    """Validate 'YYYY-MM' and return [first day, first day of next month)."""
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", stay_month):
        raise ValueError(f"stay_month must be YYYY-MM, got {stay_month!r}")
    year, month = int(stay_month[:4]), int(stay_month[5:7])
    start = f"{year:04d}-{month:02d}-01"
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    return start, f"{ny:04d}-{nm:02d}-01"


def _query(sql: str, params: tuple = ()) -> list[tuple]:
    with _get_pool().connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def get_otb_summary(stay_month: str, exclude_cancelled: bool = True) -> dict:
    """On-the-books summary for a calendar month of stay dates (YYYY-MM).

    Default universe: vw_stay_night_base (Posted, non-cancelled). With
    exclude_cancelled=False, cancelled rows are included but the universe stays
    Posted-only (provisional business is never silently mixed in).

    Grain: row_count counts STAY ROWS (reservation x stay_date) — it is NOT the
    reservation count. reservation_count is count(distinct reservation_id).
    room_nights is sum(number_of_spaces) over stay rows.

    Returns: stay_month, row_count, reservation_count, room_nights,
    room_revenue (sum daily_room_revenue_before_tax),
    total_revenue (sum daily_total_revenue_before_tax), exclude_cancelled.
    """
    start, end = _month_bounds(stay_month)
    view = "vw_stay_night_base" if exclude_cancelled else "vw_stay_night_all"
    extra = "" if exclude_cancelled else "and financial_status = 'Posted'"
    rows = _query(
        f"""select count(*),
                   count(distinct reservation_id),
                   coalesce(sum(number_of_spaces), 0),
                   coalesce(sum(daily_room_revenue_before_tax), 0),
                   coalesce(sum(daily_total_revenue_before_tax), 0)
            from public.{view}
            where stay_date >= %s and stay_date < %s {extra}""",
        (start, end),
    )
    row_count, reservation_count, room_nights, room_rev, total_rev = rows[0]
    return {
        "stay_month": stay_month,
        "row_count": row_count,
        "reservation_count": reservation_count,
        "room_nights": int(room_nights),
        "room_revenue": float(room_rev),
        "total_revenue": float(total_rev),
        "exclude_cancelled": exclude_cancelled,
    }


def get_segment_mix(stay_month: str, macro_group: str | None = None) -> dict:
    """Segment mix for a stay month using vw_segment_stay_night.

    Grain: room_nights = sum(number_of_spaces) over stay rows; revenue sums are
    at stay-row grain. Shares are fractions of ALL segments in scope (the
    filtered population is the denominator for every segment, stated in the
    payload as denominator_*). Universe: Posted, non-cancelled.

    macro_group filters on the stay-date-EFFECTIVE macro group (from
    market_macro_group_history), not the static lookup value.

    Returns: stay_month, macro_group, denominator_room_nights,
    denominator_total_revenue, segments[] each with market_code, market_name,
    macro_group, room_nights, total_revenue, share_of_room_nights (0-1),
    share_of_revenue (0-1).
    """
    start, end = _month_bounds(stay_month)
    filt, params = "", [start, end]
    if macro_group is not None:
        filt = "and effective_macro_group = %s"
        params.append(macro_group)
    rows = _query(
        f"""select market_code, market_name, effective_macro_group,
                   coalesce(sum(number_of_spaces), 0) as room_nights,
                   coalesce(sum(daily_total_revenue_before_tax), 0) as total_revenue
            from public.vw_segment_stay_night
            where stay_date >= %s and stay_date < %s {filt}
            group by 1, 2, 3
            order by total_revenue desc""",
        tuple(params),
    )
    total_rn = sum(int(r[3]) for r in rows)
    total_rev = sum(float(r[4]) for r in rows)
    segments = [
        {
            "market_code": code,
            "market_name": name,
            "macro_group": group,
            "room_nights": int(rn),
            "total_revenue": float(rev),
            "share_of_room_nights": (int(rn) / total_rn) if total_rn else 0.0,
            "share_of_revenue": (float(rev) / total_rev) if total_rev else 0.0,
        }
        for code, name, group, rn, rev in rows
    ]
    return {
        "stay_month": stay_month,
        "macro_group": macro_group,
        "denominator_room_nights": total_rn,
        "denominator_total_revenue": total_rev,
        "segments": segments,
    }


def get_pickup_delta(booking_window_days: int, future_stay_from: str) -> dict:
    """Booking pace / pickup for future stays.

    The booking window is defined on create_datetime — NOT stay_date:
    [Europe/London local midnight of (now - booking_window_days), now],
    compared in UTC. Only stay rows with stay_date >= future_stay_from count.
    Universe: Posted, non-cancelled (vw_stay_night_base semantics via
    vw_segment_stay_night for the segment split).

    Grain: new_reservations = count(distinct reservation_id) created in the
    window; new_room_nights = sum(number_of_spaces) over their qualifying stay
    rows; new_total_revenue at stay-row grain.

    Returns: booking_window_days, future_stay_from, window_start_utc,
    window_end_utc, new_reservations, new_room_nights, new_total_revenue,
    by_segment (top 5 by revenue: market_code, macro_group, room_nights,
    total_revenue).
    """
    if booking_window_days < 0:
        raise ValueError("booking_window_days must be >= 0")
    datetime.strptime(future_stay_from, "%Y-%m-%d")  # validate

    now_utc = datetime.now(timezone.utc)
    london_start = (now_utc.astimezone(LONDON) - timedelta(days=booking_window_days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    window_start_utc = london_start.astimezone(timezone.utc)

    rows = _query(
        """select count(distinct reservation_id),
                  coalesce(sum(number_of_spaces), 0),
                  coalesce(sum(daily_total_revenue_before_tax), 0)
           from public.vw_stay_night_base
           where create_datetime >= %s and create_datetime <= %s
             and stay_date >= %s""",
        (window_start_utc, now_utc, future_stay_from),
    )
    new_res, new_rn, new_rev = rows[0]

    seg_rows = _query(
        """select market_code, effective_macro_group,
                  coalesce(sum(number_of_spaces), 0),
                  coalesce(sum(daily_total_revenue_before_tax), 0) as rev
           from public.vw_segment_stay_night
           where create_datetime >= %s and create_datetime <= %s
             and stay_date >= %s
           group by 1, 2
           order by rev desc
           limit 5""",
        (window_start_utc, now_utc, future_stay_from),
    )
    return {
        "booking_window_days": booking_window_days,
        "future_stay_from": future_stay_from,
        "window_start_utc": window_start_utc.isoformat(),
        "window_end_utc": now_utc.isoformat(),
        "new_reservations": new_res,
        "new_room_nights": int(new_rn),
        "new_total_revenue": float(new_rev),
        "by_segment": [
            {
                "market_code": code,
                "macro_group": group,
                "room_nights": int(rn),
                "total_revenue": float(rev),
            }
            for code, group, rn, rev in seg_rows
        ],
    }


def get_as_of_otb(stay_month: str, as_of_utc: str) -> dict:
    """Point-in-time on-the-books for a stay month as known at as_of_utc.

    A stay row is included when it was already booked (create_datetime <=
    as_of_utc), was not yet cancelled at that instant (not Cancelled, OR
    cancellation_datetime > as_of_utc), and financial_status = 'Posted'
    (provisional excluded, matching the default OTB universe).

    Reads vw_stay_night_all because the current-state base view has already
    dropped rows that were live at as_of_utc but cancelled since.

    Grain: identical to get_otb_summary — row_count is stay rows,
    reservation_count is distinct reservations, room_nights is
    sum(number_of_spaces).

    Returns: same shape as get_otb_summary plus as_of_utc echo.
    """
    start, end = _month_bounds(stay_month)
    as_of = datetime.fromisoformat(as_of_utc.replace("Z", "+00:00"))
    rows = _query(
        """select count(*),
                  count(distinct reservation_id),
                  coalesce(sum(number_of_spaces), 0),
                  coalesce(sum(daily_room_revenue_before_tax), 0),
                  coalesce(sum(daily_total_revenue_before_tax), 0)
           from public.vw_stay_night_all
           where stay_date >= %s and stay_date < %s
             and create_datetime <= %s
             and (reservation_status <> 'Cancelled'
                  or cancellation_datetime > %s)
             and financial_status = 'Posted'""",
        (start, end, as_of, as_of),
    )
    row_count, reservation_count, room_nights, room_rev, total_rev = rows[0]
    return {
        "stay_month": stay_month,
        "as_of_utc": as_of_utc,
        "row_count": row_count,
        "reservation_count": reservation_count,
        "room_nights": int(room_nights),
        "room_revenue": float(room_rev),
        "total_revenue": float(total_rev),
    }


def get_block_vs_transient_mix(stay_month: str) -> dict:
    """Block vs transient mix for a stay month (vw_stay_night_base).

    Grain: room nights are sum(number_of_spaces) over stay rows; revenue at
    stay-row grain. Universe: Posted, non-cancelled. Block = is_block rows;
    transient = the rest. Shares are fractions of the month's total.

    top_companies: top 3 company_name by total_revenue (null company grouped
    as 'Transient'); top3_company_revenue_share is their combined share (0-1)
    of the month's total revenue.

    Returns: stay_month, block_room_nights, transient_room_nights,
    block_total_revenue, transient_total_revenue, block_share_of_room_nights,
    block_share_of_revenue, top_companies[], top3_company_revenue_share.
    """
    start, end = _month_bounds(stay_month)
    rows = _query(
        """select is_block,
                  coalesce(sum(number_of_spaces), 0),
                  coalesce(sum(daily_total_revenue_before_tax), 0)
           from public.vw_stay_night_base
           where stay_date >= %s and stay_date < %s
           group by is_block""",
        (start, end),
    )
    by_flag = {flag: (int(rn), float(rev)) for flag, rn, rev in rows}
    block_rn, block_rev = by_flag.get(True, (0, 0.0))
    trans_rn, trans_rev = by_flag.get(False, (0, 0.0))
    total_rn, total_rev = block_rn + trans_rn, block_rev + trans_rev

    company_rows = _query(
        """select coalesce(company_name, 'Transient') as company,
                  coalesce(sum(daily_total_revenue_before_tax), 0) as rev
           from public.vw_stay_night_base
           where stay_date >= %s and stay_date < %s
           group by 1
           order by rev desc
           limit 3""",
        (start, end),
    )
    top_companies = [
        {"company_name": name, "total_revenue": float(rev)} for name, rev in company_rows
    ]
    top3_rev = sum(c["total_revenue"] for c in top_companies)
    return {
        "stay_month": stay_month,
        "block_room_nights": block_rn,
        "transient_room_nights": trans_rn,
        "block_total_revenue": block_rev,
        "transient_total_revenue": trans_rev,
        "block_share_of_room_nights": (block_rn / total_rn) if total_rn else 0.0,
        "block_share_of_revenue": (block_rev / total_rev) if total_rev else 0.0,
        "top_companies": top_companies,
        "top3_company_revenue_share": (top3_rev / total_rev) if total_rev else 0.0,
    }


ALL_TOOLS = [
    get_otb_summary,
    get_segment_mix,
    get_pickup_delta,
    get_as_of_otb,
    get_block_vs_transient_mix,
]
