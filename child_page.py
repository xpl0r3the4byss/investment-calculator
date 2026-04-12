"""
Shared renderer for individual child account pages.
Each page in pages/ calls render_child_page() with its child config.
"""

import os
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from calculator import (
    calculate_acorns_dca,
    calculate_acorns_from_schedule,
    should_have_invested,
)
from children_config import ACORNS_EARLY_PORTFOLIO, MONTHLY_TARGET

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _load_schedule(data_file: str, birth_date: date) -> pd.DataFrame:
    """Load investment history from CSV, or return a starter row."""
    if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
        df = pd.read_csv(data_file)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["amount"] = df["amount"].astype(float)
        if "notes" not in df.columns:
            df["notes"] = ""
        return df[["date", "amount", "notes"]]
    # Default: just the birthday deposit
    return pd.DataFrame({
        "date":   [birth_date],
        "amount": [MONTHLY_TARGET],
        "notes":  ["Birthday"],
    })


def _to_schedule(df: pd.DataFrame) -> list[tuple[date, float]]:
    """Convert an edited dataframe to a list of (date, amount) pairs."""
    pairs = []
    for _, row in df.iterrows():
        d = row["date"]
        if hasattr(d, "date"):        # datetime → date
            d = d.date()
        elif isinstance(d, str):
            d = date.fromisoformat(d)
        pairs.append((d, float(row["amount"])))
    return sorted(pairs, key=lambda x: x[0])


