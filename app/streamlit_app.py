"""Interactive dashboard: e-commerce analytics and forecasting.

Run it locally from the project root:
    streamlit run app/streamlit_app.py

It reads only the small summary files in app/data/ (made by src/06_export_dashboard_data.py).
"""
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"
REPO_URL = "https://github.com/AAchar-0/ecommerce-analytics-dashboard"
PORTFOLIO_URL = "https://aachar-0.github.io/"
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MODEL_LABELS = {
    "naive": "Repeat last month",
    "seasonal_naive": "Same month last year",
    "seasonal_naive_growth": "Same month last year, scaled by growth",
}

st.set_page_config(page_title="E-commerce Analytics and Forecasting", layout="wide")


# ---------- Helpers ----------
@st.cache_data                         # read each file once, not on every click
def load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / f"{name}.csv")


def gbp(value: float) -> str:
    return f"£{value:,.0f}"


def to_date(months: pd.Series) -> pd.Series:
    """'2010-11' -> a real date, so chart axes order and label months properly."""
    return pd.to_datetime(months + "-01")


def style(fig: go.Figure, money: bool = True) -> go.Figure:
    """Shared look for every chart."""
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), legend_title_text="")
    if money:
        fig.update_yaxes(tickprefix="£", tickformat=",.0f")
    return fig


# ---------- Data ----------
monthly = load_csv("monthly")
backtest = load_csv("backtest")
scores = load_csv("scores")
forecast = load_csv("forecast")
products = load_csv("products")
countries = load_csv("countries")
cancellations = load_csv("cancellations")
meta = dict(zip(*load_csv("meta").T.values))      # {"sale_lines": ..., "customers_with_id": ...}

# ---------- Sidebar ----------
st.sidebar.header("Controls")
basis_label = st.sidebar.radio(
    "Sales basis", ["Net sales", "Gross sales"],
    help="Gross counts every valid sale line. Net removes lines that a later cancellation "
         "undid in full (matched on customer, product, quantity and price).")
basis = "net" if basis_label == "Net sales" else "gross"

all_months = sorted(monthly["month"].unique())
start, end = st.sidebar.select_slider("Months shown", options=all_months,
                                      value=(all_months[0], all_months[-1]))
st.sidebar.caption("December 2011 is excluded: the data ends on 9 December, "
                   "so that month is incomplete.")

series_all = monthly[monthly["basis"] == basis]
series = series_all[(series_all["month"] >= start) & (series_all["month"] <= end)]

# ---------- Header and headline numbers ----------
st.title("E-commerce Analytics and Forecasting")
st.write("Two years of transactions from a UK online gift retailer: what sells, where, "
         "when, and what the next months may look like.")

revenue = series["revenue"].sum()
orders = series["orders"].sum()
best_month = series.loc[series["revenue"].idxmax()]

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"Revenue ({basis_label.lower()})", gbp(revenue))
c2.metric("Orders", f"{orders:,}")
c3.metric("Average order value", gbp(revenue / orders))
c4.metric("Best month", best_month["month"], gbp(best_month["revenue"]), delta_color="off")

tab_overview, tab_forecast, tab_markets, tab_notes = st.tabs(
    ["Overview", "Forecast", "Products and markets", "Data notes"])

# ---------- Tab 1: Overview ----------
with tab_overview:
    st.subheader("Monthly revenue")
    fig = px.line(series, x=to_date(series["month"]), y="revenue", markers=True,
                  labels={"x": "Month", "revenue": "Revenue"})
    st.plotly_chart(style(fig))

    left, right = st.columns(2)
    with left:
        st.subheader("Seasonality: year over year")
        yoy = series.assign(date=to_date(series["month"]))
        yoy["Year"] = yoy["date"].dt.year.astype(str)
        yoy["Month"] = yoy["date"].dt.strftime("%b")
        fig = px.line(yoy, x="Month", y="revenue", color="Year", markers=True,
                      category_orders={"Month": MONTH_NAMES}, labels={"revenue": "Revenue"})
        st.plotly_chart(style(fig))
        st.caption("Sales build from September, peak in November, and fall in December.")
    with right:
        st.subheader("Share of invoices cancelled")
        canc = cancellations[(cancellations["month"] >= start) & (cancellations["month"] <= end)]
        fig = px.bar(canc, x=to_date(canc["month"]), y="cancel_rate_pct",
                     labels={"x": "Month", "cancel_rate_pct": "Cancelled (%)"})
        st.plotly_chart(style(fig, money=False))
        st.caption("Cancellations are steady at roughly 12% to 18% of invoices.")

