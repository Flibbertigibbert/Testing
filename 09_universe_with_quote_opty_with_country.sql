/* =====================================================================
   universe_with_quote_opty.sql  -  WITH COUNTRY + RTM IN THE OUTPUT
   Run in DBeaver (Hive). Logic is unchanged from eClerx's version; the
   only edits are marked  -- [ADDED]  or  -- [GRAIN FILTER].

   Output now has 13 columns: the original 11 + country_code + go_to_mkt_rt_nm

   HOW TO SWITCH GRAIN - edit the TWO places marked [GRAIN FILTER]:
     US Indirect : country_code = 'US'                    / 'INDIRECT'
     US Direct   : country_code = 'US'                    / 'DIRECT'
     India       : country_code = 'IN'                    / 'INDIRECT'
     DACH        : country_code IN ('DE','AT','CH','LI')  / 'INDIRECT'
   Both places must use the same grain.
   ===================================================================== */

WITH target_accounts AS (
    SELECT
        party_id,
        global_entity_id,
        entity_tier
    FROM (
        SELECT
            party_id,
            global_entity_id,
            entity_tier,
            ROW_NUMBER() OVER (PARTITION BY party_id ORDER BY total_orders DESC) AS rn
        FROM ps_olaaondemand.order_quote_opportunity_seg
        WHERE business_pch_level_3 = 'Compute'
          AND (
                TRIM(entity_tier) LIKE '%Large%'
             OR TRIM(entity_tier) LIKE '%Whale%'
          )
    ) s
    WHERE rn = 1
),

opportunity AS (
    SELECT DISTINCT
        TRIM(a.hpe_opty_i_nm) AS hpe_opty_i_nm,
        a.crt_4_dt,
        a.cl_2_dt,
        ROUND(a.total_opportunity_value_close_dt_usd, 2) AS total_opportunity_value_close_dt_usd,
        b.country_code,                                          -- [ADDED]
        UPPER(TRIM(a.go_to_mkt_rt_nm)) AS go_to_mkt_rt_nm        -- [ADDED]
    FROM ps_olaaondemand.opty_dim a
    LEFT JOIN ps_olaaondemand.dataiku_country_dim b
        ON a.ctr_19_nm = b.country_name
    WHERE b.country_code = 'US'                                  -- [GRAIN FILTER] country
      AND UPPER(TRIM(a.go_to_mkt_rt_nm)) = 'DIRECT'              -- [GRAIN FILTER] RTM
),

quote AS (
    SELECT
        CONCAT(q.asset_quote_nr_cd, '-', q.asset_quote_vrsn_cd) AS quote_id_version,
        TRIM(q.opportunity_id_id) AS opportunity_id_id,
        b.mdm_id,
        CAST(q.creation_ts_cd AS DATE) AS creation_dt,
        SUM(q.lcl_xtnd_nt_amt_cd) AS quote_net_amount,
        CASE WHEN c.mtrl_mstr_mtrl_grp_cd = 'SERVER' THEN 'server' ELSE 'non-server' END AS server_tag
    FROM ps_olaaondemand.quotes_dim q
    LEFT JOIN (SELECT DISTINCT mdm_id FROM ps_olaaondemand.party_fact) b
        ON q.mdm_id = b.mdm_id
    LEFT JOIN (
        SELECT DISTINCT
            mtrl_mstr_mtrl_id,
            mtrl_mstr_sls_dvsn_cd,
            mtrl_mstr_mtrl_grp_cd,
            pch_level_3_desc
        FROM ps_olaaondemand.product_fact
    ) c
        ON q.product_id_id = c.mtrl_mstr_mtrl_id
    WHERE q.sls_qtn_vrsn_stts_cd_cd <> 'Cancelled'
      AND q.product_id_id NOT LIKE '%#%'
      AND c.pch_level_3_desc = 'Compute'
      AND c.mtrl_mstr_mtrl_grp_cd = 'SERVER'
    GROUP BY
        CONCAT(q.asset_quote_nr_cd, '-', q.asset_quote_vrsn_cd),
        TRIM(q.opportunity_id_id),
        b.mdm_id,
        CAST(q.creation_ts_cd AS DATE),
        CASE WHEN c.mtrl_mstr_mtrl_grp_cd = 'SERVER' THEN 'server' ELSE 'non-server' END
),

cte0 AS (
    SELECT
        o.order_number,
        o.end_customer_party_id,
        o.legacy_quote_number,
        o.opportunity_id_on_header,
        o.mfrg_mtrl_id,
        o.transaction_country,
        CAST(o.order_create_date AS DATE) AS order_create_date,
        SUM(o.source_quantity) AS quantity_dim,
        SUM(o.net_usd_currency_amount - o.dscnt_sls_ord_usd_curr_amt) AS list_price_order_dim,
        SUM(o.dscnt_sls_ord_usd_curr_amt) AS discount_order_dim,
        SUM(o.net_usd_currency_amount) AS net_order_dim
    FROM ps_olaaondemand.orders_dim o
    INNER JOIN ps_olaaondemand.product_fact pd
        ON o.mfrg_mtrl_id = pd.mtrl_mstr_mtrl_id
    WHERE o.transaction_country = 'US'                           -- [GRAIN FILTER] country (same as above)
      AND TRIM(o.rtm_cleaned) = 'DIRECT'                         -- [GRAIN FILTER] RTM (same as above)
      AND TRIM(pd.mtrl_mstr_mtrl_grp_cd) = 'SERVER'
      AND pd.pch_level_3_desc = 'Compute'
    GROUP BY
        o.order_number,
        o.end_customer_party_id,
        o.legacy_quote_number,
        o.opportunity_id_on_header,
        o.mfrg_mtrl_id,
        o.transaction_country,
        CAST(o.order_create_date AS DATE)
),

