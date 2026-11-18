# Testing
Testing my skills on different subjests



select bucket, count(distinct order_number) as orders, sum(order_value) as total_value
from (
  select o.order_number, o.order_value,
         case
           when coalesce(trim(o.order_legacy_quote_number), '') = '' then '1 no quote number'
           when a.k is not null then '2 matched'
           when b.k is not null then '3 quote kept, opportunity not in opp'
           when d.k is not null then '4 quote exists, filtered out'
           when c.k is not null then '5 quote number matches, version differs'
           else '6 not found in quotes_dim'
         end as bucket
  from ord o
  left join (select distinct trim(q.quote_key) k
             from quote q join opp p on p.opp_id = q.opportunity_id_id) a
         on a.k = trim(o.order_legacy_quote_number)
  left join (select distinct trim(quote_key) k from quote) b
         on b.k = trim(o.order_legacy_quote_number)
  left join (select distinct trim(concat(asset_quote_nr_cd, '-', asset_quote_vrsn_cd)) k
             from ps_olaaondemand.quotes_dim) d
         on d.k = trim(o.order_legacy_quote_number)
  left join (select distinct trim(asset_quote_nr_cd) k
             from ps_olaaondemand.quotes_dim) c
         on c.k = trim(o.order_legacy_quote_number)
) t
group by bucket
order by bucket












select yr,
       count(distinct order_number) as orders,
       count(distinct case when matched = 1 then order_number end) as orders_matched,
       sum(order_value) as total_value,
       sum(case when matched = 1 then order_value end) as value_matched
from (
  select year(o.order_date_month) as yr, o.order_number, o.order_value,
         case when a.k is not null then 1 else 0 end as matched
  from ord o
  left join (select distinct trim(q.quote_key) k
             from quote q join opp p on p.opp_id = q.opportunity_id_id) a
         on a.k = trim(o.order_legacy_quote_number)
) t
group by yr
order by yr
