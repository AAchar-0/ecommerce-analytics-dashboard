-- 04_gross_vs_net.sql
-- Compares sales before and after removing lines that were later cancelled in full.

-- name: gross_vs_net_monthly
-- Question: how much does each month change once fully cancelled lines are removed?
-- Two views are joined on the month label; the difference shows what was removed.
SELECT
    g.month,
    g.revenue                                              AS gross_revenue,
    n.revenue                                              AS net_revenue,
    ROUND(g.revenue - n.revenue, 0)                        AS removed,
    ROUND(100.0 * (g.revenue - n.revenue) / g.revenue, 1)  AS removed_pct
FROM v_monthly_sales g
JOIN v_monthly_net_sales n ON n.month = g.month
ORDER BY g.month;

-- name: top_products_net
-- Question: does the product ranking change when cancelled lines are removed?
-- Same shape as top_10_products, but built on v_net_sales.
WITH product_revenue AS (
    SELECT
        stock_code,
        MAX(description)       AS description,
        ROUND(SUM(revenue), 2) AS revenue,
        SUM(quantity)          AS units
    FROM v_net_sales
    GROUP BY stock_code
)
SELECT
    RANK() OVER (ORDER BY revenue DESC)              AS position,
    stock_code,
    description,
    revenue,
    units,
    ROUND(100.0 * revenue / SUM(revenue) OVER (), 2) AS share_pct
FROM product_revenue
ORDER BY revenue DESC
LIMIT 10;
