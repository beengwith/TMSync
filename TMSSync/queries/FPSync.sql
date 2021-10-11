-- CREATING THE TABLE IF IT DOES NOT EXIST
IF  NOT EXISTS (
    SELECT * FROM sys.objects 
    WHERE object_id = OBJECT_ID(N'dbo.FPEntries') AND type in (N'U')
)
BEGIN
CREATE TABLE dbo.FPEntries (
    C_Date char(8),
    C_Time char(6),
    L_TID int,
    L_UID int
)
END

-- CREATING COLUMN inOutType
IF NOT EXISTS (
      SELECT * 
      FROM   sys.columns 
      WHERE  object_id = OBJECT_ID(N'[dbo].[AttendanceDetails]') 
             AND name = 'inOutType'
            ) BEGIN
    ALTER TABLE [dbo].[AttendanceDetails]
    ADD inOutType Varchar(10) Default 'biometric'
END

-- 

-- ALL NEW ENTRIES WILL BE ADDED TO THIS TABLE
DECLARE @NewFPEntries TABLE(
    C_Date char(8),
    C_Time char(6),
    L_TID int,
    L_UID int
)

-- GET FROM UNIS
INSERT INTO @NewFPEntries 
    SELECT DISTINCT C_Date, C_Time, L_TID, L_UID
    FROM UNIS.dbo.tEnter as TE
    WHERE 
        L_UID <> -1
        AND NOT EXISTS ( 
            SELECT *
            FROM dbo.FPEntries
            WHERE
                C_Date=TE.C_Date AND
                C_Time=TE.C_Time AND
                L_UID=TE.L_UID )

-- GET FROM Manual
IF DB_ID('TMSManualRegistry') IS NOT NULL
INSERT INTO @NewFPEntries
    SELECT DISTINCT C_Date, C_Time, L_TID, L_UID
    FROM TMSManualRegistry.dbo.ManualEntry as ME
    WHERE
        L_UID <> -1
        AND NOT EXISTS(
            SELECT *
            FROM dbo.FPEntries
            WHERE
                C_Date=ME.C_Date AND
                C_Time=ME.C_Time AND
                L_UID=ME.L_UID )

DECLARE @NewFPEntriesOrdered TABLE(
    C_Date char(8),
    C_Time char(6),
    L_TID int,
    L_UID int
)

SELECT * FROM @NewFPEntries ORDER BY C_Date ASC, C_Time ASC
