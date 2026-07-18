---
name: otb-summary
description: "Answer 'what's on the books' questions — monthly revenue, room nights, reservation counts — using get_otb_summary. Covers how to brief totals commercially, which revenue column to quote, and the stay-row vs reservation trap."
---

# On-the-books briefing

Use `get_otb_summary(stay_month)` for any "what revenue is on the books", "how
big is <month>", or "how many bookings" question. Call it once per month in
scope; for "by month" questions, call it for each future month and present a
compact table.

## Make it commercial, not a read-out
A total on its own is not an answer — the GM already knows the hotel has
bookings. What they need is whether that total is good, and what to do. So a
strong OTB answer always pairs the number with a benchmark and a "so what":
lead with **total_revenue** and **room_nights**, then say how the month compares
to same-time-last-year (hand pacing to the pace-analyst / pace-vs-last-year
skill) and flag the earliest month that looks soft — a thin month spotted now is
revenue you can still rescue; spotted late it is a discount you are forced into.

## How to brief the numbers
- Quote **reservation_count** as "bookings". Never surface `row_count` to the
  GM — it is stay rows, an internal grain, and reads ~2× too high as "bookings".
- **ADR = room_revenue ÷ room_nights — ALWAYS room revenue, NEVER total
  revenue.** total_revenue ÷ room_nights is a different, higher number
  (it includes packages/breakfast); do not label it "ADR". If you quote ADR,
  it must come from `room_revenue`.
- Always state the universe ("posted, non-cancelled") and that OTB moves daily.

## Traps
- Monthly buckets are **stay_date** months: a guest arriving 31 Jul for 3 nights
  contributes 1 July stay row and 2 August rows.
- Do not inflate a month with cancelled or provisional rows. If the GM asks for
  "everything including tentative", call `get_otb_summary(month,
  exclude_cancelled=False)` and label the difference explicitly.
