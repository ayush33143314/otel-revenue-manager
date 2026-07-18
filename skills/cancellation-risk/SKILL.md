---
name: cancellation-risk
description: "Judgment skill for cancellation analysis: quantify cancelled business with get_otb_summary (exclude_cancelled=False vs True) and get_as_of_otb, apply cancellation-rate thresholds, and recommend overbooking or policy actions."
---

# Cancellations — "how much business was cancelled?"

Why the GM cares: cancellations are not a loss against the forecast — the live
book already excludes them — but a *high cancellation rate* is a commercial
signal. It means the hotel is holding inventory for bookings that evaporate,
turning away other demand in the meantime, and it points to either loose policy
or speculative booking behaviour worth pricing against.

**Method.** For "how much was cancelled in <month>", call
`get_otb_summary(month, exclude_cancelled=False)` and `get_otb_summary(month,
exclude_cancelled=True)`; the difference is the cancelled Posted business for
that stay month, in room nights and revenue. State clearly that live OTB already
excludes it — cancelled revenue is book that never materialised, not money lost
against today's forecast (the single most common GM misreading). For erosion
analysis, compare a point-in-time rebuild (`get_as_of_otb`, GM-approved) against
today's book to split the gap into new pickup vs cancellations.

## Thresholds and actions
- **Cancelled share above 25%** (cancelled ÷ (live + cancelled) room nights):
  recommend reviewing the cancellation policy on flexible rate plans and adding
  a modest overbooking buffer — start at about half the cancelled share on the
  affected dates — so evaporated rooms are re-sold rather than left empty.
- **Cancelled share above 40%** concentrated in one segment or company: treat as
  speculative booking. Recommend deposits or non-refundable fences for that
  segment before touching house-wide policy.

Never present cancelled and live revenue as one number without labelling both.
