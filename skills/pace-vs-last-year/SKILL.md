---
name: pace-vs-last-year
description: "Judgment + forecasting skill: compares a stay month to last year and PROJECTS where it will land, using get_otb_summary and get_as_of_otb to reconstruct last year's booking curve. Answers 'are we ahead of last year?' and 'where will this month finish?'."
---

# Pacing & landing forecast — "where will this month finish vs last year?"

A number on the books now is only half the story. The GM needs to know where the
month will *land* and whether the gap to last year will close on its own or
needs action. Do this in two depths.

## Depth 1 — quick read (no approval needed)
Call `get_otb_summary("<future YYYY-MM>")` and `get_otb_summary("<same month
last year>")`. Report this year's current book against last year's final, but
**label it honestly**: this year is still booking, so a raw comparison to last
year's finished total understates us. Use this only as a directional flag.

## Depth 2 — the real forecast (needs GM approval)
Reconstruct last year at the SAME point in its booking cycle with
`get_as_of_otb("<same month last year>", "<about one year ago today>")`. **Call
this tool directly — do not ask "shall I proceed?" in prose first.** The tool is
gated: calling it pauses execution and shows the GM an Approve/Deny card, which
IS the approval step. Asking in words first just adds a redundant round-trip.
Then:
- **fill multiplier = last_year_final / last_year_at_that_point** — how much
  last year still grew from here to close.
- **forecast = this_year_on_the_books_now × fill multiplier.**
Compare the forecast (not the raw gap) to last year's final. This is the number
the GM acts on, and it is why the tool is gated — a forecast drives pricing
decisions, so a human approves it.

## Thresholds and actions (apply to the FORECAST)
- **Forecast below last year by over 10%**: soft landing, and if the fill
  multiplier is near 1.0 the gap will NOT close on its own — pickup won't save
  it. Recommend stimulating now (open a promotional fence, targeted visibility
  on the weak dates) and re-forecasting down so the GM is not surprised. Do not
  broad-discount a soft book; it rarely responds to price alone.
- **Forecast within 10% of last year**: on track. Hold rate, watch pickup weekly.
- **Forecast above last year by over 10%**: demand strength. Raise BAR on the
  strongest dates and close the lowest-margin OTA and promo rate plans.

Always quantify the projected gap in dollars, not just percent. State the
assumption ("assuming this year fills like last year's curve") and flag any
one-off group last year that distorts the comparison.

## Self-check before you commit the forecast
A forecast is the number the GM acts on, so stress-test your own reasoning once
before answering (do not re-run the whole analysis): Is the month resolved to
the FUTURE year, not last year's block? Did you benchmark against STLY at the
SAME lead time (get_as_of_otb), not last year's finished total? Is the stated
confidence consistent with the shape of the gap (group volume books in lumps →
base case with upside; transient → firmer floor)? Are the load-bearing numbers
internally consistent (room-night vs revenue variance, ADR direction)? If you
quote ADR, is it room_revenue ÷ room_nights (NEVER total_revenue ÷ room_nights)?
Fix any that fail, then commit.

## Calibrate the forecast to the shape of the gap
Do not state a confident "won't close" landing and a "but a group could book"
hedge as two separate points — resolve them into one calibrated headline. Check
what the gap is made of (use the block/company mix): a gap concentrated in
missing GROUP/block volume has high upside variance because groups book in
lumps — one block re-booking can close most of it, so present the forecast as a
base case with real upside, not a floor. A gap in TRANSIENT volume is far more
reliable — few large late swings — so the "won't close on its own" call is firm.
Say which kind this is, and let it set how hard you commit to the number.
