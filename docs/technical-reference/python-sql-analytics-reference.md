# Python and SQL Analytics Technical Reference

**Scope:** Methods, patterns and decisions used in the E-commerce Analytics and Forecasting Dashboard: data preparation with pandas, analysis in SQL, forecasting evaluation, testing and deployment.
**Audience:** Developers and analysts maintaining or extending the project.
**Last updated:** November 2026

## Contents

1. [Pipeline overview](#1-pipeline-overview)
2. [Environment and reproducibility](#2-environment-and-reproducibility)
3. [pandas patterns](#3-pandas-patterns)
4. [SQL patterns (SQLite)](#4-sql-patterns-sqlite)
5. [Data quality methodology](#5-data-quality-methodology)
6. [Forecasting and evaluation](#6-forecasting-and-evaluation)
7. [Testing](#7-testing)
8. [Dashboard and deployment](#8-dashboard-and-deployment)
9. [Common pitfalls and resolutions](#9-common-pitfalls-and-resolutions)
10. [Release checklist](#10-release-checklist)

---

## 1. Pipeline overview

| Stage | Script | Input | Output |
|---|---|---|---|
| 1. Load and inspect | `src/01_load_and_inspect.py` | `data/raw/online_retail_II.xlsx` | `data/processed/online_retail_raw.csv` |
| 2. Clean and flag | `src/02_clean_data.py` | Raw CSV | `data/processed/clean_transactions.csv` |
| 3. Build database | `src/03_build_database.py`, `sql/01_views.sql` | Clean CSV | `data/processed/retail.db` (SQLite) |
| 4. Query | `src/04_run_queries.py`, `sql/02` to `sql/05` | Database | Printed result tables |
| 5. Forecast | `src/05_run_forecast.py`, `src/forecasting.py` | Database views | Backtest and forecast CSV files |
| 6. Export | `src/06_export_dashboard_data.py` | Database | Eight small CSV files in `app/data/` |
| 7. Dashboard | `app/streamlit_app.py` | `app/data/*.csv` | Interactive web application |

The raw data and database are excluded from version control. The dashboard reads only the exported aggregates.

## 2. Environment and reproducibility

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # prompt then starts with (.venv)
python -m pip install --upgrade pip
pip install pandas openpyxl numpy plotly streamlit scikit-learn statsmodels pytest
pip freeze > requirements.txt         # record exact versions for development
```

- Development and deployment use the same Python minor version (3.13).
- The deployed app has its own minimal `app/requirements.txt` (`streamlit`, `pandas`, `plotly`), kept separate from the full development list.
- Scripts build paths from their own location, so they run from any working directory:

```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "online_retail_II.xlsx"
```

## 3. pandas patterns

```python
sheets = pd.read_excel(path, sheet_name=None)           # dict of {sheet name: DataFrame}
df = pd.concat(sheets.values(), ignore_index=True)      # stack the sheets
df = df.rename(columns={"Customer ID": "customer_id"})  # snake_case names
df = df.drop_duplicates()                               # exact duplicate rows
df["customer_id"] = df["customer_id"].astype("Int64")   # whole numbers that allow blanks
df["description"] = df["description"].str.strip()
df["revenue"] = (df["quantity"] * df["unit_price"]).round(2)

df["is_cancellation"] = df["invoice"].str.startswith("C").fillna(False).astype(bool)
df["is_product"] = df["stock_code"].str.match(r"^\d{5}[A-Z]*$").fillna(False).astype(bool)
df["is_valid_sale"] = (~df["is_cancellation"] & df["is_product"]
                       & (df["quantity"] > 0) & (df["unit_price"] > 0))

monthly = sales.set_index("invoice_date")["revenue"].resample("MS").sum()   # calendar-month totals
df.to_sql("transactions", conn, index=False, chunksize=50_000)              # write in batches
```

Intermediate results are saved as CSV so that later stages load in seconds instead of re-reading a 1-million-row Excel file.

## 4. SQL patterns (SQLite)

**View:** a saved query that centralises a business definition.

```sql
CREATE VIEW v_sales AS
SELECT invoice, stock_code, quantity, revenue, strftime('%Y-%m', invoice_date) AS month
FROM transactions WHERE is_valid_sale = 1;
```

**Common table expression and window functions:**

```sql
WITH product_revenue AS (
    SELECT stock_code, SUM(revenue) AS revenue FROM v_sales GROUP BY stock_code
)
SELECT RANK() OVER (ORDER BY revenue DESC) AS position,
       stock_code, revenue,
       ROUND(100.0 * revenue / SUM(revenue) OVER (), 2) AS share_pct
FROM product_revenue ORDER BY revenue DESC LIMIT 10;
```

| Construct | Use |
|---|---|
| `LAG(x) OVER (ORDER BY month)` | Value from the previous row (growth rates) |
| `AVG(x) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)` | Rolling average |
| `SUM(x) OVER (ORDER BY month)` | Running total |
| `SUM(x) OVER ()` | Total across all rows, for shares |
| `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ... DESC)` | Rank candidates within a group |
| `SUM(CASE WHEN cond THEN x ELSE 0 END)` | Conditional aggregation |
| `HAVING` | Filter after grouping (`WHERE` filters before) |
| `CREATE TABLE ... AS SELECT` | Materialise an expensive result once |

**Indexing:** a composite index covering every column compared in a join allows efficient lookups, and `ANALYZE` lets the query planner learn the table's shape.

```sql
CREATE INDEX IF NOT EXISTS idx_match
    ON transactions (customer_id, stock_code, quantity, unit_price, invoice_date);
ANALYZE;
```

## 5. Data quality methodology

Principle: **remove only what is certainly wrong (exact duplicates); flag everything else**, so that downstream queries state their filters openly.

| Issue | Observation in this dataset | Treatment |
|---|---|---|
| Overlapping source sheets | 34,335 exact duplicate rows | Removed and counted in the cleaning report |
| Cancellations (invoice prefix `C`) | 19,104 rows | Flagged; excluded from sales |
| Non-product codes (postage, fees, adjustments) | 5,980 rows | Flagged by stock-code pattern |
| Missing customer ID | 235,151 rows after de-duplication | Kept for sales; excluded from customer analysis |
| Incomplete final month | Data ends on 9 December 2011 | Excluded from monthly analysis and forecasting |
| Orders later cancelled in full | Single lines worth up to £168k | Net sales definition (below) |

**Gross and net sales.** Gross sales include every valid sale line. Net sales additionally remove lines that a later cancellation undid in full. A cancellation row carries no reference to its original sale, so the match uses: same customer, same product, opposite quantity, **same unit price**, and a sale date not later than the cancellation. Each cancellation removes only the latest earlier sale that fits. Guest checkouts cannot be matched, and partial cancellations remain in the data, so net sales are an approximation. Comparing the two series is the recommended robustness check.

## 6. Forecasting and evaluation

With 24 months of history, seasonal models such as Holt-Winters are not reliably estimable, so the comparison uses transparent baselines.

| Model | Rule |
|---|---|
| Naive | Repeat the last month |
| Seasonal naive | Value of the same month one year earlier |
| Seasonal naive with growth | Seasonal naive scaled by recent year-over-year growth (clipped to 0.5 to 1.5) |

**Rolling-origin backtest.** For each month from the thirteenth onward, each model sees only earlier months and predicts the next one. This avoids data leakage and produces 12 out-of-sample forecasts.

| Metric | Meaning |
|---|---|
| MAE | Average absolute error in currency units |
| RMSE | Root mean squared error; penalises large misses |
| MAPE | Average absolute percentage error |

Result on net sales: seasonal naive MAE 63,357 (MAPE 9.0%), seasonal naive with growth 75,191 (9.5%), naive 190,854 (24.6%). The growth adjustment did not improve on the baseline, because the growth estimate is noisy over a short history.

The forecast range is the 10th to 90th percentile of the winning model's relative backtest errors. With 12 errors it is indicative only. The winner was selected on the same 12 months used to report it, which slightly favours it.

## 7. Testing

```powershell
pytest
```

Tests cover each model, the growth calculation and its clipping, the metrics against hand-computed values, the number of backtest rows, and **absence of leakage**: changing future values must not change an earlier forecast.

```python
def test_backtest_never_uses_future_data():
    altered = series.copy(); altered.iloc[18:] = 9999.0
    assert backtest(series).iloc[3]["seasonal_naive"] == backtest(altered).iloc[3]["seasonal_naive"]
```

`pytest.ini` sets `pythonpath = src` so that tests import modules from `src`.

## 8. Dashboard and deployment

**Application structure.** `app/streamlit_app.py` loads the exported CSV files with `@st.cache_data`. Sidebar widgets (`st.radio`, `st.select_slider`) re-run the script from top to bottom on every change. Layout uses `st.tabs` and `st.columns`; headline figures use `st.metric`.

**Chart interactivity.** The charts keep Plotly's default interactions (hover tooltips, zoom, pan and the toolbar) so that viewers can investigate the data. On touch screens a swipe across a chart can pan or zoom it. The toolbar's reset (home) button restores the original view. If this proves disruptive, axes can be locked and the toolbar hidden:

```python
fig.update_xaxes(fixedrange=True)
fig.update_yaxes(fixedrange=True)
st.plotly_chart(fig, config={"displayModeBar": False})
```

**Deployment (Streamlit Community Cloud).**

| Setting | Value |
|---|---|
| Repository and branch | `AAchar-0/ecommerce-analytics-dashboard`, `main` |
| Main file path | `app/streamlit_app.py` |
| Dependencies | `app/requirements.txt`, found because the platform searches the entry file's folder before the repository root |
| Python version | Chosen under Advanced settings before the first deployment. It cannot be changed afterwards without deleting and redeploying the app |

Each push to `main` redeploys the application. Free applications may sleep after a period without visitors and restart on the next visit.

## 9. Common pitfalls and resolutions

| Symptom | Cause | Resolution |
|---|---|---|
| Loading the Excel file takes minutes | One million rows read through `openpyxl` | Read once and cache as CSV |
| `KeyError` or odd column names | Source names contain spaces and capitals | Rename to snake_case and validate the expected columns first |
| Counts higher than expected after combining sheets | Sheets overlap in time | `drop_duplicates()` and report the count |
| Sharp drop in the final month | Incomplete period | Exclude partial months from analysis and forecasting |
| One order dominates a product or month | Large order later cancelled | Flag cancellations and report net and gross series |
| Cancellations matched to the wrong sale | Match ignored unit price | Include price in the match key |
| Database build runs for 10 minutes or more | Join without a suitable index; poor query plan | Composite index covering the join columns, then `ANALYZE` (synthetic 1M-row test: 1.9 seconds) |
| `FileNotFoundError` on relative paths | Script run from another folder | Build paths from `Path(__file__)` |
| A script behaves as before an edit | Unsaved editor changes | Save before running |
| `ModuleNotFoundError` | Virtual environment not active | Activate it; the prompt should start with `(.venv)` |
| Forecast looks better than it should | Test data leaked into training | Rolling-origin backtest plus a leakage test |
| Seasonal model fails or overfits | Fewer than two full seasonal cycles | Use baselines and state the limitation |
| Deployed build is slow or fails | Full development requirements deployed | Provide `app/requirements.txt` with only runtime packages |
| Chart pans or zooms during a swipe on a phone | Default Plotly touch interaction, retained deliberately for exploration | Use the toolbar's reset button; to lock charts, set `fixedrange=True` on both axes and hide the mode bar |
| README images do not display | README in a subfolder, or wrong relative path | Keep `README.md` in the repository root |
| Data or environment folders appear in `git status` | Missing ignore rule | Add them to `.gitignore` before the first commit |

## 10. Release checklist

1. `pytest` passes.
2. The build script's reconciliation line matches the cleaning report (valid sale rows and revenue).
3. Gross and net results have been compared and any large differences explained.
4. Incomplete periods are excluded and noted.
5. The data licence and citation are present in the README and in the dashboard's data notes.
6. Exported files in `app/data/` contain aggregates only: no customer identifiers.
7. The deployed application has been checked on desktop and on a phone using mobile data, in light and dark themes.
