# Testing
Testing my skills on different subjests


Hi , quick check on ORDERS_DAILY_REF. The order_side_dataset.sql output is at entity-tier level (date, RTM, country, material group, entity tier), while the design diagram is at customer + material level (order_date, mdm_id, mtrl_id, country_id, route_to_market).

I'm going ahead with the diagram structure, keeping the same source tables, filters and calculations, and only changing the final grouping to keep party_id (as mdm_id) and mfrg_mtrl_id (as mtrl_id). Total value, units and cost will match the original output; row count and order_count will be higher because of the extra detail.

Can you confirm that's the structure you want? Happy to switch to the tier-level version if not.
