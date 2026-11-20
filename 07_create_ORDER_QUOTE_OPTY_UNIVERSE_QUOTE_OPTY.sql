/* =====================================================================
   wallaby.eap.ORDER_QUOTE_OPTY  and  wallaby.eap.UNIVERSE_QUOTE_OPTY
   Run in SSMS (server: tartarus). Creates EMPTY tables; whole file can
   run in one go. Columns match each script's final output exactly,
   plus the 7 standard audit columns.
   ===================================================================== */

USE wallaby;
GO

/* ---------------------------------------------------------------------
   1. order_with_quote_opty.sql  ->  eap.ORDER_QUOTE_OPTY   (15 + 7 cols)
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'eap.ORDER_QUOTE_OPTY', N'U') IS NOT NULL
    DROP TABLE [eap].[ORDER_QUOTE_OPTY];
GO

CREATE TABLE [eap].[ORDER_QUOTE_OPTY] (
    order_create_date                       DATE           NULL,
    opportunity_id_on_header                VARCHAR(100)   NULL,
    rtm_cleaned                             VARCHAR(100)   NULL,
    transaction_country                     VARCHAR(50)    NULL,
    mtrl_mstr_mtrl_grp_cd                   VARCHAR(100)   NULL,
    business_pch_level_3                    VARCHAR(100)   NULL,
    entity_tier                             VARCHAR(100)   NULL,
    cl_2_dt                                 DATE           NULL,
    total_opportunity_value_close_dt_usd    DECIMAL(19,2)  NULL,
    order_count                             BIGINT         NULL,
    quantity                                DECIMAL(19,4)  NULL,
    list_price                              DECIMAL(19,4)  NULL,
    discount_amount                         DECIMAL(19,4)  NULL,
    net_amount_usd                          DECIMAL(19,4)  NULL,
    final_total_cost                        DECIMAL(19,4)  NULL,

    -- 7 audit columns (Wallaby data standards); leave unmapped in DBeaver
    is_active    BIT            NOT NULL CONSTRAINT DF_ORDER_QUOTE_OPTY_is_active   DEFAULT (1),
    is_deleted   BIT            NOT NULL CONSTRAINT DF_ORDER_QUOTE_OPTY_is_deleted  DEFAULT (0),
    is_indexed   BIT            NOT NULL CONSTRAINT DF_ORDER_QUOTE_OPTY_is_indexed  DEFAULT (0),
    create_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_ORDER_QUOTE_OPTY_create_date DEFAULT (SYSDATETIME()),
    update_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_ORDER_QUOTE_OPTY_update_date DEFAULT (SYSDATETIME()),
    create_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_ORDER_QUOTE_OPTY_create_user DEFAULT (SUSER_SNAME()),
    update_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_ORDER_QUOTE_OPTY_update_user DEFAULT (SUSER_SNAME())
);
GO

/* ---------------------------------------------------------------------
   2. universe_with_quote_opty.sql  ->  eap.UNIVERSE_QUOTE_OPTY  (12 + 7 cols)
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'eap.UNIVERSE_QUOTE_OPTY', N'U') IS NOT NULL
    DROP TABLE [eap].[UNIVERSE_QUOTE_OPTY];
GO

CREATE TABLE [eap].[UNIVERSE_QUOTE_OPTY] (
    hpe_opty_i_nm                           VARCHAR(100)   NULL,   -- opportunity ID
    crt_4_dt                                DATE           NULL,   -- opportunity create date
    cl_2_dt                                 DATE           NULL,   -- opportunity close date
    total_opportunity_value_close_dt_usd    DECIMAL(19,2)  NULL,
    quote_id_version                        VARCHAR(100)   NULL,
    creation_dt                             DATE           NULL,   -- quote creation date
    quote_net_amount                        DECIMAL(19,4)  NULL,
    order_create_date                       DATE           NULL,
    net_amount_usd                          DECIMAL(19,4)  NULL,
    global_entity_id                        VARCHAR(100)   NULL,
    entity_tier                             VARCHAR(100)   NULL,

    -- 7 audit columns (Wallaby data standards); leave unmapped in DBeaver
    is_active    BIT            NOT NULL CONSTRAINT DF_UNIVERSE_QUOTE_OPTY_is_active   DEFAULT (1),
    is_deleted   BIT            NOT NULL CONSTRAINT DF_UNIVERSE_QUOTE_OPTY_is_deleted  DEFAULT (0),
    is_indexed   BIT            NOT NULL CONSTRAINT DF_UNIVERSE_QUOTE_OPTY_is_indexed  DEFAULT (0),
    create_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_UNIVERSE_QUOTE_OPTY_create_date DEFAULT (SYSDATETIME()),
    update_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_UNIVERSE_QUOTE_OPTY_update_date DEFAULT (SYSDATETIME()),
    create_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_UNIVERSE_QUOTE_OPTY_create_user DEFAULT (SUSER_SNAME()),
    update_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_UNIVERSE_QUOTE_OPTY_update_user DEFAULT (SUSER_SNAME())
);
GO

-- Check: expect ORDER_QUOTE_OPTY = 22, UNIVERSE_QUOTE_OPTY = 18 columns,
-- and 7 audit columns each
SELECT TABLE_NAME,
       COUNT(*) AS total_cols,
       SUM(CASE WHEN COLUMN_NAME IN (N'is_active', N'is_deleted', N'is_indexed', N'create_date',
                                     N'update_date', N'create_user', N'update_user')
                THEN 1 ELSE 0 END) AS audit_cols
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = N'eap' AND TABLE_NAME IN (N'ORDER_QUOTE_OPTY', N'UNIVERSE_QUOTE_OPTY')
GROUP BY TABLE_NAME;
GO
