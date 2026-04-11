"""
ETF Dollar-Cost Averaging Calculator — Streamlit UI
Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date

from calculator import calculate_dca

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ETF DCA Calculator",
    page_icon="📈",
    layout="wide",
)

st.title("ETF Dollar-Cost Averaging Calculator")
st.markdown(
    "Calculates the outcome of investing a fixed amount every month into one or more ETFs, "
    "using historical adjusted closing prices from Yahoo Finance."
)

# ---------------------------------------------------------------------------
# Sidebar inputs
# ---------------------------------------------------------------------------
st.sidebar.header("Settings")

monthly_amount = st.sidebar.number_input(
    "Monthly investment ($)",
    min_value=1.0,
    max_value=1_000_000.0,
    value=5.0,
    step=1.0,
    format="%.2f",
)

start_date = st.sidebar.date_input(
    "Start date",
    value=date(2015, 8, 25),
    min_value=date(2000, 1, 1),
    max_value=date.today(),
)

end_date = st.sidebar.date_input(
    "End date",
    value=date.today(),
    min_value=date(2000, 1, 2),
    max_value=date.today(),
)

tickers_input = st.sidebar.text_input(
    "ETF tickers (comma-separated)",
    value="SMH, SOXX, VGT",
)

if start_date >= end_date:
    st.sidebar.error("Start date must be before end date.")
    st.stop()

tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
if not tickers:
    st.sidebar.error("Enter at least one ticker.")
    st.stop()

run = st.sidebar.button("Calculate", type="primary", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Default ETFs** are the top 3 performers (Aug 2015 – Apr 2026):\n"
    "- **SMH** — VanEck Semiconductor (~1,450% total return)\n"
    "- **SOXX** — iShares Semiconductor (~1,090%)\n"
    "- **VGT** — Vanguard Information Technology (~620%)"
)

# ---------------------------------------------------------------------------
# Calculation
# ---------------------------------------------------------------------------
if not run:
    st.info("Adjust the settings in the sidebar, then click **Calculate**.")
    st.stop()

results = {}
errors = []

progress = st.progress(0, text="Fetching data…")
for i, ticker in enumerate(tickers):
    progress.progress((i + 1) / len(tickers), text=f"Fetching {ticker}…")
    result = calculate_dca(ticker, monthly_amount, start_date, end_date)
    if result:
        results[ticker] = result
    else:
        errors.append(ticker)

progress.empty()

if errors:
    st.warning(f"Could not fetch data for: {', '.join(errors)}")

if not results:
    st.error("No results — check your tickers and date range.")
    st.stop()

# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------
st.subheader("Summary")

summary_rows = []
for ticker, r in results.items():
    summary_rows.append(
        {
            "Ticker": ticker,
            "Monthly Investment": f"${monthly_amount:,.2f}",
            "Months Invested": len(r["purchases"]),
            "Total Invested": f"${r['total_invested']:,.2f}",
            "Final Value": f"${r['final_value']:,.2f}",
            "Gain / Loss": f"${r['gain']:,.2f}",
            "Return %": f"{r['gain_pct']:,.1f}%",
        }
    )

summary_df = pd.DataFrame(summary_rows)
st.dataframe(summary_df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Portfolio growth chart
# ---------------------------------------------------------------------------
st.subheader("Portfolio Value Over Time")

fig = go.Figure()
for ticker, r in results.items():
    df = r["purchases"]
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["portfolio_value"],
            mode="lines",
            name=ticker,
            hovertemplate=(
                f"<b>{ticker}</b><br>"
                "Date: %{x}<br>"
                "Portfolio value: $%{y:,.2f}<extra></extra>"
            ),
        )
    )

# Add "total invested" reference line (same for all tickers)
first_r = next(iter(results.values()))
invested_df = first_r["purchases"][["date"]].copy()
invested_df["total_invested"] = [
    (i + 1) * monthly_amount for i in range(len(invested_df))
]
fig.add_trace(
    go.Scatter(
        x=invested_df["date"],
        y=invested_df["total_invested"],
        mode="lines",
        name="Amount Invested",
        line=dict(dash="dash", color="gray"),
        hovertemplate="Amount Invested: $%{y:,.2f}<extra></extra>",
    )
)

fig.update_layout(
    xaxis_title="Date",
    yaxis_title="Value (USD)",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    height=450,
    margin=dict(l=0, r=0, t=10, b=0),
)
st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Monthly breakdown (per ticker, in expanders)
# ---------------------------------------------------------------------------
st.subheader("Monthly Purchase Breakdown")

for ticker, r in results.items():
    with st.expander(f"{ticker} — {len(r['purchases'])} purchases"):
        df = r["purchases"].copy()
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df.columns = ["Date", "Price ($)", "Shares Bought", "Cumulative Shares", "Portfolio Value ($)"]
        df["Price ($)"] = df["Price ($)"].map("${:,.4f}".format)
        df["Portfolio Value ($)"] = df["Portfolio Value ($)"].map("${:,.2f}".format)
        st.dataframe(df, use_container_width=True, hide_index=True)