cte AS (
    SELECT
        o.order_number,
        o.end_customer_party_id,
        o.legacy_quote_number,
        o.opportunity_id_on_header,
        o.mfrg_mtrl_id,
        o.transaction_country,
        o.order_create_date,
        a.gross_margin_usd_amt,
        COALESCE(a.discount_usd_amt, o.discount_order_dim) AS discount_amt,
        COALESCE(a.net_itm_usd_amt, o.net_order_dim) AS net_usd_amount,
        COALESCE(a.net_itm_usd_amt - a.discount_usd_amt, o.list_price_order_dim) AS list_price,
        COALESCE(CASE WHEN a.ord_base_qty = 0 THEN o.quantity_dim ELSE a.ord_base_qty END, o.quantity_dim) AS quantity
    FROM cte0 o
    LEFT JOIN ps_olaaondemand.orders_amt_dim a
        ON TRIM(a.sls_ord_id) = TRIM(o.order_number)
       AND TRIM(a.mtrl_nr)    = TRIM(o.mfrg_mtrl_id)
    WHERE NOT REGEXP_LIKE(o.mfrg_mtrl_id, '#[A-Za-z0-9]+$')
),

cost_data AS (
    SELECT
        mtrl_nr,
        country_code,
        date AS effective_date,
        LEAD(date) OVER (
            PARTITION BY mtrl_nr, country_code
            ORDER BY date
        ) AS next_effective_date,
        amt_usd_per_unit
    FROM ps_olaaondemand.cost_dim
),

cte2 AS (
    SELECT DISTINCT
        o.order_number,
        o.end_customer_party_id,
        o.legacy_quote_number,
        o.opportunity_id_on_header,
        o.mfrg_mtrl_id,
        o.transaction_country,
        o.order_create_date,
        o.list_price,
        o.discount_amt,
        o.net_usd_amount,
        o.quantity,
        o.gross_margin_usd_amt,
        COALESCE(
            o.net_usd_amount - o.gross_margin_usd_amt,
            c.amt_usd_per_unit * o.quantity
        ) AS final_total_cost
    FROM cte o
    LEFT JOIN cost_data c
        ON TRIM(o.mfrg_mtrl_id) = TRIM(c.mtrl_nr)
       AND TRIM(o.transaction_country) = TRIM(c.country_code)
       AND o.order_create_date >= c.effective_date
       AND (
            o.order_create_date < c.next_effective_date
         OR c.next_effective_date IS NULL
       )
    WHERE o.quantity >= 0
      AND o.net_usd_amount >= 0
      AND o.list_price >= 0
),

cte3 AS (
    SELECT
        *,
        COALESCE(
            gross_margin_usd_amt,
            net_usd_amount - final_total_cost
        ) AS final_gross_margin
    FROM cte2
),

orders AS (
    SELECT
        order_create_date,
        end_customer_party_id,
        TRIM(legacy_quote_number)      AS legacy_quote_number,
        TRIM(opportunity_id_on_header) AS opportunity_id_on_header,
        SUM(net_usd_amount)            AS net_amount_usd
    FROM cte3
    WHERE final_total_cost IS NOT NULL
      AND TRIM(CAST(final_total_cost AS VARCHAR)) <> ''
    GROUP BY
        order_create_date,
        end_customer_party_id,
        TRIM(legacy_quote_number),
        TRIM(opportunity_id_on_header)
),

status_table AS (
    SELECT
        q.quote_id_version,
        q.opportunity_id_id,
        q.creation_dt,
        q.quote_net_amount,
        q.server_tag,
        o.order_create_date,
        o.net_amount_usd,
        ta.global_entity_id,
        ta.entity_tier
    FROM quote q
    INNER JOIN target_accounts ta
        ON TRIM(q.mdm_id) = TRIM(ta.party_id)
    LEFT JOIN orders o
        ON TRIM(q.quote_id_version) = TRIM(o.legacy_quote_number)
       AND TRIM(q.opportunity_id_id) = TRIM(o.opportunity_id_on_header)
),

final_table AS (
    SELECT
        op.hpe_opty_i_nm,
        op.crt_4_dt,
        op.cl_2_dt,
        op.total_opportunity_value_close_dt_usd,
        op.country_code,                                         -- [ADDED]
        op.go_to_mkt_rt_nm,                                      -- [ADDED]
        s.quote_id_version,
        s.opportunity_id_id,
        s.creation_dt,
        s.quote_net_amount,
        s.server_tag,
        s.order_create_date,
        s.net_amount_usd,
        s.global_entity_id,
        s.entity_tier
    FROM opportunity op
    LEFT JOIN status_table s
        ON op.hpe_opty_i_nm = s.opportunity_id_id
),

universe_with_quote_opty AS (
    SELECT
        hpe_opty_i_nm,
        crt_4_dt,
        cl_2_dt,
        total_opportunity_value_close_dt_usd,
        quote_id_version,
        creation_dt,
        quote_net_amount,
        order_create_date,
        net_amount_usd,
        global_entity_id,
        entity_tier,
        country_code,                                            -- [ADDED]
        go_to_mkt_rt_nm                                          -- [ADDED]
    FROM final_table
    WHERE entity_tier IS NOT NULL
      AND server_tag = 'server'
    GROUP BY
        hpe_opty_i_nm,
        crt_4_dt,
        cl_2_dt,
        total_opportunity_value_close_dt_usd,
        quote_id_version,
        creation_dt,
        quote_net_amount,
        order_create_date,
        net_amount_usd,
        global_entity_id,
        entity_tier,
        country_code,                                            -- [ADDED]
        go_to_mkt_rt_nm                                          -- [ADDED]
)

SELECT *
FROM universe_with_quote_opty
-- ORDER BY removed for the export (not needed, only slows the load)
