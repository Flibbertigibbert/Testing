/* Run in SSMS ONLY AFTER the DBeaver export has finished.
   Compare with the same totals from order_side_dataset.sql in DBeaver:
   SELECT COUNT(*), SUM(net_amount_usd), SUM(order_count),
          MIN(order_create_date), MAX(order_create_date)
   FROM ( <order_side_dataset.sql without the final ORDER BY and semicolon> ) t
*/
USE wallaby;
GO

SELECT COUNT(*)                AS row_count,
       SUM(net_amount_usd)     AS total_net_amount_usd,
       SUM(order_count)        AS total_order_count,
       MIN(order_create_date)  AS first_date,
       MAX(order_create_date)  AS last_date
FROM [eap].[ORDERS_DAILY_REF];

-- Audit columns filled? Expect 0
SELECT COUNT(*) AS rows_missing_audit
FROM [eap].[ORDERS_DAILY_REF]
WHERE create_date IS NULL OR create_user IS NULL;

SELECT TOP 10 * FROM [eap].[ORDERS_DAILY_REF] ORDER BY order_create_date DESC;
GO
