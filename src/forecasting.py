"""Forecasting models and evaluation helpers for the monthly revenue series.

These are pure functions: no files, no database. That makes them easy to test.
Every model takes the history up to "now" and returns the next h monthly values.
"""
import numpy as np
import pandas as pd

SEASON = 12                  # months in one seasonal cycle (a year)
GROWTH_WINDOW = 6            # recent months used to measure year-over-year growth
GROWTH_LIMITS = (0.5, 1.5)   # growth is clipped to this range so one odd stretch cannot explode a forecast


def naive(history, h):
    """Repeat the last observed month."""
    return [float(history[-1])] * h


def seasonal_naive(history, h):
    """Use the value from the same month one year earlier."""
    if len(history) < SEASON:
        raise ValueError(f"Need at least {SEASON} months of history, got {len(history)}")
    if h > SEASON:
        raise ValueError(f"h can be at most {SEASON}, got {h}")
    start = len(history) - SEASON            # position of the month that is 12 months before the next one
    return [float(history[start + k]) for k in range(h)]


def yoy_growth(history, window=GROWTH_WINDOW):
    """Recent months divided by the same months a year earlier (1.0 = no growth)."""
    history = np.asarray(history, dtype=float)
    n = min(window, len(history) - SEASON)   # how many month pairs we can compare
    if n <= 0:
        return 1.0                           # not enough history: assume no growth
    recent = history[-n:].sum()
    year_before = history[-n - SEASON:-SEASON].sum()
    if year_before <= 0:
        return 1.0
    return float(np.clip(recent / year_before, *GROWTH_LIMITS))


def seasonal_naive_growth(history, h):
    """Same month last year, scaled by the recent year-over-year growth."""
    growth = yoy_growth(history)
    return [value * growth for value in seasonal_naive(history, h)]


# The models we compare. Add a new model here and it is backtested automatically.
MODELS = {
    "naive": naive,
    "seasonal_naive": seasonal_naive,
    "seasonal_naive_growth": seasonal_naive_growth,
}


def backtest(series: pd.Series, h: int = 1) -> pd.DataFrame:
    """Rolling-origin backtest.

    For each month from the 13th onwards, every model sees ONLY the months before it
    and predicts h months ahead. Nothing from the future is used (no data leakage).
    """
    values = series.to_numpy(dtype=float)
    rows = []
    for t in range(SEASON, len(values) - h + 1):
        history = values[:t]                           # everything before the forecast origin
        row = {"month": series.index[t + h - 1], "actual": values[t + h - 1]}
        for name, model in MODELS.items():
            row[name] = model(history, h)[h - 1]
        rows.append(row)
    return pd.DataFrame(rows)


def error_metrics(actual, predicted) -> dict:
    """MAE (average miss in GBP), RMSE (punishes big misses), MAPE (average % miss)."""
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    errors = actual - predicted
    return {
        "MAE": float(np.mean(np.abs(errors))),
        "RMSE": float(np.sqrt(np.mean(errors ** 2))),
        "MAPE_%": float(np.mean(np.abs(errors / actual)) * 100),
    }


def score_models(bt: pd.DataFrame) -> pd.DataFrame:
    """One row per model, best (lowest MAE) first."""
    scores = {name: error_metrics(bt["actual"], bt[name]) for name in MODELS}
    return pd.DataFrame(scores).T.sort_values("MAE")


def prediction_range(bt: pd.DataFrame, model: str, forecasts, low=10, high=90):
    """A rough range from the model's own past errors (relative to its forecast)."""
    relative_errors = (bt["actual"] - bt[model]) / bt[model]
    low_adj, high_adj = np.percentile(relative_errors, [low, high])
    return [(f * (1 + low_adj), f * (1 + high_adj)) for f in forecasts]


def future_months(last_month: str, n: int) -> list:
    """The n month labels after last_month, e.g. '2011-11' -> ['2011-12', '2012-01', ...]."""
    return [str(pd.Period(last_month, "M") + k) for k in range(1, n + 1)]
