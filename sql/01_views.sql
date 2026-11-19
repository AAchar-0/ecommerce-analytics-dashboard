-- 01_views.sql
-- A VIEW is a saved query that behaves like a table.
-- Views keep the cleaning rules in one place, so every analysis uses the same definition of a "sale".
--
-- Two definitions of sales are built here:
--   GROSS sales (v_sales)     = every valid sale line, including ones that were later cancelled.
--   NET sales   (v_net_sales) = gross sales minus the lines that were later cancelled in full.

-- Drop first so this script can be re-run without errors (views before the things they use).
DROP VIEW  IF EXISTS v_monthly_net_sales;
DROP VIEW  IF EXISTS v_net_sales;
DROP VIEW  IF EXISTS v_monthly_sales;
DROP VIEW  IF EXISTS v_sales;
DROP TABLE IF EXISTS cancelled_sale_lines;

-- v_sales: only valid sales (real products, not cancelled invoices, positive quantity and price).
-- strftime('%Y-%m', ...) turns a date like 2010-11-23 into the month label 2010-11.
CREATE VIEW v_sales AS
SELECT
    invoice, stock_code, description, quantity, invoice_date,
    unit_price, customer_id, country, revenue,
    strftime('%Y-%m', invoice_date) AS month
FROM transactions
WHERE is_valid_sale = 1;

-- v_monthly_sales: one row per month of GROSS sales.
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

-- cancelled_sale_lines: the sale lines that a cancellation later undid.
-- A cancellation row (a "C" invoice) has no link to the sale it undoes, so we match on:
-- same customer, same product, opposite quantity, and the cancellation is not earlier than the sale.
-- To stop one cancellation from wiping out several identical orders, each group is numbered
-- in date order with ROW_NUMBER(): the 1st sale pairs with the 1st cancellation, the 2nd with the 2nd.
-- This is a TABLE, not a view, so the matching is calculated once when the database is built.
-- rowid is SQLite's built-in row number; it identifies each sale line.
CREATE TABLE cancelled_sale_lines AS
WITH sales_ranked AS (
    SELECT
        rowid AS line_id, customer_id, stock_code, quantity, invoice_date,
        ROW_NUMBER() OVER (PARTITION BY customer_id, stock_code, quantity
                           ORDER BY invoice_date) AS n
    FROM transactions
    WHERE is_valid_sale = 1 AND customer_id IS NOT NULL
),
cancels_ranked AS (
    SELECT
        customer_id, stock_code, -quantity AS quantity, invoice_date,
        ROW_NUMBER() OVER (PARTITION BY customer_id, stock_code, -quantity
                           ORDER BY invoice_date) AS n
    FROM transactions
    WHERE is_cancellation = 1 AND customer_id IS NOT NULL
)
SELECT s.line_id
FROM sales_ranked s
JOIN cancels_ranked c
  ON  c.customer_id  = s.customer_id
  AND c.stock_code   = s.stock_code
  AND c.quantity     = s.quantity
  AND c.n            = s.n
  AND c.invoice_date >= s.invoice_date;

-- v_net_sales: valid sales without the lines that were later cancelled in full.
-- Guest checkouts (no customer ID) cannot be matched, so they always stay in.
CREATE VIEW v_net_sales AS
SELECT
    invoice, stock_code, description, quantity, invoice_date,
    unit_price, customer_id, country, revenue,
    strftime('%Y-%m', invoice_date) AS month
FROM transactions
WHERE is_valid_sale = 1
  AND rowid NOT IN (SELECT line_id FROM cancelled_sale_lines);

-- v_monthly_net_sales: the same monthly summary, but for NET sales.
CREATE VIEW v_monthly_net_sales AS
SELECT
    month,
    ROUND(SUM(revenue), 2)          AS revenue,
    COUNT(DISTINCT invoice)         AS orders,
    COUNT(DISTINCT customer_id)     AS customers,
    SUM(quantity)                   AS units
FROM v_net_sales
WHERE month < '2011-12'
GROUP BY month;
