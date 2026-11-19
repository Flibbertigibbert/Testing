/* =====================================================================
   wallaby.eap.ORDERS_DAILY_REF  -  run in SSMS (server: tartarus)
   Matches Kevin's design: fact table, daily grain, 5-column primary key,
   12 measures, 7 standard audit columns.
   ===================================================================== */

USE wallaby;
GO

IF SCHEMA_ID(N'eap') IS NULL EXEC (N'CREATE SCHEMA [eap]');
GO

CREATE TABLE [eap].[ORDERS_DAILY_REF] (
    -- Primary key / grain
    order_date          DATE           NOT NULL,
    mdm_id              VARCHAR(50)    NOT NULL,
    mtrl_id             VARCHAR(50)    NOT NULL,
    country_id          VARCHAR(10)    NOT NULL,
    route_to_market     VARCHAR(50)    NOT NULL,

    -- Order measures
    order_value         DECIMAL(19,4)  NULL,
    order_units         DECIMAL(19,4)  NULL,
    order_count         INT            NULL,
    list_price_value    DECIMAL(19,4)  NULL,
    discount_value      DECIMAL(19,4)  NULL,
    discount_pct        DECIMAL(9,6)   NULL,
    cost_value          DECIMAL(19,4)  NULL,
    margin_value        DECIMAL(19,4)  NULL,

    -- Quote / opportunity measures (filled later from the quote & opportunity files)
    quote_value         DECIMAL(19,4)  NULL,
    quote_count         INT            NULL,
    opportunity_value   DECIMAL(19,4)  NULL,
    opportunity_count   INT            NULL,

    -- 7 audit columns (Wallaby data standards); defaults fill them on insert
    is_active    BIT            NOT NULL CONSTRAINT DF_ORDERS_DAILY_REF_is_active   DEFAULT (1),
    is_deleted   BIT            NOT NULL CONSTRAINT DF_ORDERS_DAILY_REF_is_deleted  DEFAULT (0),
    is_indexed   BIT            NOT NULL CONSTRAINT DF_ORDERS_DAILY_REF_is_indexed  DEFAULT (0),
    create_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_ORDERS_DAILY_REF_create_date DEFAULT (SYSDATETIME()),
    update_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_ORDERS_DAILY_REF_update_date DEFAULT (SYSDATETIME()),
    create_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_ORDERS_DAILY_REF_create_user DEFAULT (SUSER_SNAME()),
    update_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_ORDERS_DAILY_REF_update_user DEFAULT (SUSER_SNAME()),

    CONSTRAINT PK_ORDERS_DAILY_REF
        PRIMARY KEY CLUSTERED (order_date, mdm_id, mtrl_id, country_id, route_to_market)
);
GO

-- Check: expect 24 columns
SELECT COUNT(*) AS column_count
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = N'eap' AND TABLE_NAME = N'ORDERS_DAILY_REF';
GO

/* AFTER THE DBEAVER LOAD - compare with the Hive check numbers */
SELECT COUNT(*)          AS row_count,
       SUM(order_value)  AS total_order_value,
       SUM(order_units)  AS total_units,
       SUM(cost_value)   AS total_cost,
       MIN(order_date)   AS first_date,
       MAX(order_date)   AS last_date
FROM [eap].[ORDERS_DAILY_REF];
GO