def render_child_page(child: dict) -> None:
    name       = child["name"]
    birth_date = child["birth_date"]
    data_file  = os.path.join(DATA_DIR, f"{name.lower()}.csv")
    today      = date.today()

    # ---- Header ----
    age = today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )
    bday_21     = date(birth_date.year + 21, birth_date.month, birth_date.day)
    yrs_to_21   = max(0, bday_21.year - today.year - (
        (today.month, today.day) < (bday_21.month, bday_21.day)
    ))
    months_to_21 = max(0, (bday_21.year - today.year) * 12 + (bday_21.month - today.month))

    st.title(f"{name}'s Acorns Early Account")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Born",        birth_date.strftime("%b %d, %Y"))
    c2.metric("Age",         f"{age} yrs")
    c3.metric("Years to 21", str(yrs_to_21))
    c4.metric("21st Birthday", bday_21.strftime("%b %d, %Y"))

    st.divider()

    # ---- Investment history ----
    st.subheader("Investment History")
    st.caption(
        "Enter every deposit you have made or plan to make. "
        "Click **Save** to persist changes between sessions."
    )

    os.makedirs(DATA_DIR, exist_ok=True)
    saved_df = _load_schedule(data_file, birth_date)

    edited_df = st.data_editor(
        saved_df,
        column_config={
            "date":   st.column_config.DateColumn("Date", format="YYYY-MM-DD", required=True),
            "amount": st.column_config.NumberColumn("Amount ($)", format="$%.2f", min_value=0.01, required=True),
            "notes":  st.column_config.TextColumn("Notes"),
        },
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
    )

    btn_col1, btn_col2, _ = st.columns([1, 1, 5])
    save = btn_col1.button("Save", use_container_width=True)
    run  = btn_col2.button("Calculate", type="primary", use_container_width=True)

    if save:
        clean = edited_df.dropna(subset=["date", "amount"])
        clean.to_csv(data_file, index=False)
        st.success("Saved!")

    if not run:
        st.stop()

    # ---- Build schedule from edited table ----
    clean_df = edited_df.dropna(subset=["date", "amount"]).copy()
    if clean_df.empty:
        st.warning("No investments to calculate.")
        st.stop()

    schedule = _to_schedule(clean_df)

    # ---- Fetch data ----
    progress = st.progress(0, text="Calculating actual portfolio…")
    actual = calculate_acorns_from_schedule(ACORNS_EARLY_PORTFOLIO, schedule, today)
    progress.progress(60, text="Calculating target portfolio…")
    target = calculate_acorns_dca(
        ACORNS_EARLY_PORTFOLIO, MONTHLY_TARGET, birth_date, today, birthday_mode=True
    )
    progress.empty()

    if actual is None:
        st.error("Could not fetch price data for the investment dates — check your dates.")
        st.stop()

    if actual.get("errors"):
        st.warning(f"Could not fetch data for: {', '.join(actual['errors'])}")

    # ---- Summary metrics ----
    st.subheader("Summary")

    target_invested = target["total_invested"] if target else should_have_invested(birth_date, MONTHLY_TARGET, today)
    target_value    = target["final_value"]    if target else 0.0
    target_gain     = target["gain"]           if target else 0.0
    target_gain_pct = target["gain_pct"]       if target else 0.0

    principal_gap = round(max(0.0, target_invested - actual["total_invested"]), 2)
    value_gap     = round(max(0.0, target_value    - actual["final_value"]),    2)

    col_a, col_t, col_g = st.columns(3)

    with col_a:
        st.markdown("**Actual**")
        st.metric("Invested",      f"${actual['total_invested']:,.2f}")
        st.metric("Current Value", f"${actual['final_value']:,.2f}")
        st.metric("Gain / Loss",   f"${actual['gain']:,.2f}",
                  delta=f"{actual['gain_pct']:.1f}%")

    with col_t:
        st.markdown(f"**Target (${MONTHLY_TARGET:.0f}/mo from birth)**")
        st.metric("Invested",      f"${target_invested:,.2f}")
        st.metric("Current Value", f"${target_value:,.2f}")
        st.metric("Gain / Loss",   f"${target_gain:,.2f}",
                  delta=f"{target_gain_pct:.1f}%")

    with col_g:
        st.markdown("**Gap**")
        st.metric("Principal Behind", f"${principal_gap:,.2f}",
                  delta=f"-${principal_gap:,.2f}" if principal_gap > 0 else "Caught up",
                  delta_color="inverse")
        st.metric("Value Behind",     f"${value_gap:,.2f}",
                  delta=f"-${value_gap:,.2f}" if value_gap > 0 else "Caught up",
                  delta_color="inverse")
        st.metric("Months to 21",     str(months_to_21))

    # ---- Chart ----
    st.subheader("Portfolio Value Over Time")

    fig = go.Figure()

    # Actual portfolio value
    act_purch = actual["purchases"]
    fig.add_trace(go.Scatter(
        x=act_purch["date"],
        y=act_purch["portfolio_value"],
        mode="lines",
        name="Actual Value",
        line=dict(color="#2196F3", width=2),
        hovertemplate="Actual value: $%{y:,.2f}<extra></extra>",
    ))

    # Cumulative actual invested (step function on deposit dates)
    sorted_df  = clean_df.sort_values("date")
    cum_amounts = sorted_df["amount"].cumsum().tolist()
    fig.add_trace(go.Scatter(
        x=list(sorted_df["date"]),
        y=cum_amounts,
        mode="lines",
        name="Actual Invested",
        line=dict(color="#2196F3", width=1, dash="dot"),
        hovertemplate="Actual invested: $%{y:,.2f}<extra></extra>",
    ))

    if target:
        tgt_purch = target["purchases"]
        # Target portfolio value
        fig.add_trace(go.Scatter(
            x=tgt_purch["date"],
            y=tgt_purch["portfolio_value"],
            mode="lines",
            name="Target Value",
            line=dict(color="#4CAF50", width=2),
            hovertemplate="Target value: $%{y:,.2f}<extra></extra>",
        ))
        # Cumulative target invested
        fig.add_trace(go.Scatter(
            x=tgt_purch["date"],
            y=[(i + 1) * MONTHLY_TARGET for i in range(len(tgt_purch))],
            mode="lines",
            name="Target Invested",
            line=dict(color="#4CAF50", width=1, dash="dot"),
            hovertemplate="Target invested: $%{y:,.2f}<extra></extra>",
        ))

    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Value (USD)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=420,
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ---- Actual purchase breakdown ----
    with st.expander("Actual deposit breakdown"):
        disp = clean_df[["date", "amount", "notes"]].copy()
        disp.insert(2, "cum_invested", disp["amount"].cumsum())
        disp.columns = ["Date", "Amount ($)", "Cumulative Invested ($)", "Notes"]
        disp["Amount ($)"]             = disp["Amount ($)"].map("${:,.2f}".format)
        disp["Cumulative Invested ($)"] = disp["Cumulative Invested ($)"].map("${:,.2f}".format)
        st.dataframe(disp, use_container_width=True, hide_index=True)
