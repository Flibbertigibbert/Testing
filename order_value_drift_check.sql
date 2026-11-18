-- =====================================================================================
-- ORDER VALUE DRIFT CHECK  (Hive, run in DBeaver)
-- Why do old months keep growing between extracts (30 Oct -> 10 Nov -> 18 Nov)?
--
-- HOW TO RUN
--   * Run ONE block at a time: highlight it, Ctrl+Enter.
--   * Part A runs as it is.
--   * Part B needs the eClerx CTEs: copy their script from "with cte0 as (" down to the
--     closing bracket of "global_entity", delete their "--overall" SELECT, paste ONE
--     Part B block underneath, and run the whole thing.
--   * Export each result to CSV with today's date in the file name. Run the same blocks
--     again on a later day: the block whose numbers move is where the change is.
--   * If the amounts table has a different name, replace ps_olaaondemand.orders_amt_dim.
-- =====================================================================================


-- =====================================================================================
-- PART A: checks that run as they are
-- =====================================================================================

-- A1. Is the "backup" really a frozen copy?
--     Read: Table Type (VIRTUAL_VIEW = not a copy), Location (same folder as the live
--     table = same data), CreateTime / transient_lastDdlTime (recent = rebuilt),
--     numRows / totalSize / numFiles (write down, compare tomorrow).
DESCRIBE FORMATTED ps_olaaondemand.orders_amt_dim_v2;
SHOW CREATE TABLE ps_olaaondemand.orders_amt_dim_v2;
DESCRIBE FORMATTED ps_olaaondemand.orders_amt_dim;
DESCRIBE FORMATTED ps_olaaondemand.order_quote_opportunity_seg;


-- A2. MOST LIKELY CAUSE: the segment table has many rows per customer.
--     eClerx join it on party_id only, so every order of a customer is counted once
--     per segment row. When new quotes/opportunities land in that table, every OLD
--     order of that customer is counted again -> old months grow on every refresh.
--     Read: avg_rows_per_customer above 1 = orders are being multiplied.
SELECT COUNT(*)                                AS customers,
       SUM(n)                                  AS seg_rows,
       ROUND(AVG(n), 1)                        AS avg_rows_per_customer,
       MAX(n)                                  AS max_rows_per_customer,
       SUM(CASE WHEN n > 1 THEN 1 ELSE 0 END)  AS customers_with_more_than_1_row
FROM (
    SELECT party_id, COUNT(*) AS n
    FROM ps_olaaondemand.order_quote_opportunity_seg
    WHERE business_pch_level_3 = 'Compute'
      AND (TRIM(entity_tier) LIKE '%Large%' OR TRIM(entity_tier) LIKE '%Whale%')
    GROUP BY party_id
) t;


-- A3. The other joins can multiply rows too. For each: keys with more than 1 row.
-- A3a. product_fact: rows per material
SELECT COUNT(*) AS materials, SUM(n) AS n_rows, MAX(n) AS max_rows_per_material,
       SUM(CASE WHEN n > 1 THEN 1 ELSE 0 END) AS materials_with_more_than_1_row
FROM (SELECT mtrl_mstr_mtrl_id, COUNT(*) AS n
      FROM ps_olaaondemand.product_fact
      GROUP BY mtrl_mstr_mtrl_id) t;

-- A3b. party_fact: vertical rows per customer (their join uses DISTINCT mdm_id, indy_vtcl_nm)
SELECT COUNT(*) AS customers, SUM(n) AS n_rows, MAX(n) AS max_rows_per_customer,
       SUM(CASE WHEN n > 1 THEN 1 ELSE 0 END) AS customers_with_more_than_1_row
FROM (SELECT TRIM(mdm_id) AS k, COUNT(*) AS n
      FROM (SELECT DISTINCT mdm_id, indy_vtcl_nm FROM ps_olaaondemand.party_fact) d
      GROUP BY TRIM(mdm_id)) t;

-- A3c. cost_dim: rows per material + country + effective date (US only)
SELECT COUNT(*) AS keys_, SUM(n) AS n_rows, MAX(n) AS max_rows_per_key,
       SUM(CASE WHEN n > 1 THEN 1 ELSE 0 END) AS keys_with_more_than_1_row
