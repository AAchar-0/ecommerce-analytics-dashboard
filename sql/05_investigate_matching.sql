-- 05_investigate_matching.sql
-- Looks at the lines the matching rule might have missed.

-- name: investigate_customer_15098_picnic_baskets
-- Question: why was the 60 x GBP 649.50 line in June 2011 not removed as cancelled?
-- Every row for that customer and product, oldest first, so the order of sales
-- and cancellations is visible.
SELECT
    invoice,
    substr(invoice_date, 1, 16) AS date_time,
    quantity,
    unit_price,
    revenue,
    is_cancellation,
    is_valid_sale
FROM transactions
WHERE customer_id = 15098
  AND stock_code = '22502'
ORDER BY invoice_date;

-- name: large_lines_still_in_net_sales
-- Question: which big sale lines are still counted as net sales, and do any have a cancellation partner?
-- loose_matches counts cancellations with the same customer, product, opposite quantity
-- and unit price, ignoring dates. A value above 0 means the line may have been cancelled but was not removed.
SELECT
    n.invoice,
    substr(n.invoice_date, 1, 10) AS sale_date,
    n.customer_id,
    n.stock_code,
    n.quantity,
    n.revenue,
    (SELECT COUNT(*)
       FROM transactions c
      WHERE c.is_cancellation = 1
        AND c.customer_id = n.customer_id
        AND c.stock_code  = n.stock_code
        AND c.quantity    = -n.quantity
        AND c.unit_price  = n.unit_price) AS loose_matches
FROM v_net_sales n
WHERE n.revenue >= 5000
ORDER BY n.revenue DESC
LIMIT 15;
