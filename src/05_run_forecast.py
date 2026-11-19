"""Step 5: backtest the forecasting models and forecast the next months.

Run it from the project root with the virtual environment active:
    python src/05_run_forecast.py                      # net sales (default)
    python src/05_run_forecast.py --series gross       # sensitivity: include cancelled lines
    python src/05_run_forecast.py --series net_ex_outlier   # sensitivity: drop the one odd June 2011 line
"""
import argparse
import sqlite3
from pathlib import Path

import pandas as pd

from forecasting import (MODELS, backtest, future_months, prediction_range,
                         score_models)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_FILE = PROJECT_ROOT / "data" / "processed" / "retail.db"
OUT_DIR = PROJECT_ROOT / "data" / "processed"

HORIZON = 3                       # how many months ahead to forecast
OUTLIER_INVOICES = ["556444"]     # 60 x GBP 649.50 in June 2011: no cancellation found, kept in "net"


def load_series(conn: sqlite3.Connection, name: str) -> pd.Series:
    """Monthly revenue as a Series indexed by month label like '2010-11'."""
    if name == "net":
        sql, params = "SELECT month, revenue FROM v_monthly_net_sales ORDER BY month", []
    elif name == "gross":
        sql, params = "SELECT month, revenue FROM v_monthly_sales ORDER BY month", []
    else:  # net_ex_outlier
        marks = ",".join("?" * len(OUTLIER_INVOICES))      # "?,?" placeholders keep the SQL safe
        sql = (f"SELECT month, ROUND(SUM(revenue), 2) AS revenue FROM v_net_sales "
               f"WHERE month < '2011-12' AND invoice NOT IN ({marks}) "
               f"GROUP BY month ORDER BY month")
        params = OUTLIER_INVOICES
    df = pd.read_sql_query(sql, conn, params=params)
    return df.set_index("month")["revenue"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest and forecast monthly revenue.")
    parser.add_argument("--series", choices=["net", "gross", "net_ex_outlier"], default="net")
    args = parser.parse_args()

    if not DB_FILE.exists():
        raise FileNotFoundError(f"Run step 3 first. Missing: {DB_FILE}")
    with sqlite3.connect(DB_FILE) as conn:
        series = load_series(conn, args.series)

    print(f"Series '{args.series}': {len(series)} months, {series.index[0]} to {series.index[-1]}")

    # ---------- Backtest ----------
    bt = backtest(series)
    print(f"\n--- Backtest: {len(bt)} one-month-ahead forecasts (GBP) ---")
    print(bt.round(0).to_string(index=False))

    scores = score_models(bt)
    print("\n--- Model scores (lower is better) ---")
    print(scores.round(1).to_string())

    best = scores.index[0]
    print(f"\nBest model: {best}")
    # Seasonal naive ("same month last year") is the bar to beat, so show every model against it.
    relative = (scores["MAE"] / scores.loc["seasonal_naive", "MAE"] - 1) * 100
    print("MAE relative to seasonal naive (negative = better than the bar):")
    print(relative.map(lambda value: f"{value:+.1f}%").to_string())

    # ---------- Forecast ----------
    forecasts = MODELS[best](series.to_numpy(dtype=float), HORIZON)
    ranges = prediction_range(bt, best, forecasts)
    future = pd.DataFrame({
        "month": future_months(series.index[-1], HORIZON),
        "model": best,
        "forecast": forecasts,
        "low_10pct": [r[0] for r in ranges],
        "high_90pct": [r[1] for r in ranges],
    })
    print(f"\n--- Forecast for the next {HORIZON} months (GBP, rough 80% range) ---")
    print(future.round(0).to_string(index=False))

    print("\nCaution: only 24 months of history. The range comes from just "
          f"{len(bt)} backtest errors, so treat it as indicative.")
    print("Caution: the first forecast month (2011-12) is a month the data only partly covers.")

    bt.to_csv(OUT_DIR / f"backtest_{args.series}.csv", index=False)
    future.to_csv(OUT_DIR / f"forecast_{args.series}.csv", index=False)
    print(f"\nSaved backtest_{args.series}.csv and forecast_{args.series}.csv to {OUT_DIR}")


if __name__ == "__main__":
    main()
