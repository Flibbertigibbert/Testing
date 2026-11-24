/* =====================================================================
   Add country_code + go_to_mkt_rt_nm to wallaby.eap.UNIVERSE_QUOTE_OPTY
   Run ONCE in SSMS (server: tartarus), before loading any new grain.
   Existing data is kept.
   ===================================================================== */

USE wallaby;
GO

-- 0. What is in the table right now? (should be the US Indirect load only, ~221,622 rows)
SELECT COUNT(*) AS current_rows FROM [eap].[UNIVERSE_QUOTE_OPTY];
GO

-- 1. Add the two columns (skips if they already exist)
IF COL_LENGTH(N'eap.UNIVERSE_QUOTE_OPTY', N'country_code') IS NULL
    ALTER TABLE [eap].[UNIVERSE_QUOTE_OPTY] ADD country_code VARCHAR(10) NULL;
IF COL_LENGTH(N'eap.UNIVERSE_QUOTE_OPTY', N'go_to_mkt_rt_nm') IS NULL
    ALTER TABLE [eap].[UNIVERSE_QUOTE_OPTY] ADD go_to_mkt_rt_nm VARCHAR(50) NULL;
GO

-- 2. Label the rows already loaded (they all came from the US Indirect run)
--    ONLY run this if step 0 showed just the original US Indirect load.
UPDATE [eap].[UNIVERSE_QUOTE_OPTY]
SET country_code    = 'US',
    go_to_mkt_rt_nm = 'INDIRECT',
    update_date     = SYSDATETIME(),
    update_user     = SUSER_SNAME()
WHERE country_code IS NULL;
GO

-- 3. Check: expect one row - US / INDIRECT / 221,622
SELECT country_code, go_to_mkt_rt_nm, COUNT(*) AS row_count
FROM [eap].[UNIVERSE_QUOTE_OPTY]
GROUP BY country_code, go_to_mkt_rt_nm;
GO

/* ---------------------------------------------------------------------
   AFTER EACH NEW GRAIN LOAD (run 09 query in DBeaver, export with
   Truncate = OFF, map country_code and go_to_mkt_rt_nm too), check:
   --------------------------------------------------------------------- */
-- SELECT country_code, go_to_mkt_rt_nm, COUNT(*) AS row_count, SUM(net_amount_usd) AS net
-- FROM [eap].[UNIVERSE_QUOTE_OPTY]
-- GROUP BY country_code, go_to_mkt_rt_nm
-- ORDER BY country_code, go_to_mkt_rt_nm;
