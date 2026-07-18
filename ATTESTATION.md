# ATTESTATION.md (Phase 0)

## Candidate

- Name: Ayush Tripathi
- Repository URL: (this repo)
- Date: 2026-07-17

---

## Comprehension prompts

### 1. Fact-table grain

In one sentence, what is the grain of `reservations_hackathon`?

> One row per reservation × stay_date: a reservation staying N nights produces
> N rows, each carrying `number_of_spaces` rooms for that night.

### 2. Revenue columns

Name the two revenue columns and when to use each.

> `daily_room_revenue_before_tax` — room revenue only; use for room-revenue and
> ADR/rate questions. `daily_total_revenue_before_tax` — room plus package /
> breakfast effects; use for "what is the month worth" total-revenue questions.
> Room ≤ total on every row.

### 3. Row vs reservation

Give one example question where counting rows would be wrong.

> "How many bookings do we have in July?" — a 3-night July reservation is 3
> stay rows but 1 booking; the answer is `count(distinct reservation_id)`,
> which in this dataset is roughly half the row count.

### 4. Schema fields

Is there an `otel_challenge_token` column in the official schema? If so, what is it used for?

> No. No such column exists in `schema.sql` — it appears nowhere in the seven
> official tables.

### 5. Default OTB filters

Which `reservation_status` and `financial_status` values are excluded from default OTB?

> `reservation_status = 'Cancelled'` and `financial_status = 'Provisional'`.
> Default OTB is Posted, non-cancelled.

### 6. Stay date vs property date

When can `property_date` differ from `stay_date`, and which field drives monthly OTB?

> On night-boundary / audit rows the hotel business date can differ from the
> calendar stay night (3 such rows in the current dataset). Monthly OTB always
> buckets on `stay_date`.

### 7. Point-in-time OTB

How does `as_of_utc` change which cancelled rows are included in `get_as_of_otb`?

> A cancelled reservation's rows are included when it was already booked
> (`create_datetime <= as_of_utc`) and not yet cancelled at that instant
> (`cancellation_datetime > as_of_utc`); once `as_of_utc` passes the
> cancellation moment the rows drop out.

### 8. Block vs transient

How does `is_block` affect a "group vs transient mix" question?

> `is_block = true` rows are group/block business and everything else is
> transient — the split is defined by this flag, not by market codes, so
> "group business" questions filter on it.

### 9. List pagination

How many reservations does the data site show per list page?

> 100 (currently 254 reservations across 3 pages).

### 10. Pagination completeness

How will you prove you did not miss the last list page during ETL?

> The scraper reads "Page X of Y" from the page indicator and walks every page;
> the collected distinct-ID count and their sha256 go into
> `etl/SCRAPE_MANIFEST.json` and must equal `count(distinct reservation_id)` in
> the DB and `total_reservations` on `/verify` (asserted by `etl/reconcile.py`
> and `tests/test_etl.py`).

### 11. Tool grain

For `get_otb_summary`, what is the difference between `row_count` and `reservation_count`?

> `row_count` counts stay rows (reservation × stay_date) in the month;
> `reservation_count` counts distinct `reservation_id`s — always ≤ row_count,
> and the only one that may be quoted as "bookings".

### 12. Human-in-the-loop

Why must `get_as_of_otb` be gated behind approval, and what goes wrong if it is not?

> It is a full point-in-time rebuild — the expensive query path — and its
> output is easy to misread (an as-of instant inside a cancellation wave makes
> pace look artificially strong). Ungated, the agent can spam costly rebuilds
> and present misleading pace deltas without the GM sanctioning the comparison
> instants.

### 13. Skill vs tool

Name one revenue-manager question that should load a **skill** but call **`get_segment_mix`**, not raw SQL.

> "Are we too dependent on OTA?" — the `ota-concentration` skill supplies the
> thresholds (≤20% healthy, >35% over-dependent) and actions, while the number
> itself comes from `get_segment_mix`'s `share_of_revenue`.

---

## ETL design (one line)

> Playwright walks the "Page X of Y" list (100/page) collecting IDs, drills
> into every detail page for fields + per-night stay rows, and truncate-and-
> reloads Postgres in one transaction (re-runnable, duplicate-free, resumable
> mid-scrape); anchor date 2026-07-17 reconciled 13/13 against `/verify`
> including `reservation_stay_status_sha256`. Note: detail pages publish raw
> channel rate codes absent from the 8-row published `rate_plan_lookup` (no
> alias mapping exists on the site), so the fact table keeps the source code
> verbatim and the lookup joins are LEFT joins — documented in ARCHITECTURE.md.
