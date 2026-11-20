"""Step 6: export small summary files for the dashboard.

Run it from the project root with the virtual environment active:
    python src/06_export_dashboard_data.py

The dashboard reads only these files (in app/data/), never the big database,
so the deployed app works without the raw data. They hold aggregated totals only:
no customer IDs and no individual transactions.
"""
import sqlite3
from pathlib import Path

import pandas as pd

from forecasting import MODELS, backtest, future_months, prediction_range, score_models

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_FILE = PROJECT_ROOT / "data" / "processed" / "retail.db"
OUT_DIR = PROJECT_ROOT / "app" / "data"

HORIZON = 3                                   # months to forecast ahead
# December 2011 is a partial month (data ends 9 December), so it is excluded everywhere.
LAST_FULL_MONTH_FILTER = "month < '2011-12'"

MONTHLY_VIEWS = {"net": "v_monthly_net_sales", "gross": "v_monthly_sales"}


def export_monthly_and_forecasts(conn: sqlite3.Connection) -> dict:
    """Monthly totals plus backtest, scores and forecast, for net and gross sales."""
    monthly, backtests, scores_all, forecasts = [], [], [], []

    for basis, view in MONTHLY_VIEWS.items():
        df = pd.read_sql_query(
            f"SELECT month, revenue, orders, customers, units FROM {view} ORDER BY month", conn)
        monthly.append(df.assign(basis=basis))

        series = df.set_index("month")["revenue"]
        bt = backtest(series)
        backtests.append(bt.assign(basis=basis))

        scores = score_models(bt)
        scores.index.name = "model"
        scores_all.append(scores.reset_index().assign(basis=basis))

        best = scores.index[0]
        values = MODELS[best](series.to_numpy(dtype=float), HORIZON)
        ranges = prediction_range(bt, best, values)
        forecasts.append(pd.DataFrame({
            "month": future_months(series.index[-1], HORIZON),
            "model": best,
            "forecast": values,
            "low_10pct": [r[0] for r in ranges],
            "high_90pct": [r[1] for r in ranges],
            "basis": basis,
        }))

    return {
        "monthly": pd.concat(monthly, ignore_index=True),
        "backtest": pd.concat(backtests, ignore_index=True),
        "scores": pd.concat(scores_all, ignore_index=True),
        "forecast": pd.concat(forecasts, ignore_index=True),
    }


def export_breakdowns(conn: sqlite3.Connection) -> dict:
    """Top products, top countries, cancellation rate and a few headline facts."""
    products = pd.read_sql_query(f"""
        WITH product_revenue AS (
            SELECT stock_code, MAX(description) AS description,
                   ROUND(SUM(revenue), 2) AS revenue, SUM(quantity) AS units
            FROM v_net_sales WHERE {LAST_FULL_MONTH_FILTER}
            GROUP BY stock_code
        )
        SELECT stock_code, description, revenue, units,
               ROUND(100.0 * revenue / SUM(revenue) OVER (), 2) AS share_pct
        FROM product_revenue ORDER BY revenue DESC LIMIT 15""", conn)

    countries = pd.read_sql_query(f"""
        SELECT country, ROUND(SUM(revenue), 0) AS revenue, COUNT(DISTINCT invoice) AS orders,
               ROUND(100.0 * SUM(revenue) / SUM(SUM(revenue)) OVER (), 1) AS share_pct
        FROM v_net_sales WHERE {LAST_FULL_MONTH_FILTER}
        GROUP BY country ORDER BY revenue DESC LIMIT 10""", conn)

    cancellations = pd.read_sql_query("""
        SELECT strftime('%Y-%m', invoice_date) AS month,
               COUNT(DISTINCT CASE WHEN is_cancellation = 1 THEN invoice END) AS cancelled_invoices,
               COUNT(DISTINCT invoice) AS all_invoices,
               ROUND(100.0 * COUNT(DISTINCT CASE WHEN is_cancellation = 1 THEN invoice END)
                           / COUNT(DISTINCT invoice), 1) AS cancel_rate_pct
        FROM transactions
        WHERE strftime('%Y-%m', invoice_date) < '2011-12'
        GROUP BY month ORDER BY month""", conn)

    facts = conn.execute(f"""
        SELECT COUNT(*), COUNT(DISTINCT customer_id), COUNT(DISTINCT stock_code),
               COUNT(DISTINCT country), MIN(month), MAX(month)
        FROM v_net_sales WHERE {LAST_FULL_MONTH_FILTER}""").fetchone()
    meta = pd.DataFrame({
        "key": ["sale_lines", "customers_with_id", "products", "countries", "first_month", "last_month"],
        "value": list(facts),
    })
    return {"products": products, "countries": countries, "cancellations": cancellations, "meta": meta}


def main() -> None:
    if not DB_FILE.exists():
        raise FileNotFoundError(f"Run step 3 first. Missing: {DB_FILE}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_FILE) as conn:
        outputs = {**export_monthly_and_forecasts(conn), **export_breakdowns(conn)}

    for name, df in outputs.items():
        path = OUT_DIR / f"{name}.csv"
        df.round(2).to_csv(path, index=False)
        print(f"{name + '.csv':18} {len(df):4d} rows  {path.stat().st_size / 1024:6.1f} KB")
    print(f"\nExported to {OUT_DIR}")


if __name__ == "__main__":
    main()
