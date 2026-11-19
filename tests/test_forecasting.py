"""Tests for the forecasting helpers. Run from the project root with:  pytest"""
import numpy as np
import pandas as pd
import pytest

from forecasting import (backtest, error_metrics, future_months, naive,
                         seasonal_naive, seasonal_naive_growth, yoy_growth)


def make_series(n=24, start="2009-12"):
    """Months 1, 2, 3 ... as revenue, labelled like the real data."""
    months = [str(pd.Period(start, "M") + k) for k in range(n)]
    return pd.Series(np.arange(1, n + 1, dtype=float), index=months)


def test_naive_repeats_last_value():
    assert naive([5, 6, 7], 3) == [7.0, 7.0, 7.0]


def test_seasonal_naive_uses_same_month_last_year():
    history = list(range(1, 15))                  # 14 months: 1..14
    # The next month (15th) is 12 months after month 3, so it should return 3, then 4.
    assert seasonal_naive(history, 2) == [3.0, 4.0]


def test_seasonal_naive_needs_a_full_year():
    with pytest.raises(ValueError):
        seasonal_naive([1, 2, 3], 1)


def test_growth_is_one_without_enough_history():
    assert yoy_growth(list(range(1, 13))) == 1.0   # exactly 12 months: nothing to compare


def test_growth_measures_year_over_year():
    year_one = np.full(12, 100.0)
    year_two = np.full(6, 120.0)                   # last 6 months are 20% above a year earlier
    history = np.concatenate([year_one, year_two])
    assert yoy_growth(history) == pytest.approx(1.2)


def test_growth_is_clipped():
    history = np.concatenate([np.full(12, 100.0), np.full(6, 1000.0)])
    assert yoy_growth(history) == 1.5              # upper limit


def test_growth_model_scales_seasonal_naive():
    history = np.concatenate([np.full(12, 100.0), np.full(6, 120.0)])
    assert seasonal_naive_growth(history, 1) == [pytest.approx(120.0)]


def test_backtest_has_one_row_per_forecastable_month():
    bt = backtest(make_series(24))
    assert len(bt) == 12                           # months 13..24
    assert bt["month"].iloc[0] == "2010-12"


def test_backtest_never_uses_future_data():
    series = make_series(24)
    altered = series.copy()
    altered.iloc[18:] = 9999.0                     # change everything from month 19 onwards
    row_a = backtest(series).iloc[3]               # forecast for month 16
    row_b = backtest(altered).iloc[3]
    for column in ["naive", "seasonal_naive", "seasonal_naive_growth"]:
        assert row_a[column] == row_b[column]


def test_error_metrics_known_values():
    metrics = error_metrics([100, 200], [110, 180])
    assert metrics["MAE"] == pytest.approx(15.0)
    assert metrics["RMSE"] == pytest.approx(np.sqrt((100 + 400) / 2))
    assert metrics["MAPE_%"] == pytest.approx((10 / 100 + 20 / 200) / 2 * 100)


def test_future_months_cross_a_year_boundary():
    assert future_months("2011-11", 3) == ["2011-12", "2012-01", "2012-02"]
