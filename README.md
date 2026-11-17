# Testing
Testing my skills on different subjests

select count(*) as seg_rows,
       count(distinct party_id) as customers,
       count(distinct concat(party_id, '|', business_pch_level_3)) as customer_business_pairs
from ps_olaaondemand.order_quote_opportunity_seg






select count(*) as product_rows, count(distinct mtrl_mstr_mtrl_id) as materials
from ps_olaaondemand.product_fact


select count(distinct o.order_number) as orders_in_scope,
       count(distinct case when q.quote_key is not null then o.order_number end) as orders_matched,
       sum(o.order_value) as value_in_scope,
       sum(case when q.quote_key is not null then o.order_value end) as value_matched
from ord o
left join (select distinct qq.quote_key
           from quote qq
           join opp p on p.opp_id = qq.opportunity_id_id) q
  on trim(q.quote_key) = trim(o.order_legacy_quote_number)



  select 'orders with more than 1 quote' as what, count(*) as n
from (select order_number from ord group by order_number
      having count(distinct order_legacy_quote_number) > 1) a
union all
select 'quotes with more than 1 order', count(*)
from (select quote_key from status_table where order_number is not null group by quote_key
      having count(distinct order_number) > 1) b
