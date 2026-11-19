-- 01_views.sql
-- A VIEW is a saved query that behaves like a table.
-- Views keep the cleaning rules in one place, so every analysis uses the same definition of a "sale".

-- Drop first so this script can be re-run without errors.
DROP VIEW IF EXISTS v_sales;
DROP VIEW IF EXISTS v_monthly_sales;

-- v_sales: only valid sales (real products, not cancelled, positive quantity and price).
-- strftime('%Y-%m', ...) turns a date like 2010-11-23 into the month label 2010-11.
CREATE VIEW v_sales AS
SELECT
    invoice,
    stock_code,
    description,
    quantity,
    invoice_date,
    unit_price,
    customer_id,
    country,
    revenue,
    strftime('%Y-%m', invoice_date) AS month
FROM transactions
WHERE is_valid_sale = 1;

-- v_monthly_sales: one row per month.
-- December 2011 is left out on purpose: the data stops on 9 December 2011,
-- so that month is incomplete and would look like a false crash in sales.
CREATE VIEW v_monthly_sales AS
SELECT
    month,
    ROUND(SUM(revenue), 2)          AS revenue,
    COUNT(DISTINCT invoice)         AS orders,
    COUNT(DISTINCT customer_id)     AS customers,   -- COUNT(DISTINCT ...) ignores blanks (NULL)
    SUM(quantity)                   AS units
FROM v_sales
WHERE month < '2011-12'
GROUP BY month;
