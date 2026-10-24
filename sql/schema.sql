
-- 1. Customer dimension
CREATE OR REPLACE TABLE DIM_CUSTOMER AS
SELECT
    CUSTOMER_ID,
    CUSTOMER_NAME,
    CITY,
    STATE,
    CUSTOMER_SEGMENT,
    TRY_CAST(REGISTRATION_DATE AS DATE) AS REGISTRATION_DATE
FROM source_customers;


-- 2. Courier dimension
CREATE OR REPLACE TABLE DIM_COURIER AS
SELECT
    COURIER_ID,
    COURIER_NAME,
    SLA_DAYS,
    SERVICE_TYPE,
    REGION_COVERAGE,
    ACTIVE_FLAG
FROM source_couriers;


-- 3. Date dimension
CREATE OR REPLACE TABLE DIM_DATE AS
WITH date_range AS (
    SELECT
        MIN(TRY_CAST(ORDER_DATE AS DATE)) AS min_date,
        MAX(TRY_CAST(ORDER_DATE AS DATE)) AS max_date
    FROM source_orders
)
SELECT
    calendar_date AS DATE_KEY,
    EXTRACT(YEAR FROM calendar_date)::INTEGER AS YEAR,
    EXTRACT(QUARTER FROM calendar_date)::INTEGER AS QUARTER,
    EXTRACT(MONTH FROM calendar_date)::INTEGER AS MONTH,
    STRFTIME(calendar_date, '%B') AS MONTH_NAME,
    EXTRACT(DAY FROM calendar_date)::INTEGER AS DAY,
    STRFTIME(calendar_date, '%A') AS DAY_NAME
FROM date_range,
     GENERATE_SERIES(
         min_date,
         max_date,
         INTERVAL 1 DAY
     ) AS dates(calendar_date)
WHERE min_date IS NOT NULL
  AND max_date IS NOT NULL;



-- 4. Order fulfillment fact table
-- Ensure each source order produces exactly one fact row.

CREATE OR REPLACE TABLE FACT_ORDER_FULFILLMENT AS

WITH unique_couriers AS (
    SELECT *
    FROM source_couriers
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY LOWER(TRIM(COURIER_NAME))
        ORDER BY COURIER_ID
    ) = 1
)

SELECT
    o.ORDER_ID,
    o.CUSTOMER_ID,
    c.COURIER_ID,
    TRY_CAST(o.ORDER_DATE AS DATE) AS ORDER_DATE_KEY,
    TRY_CAST(o.SHIPPED_DATE AS DATE) AS SHIPPED_DATE_KEY,
    TRY_CAST(o.DELIVERY_DATE AS DATE) AS DELIVERY_DATE_KEY,
    o.PRODUCT_ID,
    o.PRODUCT_NAME,
    o.CATEGORY,
    o.UNIT_PRICE,
    o.QUANTITY,
    o.ORDER_VALUE,
    o.ORDER_STATUS,
    o.PAYMENT_MODE,
    o.DELIVERY_DURATION_DAYS,
    c.SLA_DAYS,

    CASE
        WHEN o.ORDER_STATUS = 'Delivered'
         AND TRY_CAST(o.DELIVERY_DURATION_DAYS AS DOUBLE) IS NOT NULL
         AND TRY_CAST(c.SLA_DAYS AS DOUBLE) IS NOT NULL
        THEN TRY_CAST(o.DELIVERY_DURATION_DAYS AS DOUBLE)
             <= TRY_CAST(c.SLA_DAYS AS DOUBLE)
        ELSE NULL
    END AS SLA_MET

FROM source_orders AS o

LEFT JOIN unique_couriers AS c
    ON LOWER(TRIM(o.COURIER_NAME))
     = LOWER(TRIM(c.COURIER_NAME));
