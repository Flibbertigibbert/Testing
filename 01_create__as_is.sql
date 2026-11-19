/* =====================================================================
   wallaby.eap.ORDERS_DAILY_REF  -  run in SSMS (server: tartarus)
   Columns match the output of order_side_dataset.sql exactly
   (wallaby_price_forecasting repo), plus the 7 standard audit columns.
   ===================================================================== */

USE wallaby;
GO

-- Remove the earlier customer/material-level version first
IF OBJECT_ID(N'eap.ORDERS_DAILY_REF', N'U') IS NOT NULL
    DROP TABLE [eap].[ORDERS_DAILY_REF];
GO

IF SCHEMA_ID(N'eap') IS NULL EXEC (N'CREATE SCHEMA [eap]');
GO

CREATE TABLE [eap].[ORDERS_DAILY_REF] (
    -- Columns from order_side_dataset.sql, same names and order
    order_create_date       DATE           NULL,
    rtm_cleaned             VARCHAR(100)   NULL,
    transaction_country     VARCHAR(50)    NULL,
    mtrl_mstr_mtrl_grp_cd   VARCHAR(100)   NULL,
    business_pch_level_3    VARCHAR(100)   NULL,
    entity_tier             VARCHAR(100)   NULL,
    order_count             BIGINT         NULL,
    quantity                DECIMAL(19,4)  NULL,
    list_price              DECIMAL(19,4)  NULL,
    discount_amount         DECIMAL(19,4)  NULL,
    net_amount_usd          DECIMAL(19,4)  NULL,
    final_total_cost        DECIMAL(19,4)  NULL,
    final_gross_margin      DECIMAL(19,4)  NULL,

    -- 7 audit columns (Wallaby data standards). Defaults fill them on insert,
    -- so leave them unmapped in the DBeaver export.
    is_active    BIT            NOT NULL CONSTRAINT DF_ORDERS_DAILY_REF_is_active   DEFAULT (1),
    is_deleted   BIT            NOT NULL CONSTRAINT DF_ORDERS_DAILY_REF_is_deleted  DEFAULT (0),
    is_indexed   BIT            NOT NULL CONSTRAINT DF_ORDERS_DAILY_REF_is_indexed  DEFAULT (0),
    create_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_ORDERS_DAILY_REF_create_date DEFAULT (SYSDATETIME()),
    update_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_ORDERS_DAILY_REF_update_date DEFAULT (SYSDATETIME()),
    create_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_ORDERS_DAILY_REF_create_user DEFAULT (SUSER_SNAME()),
    update_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_ORDERS_DAILY_REF_update_user DEFAULT (SUSER_SNAME())
);
GO

-- Check: expect 20 columns
SELECT COUNT(*) AS column_count
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = N'eap' AND TABLE_NAME = N'ORDERS_DAILY_REF';
GO
