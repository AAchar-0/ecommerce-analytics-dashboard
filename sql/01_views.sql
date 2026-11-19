-- 01_views.sql
-- A VIEW is a saved query that behaves like a table.
-- Views keep the cleaning rules in one place, so every analysis uses the same definition of a "sale".
--
-- Two definitions of sales are built here:
--   GROSS sales (v_sales)     = every valid sale line, including ones that were later cancelled.
--   NET sales   (v_net_sales) = gross sales minus the lines that were later cancelled in full.

-- A composite index covers every column the cancellation matching below compares.
-- Without it, SQLite can pick a poor lookup plan and the build takes forever on 1 million rows.
-- ANALYZE then lets SQLite learn the table's shape so it chooses well.
CREATE INDEX IF NOT EXISTS idx_match
    ON transactions (customer_id, stock_code, quantity, unit_price, invoice_date);
ANALYZE;

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
-- same customer, same product, opposite quantity, SAME UNIT PRICE, and the sale happened first.
-- Matching the unit price matters: a cancellation of 60 items at GBP 4.95 must not be paired
-- with a different sale of 60 items at GBP 649.50.
-- Rule: each cancellation undoes the LATEST earlier sale that fits, because cancellations
-- usually follow their sale within minutes or days.
-- ROW_NUMBER() ... ORDER BY date DESC numbers the candidate sales for each cancellation,
-- newest first, and closeness = 1 picks the newest.
-- DISTINCT stops one sale line being counted twice if two cancellations pick the same one.
-- This is a TABLE, not a view, so the matching is calculated once when the database is built.
-- rowid is SQLite's built-in row number; it identifies each row.
CREATE TABLE cancelled_sale_lines AS
WITH cancels AS (
    SELECT rowid AS cancel_id, customer_id, stock_code,
           -quantity AS quantity,                 -- flip the sign so it lines up with the sale
           unit_price, invoice_date
    FROM transactions
    WHERE is_cancellation = 1 AND customer_id IS NOT NULL
),
candidates AS (
    SELECT
        c.cancel_id,
        s.rowid AS line_id,
        ROW_NUMBER() OVER (PARTITION BY c.cancel_id
                           ORDER BY s.invoice_date DESC) AS closeness
    FROM cancels c
    JOIN transactions s
      ON  s.customer_id   = c.customer_id
      AND s.stock_code    = c.stock_code
      AND s.quantity      = c.quantity
      AND s.unit_price    = c.unit_price
      AND s.invoice_date <= c.invoice_date
    WHERE s.is_valid_sale = 1
)
SELECT DISTINCT line_id
FROM candidates
WHERE closeness = 1;

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