FROM (SELECT TRIM(mtrl_nr) AS m, `date` AS d, COUNT(*) AS n
      FROM ps_olaaondemand.cost_dim
      WHERE TRIM(country_code) = 'US'
      GROUP BY TRIM(mtrl_nr), `date`) t;

-- A3d. Amounts table and its backup: identical copies of the same line
--      (a refresh that APPENDS instead of OVERWRITES leaves extra copies)
SELECT tbl, distinct_lines, n_rows, n_rows - distinct_lines AS extra_identical_copies
FROM (
    SELECT 'orders_amt_dim' AS tbl, COUNT(*) AS distinct_lines, SUM(n) AS n_rows
    FROM (SELECT sls_ord_id, mtrl_nr, net_itm_usd_amt, discount_usd_amt, ord_base_qty, gross_margin_usd_amt, COUNT(*) AS n
          FROM ps_olaaondemand.orders_amt_dim
          GROUP BY sls_ord_id, mtrl_nr, net_itm_usd_amt, discount_usd_amt, ord_base_qty, gross_margin_usd_amt) a
    UNION ALL
    SELECT 'orders_amt_dim_v2', COUNT(*), SUM(n)
    FROM (SELECT sls_ord_id, mtrl_nr, net_itm_usd_amt, discount_usd_amt, ord_base_qty, gross_margin_usd_amt, COUNT(*) AS n
          FROM ps_olaaondemand.orders_amt_dim_v2
          GROUP BY sls_ord_id, mtrl_nr, net_itm_usd_amt, discount_usd_amt, ord_base_qty, gross_margin_usd_amt) b
) z;


