/* =====================================================================
   DATES_DIM and COUNTRY_DIM  -  run in SSMS (server: tartarus)
   tardis and wallaby are on the same server, so this is a direct copy:
   no DBeaver, no export. The whole file can be run in one go.
   ===================================================================== */

USE wallaby;
GO

-- 0. Schema
IF SCHEMA_ID(N'global') IS NULL EXEC (N'CREATE SCHEMA [global]');
GO


/* ---------------------------------------------------------------------
   1. tardis.dbo.dates  ->  wallaby.global.DATES_DIM
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'global.DATES_DIM', N'U') IS NOT NULL
    DROP TABLE [global].[DATES_DIM];     -- lets you re-run the script safely
GO

SELECT *
INTO [global].[DATES_DIM]
FROM tardis.dbo.dates;
GO

-- 7 standard audit columns (NOT NULL + DEFAULT fills the rows already copied)
ALTER TABLE [global].[DATES_DIM] ADD
    is_active    BIT            NOT NULL CONSTRAINT DF_DATES_DIM_is_active   DEFAULT (1),
    is_deleted   BIT            NOT NULL CONSTRAINT DF_DATES_DIM_is_deleted  DEFAULT (0),
    is_indexed   BIT            NOT NULL CONSTRAINT DF_DATES_DIM_is_indexed  DEFAULT (0),
    create_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_DATES_DIM_create_date DEFAULT (SYSDATETIME()),
    update_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_DATES_DIM_update_date DEFAULT (SYSDATETIME()),
    create_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_DATES_DIM_create_user DEFAULT (SUSER_SNAME()),
    update_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_DATES_DIM_update_user DEFAULT (SUSER_SNAME());
GO


/* ---------------------------------------------------------------------
   2. tardis.dbo.country_mapping  ->  wallaby.global.COUNTRY_DIM
      + rename subRegion2 -> country_cluster
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'global.COUNTRY_DIM', N'U') IS NOT NULL
    DROP TABLE [global].[COUNTRY_DIM];
GO

SELECT *
INTO [global].[COUNTRY_DIM]
FROM tardis.dbo.country_mapping;
GO

-- The "Caution: Changing any part of an object name..." message is normal
EXEC sp_rename N'[global].[COUNTRY_DIM].[subRegion2]', N'country_cluster', N'COLUMN';
GO

ALTER TABLE [global].[COUNTRY_DIM] ADD
    is_active    BIT            NOT NULL CONSTRAINT DF_COUNTRY_DIM_is_active   DEFAULT (1),
    is_deleted   BIT            NOT NULL CONSTRAINT DF_COUNTRY_DIM_is_deleted  DEFAULT (0),
    is_indexed   BIT            NOT NULL CONSTRAINT DF_COUNTRY_DIM_is_indexed  DEFAULT (0),
    create_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_COUNTRY_DIM_create_date DEFAULT (SYSDATETIME()),
    update_date  DATETIME2(0)   NOT NULL CONSTRAINT DF_COUNTRY_DIM_update_date DEFAULT (SYSDATETIME()),
    create_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_COUNTRY_DIM_create_user DEFAULT (SUSER_SNAME()),
    update_user  NVARCHAR(128)  NOT NULL CONSTRAINT DF_COUNTRY_DIM_update_user DEFAULT (SUSER_SNAME());
GO


/* ---------------------------------------------------------------------
   3. CHECKS - row counts must match source; rename and audit columns present
   --------------------------------------------------------------------- */
SELECT 'DATES_DIM'   AS tbl,
       (SELECT COUNT(*) FROM tardis.dbo.dates)             AS source_rows,
       (SELECT COUNT(*) FROM [global].[DATES_DIM])         AS target_rows
UNION ALL
SELECT 'COUNTRY_DIM',
       (SELECT COUNT(*) FROM tardis.dbo.country_mapping),
       (SELECT COUNT(*) FROM [global].[COUNTRY_DIM]);

-- Expect only country_cluster (subRegion2 gone)
SELECT COLUMN_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = N'global' AND TABLE_NAME = N'COUNTRY_DIM'
  AND COLUMN_NAME IN (N'subRegion2', N'country_cluster');

-- Expect 7 audit columns per table
SELECT TABLE_NAME, COUNT(*) AS audit_cols
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = N'global'
  AND TABLE_NAME IN (N'DATES_DIM', N'COUNTRY_DIM')
  AND COLUMN_NAME IN (N'is_active', N'is_deleted', N'is_indexed', N'create_date',
                      N'update_date', N'create_user', N'update_user')
GROUP BY TABLE_NAME;
GO
