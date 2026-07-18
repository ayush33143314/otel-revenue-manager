# Metric definitions

**Stay rows vs reservations vs room nights.** The fact table is one row per
*reservation × stay_date*. A **stay row** is one such row. A **reservation** is
`count(distinct reservation_id)` within the filtered scope — never a row count.
**Room nights** are `sum(number_of_spaces)` over stay rows in scope: 2 rooms ×
3 nights = 1 reservation, 3 stay rows, 6 room nights.

**Default OTB.** Unless a question explicitly asks otherwise, on-the-books
excludes `reservation_status = 'Cancelled'` **and** `financial_status =
'Provisional'` (i.e. Posted, non-cancelled — the `vw_stay_night_base`
universe). The dataset is regenerated daily from an **anchor date** (scrape
day); all loads and proofs are reconciled against `/verify` for that anchor.

**Pickup windows.** A booking is "in the last N days" when its
`create_datetime` (stored UTC) falls in `[Europe/London local midnight of
(now − N days) → now]`, boundaries converted London → UTC. Pickup is always
defined on booking date, never stay date.

**Effective macro group.** `market_code_lookup.macro_group` is static;
`market_macro_group_history` re-classifies codes over time (e.g. PROM: Retail →
Leisure Group effective 2025-06-01). The **effective** macro group is the
history row whose `[valid_from, valid_to)` contains the **stay_date**, falling
back to the static value — this is what `vw_segment_stay_night` exposes and all
segment tools use.