# ---------- Tab 2: Forecast ----------
with tab_forecast:
    bt = backtest[backtest["basis"] == basis]
    sc = scores[scores["basis"] == basis].sort_values("MAE")
    fc = forecast[forecast["basis"] == basis]
    best = sc.iloc[0]["model"]
    naive_row = sc[sc["model"] == "naive"].iloc[0]

    st.subheader("Forecast for the next three months")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=to_date(series_all["month"]), y=series_all["revenue"],
                             mode="lines+markers", name="Actual"))
    fig.add_trace(go.Scatter(x=to_date(bt["month"]), y=bt[best], mode="lines",
                             line=dict(dash="dot"), name=f"Backtest: {MODEL_LABELS[best].lower()}"))
    fx = to_date(fc["month"])
    fig.add_trace(go.Scatter(x=fx, y=fc["high_90pct"], mode="lines", line=dict(width=0),
                             showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=fx, y=fc["low_10pct"], mode="lines", line=dict(width=0),
                             fill="tonexty", fillcolor="rgba(120, 120, 255, 0.25)",
                             name="Rough 80% range"))
    fig.add_trace(go.Scatter(x=fx, y=fc["forecast"], mode="lines+markers",
                             line=dict(dash="dash"), name="Forecast"))
    fig.update_yaxes(title_text="Revenue")
    st.plotly_chart(style(fig))

    m1, m2, m3 = st.columns(3)
    m1.metric("Best model", MODEL_LABELS[best])
    m2.metric("Its average error (MAPE)", f"{sc.iloc[0]['MAPE_%']:.1f}%")
    m3.metric("Repeat-last-month error", f"{naive_row['MAPE_%']:.1f}%")

    table = fc[["month", "forecast", "low_10pct", "high_90pct"]].rename(columns={
        "month": "Month", "forecast": "Forecast (£)",
        "low_10pct": "Low (£)", "high_90pct": "High (£)"})
    st.dataframe(table.round(0), hide_index=True)

    st.subheader("How the models compare")
    comparison = sc.assign(model=sc["model"].map(MODEL_LABELS))[["model", "MAE", "RMSE", "MAPE_%"]]
    comparison.columns = ["Model", "Average miss (£)", "RMSE (£)", "Average miss (%)"]
    st.dataframe(comparison.round(1), hide_index=True)
    # The wording follows the actual winner, so the page never states something the data does not show.
    verdict = (f"The best performer was '{MODEL_LABELS[best].lower()}'. "
               + ("With only 24 months of history, reusing last year's pattern is hard to beat, "
                  "so the forecast is last year's pattern. " if best == "seasonal_naive" else ""))
    st.info(
        "Each model was tested one month ahead, from December 2010 to November 2011, seeing only "
        "earlier months. " + verdict + "The range comes from only 12 test errors, so treat it as "
        "indicative. A richer model needs more history.")

# ---------- Tab 3: Products and markets ----------
with tab_markets:
    st.caption("Net sales, December 2009 to November 2011. These two charts ignore the month slider.")
    left, right = st.columns(2)
    with left:
        st.subheader("Top 15 products by revenue")
        fig = px.bar(products.sort_values("revenue"), x="revenue", y="description",
                     orientation="h", hover_data=["stock_code", "units", "share_pct"],
                     labels={"revenue": "Revenue", "description": ""})
        fig.update_xaxes(tickprefix="£", tickformat=",.0f")
        fig.update_layout(margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig)
    with right:
        st.subheader("Top 10 countries by revenue")
        fig = px.bar(countries.sort_values("revenue"), x="revenue", y="country",
                     orientation="h", hover_data=["orders", "share_pct"],
                     labels={"revenue": "Revenue", "country": ""})
        fig.update_xaxes(tickprefix="£", tickformat=",.0f")
        fig.update_layout(margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig)
        uk = countries[countries["country"] == "United Kingdom"]
        if not uk.empty:
            st.caption(f"The United Kingdom accounts for {uk.iloc[0]['share_pct']}% of revenue.")

# ---------- Tab 4: Data notes ----------
with tab_notes:
    st.markdown(f"""
**Data.** Online Retail II, UCI Machine Learning Repository, licensed CC BY 4.0.
Chen, D. (2012). Online Retail II [Dataset]. https://doi.org/10.24432/C5CG6D

**Scope.** {int(meta['sale_lines']):,} sale lines, {int(meta['customers_with_id']):,} customers with an ID,
{int(meta['products']):,} products and {int(meta['countries'])} countries,
from {meta['first_month']} to {meta['last_month']}.

**Cleaning.**
- Exact duplicate rows (an overlap between the two source sheets) were removed.
- Cancellations, non-product codes (postage, fees, adjustments) and zero or negative prices were
  flagged and excluded from sales.
- *Net sales* also removes sale lines that a later cancellation undid in full, matched on customer,
  product, quantity and unit price. The match is approximate, and guest checkouts cannot be matched.

**Known limits.**
- December 2011 is incomplete and is left out.
- One June 2011 line (60 items at £649.50, £38,970) has no cancellation in the data and is kept.
- The first month of data makes every customer look new, so new-customer counts are not shown.
- Only 24 months of history: forecasts are indicative.

**Privacy.** Customer IDs are anonymous numbers in the source. They are not shown here, and no
attempt is made to identify anyone.

Source code and method: [GitHub repository]({REPO_URL})
""")

st.divider()
st.caption(f"Built by Anade A’Acharo · [Portfolio]({PORTFOLIO_URL}) · [Source code]({REPO_URL})")
