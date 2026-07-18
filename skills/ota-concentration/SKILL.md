---
name: ota-concentration
description: "Judgment skill for OTA dependency: measures OTA share_of_revenue with get_segment_mix, applies concentration thresholds, and recommends channel-shift actions. Answers 'are we too dependent on OTA?'."
---

# OTA concentration — "are we too dependent on OTA?"

Why the GM cares: every OTA room costs 15–25% commission, and beyond the cash
leak, a book leaning on OTA means the hotel has ceded pricing power and the guest
relationship to a third party. The commercial goal is to use OTA to fill gaps,
not to run the house. Call `get_segment_mix(stay_month)` **without a
macro_group filter** and read the **OTA** row from the returned segments — take
its **share_of_revenue** and **share_of_room_nights**. Note: OTA is a *market
code*, not a macro group (its macro group is "Retail"), so never pass
`macro_group="OTA"` — that matches nothing and wastes a call. Valid macro_group
values are only Retail / MICE / Corporate / Leisure / Leisure Group.

## Thresholds and actions
- **OTA share_of_revenue at or below 20%**: healthy — OTA is filling gaps, not
  owning the book. No action.
- **Share between 20% and 35%**: watch zone. Recommend strengthening direct —
  a book-direct/member rate advantage of 5–10% under OTA BAR — and check whether
  OTA's room-night share exceeds its revenue share; if it does, OTA is also
  *dilutive*, which strengthens the case.
- **Share above 35%** in any month: over-dependent. Quantify the leak for the
  GM first: at ~15–25% commission, a 35% OTA month is surrendering roughly 5–9%
  of that month's revenue to commission — put that in dollars. Then, in order:
  (1) cap or close OTA availability on high-demand dates the month already fills
  without it, (2) fence direct offers so parity is not breached, (3) shift the
  freed inventory to direct and corporate.

## Caveats to state
- Concentration risk is month-specific: quote the worst month, not an average.
- A high OTA share in a distressed month is a symptom (weak base demand), not
  the disease — check pace and STLY before recommending OTA cuts there, or you
  will strip out the only demand you have.