-- A4. Which files sit behind the backup? (Hive's built-in INPUT__FILE__NAME column)
--     Same folder as the live table = the backup is the live data.
--     New files tomorrow = the table is being added to.
SELECT INPUT__FILE__NAME AS file_path, COUNT(*) AS n_rows
FROM ps_olaaondemand.orders_amt_dim_v2
GROUP BY INPUT__FILE__NAME
ORDER BY file_path;

SELECT INPUT__FILE__NAME AS file_path, COUNT(*) AS n_rows
FROM ps_olaaondemand.orders_amt_dim
GROUP BY INPUT__FILE__NAME
ORDER BY file_path;


-- =====================================================================================
-- PART B: paste ONE block under the eClerx CTEs (see HOW TO RUN)
-- =====================================================================================

-- B1. Total after each step of their query, same window as the eClerx sheet
--     (Nov 2021 to Sep 2026). The step where net_usd jumps but n_orders does not is
--     where rows are being multiplied.
--     Read: step 5 much bigger than step 6 -> the segment join multiplies orders.
--           step 2 much bigger than step 1 -> the amounts table has duplicates (see A3d).
--           step 1 itself changes from day to day -> orders_dim really is restated.
SELECT stage, n_rows, n_orders, net_usd
FROM (
    SELECT '1 orders_dim + product + party (cte0)' AS stage,
           COUNT(*) AS n_rows, COUNT(DISTINCT order_number) AS n_orders,
           CAST(SUM(net_order_dim) AS DOUBLE) AS net_usd
    FROM cte0
    WHERE TO_DATE(order_create_date) BETWEEN '2021-11-01' AND '2026-09-30'
    UNION ALL
    SELECT '2 + amounts table (cte)',
           COUNT(*), COUNT(DISTINCT order_number), CAST(SUM(net_usd_amount) AS DOUBLE)
    FROM cte
    WHERE TO_DATE(order_create_date) BETWEEN '2021-11-01' AND '2026-09-30'
    UNION ALL
    SELECT '3 + cost table, negatives removed (cte2)',
           COUNT(*), COUNT(DISTINCT order_number), CAST(SUM(net_usd_amount) AS DOUBLE)
    FROM cte2
    WHERE order_create_date BETWEEN DATE '2021-11-01' AND DATE '2026-09-30'
    UNION ALL
    SELECT '4 grouped per order (orders)',
           COUNT(*), COUNT(DISTINCT order_number), CAST(SUM(net_amount_usd) AS DOUBLE)
    FROM orders
    WHERE order_create_date BETWEEN DATE '2021-11-01' AND DATE '2026-09-30'
    UNION ALL
    SELECT '5 + segment join, as eClerx sum it',
           COUNT(*), COUNT(DISTINCT o.order_number), CAST(SUM(o.net_amount_usd) AS DOUBLE)
    FROM orders o
    JOIN ps_olaaondemand.order_quote_opportunity_seg s ON s.party_id = o.end_customer_party_id
    WHERE s.business_pch_level_3 = 'Compute'
      AND (TRIM(s.entity_tier) LIKE '%Large%' OR TRIM(s.entity_tier) LIKE '%Whale%')
      AND o.order_create_date BETWEEN DATE '2021-11-01' AND DATE '2026-09-30'
    UNION ALL
    SELECT '6 + segment, one row per customer',
           COUNT(*), COUNT(DISTINCT o.order_number), CAST(SUM(o.net_amount_usd) AS DOUBLE)
    FROM orders o
    JOIN (SELECT DISTINCT party_id
          FROM ps_olaaondemand.order_quote_opportunity_seg
          WHERE business_pch_level_3 = 'Compute'
            AND (TRIM(entity_tier) LIKE '%Large%' OR TRIM(entity_tier) LIKE '%Whale%')) s
      ON s.party_id = o.end_customer_party_id
    WHERE o.order_create_date BETWEEN DATE '2021-11-01' AND DATE '2026-09-30'
) z
ORDER BY stage;


-- B2. Month by month: counted the eClerx way vs each order counted once.
--     net_eclerx_way should match the "18th Nov" column of their sheet.
--     times_counted above 1 = orders multiplied. Save this today and re-run later:
--     if net_counted_once stays put while net_eclerx_way grows, the cause is proven.
SELECT x.mth,
       x.net_eclerx_way,
       y.net_counted_once,
       ROUND(x.net_eclerx_way / y.net_counted_once, 2) AS times_counted
FROM (
    SELECT SUBSTR(CAST(o.order_create_date AS STRING), 1, 7) AS mth,
           CAST(SUM(o.net_amount_usd) AS DOUBLE) AS net_eclerx_way
    FROM orders o
    JOIN ps_olaaondemand.order_quote_opportunity_seg s ON s.party_id = o.end_customer_party_id
    WHERE s.business_pch_level_3 = 'Compute'
      AND (TRIM(s.entity_tier) LIKE '%Large%' OR TRIM(s.entity_tier) LIKE '%Whale%')
    GROUP BY SUBSTR(CAST(o.order_create_date AS STRING), 1, 7)
) x
JOIN (
    SELECT SUBSTR(CAST(o.order_create_date AS STRING), 1, 7) AS mth,
           CAST(SUM(o.net_amount_usd) AS DOUBLE) AS net_counted_once
    FROM orders o
    JOIN (SELECT DISTINCT party_id
          FROM ps_olaaondemand.order_quote_opportunity_seg
          WHERE business_pch_level_3 = 'Compute'
            AND (TRIM(entity_tier) LIKE '%Large%' OR TRIM(entity_tier) LIKE '%Whale%')) s
      ON s.party_id = o.end_customer_party_id
    GROUP BY SUBSTR(CAST(o.order_create_date AS STRING), 1, 7)
) y ON x.mth = y.mth
WHERE x.mth BETWEEN '2021-11' AND '2026-09'
ORDER BY x.mth;


-- B3. One month in detail: Jan 2022 (0.71M on 10 Nov, 3.06M on 18 Nov).
--     Which customers drive it, and how many segment rows each one has.
--     net_as_counted = net_counted_once x seg_rows (what ends up in the eClerx total).
SELECT o.end_customer_party_id,
       COUNT(DISTINCT o.order_number)                    AS n_orders,
       CAST(SUM(o.net_amount_usd) AS DOUBLE)             AS net_counted_once,
       s.seg_rows,
       CAST(SUM(o.net_amount_usd) * s.seg_rows AS DOUBLE) AS net_as_counted
FROM orders o
JOIN (SELECT party_id, COUNT(*) AS seg_rows
      FROM ps_olaaondemand.order_quote_opportunity_seg
      WHERE business_pch_level_3 = 'Compute'
        AND (TRIM(entity_tier) LIKE '%Large%' OR TRIM(entity_tier) LIKE '%Whale%')
      GROUP BY party_id) s
  ON s.party_id = o.end_customer_party_id
WHERE o.order_create_date >= DATE '2022-01-01'
  AND o.order_create_date <  DATE '2022-02-01'
GROUP BY o.end_customer_party_id, s.seg_rows
ORDER BY net_as_counted DESC
LIMIT 20;
