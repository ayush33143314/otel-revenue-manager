---
name: block-concentration
description: "Judgment skill for group/block exposure: block_share_of_revenue and top-company concentration via get_block_vs_transient_mix, with wash-risk and displacement thresholds and recommended actions. Answers 'how much group business do we have?'."
---

# Block & company concentration — group exposure

Why the GM cares: group business is a double-edged commercial bet. It secures
volume early, but a block can *wash* (cancel or fall short of its contracted
rooms) close to arrival, and every group room held also *displaces* a
higher-rate transient booking you turned away. So the questions are: how exposed
is the month to a single group failing, and is the group business even worth the
transient it crowds out? Call `get_block_vs_transient_mix(stay_month)`; group is
`is_block`, never inferred from market codes.

## Thresholds and actions
- **block_share_of_revenue above 40%**: over-exposed to wash. One cancelled
  block holes the month. Verify contract cut-off and attrition clauses now, and
  hold transient BAR (do not discount) — the block base means low remaining
  supply, so transient scarcity is your friend.
- **top3_company_revenue_share above 30%**: name-level concentration. Name the
  companies, quantify what each represents in dollars, and have sales confirm
  their pickup before the GM trusts the month's number in a forecast.
- **Block room-night share exceeding block revenue share by over 10 points**:
  blocks are heavily rate-dilutive — you are giving away peak inventory cheap.
  Re-price future group quotes upward or fence group rates off peak dates.
- **block_share_of_revenue below 10%** with soft transient pace: the base is
  thin — recommend sales actively source small corporate/SMERF blocks to build a
  floor under the month.

Give the block/transient split in both room nights and revenue, then the top
companies, then the one action tied to the threshold that fired.
