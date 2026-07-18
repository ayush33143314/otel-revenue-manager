-- Semantic views: the only surface agent-facing tools may query.
-- vw_stay_night_base / vw_segment_stay_night follow sql/VIEWS.example.sql from the brief;
-- vw_stay_night_all is ours, for point-in-time (as-of) rebuilds — see bottom.

create or replace view public.vw_stay_night_base as
select
  r.*
from public.reservations_hackathon r
where r.reservation_status <> 'Cancelled'
  and r.financial_status = 'Posted';

create or replace view public.vw_segment_stay_night as
select
  b.*,
  coalesce(h.macro_group, m.macro_group) as effective_macro_group,
  m.market_name
from public.vw_stay_night_base b
join public.market_code_lookup m on m.market_code = b.market_code
left join lateral (
  select h.macro_group
  from public.market_macro_group_history h
  where h.market_code = b.market_code
    and b.stay_date >= h.valid_from
    and (h.valid_to is null or b.stay_date < h.valid_to)
  order by h.valid_from desc
  limit 1
) h on true;

-- Unfiltered stay-night view for point-in-time (as-of) rebuilds and explicit
-- cancellation questions: get_as_of_otb must see rows that were cancelled
-- AFTER the as-of instant, which vw_stay_night_base excludes. Exists so tools
-- never query reservations_hackathon directly; status filters are applied in
-- the tool layer with documented semantics.
create or replace view public.vw_stay_night_all as
select r.* from public.reservations_hackathon r;
