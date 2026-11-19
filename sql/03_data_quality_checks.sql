-- 03_data_quality_checks.sql
-- Checks whether big sales were later cancelled. Run with:
--     python src/04_run_queries.py largest_sale_lines_and_matching_cancellations
-- (or run everything with no name).

-- name: largest_sale_lines_and_matching_cancellations
-- Question: are the biggest sale lines later cancelled?
-- For each of the 10 largest lines we look for a cancellation row with the same customer,
-- the same product, and the opposite quantity (e.g. -80995 against +80995).
-- The bracketed SELECT inside the column list is a "correlated subquery": it runs once per row
-- and can refer to that row (b.customer_id and so on).
WITH big_lines AS (
    SELECT invoice, invoice_date, customer_id, stock_code, quantity, revenue
    FROM v_sales
    ORDER BY revenue DESC
    LIMIT 10
)
SELECT
    b.invoice,
    substr(b.invoice_date, 1, 10) AS sale_date,
    b.customer_id,
    b.stock_code,
    b.quantity,
    b.revenue,
    (SELECT COUNT(*)
       FROM transactions c
      WHERE c.is_cancellation = 1
        AND c.customer_id = b.customer_id
        AND c.stock_code  = b.stock_code
        AND c.quantity    = -b.quantity) AS matching_cancellations
FROM big_lines b
ORDER BY b.revenue DESC;

-- name: share_of_sales_with_exact_cancellation_match
-- Question: how much of the "valid sales" revenue has an exact matching cancellation?
-- The CTE lists every distinct cancelled (customer, product, quantity) combination,
-- with the quantity sign flipped so it lines up with the original sale.
-- JOIN keeps only the sale lines that have a partner in that list.
-- This is an upper bound: a customer who ordered the same quantity several times
-- would have all of those lines counted.
WITH cancelled AS (
    SELECT DISTINCT customer_id, stock_code, -quantity AS quantity
    FROM transactions
    WHERE is_cancellation = 1 AND customer_id IS NOT NULL
)
SELECT
    COUNT(*)                                   AS matched_lines,
    ROUND(SUM(s.revenue), 2)                   AS matched_revenue,
    ROUND(100.0 * SUM(s.revenue) / (SELECT SUM(revenue) FROM v_sales), 2) AS pct_of_valid_sales
FROM v_sales s
JOIN cancelled c
  ON c.customer_id = s.customer_id
 AND c.stock_code  = s.stock_code
 AND c.quantity    = s.quantity;

-- name: bulk_orders_by_month
-- Question: which months contain huge lines (10,000 units or more), and what would they be without them?
-- CASE WHEN inside SUM adds up only the rows that meet a condition.
-- HAVING filters AFTER grouping (WHERE filters before), so we keep only months with bulk lines.
SELECT
    month,
    ROUND(SUM(revenue), 0)                                          AS revenue_all,
    ROUND(SUM(CASE WHEN quantity < 10000 THEN revenue ELSE 0 END), 0) AS revenue_without_bulk,
    SUM(CASE WHEN quantity >= 10000 THEN 1 ELSE 0 END)              AS bulk_lines
FROM v_sales
WHERE month < '2011-12'
GROUP BY month
HAVING bulk_lines > 0
ORDER BY month;
