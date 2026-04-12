"""
ETF Dollar-Cost Averaging Calculator — Streamlit UI
Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date

from calculator import (
    calculate_dca,
    calculate_acorns_dca,
    generate_catchup_plan,
    should_have_invested,
    ACORNS_PORTFOLIOS,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ETF DCA Calculator",
    page_icon="📈",
    layout="wide",
)

st.title("ETF Dollar-Cost Averaging Calculator")

# ---------------------------------------------------------------------------
# Sidebar — mode first, then mode-specific inputs
# ---------------------------------------------------------------------------
st.sidebar.header("Settings")

mode = st.sidebar.radio(
    "Mode",
    ["Custom ETFs", "Acorns Portfolio", "Catch-up Planner"],
)

# ---- DCA modes ----
if mode in ("Custom ETFs", "Acorns Portfolio"):
    st.sidebar.markdown("---")
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

    if mode == "Custom ETFs":
        tickers_input = st.sidebar.text_input(
            "ETF tickers (comma-separated)",
            value="SMH, SOXX, VGT",
        )
    else:
        acorns_portfolio = st.sidebar.selectbox(
            "Acorns portfolio",
            options=list(ACORNS_PORTFOLIOS.keys()),
        )
        weights = ACORNS_PORTFOLIOS[acorns_portfolio]
        st.sidebar.caption(
            "Allocation: " + ", ".join(f"{t} {w*100:.0f}%" for t, w in weights.items())
        )

    if start_date >= end_date:
        st.sidebar.error("Start date must be before end date.")
        st.stop()

    if mode == "Custom ETFs":
        tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
        if not tickers:
            st.sidebar.error("Enter at least one ticker.")
            st.stop()

    st.sidebar.markdown("---")
    if mode == "Custom ETFs":
        st.sidebar.markdown(
            "**Default ETFs** are the top 3 performers (Aug 2015 – Apr 2026):\n"
            "- **SMH** — VanEck Semiconductor (~1,450% total return)\n"
            "- **SOXX** — iShares Semiconductor (~1,090%)\n"
            "- **VGT** — Vanguard Information Technology (~620%)"
        )
    else:
        st.sidebar.markdown(
            "Acorns splits your monthly investment across its constituent ETFs "
            "by the target weights shown above."
        )

# ---- Catch-up Planner mode ----
else:
    st.sidebar.markdown("---")
    monthly_budget = st.sidebar.number_input(
        "Total monthly budget ($)",
        min_value=1.0,
        max_value=10_000.0,
        value=100.0,
        step=5.0,
        format="%.2f",
    )
    ongoing_per_child = st.sidebar.number_input(
        "Ongoing contribution per child ($/mo)",
        min_value=1.0,
        max_value=1_000.0,
        value=5.0,
        step=1.0,
        format="%.2f",
    )
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "Edit the children table to match your current account values. "
        "**Target Value** is what the account *should* be worth today — "
        "get the latest figure from the **Acorns Portfolio** mode."
    )

run = st.sidebar.button("Calculate", type="primary", use_container_width=True)

# ===========================================================================
# CATCH-UP PLANNER
# ===========================================================================
if mode == "Catch-up Planner":
    st.markdown(
        "Track your progress catching up on missed contributions for each child. "
        "Edit the table to reflect current account values, then click **Calculate**."
    )

    default_children = pd.DataFrame([
        {"Name": "Easton",  "Birth Date": date(2015,  8, 25), "Monthly ($)": 5.0, "Invested ($)": 305.0,  "Current Value ($)": 435.17,  "Target Value ($)": 1311.34},
        {"Name": "Ava",     "Birth Date": date(2018,  1, 12), "Monthly ($)": 5.0, "Invested ($)": 235.0,  "Current Value ($)": 339.60,  "Target Value ($)":  870.53},
        {"Name": "Millie",  "Birth Date": date(2019, 10, 29), "Monthly ($)": 5.0, "Invested ($)": 195.0,  "Current Value ($)": 279.58,  "Target Value ($)":  617.39},
        {"Name": "Michael", "Birth Date": date(2021,  1, 11), "Monthly ($)": 5.0, "Invested ($)": 165.0,  "Current Value ($)": 116.17,  "Target Value ($)":  458.16},
        {"Name": "Trip",    "Birth Date": date(2022,  7, 12), "Monthly ($)": 5.0, "Invested ($)": 125.0,  "Current Value ($)": 178.55,  "Target Value ($)":  313.43},
    ])

    children_df = st.data_editor(
        default_children,
        column_config={
            "Name": st.column_config.TextColumn("Name"),
            "Birth Date": st.column_config.DateColumn("Birth Date", format="YYYY-MM-DD"),
            "Monthly ($)": st.column_config.NumberColumn("Monthly ($)", format="$%.2f", min_value=1.0),
            "Invested ($)": st.column_config.NumberColumn("Invested ($)", format="$%.2f", min_value=0.0),
            "Current Value ($)": st.column_config.NumberColumn("Current Value ($)", format="$%.2f", min_value=0.0),
            "Target Value ($)": st.column_config.NumberColumn("Target Value ($)", format="$%.2f", min_value=0.0),
        },
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
    )

    if not run:
        st.info("Adjust the table and budget in the sidebar, then click **Calculate**.")
        st.stop()

    today = date.today()

    # -----------------------------------------------------------------------
    # Gap analysis
    # -----------------------------------------------------------------------
    st.subheader("Gap Analysis")

    gap_rows = []
    catchup_children = []

    for _, row in children_df.iterrows():
        name = str(row["Name"])
        bdate = row["Birth Date"]
        monthly = float(row["Monthly ($)"])
        invested = float(row["Invested ($)"])
        current_val = float(row["Current Value ($)"])
        target_val = float(row["Target Value ($)"])

        age = today.year - bdate.year - ((today.month, today.day) < (bdate.month, bdate.day))
        yrs_to_21 = max(0, 21 - age)
        bday_21 = date(bdate.year + 21, bdate.month, bdate.day)
        months_to_21 = max(0, (bday_21.year - today.year) * 12 + (bday_21.month - today.month))

        should_inv = should_have_invested(bdate, monthly, today)
        principal_gap = round(max(0.0, should_inv - invested), 2)
        value_gap = round(max(0.0, target_val - current_val), 2)

        gap_rows.append({
            "Name": name,
            "Age": age,
            "Yrs to 21": yrs_to_21,
            "months_to_21": months_to_21,
            "Should Have Invested": f"${should_inv:,.2f}",
            "Actually Invested": f"${invested:,.2f}",
            "Principal Gap": f"${principal_gap:,.2f}",
            "Target Value": f"${target_val:,.2f}",
            "Current Value": f"${current_val:,.2f}",
            "Value Gap": f"${value_gap:,.2f}",
        })

        catchup_children.append({
            "name": name,
            "birth_date": bdate,
            "principal_gap": principal_gap,
            "months_to_21": months_to_21,
        })

    display_cols = ["Name", "Age", "Yrs to 21", "Should Have Invested",
                    "Actually Invested", "Principal Gap",
                    "Target Value", "Current Value", "Value Gap"]
    st.dataframe(pd.DataFrame(gap_rows)[display_cols], use_container_width=True, hide_index=True)

    total_principal_gap = sum(c["principal_gap"] for c in catchup_children)
    total_value_gap = sum(
        max(0.0, float(r["Target Value ($)"]) - float(r["Current Value ($)"]))
        for _, r in children_df.iterrows()
    )
    col1, col2 = st.columns(2)
    col1.metric("Total Principal Gap", f"${total_principal_gap:,.2f}")
    col2.metric("Total Value Gap (Phase 2)", f"${total_value_gap:,.2f}")

    # -----------------------------------------------------------------------
    # Phase 1: Principal catch-up plan
    # -----------------------------------------------------------------------
    st.subheader("Phase 1 — Close the Principal Gap")

    plan = generate_catchup_plan(catchup_children, monthly_budget, ongoing_per_child)

    n_children = len(children_df)
    ongoing_total = ongoing_per_child * n_children

    if plan is None:
        st.error(
            f"Your budget of ${monthly_budget:,.2f}/month doesn't cover the ongoing contributions "
            f"(${ongoing_total:,.2f}/month for {n_children} children). Increase your budget."
        )
        st.stop()

    st.markdown(
        f"**Monthly budget:** ${monthly_budget:,.2f} — "
        f"${ongoing_total:,.2f} ongoing ({n_children} × ${ongoing_per_child:,.2f}) + "
        f"**${plan['catch_up_budget']:,.2f} catch-up**"
    )

    # Summary: when does each gap close?
    summary_rows = []
    for child in catchup_children:
        name = child["name"]
        gap = child["principal_gap"]
        months_to_21 = child["months_to_21"]
        close = plan["close_months"].get(name)

        if gap <= 0:
            close_str, months_str, note = "Already caught up", "0", ""
        elif close:
            months_away = (close.year - today.year) * 12 + (close.month - today.month)
            close_str = close.strftime("%b %Y")
            months_str = str(months_away)
            note = " ⚠️ after 21st birthday" if months_away > months_to_21 else ""
        else:
            close_str, months_str, note = "> 20 years", "240+", " ⚠️"

        summary_rows.append({
            "Name": name,
            "Principal Gap": f"${gap:,.2f}",
            "Gap Closes": close_str + note,
            "Months Away": months_str,
        })

    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    # Remaining gap chart
    st.markdown("**Remaining principal gap over time**")
    got = plan["gap_over_time"]
    fig = go.Figure()
    for name in plan["priority_order"]:
        if name in got.columns:
            fig.add_trace(go.Scatter(
                x=got["month"],
                y=got[name],
                mode="lines",
                name=name,
                hovertemplate=f"<b>{name}</b><br>%{{x|%b %Y}}<br>Remaining: $%{{y:,.2f}}<extra></extra>",
            ))
    fig.update_layout(
        xaxis_title="Month",
        yaxis_title="Remaining Principal Gap ($)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=350,
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Month-by-month breakdown
    with st.expander("Month-by-month allocation breakdown"):
        names_ordered = plan["priority_order"]
        rows = []
        for rec in plan["monthly_records"]:
            row = {"Month": rec["month"].strftime("%b %Y")}
            for name in names_ordered:
                alloc = rec["allocations"].get(name, 0.0)
                row[f"{name} (+)"] = f"${alloc:,.2f}" if alloc else "—"
            for name in names_ordered:
                rem = rec["remaining"].get(name, 0.0)
                row[f"{name} gap"] = f"${rem:,.2f}"
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # -----------------------------------------------------------------------
    # Phase 2 preview: value gap
    # -----------------------------------------------------------------------
    st.subheader("Phase 2 Preview — Value Gap")
    st.markdown(
        "After the principal gap is closed, this is the gap between what each account "
        "*should* be worth and its actual current value. Once you've caught up on principal, "
        "re-run the **Acorns Portfolio** mode to get a fresh target and calculate the "
        "extra monthly investment needed to close this gap."
    )

    phase2_rows = []
    for _, row in children_df.iterrows():
        target = float(row["Target Value ($)"])
        current = float(row["Current Value ($)"])
        vgap = round(max(0.0, target - current), 2)
        phase2_rows.append({
            "Name": row["Name"],
            "Target Value Today": f"${target:,.2f}",
            "Actual Value Today": f"${current:,.2f}",
            "Value Gap": f"${vgap:,.2f}",
        })
    st.dataframe(pd.DataFrame(phase2_rows), use_container_width=True, hide_index=True)
    st.caption(f"Total value gap across all children: ${total_value_gap:,.2f}")

# ===========================================================================
# ACORNS PORTFOLIO MODE
# ===========================================================================
elif mode == "Acorns Portfolio":
    st.markdown(
        "Calculates the outcome of investing a fixed amount every month into an Acorns portfolio, "
        "using historical adjusted closing prices from Yahoo Finance."
    )

    if not run:
        st.info("Adjust the settings in the sidebar, then click **Calculate**.")
        st.stop()

    progress = st.progress(0, text="Fetching data…")
    acorns_result = calculate_acorns_dca(acorns_portfolio, monthly_amount, start_date, end_date)
    progress.empty()

    if acorns_result is None:
        st.error("Could not fetch data — check your date range.")
        st.stop()

    if acorns_result["errors"]:
        st.warning(f"Could not fetch data for: {', '.join(acorns_result['errors'])}")

    r = acorns_result

    st.subheader("Summary")
    st.dataframe(pd.DataFrame([{
        "Portfolio": r["portfolio_name"],
        "Monthly Investment": f"${monthly_amount:,.2f}",
        "Months Invested": len(r["purchases"]),
        "Total Invested": f"${r['total_invested']:,.2f}",
        "Final Value": f"${r['final_value']:,.2f}",
        "Gain / Loss": f"${r['gain']:,.2f}",
        "Return %": f"{r['gain_pct']:,.1f}%",
    }]), use_container_width=True, hide_index=True)

    st.subheader("Holdings Breakdown")
    holdings_rows = []
    for ticker, hr in r["holdings"].items():
        weight = ACORNS_PORTFOLIOS[acorns_portfolio][ticker]
        holdings_rows.append({
            "Ticker": ticker,
            "Weight": f"{weight*100:.0f}%",
            "Monthly Allocated": f"${monthly_amount * weight:,.2f}",
            "Total Invested": f"${hr['total_invested']:,.2f}",
            "Final Value": f"${hr['final_value']:,.2f}",
            "Gain / Loss": f"${hr['gain']:,.2f}",
            "Return %": f"{hr['gain_pct']:,.1f}%",
        })
    st.dataframe(pd.DataFrame(holdings_rows), use_container_width=True, hide_index=True)

    st.subheader("Portfolio Value Over Time")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=r["purchases"]["date"],
        y=r["purchases"]["portfolio_value"],
        mode="lines",
        name=acorns_portfolio,
        hovertemplate="Date: %{x}<br>Portfolio value: $%{y:,.2f}<extra></extra>",
    ))
    invested_vals = [(i + 1) * monthly_amount for i in range(len(r["purchases"]))]
    fig.add_trace(go.Scatter(
        x=r["purchases"]["date"],
        y=invested_vals,
        mode="lines",
        name="Amount Invested",
        line=dict(dash="dash", color="gray"),
        hovertemplate="Amount Invested: $%{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Value (USD)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=450,
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

# ===========================================================================
# CUSTOM ETFs MODE
# ===========================================================================
else:
    st.markdown(
        "Calculates the outcome of investing a fixed amount every month into one or more ETFs, "
        "using historical adjusted closing prices from Yahoo Finance."
    )

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

    st.subheader("Summary")
    summary_rows = []
    for ticker, r in results.items():
        summary_rows.append({
            "Ticker": ticker,
            "Monthly Investment": f"${monthly_amount:,.2f}",
            "Months Invested": len(r["purchases"]),
            "Total Invested": f"${r['total_invested']:,.2f}",
            "Final Value": f"${r['final_value']:,.2f}",
            "Gain / Loss": f"${r['gain']:,.2f}",
            "Return %": f"{r['gain_pct']:,.1f}%",
        })
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    st.subheader("Portfolio Value Over Time")
    fig = go.Figure()
    for ticker, r in results.items():
        df = r["purchases"]
        fig.add_trace(go.Scatter(
            x=df["date"],
            y=df["portfolio_value"],
            mode="lines",
            name=ticker,
            hovertemplate=(
                f"<b>{ticker}</b><br>"
                "Date: %{x}<br>"
                "Portfolio value: $%{y:,.2f}<extra></extra>"
            ),
        ))

    first_r = next(iter(results.values()))
    invested_df = first_r["purchases"][["date"]].copy()
    invested_df["total_invested"] = [(i + 1) * monthly_amount for i in range(len(invested_df))]
    fig.add_trace(go.Scatter(
        x=invested_df["date"],
        y=invested_df["total_invested"],
        mode="lines",
        name="Amount Invested",
        line=dict(dash="dash", color="gray"),
        hovertemplate="Amount Invested: $%{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Value (USD)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=450,
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Monthly Purchase Breakdown")
    for ticker, r in results.items():
        with st.expander(f"{ticker} — {len(r['purchases'])} purchases"):
            df = r["purchases"].copy()
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df.columns = ["Date", "Price ($)", "Shares Bought", "Cumulative Shares", "Portfolio Value ($)"]
            df["Price ($)"] = df["Price ($)"].map("${:,.4f}".format)
            df["Portfolio Value ($)"] = df["Portfolio Value ($)"].map("${:,.2f}".format)
            st.dataframe(df, use_container_width=True, hide_index=True)
