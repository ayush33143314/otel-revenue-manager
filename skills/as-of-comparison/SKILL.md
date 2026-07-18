---
name: as-of-comparison
description: "Point-in-time OTB rebuilds with get_as_of_otb: same-time-last-week/month comparisons, pace vs erosion decomposition, and why this tool requires GM approval before running."
---

# As-of comparisons — "how does July look vs last month?"

`get_as_of_otb(stay_month, as_of_utc)` reconstructs the book as it stood at a
past instant: bookings created by then, minus reservations already cancelled
by then, Posted only. Comparing it with today's `get_otb_summary` decomposes
movement into **pickup** (new bookings since) and **erosion** (cancellations
since) — the core of any "are we ahead or behind" answer.

## Approval gate
This tool is a full point-in-time rebuild — the expensive path — and its
results are easy to misread (an as-of instant mid-cancellation-wave can make
pace look artificially strong). It is gated behind GM approval, and the
approval is handled by the system: when you CALL `get_as_of_otb`, execution
pauses and the GM gets an Approve/Deny card. So **call the tool directly with
the as-of instant(s) you need — do NOT ask permission in prose first** ("shall
I proceed?" is redundant with the card and just adds a step). **Decide all the
instants you need up front and issue them as ONE batch of calls in a single
turn — one Approve covers the batch.** Sequential one-at-a-time rebuilds cost
the GM a click and ~30s each; a batch costs one click total.

## How to brief
- State both instants explicitly ("as of 1 June 00:00 UTC vs today").
- Quote the delta in room nights and total revenue, then split it: "+X from
  new bookings, −Y from cancellations".
- Use `stay_month` buckets by stay date, as always — never property date.
