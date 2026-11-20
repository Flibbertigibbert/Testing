/* Run in SSMS ONLY AFTER both CSV imports have finished.
   Row counts must equal the CSV row count minus the header row.
   Totals should match a SUM of the same column in Excel. */

USE wallaby;
GO

SELECT 'MARKET_SHARE_REF'   AS tbl,
       COUNT(*)             AS row_count,
       SUM(revenue_m)       AS total_revenue_m,
       SUM(units_k)         AS total_units_k,
       MIN(fiscal_year)     AS min_year,
       MAX(fiscal_year)     AS max_year
FROM [idc].[MARKET_SHARE_REF];

SELECT 'BACKLOG_DAILY_REF'  AS tbl,
       COUNT(*)             AS row_count,
       SUM(total_qty)       AS total_qty,
       SUM(backlog_qty)     AS total_backlog_qty,
       MIN(order_year)      AS min_year,
       MAX(order_year)      AS max_year
FROM [supply_chain].[BACKLOG_DAILY_REF];

-- Blank rows imported by mistake? Expect 0 for both
SELECT COUNT(*) AS blank_ms_rows
FROM [idc].[MARKET_SHARE_REF]
WHERE preferred_company_name IS NULL AND idc_country IS NULL AND revenue_m IS NULL;

SELECT COUNT(*) AS blank_backlog_rows
FROM [supply_chain].[BACKLOG_DAILY_REF]
WHERE pl IS NULL AND country IS NULL AND total_qty IS NULL;

SELECT TOP 5 * FROM [idc].[MARKET_SHARE_REF];
SELECT TOP 5 * FROM [supply_chain].[BACKLOG_DAILY_REF];
GO
