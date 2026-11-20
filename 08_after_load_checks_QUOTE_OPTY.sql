/* Run in SSMS ONLY AFTER both DBeaver exports have finished.
   Compare with the same totals from each script in DBeaver
   (remove the final ORDER BY and semicolon, then wrap):
     SELECT COUNT(*), SUM(net_amount_usd) FROM ( <script> ) t
   Expected rows (Shreenath's email): ORDER_QUOTE_OPTY ~14k, UNIVERSE_QUOTE_OPTY ~221k */

USE wallaby;
GO

SELECT 'ORDER_QUOTE_OPTY'      AS tbl, COUNT(*) AS row_count,
       SUM(net_amount_usd)     AS total_net_amount_usd,
       MIN(order_create_date)  AS first_date, MAX(order_create_date) AS last_date
FROM [eap].[ORDER_QUOTE_OPTY]
UNION ALL
SELECT 'UNIVERSE_QUOTE_OPTY', COUNT(*),
       SUM(net_amount_usd),
       MIN(crt_4_dt), MAX(crt_4_dt)
FROM [eap].[UNIVERSE_QUOTE_OPTY];

-- Audit columns filled? Expect 0 for both
SELECT (SELECT COUNT(*) FROM [eap].[ORDER_QUOTE_OPTY]    WHERE create_date IS NULL OR create_user IS NULL) AS oqo_missing_audit,
       (SELECT COUNT(*) FROM [eap].[UNIVERSE_QUOTE_OPTY] WHERE create_date IS NULL OR create_user IS NULL) AS uqo_missing_audit;

SELECT TOP 5 * FROM [eap].[ORDER_QUOTE_OPTY];
SELECT TOP 5 * FROM [eap].[UNIVERSE_QUOTE_OPTY];
GO
