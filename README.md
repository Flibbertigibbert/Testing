# Testing
Testing my skills on different subjests



Subject: RE: Wallaby tables – eap.ORDERS_DAILY_REF created

Hi all,

The orders table has been created in Wallaby and loaded:

• Table: wallaby.eap.ORDERS_DAILY_REF (server: tartarus)
• Source: order_side_dataset.sql (wallaby_price_forecasting repo), stored as-is from the query output
• Columns: order_create_date, rtm_cleaned, transaction_country, mtrl_mstr_mtrl_grp_cd, business_pch_level_3, entity_tier, order_count, quantity, list_price, discount_amount, net_amount_usd, final_total_cost, final_gross_margin, plus the 7 standard audit columns (is_active, is_deleted, is_indexed, create_date, update_date, create_user, update_user)
• Rows loaded: [row count], covering [first date] to [last date]; totals reconcile to the Hive output

Note: discount values are negative, as in the source data.

Shreenath, once you share the backlog and IDC market share files, I'll load them into wallaby.supplychain.BACKLOG_DAILY_REF and wallaby.idc.MARKET_SHARE_REF using the same standard.

Thanks,
Meshach
