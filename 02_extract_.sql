/* =====================================================================
   ORDERS_DAILY_REF extract - run in DBeaver (Hive / Presto)
   Same source, filters and calculations as order_side_dataset.sql.
   Only the final step changes: it keeps customer and material detail
   and renames columns to match the table design.

   HOW TO USE
   1. Copy order_side_dataset.sql from the wallaby_price_forecasting repo.
   2. Keep lines 1-143 (everything up to and including cte3 and its comma).
   3. Delete lines 145-180 (the order_side CTE and the final SELECT).
   4. Paste everything below in their place.
   ===================================================================== */

order_daily AS (
    SELECT
        o.order_create_date                                             AS order_date,
        COALESCE(NULLIF(TRIM(o.end_customer_party_id), ''), 'UNKNOWN')  AS mdm_id,
        COALESCE(NULLIF(TRIM(o.mfrg_mtrl_id), ''), 'UNKNOWN')           AS mtrl_id,
        COALESCE(NULLIF(TRIM(o.transaction_country), ''), 'UNKNOWN')    AS country_id,
        COALESCE(NULLIF(TRIM(o.rtm_cleaned), ''), 'UNKNOWN')            AS route_to_market,
        SUM(o.net_usd_amount)                 AS order_value,
        SUM(o.quantity)                       AS order_units,
        COUNT(DISTINCT TRIM(o.order_number))  AS order_count,
        SUM(o.list_price)                     AS list_price_value,
        SUM(o.discount_amt)                   AS discount_value,
        SUM(o.final_total_cost)               AS cost_value,
        SUM(o.final_gross_margin)             AS margin_value
    FROM cte3 o
    INNER JOIN target_accounts ta                      -- same filter as the original
        ON TRIM(o.end_customer_party_id) = TRIM(ta.party_id)
    WHERE o.final_total_cost IS NOT NULL               -- same filter as the original
    GROUP BY 1, 2, 3, 4, 5
)

SELECT
    order_date, mdm_id, mtrl_id, country_id, route_to_market,
    order_value, order_units, order_count, list_price_value, discount_value,
    CASE WHEN list_price_value <> 0 THEN discount_value / list_price_value END AS discount_pct,
    cost_value, margin_value,
    CAST(NULL AS DOUBLE) AS quote_value,
    CAST(NULL AS BIGINT) AS quote_count,
    CAST(NULL AS DOUBLE) AS opportunity_value,
    CAST(NULL AS BIGINT) AS opportunity_count
FROM order_daily


/* ---------------------------------------------------------------------
   PROOF IT'S THE SAME DATA - run before exporting.
   Replace the final SELECT above with this; the money totals must equal
   SUM(net_amount_usd), SUM(quantity), SUM(final_total_cost) from the
   ORIGINAL query's output.

   SELECT COUNT(*), SUM(order_value), SUM(order_units), SUM(cost_value),
          MIN(order_date), MAX(order_date)
   FROM order_daily

   Primary key check - expect 0 rows:
   SELECT order_date, mdm_id, mtrl_id, country_id, route_to_market, COUNT(*)
   FROM order_daily GROUP BY 1, 2, 3, 4, 5 HAVING COUNT(*) > 1
   --------------------------------------------------------------------- */
