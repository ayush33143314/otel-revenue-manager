---
name: segment-mix
description: "Diagnose what is driving a month — segment, market and macro-group mix analysis with get_segment_mix. Explains how to read shares commercially, compare room-night vs revenue mix, and use effective macro groups."
---

# Segment mix — "what's driving <month>?"

Mix is where pricing and channel strategy come from: you cannot decide what to
raise, fence, or close until you know which segments are carrying the month and
whether they pay their way. Call `get_segment_mix(stay_month)` and read the two
share columns together — the comparison is the insight:

- **share_of_revenue > share_of_room_nights** → the segment books *above* the
  house blended rate (rate-accretive: typically BAR, corporate negotiated).
  These are the segments to protect and grow.
- **share_of_room_nights > share_of_revenue** → volume at *below-house* rates
  (dilutive: OTA promo, SMERF, event blocks). Volume is not value — if a
  dilutive segment is displacing an accretive one on the same dates, that is
  margin walking out the door, and worth quantifying for the GM.

A month is *driven* by its top 2–3 segments by revenue: name them with both
shares and the revenue figure, and say for each whether it is rate-led or
volume-led and what that implies commercially.

For macro questions ("how much is corporate?"), filter with `macro_group=`
rather than adding up codes yourself — the tool applies the **stay-date-effective**
macro group (PROM reclassified Retail → Leisure Group effective 2025-06-01), so
static groupings misfile mid-2025 stays.

For group-vs-transient phrasing specifically, use `get_block_vs_transient_mix`:
`is_block` defines group business, not the market code.
