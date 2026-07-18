#!/usr/bin/env python3
"""Transform: raw scraped JSON -> typed, schema-shaped records in data/clean/.

Enforces the fact-table grain (one row per reservation x stay_date), types every
column against sql/schema.sql, and derives the lookup tables from the reference
page. Validation failures raise — bad data never reaches the load step.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from datetime import date, datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"

DASH = {"", "—", "-", "–", "null", "None"}


def opt(value: str | None) -> str | None:
    return None if value is None or value.strip() in DASH else value.strip()


def as_date(value: str) -> str:
    return date.fromisoformat(value).isoformat()


def as_ts(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()


def as_bool(value: str) -> bool:
    if value not in ("true", "false"):
        raise ValueError(f"expected true/false, got {value!r}")
    return value == "true"


def as_money(value: str) -> str:
    cleaned = value.replace(",", "")
    if not re.fullmatch(r"-?\d+(\.\d{1,2})?", cleaned):
        raise ValueError(f"bad money value {value!r}")
    return cleaned


def transform_reservations() -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    with (RAW / "reservations.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            rid = rec["reservation_id"]
            f = rec["fields"]
            nights = int(f["nights"])
            if len(rec["stay_rows"]) != nights:
                raise ValueError(
                    f"{rid}: nights={nights} but {len(rec['stay_rows'])} stay rows"
                )
            for stay in rec["stay_rows"]:
                key = (rid, stay["stay_date"])
                if key in seen:
                    raise ValueError(f"duplicate grain key {key}")
                seen.add(key)
                if stay["financial_status"] not in ("Posted", "Provisional"):
                    raise ValueError(f"{rid}: bad financial_status {stay['financial_status']!r}")
                rows.append({
                    "reservation_id": rid,
                    "arrival_date": as_date(f["arrival_date"]),
                    "departure_date": as_date(f["departure_date"]),
                    "stay_date": as_date(stay["stay_date"]),
                    "property_date": as_date(stay["property_date"]),
                    "reservation_status": f["reservation_status"],
                    "financial_status": stay["financial_status"],
                    "create_datetime": as_ts(f["create_datetime"]),
                    "cancellation_datetime": (
                        as_ts(c) if (c := opt(f["cancellation_datetime"])) else None
                    ),
                    "guest_country": opt(f.get("guest_country")),
                    "is_block": as_bool(f["is_block"]),
                    "is_walk_in": as_bool(f["is_walk_in"]),
                    "number_of_spaces": int(f["number_of_spaces"]),
                    "space_type": f["space_type"],
                    "market_code": f["market_code"],
                    "channel_code": f["channel_code"],
                    "source_name": f["source_name"],
                    # UI label "commercial_rate_code" maps to rate_plan_code (changelog)
                    "rate_plan_code": f["rate_plan_code"],
                    "daily_room_revenue_before_tax": as_money(stay["daily_room_revenue_before_tax"]),
                    "daily_total_revenue_before_tax": as_money(stay["daily_total_revenue_before_tax"]),
                    "nights": nights,
                    "adr_room": as_money(f["adr_room"]),
                    "lead_time": int(f["lead_time"]),
                    "company_name": opt(f.get("company_name")),
                    "travel_agent_name": opt(f.get("travel_agent_name")),
                })
    return rows


def transform_reference() -> dict[str, list[dict]]:
    ref = json.loads((RAW / "reference.json").read_text())

    room_types = [{
        "space_type": r["space_type"],
        "room_class": r["room_class"],
        "display_name": r["display_name"],
        "number_of_rooms": int(r["number_of_rooms"]),
    } for r in ref["Room types"]]

    markets = [{
        "market_code": r["market_code"],
        "market_name": r["market_name"],
        "macro_group": r["macro_group"],
        "description": opt(r.get("description")),
    } for r in ref["Markets"]]

    channels = [{
        "channel_code": r["channel_code"],
        "channel_name": r["channel_name"],
        "channel_group": r["channel_group"],
    } for r in ref["Channels"]]

    rate_plans = [{
        "rate_plan_code": r["rate_plan_code"],
        "plan_family": r["plan_family"],
        "is_commissionable": as_bool(r["is_commissionable"]),
    } for r in ref["Rate plans"]]

    macro_history = [{
        "market_code": r["market_code"],
        "valid_from": as_date(r["valid_from"]),
        "valid_to": as_date(v) if (v := opt(r.get("valid_to"))) else None,
        "macro_group": r["macro_group"],
    } for r in ref["Macro history"]]

    return {
        "room_type_lookup": room_types,
        "market_code_lookup": markets,
        "channel_code_lookup": channels,
        "rate_plan_lookup": rate_plans,
        "market_macro_group_history": macro_history,
    }


def main() -> None:
    CLEAN.mkdir(parents=True, exist_ok=True)
    lookups = transform_reference()
    facts = transform_reservations()

    # Referential integrity before load: every FK value must exist in its lookup.
    fk_checks = {
        "space_type": {r["space_type"] for r in lookups["room_type_lookup"]},
        "market_code": {r["market_code"] for r in lookups["market_code_lookup"]},
        "channel_code": {r["channel_code"] for r in lookups["channel_code_lookup"]},
    }
    for row in facts:
        for col, valid in fk_checks.items():
            if row[col] not in valid:
                raise ValueError(f"{row['reservation_id']}: unknown {col}={row[col]!r}")

    # rate_plan_code is deliberately NOT FK-checked: the site publishes raw
    # channel-specific codes absent from the 8-row published lookup and offers
    # no alias mapping, so we keep source fidelity and only report the gap.
    known_plans = {r["rate_plan_code"] for r in lookups["rate_plan_lookup"]}
    unmapped = sorted({r["rate_plan_code"] for r in facts} - known_plans)
    if unmapped:
        print(f"note: {len(unmapped)} rate codes not in rate_plan_lookup: {unmapped}")

    for name, rows in lookups.items():
        (CLEAN / f"{name}.json").write_text(json.dumps(rows, indent=2))
        print(f"{name}: {len(rows)} rows")
    (CLEAN / "reservations_hackathon.json").write_text(json.dumps(facts))
    n_res = len({r["reservation_id"] for r in facts})
    print(f"reservations_hackathon: {len(facts)} stay rows across {n_res} reservations")


if __name__ == "__main__":
    sys.exit(main())
