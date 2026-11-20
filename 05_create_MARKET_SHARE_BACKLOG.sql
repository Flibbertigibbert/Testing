/* =====================================================================
   idc.MARKET_SHARE_REF  and  supply_chain.BACKLOG_DAILY_REF
   Run in SSMS (server: tartarus). Creates EMPTY tables only.
   Load the CSVs afterwards with DBeaver (see steps at the bottom).

   Per Kevin (20 Nov): table names from the architecture diagram,
   keep ALL columns from the files, names in database-standard snake_case,
   plus the 7 standard audit columns.
   ===================================================================== */

USE wallaby;
GO

IF SCHEMA_ID(N'idc')          IS NULL EXEC (N'CREATE SCHEMA [idc]');
IF SCHEMA_ID(N'supply_chain') IS NULL EXEC (N'CREATE SCHEMA [supply_chain]');
GO


/* ---------------------------------------------------------------------
   1. MarketShare.csv  ->  wallaby.idc.MARKET_SHARE_REF
      File column          ->  table column
      Preferred_Company_Name -> preferred_company_name
      IDC_Country            -> idc_country
      HPE_Product_Category   -> hpe_product_category
      Product                -> product
      Fiscal_Year            -> fiscal_year
      Fiscal_Quarter         -> fiscal_quarter
      Revenue_M_             -> revenue_m      (USD millions)
      Units__k_              -> units_k        (thousands)
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'idc.MARKET_SHARE_REF', N'U') IS NOT NULL
    DROP TABLE [idc].[MARKET_SHARE_REF];
GO

CREATE TABLE [idc].[MARKET_SHARE_REF] (
    preferred_company_name  VARCHAR(200)   NULL,
    idc_country             VARCHAR(100)   NULL,
    hpe_product_category    VARCHAR(200)   NULL,
    product                 VARCHAR(200)   NULL,
    fiscal_year             INT            NULL,
    fiscal_quarter          INT            NULL,
    revenue_m               DECIMAL(19,8)  NULL,
    units_k                 DECIMAL(19,8)  NULL,

    is_active    BIT            NOT NULL CONSTRAINT DF_MARKET_SHARE_REF_is_active   DEFAULT (1),
    is_deleted   BIT            NOT NULL CONSTRAINT DF_MARKET_SHARE_REF_is_deleted  DEFAULT (0),
    is_indexed   BIT            NOT NULL CONSTRAINT DF_MARKET_SHARE_REF_is_indexed  DEFAULT (0),
    create_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_MARKET_SHARE_REF_create_date DEFAULT (SYSDATETIME()),
    update_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_MARKET_SHARE_REF_update_date DEFAULT (SYSDATETIME()),
    create_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_MARKET_SHARE_REF_create_user DEFAULT (SUSER_SNAME()),
    update_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_MARKET_SHARE_REF_update_user DEFAULT (SUSER_SNAME())
);
GO


/* ---------------------------------------------------------------------
   2. Backlog_LT_SY.csv  ->  wallaby.supply_chain.BACKLOG_DAILY_REF
      File columns are already snake_case, so names are kept as-is.
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'supply_chain.BACKLOG_DAILY_REF', N'U') IS NOT NULL
    DROP TABLE [supply_chain].[BACKLOG_DAILY_REF];
GO

CREATE TABLE [supply_chain].[BACKLOG_DAILY_REF] (
    pl                      VARCHAR(20)    NULL,
    rtm                     VARCHAR(50)    NULL,
    country                 VARCHAR(100)   NULL,
    order_year              INT            NULL,
    order_month             INT            NULL,
    total_orders            INT            NULL,
    total_qty               DECIMAL(19,4)  NULL,
    backlog_qty             DECIMAL(19,4)  NULL,
    backlog_orders          INT            NULL,
    avg_lt_build_days       DECIMAL(19,4)  NULL,
    median_lt_build_days    DECIMAL(19,4)  NULL,
    avg_lt_ship_days        DECIMAL(19,4)  NULL,
    median_lt_ship_days     DECIMAL(19,4)  NULL,

    is_active    BIT            NOT NULL CONSTRAINT DF_BACKLOG_DAILY_REF_is_active   DEFAULT (1),
    is_deleted   BIT            NOT NULL CONSTRAINT DF_BACKLOG_DAILY_REF_is_deleted  DEFAULT (0),
    is_indexed   BIT            NOT NULL CONSTRAINT DF_BACKLOG_DAILY_REF_is_indexed  DEFAULT (0),
    create_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_BACKLOG_DAILY_REF_create_date DEFAULT (SYSDATETIME()),
    update_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_BACKLOG_DAILY_REF_update_date DEFAULT (SYSDATETIME()),
    create_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_BACKLOG_DAILY_REF_create_user DEFAULT (SUSER_SNAME()),
    update_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_BACKLOG_DAILY_REF_update_user DEFAULT (SUSER_SNAME())
);
GO

-- Check: expect 15 and 20 columns
SELECT TABLE_SCHEMA, TABLE_NAME, COUNT(*) AS column_count
FROM INFORMATION_SCHEMA.COLUMNS
WHERE (TABLE_SCHEMA = N'idc' AND TABLE_NAME = N'MARKET_SHARE_REF')
   OR (TABLE_SCHEMA = N'supply_chain' AND TABLE_NAME = N'BACKLOG_DAILY_REF')
GROUP BY TABLE_SCHEMA, TABLE_NAME;
GO


/* =====================================================================
   LOADING THE CSVs (DBeaver)
   1. Download MarketShare.csv and Backlog_LT_SY.csv from SharePoint.
   2. In DBeaver, refresh wallaby > idc and supply_chain (F5).
   3. Right-click the target table > Import Data > CSV > pick the file.
   4. Importer settings: delimiter "," , header = top, quote char ".
   5. Tables mapping: target = existing table, mapping = existing.
      Columns: map each file column to its table column (see lists above;
      for MarketShare, Revenue_M_ -> revenue_m and Units__k_ -> units_k
      need picking by hand). Leave the 7 audit columns unmapped/skip.
   6. Proceed, then run 06_after_load_checks_MS_BACKLOG.sql.
   ===================================================================== */
