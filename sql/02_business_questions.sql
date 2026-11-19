-- 02_business_questions.sql
-- Each query starts with a "-- name:" line. src/04_run_queries.py uses those names
-- to split this file, so keep one query per block and keep the marker lines.

-- name: monthly_revenue_with_growth
-- Question: how does revenue change from one month to the next?
-- LAG(x) OVER (ORDER BY month) reads x from the PREVIOUS row. It is a window function:
-- it looks at neighbouring rows without collapsing them the way GROUP BY does.
SELECT
    month,
    revenue,
    LAG(revenue) OVER (ORDER BY month) AS previous_month,
    ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
                / LAG(revenue) OVER (ORDER BY month), 1) AS growth_pct
FROM v_monthly_sales
ORDER BY month;

-- name: rolling_average_and_running_total
-- Question: what is the underlying trend once month-to-month noise is smoothed out?
-- ROWS BETWEEN 2 PRECEDING AND CURRENT ROW = a "frame" of the current month plus the two before it.
-- SUM(...) OVER (ORDER BY month) with no frame = a running total from the first month.
SELECT
    month,
    revenue,
    ROUND(AVG(revenue) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 0) AS rolling_3m_avg,
    ROUND(SUM(revenue) OVER (ORDER BY month), 0) AS running_total
FROM v_monthly_sales
ORDER BY month;

-- name: top_10_products
-- Question: which products earn the most, and how concentrated is the revenue?
-- WITH ... AS (...) is a CTE (common table expression): a named temporary result
-- that makes a long query read top to bottom.
-- RANK() numbers rows by revenue, giving ties the same number.
-- SUM(revenue) OVER () with empty brackets = the total across ALL rows, used for each product's share.
WITH product_revenue AS (
    SELECT
        stock_code,
        MAX(description)       AS description,   -- some codes have several spellings: pick one
        ROUND(SUM(revenue), 2) AS revenue,
        SUM(quantity)          AS units
    FROM v_sales
    GROUP BY stock_code
)
SELECT
    RANK() OVER (ORDER BY revenue DESC)           AS position,
    stock_code,
    description,
    revenue,
    units,
    ROUND(100.0 * revenue / SUM(revenue) OVER (), 2) AS share_pct
FROM product_revenue
ORDER BY revenue DESC
LIMIT 10;

-- name: revenue_by_country
-- Question: where does the money come from?
-- SUM(SUM(revenue)) OVER () = a window total built on top of each group's own total.
SELECT
    country,
    ROUND(SUM(revenue), 0)       AS revenue,
    COUNT(DISTINCT invoice)      AS orders,
    ROUND(100.0 * SUM(revenue) / SUM(SUM(revenue)) OVER (), 1) AS share_pct
FROM v_sales
GROUP BY country
ORDER BY revenue DESC
LIMIT 10;

-- name: top_10_customers_and_concentration
-- Question: how dependent is the business on a few customers?
-- Only rows with a customer ID can be used here (guest checkouts have none).
-- cumulative_share_pct = the running share of total revenue as we go down the ranked list.
WITH customer_revenue AS (
    SELECT
        customer_id,
        ROUND(SUM(revenue), 2)   AS revenue,
        COUNT(DISTINCT invoice)  AS orders,
        MIN(invoice_date)        AS first_order,
        MAX(invoice_date)        AS last_order
    FROM v_sales
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
)
SELECT
    customer_id,
    revenue,
    orders,
    substr(first_order, 1, 10) AS first_order,    -- substr keeps the first 10 characters: the date
    substr(last_order, 1, 10)  AS last_order,
    ROUND(100.0 * SUM(revenue) OVER (ORDER BY revenue DESC
                                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
                / SUM(revenue) OVER (), 1) AS cumulative_share_pct
FROM customer_revenue
ORDER BY revenue DESC
LIMIT 10;

-- name: cancellation_rate_by_month
-- Question: what share of orders gets cancelled?
-- This one reads the full transactions table, because v_sales excludes cancellations.
-- CASE WHEN ... THEN invoice END returns the invoice only for cancelled rows; other rows become NULL
-- and COUNT(DISTINCT ...) ignores NULLs.
SELECT
    strftime('%Y-%m', invoice_date) AS month,
    COUNT(DISTINCT CASE WHEN is_cancellation = 1 THEN invoice END) AS cancelled_invoices,
    COUNT(DISTINCT invoice)                                        AS all_invoices,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN is_cancellation = 1 THEN invoice END)
                / COUNT(DISTINCT invoice), 1)                      AS cancel_rate_pct
FROM transactions
WHERE strftime('%Y-%m', invoice_date) < '2011-12'
GROUP BY month
ORDER BY month;

-- name: new_customers_by_month
-- Question: is the business still winning new customers?
-- A CTE finds each customer's first purchase month; then we count customers per first month.
WITH first_purchase AS (
    SELECT customer_id, MIN(month) AS first_month
    FROM v_sales
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
)
SELECT first_month AS month, COUNT(*) AS new_customers
FROM first_purchase
WHERE first_month < '2011-12'
GROUP BY first_month
ORDER BY first_month;
