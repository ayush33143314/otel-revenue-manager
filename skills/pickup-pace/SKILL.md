---
name: pickup-pace
description: "Judgment skill for booking pace: 'what changed in the last N days', pickup strength, and when slow pace demands action. Uses get_pickup_delta with thresholds and recommended actions."
---

# Pickup & pace — "what changed lately?"

Why the GM cares: pace is the early-warning system. Revenue is only recoverable
while there is still time to act, so the commercial value of a pickup read is
lead time — a week of weak pickup caught now can be stimulated at rate; caught
late it becomes a fire sale. Call `get_pickup_delta(booking_window_days=N,
future_stay_from=<today>)`. Default N=7 for a "what changed" briefing, N=28 for
trend context. The window is on **booking date** (create_datetime, London
midnight boundaries) — never stay date.

## Judgment thresholds
Compute **pace share** = window room nights ÷ total future OTB room nights (from
`get_otb_summary` over future months).
- **7-day pace share below 3%** of future OTB: slow-pace warning. Stimulate
  demand — open a promotional rate or targeted OTA visibility for the weakest
  stay months — *before* cutting BAR. Rate cuts on a slow book rarely buy
  volume; visibility does.
- **Pace share above 10%**: surge. Tighten — raise BAR or close discounted rate
  plans for the dates the surge concentrates in; check `by_segment` first so you
  do not close the segment producing the surge.
- **Any single segment above 50% of window revenue**: flag the dependence and
  name it — a pipeline resting on one source is fragile.

Report the window dates, new_reservations, new_room_nights and new_total_revenue,
then the judgment, then one concrete action — and quantify the money moving.

For "are we ahead or behind last year?", this is a pacing question — hand it to
the pace-analyst / pace-vs-last-year skill, which benchmarks against STLY
actuals rather than just measuring the recent window.
