"""
Shared renderer for individual child account pages.
Each page in pages/ calls render_child_page() with its child config.
"""

import os
import re
from datetime import date, datetime

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


def _parse_date_str(s: str) -> date | None:
    """
    Parse a date string typed by the user. Accepts:
      073126        → 07/31/2026  (MMDDYY)
      07312026      → 07/31/2026  (MMDDYYYY)
      07/31/26      → 07/31/2026
      07/31/2026    → 07/31/2026
      07-31-26      → 07/31/2026
      2026-07-31    → 07/31/2026  (ISO, used internally)
    """
    if not s or not str(s).strip():
        return None
    s = str(s).strip()

    # 6 digits: MMDDYY
    if re.fullmatch(r"\d{6}", s):
        try:
            return date(2000 + int(s[4:6]), int(s[0:2]), int(s[2:4]))
        except ValueError:
            return None

    # 8 digits: MMDDYYYY
    if re.fullmatch(r"\d{8}", s):
        try:
            return date(int(s[4:8]), int(s[0:2]), int(s[2:4]))
        except ValueError:
            return None

    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%m-%d-%y", "%m-%d-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    return None


def _load_schedule(data_file: str) -> pd.DataFrame:
    """Load transaction history from CSV as strings, or return an empty table."""
    if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
        df = pd.read_csv(data_file, dtype=str).fillna("")
        # Normalise date strings to ISO format for consistent display
        df["date"] = df["date"].apply(
            lambda s: _parse_date_str(s).strftime("%Y-%m-%d") if _parse_date_str(s) else s
        )
        if "type" not in df.columns:
            df["type"] = "Deposit"
        if "notes" not in df.columns:
            df["notes"] = ""
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        return df[["date", "type", "amount", "notes"]]
    return pd.DataFrame(columns=["date", "type", "amount", "notes"])


def _to_schedule(df: pd.DataFrame) -> tuple[list[tuple[date, float]], list[str]]:
    """Convert an edited dataframe to (schedule, errors).
    schedule: list of (date, signed_amount) — deposits positive, withdrawals negative.
    errors: list of rows that couldn't be parsed."""
    pairs = []
    errors = []
    for _, row in df.iterrows():
        d = _parse_date_str(str(row["date"]))
        if d is None:
            errors.append(f"Cannot parse date: '{row['date']}'")
            continue
        try:
            amount = float(row["amount"])
        except (ValueError, TypeError):
            errors.append(f"Cannot parse amount: '{row['amount']}'")
            continue
        if str(row.get("type", "Deposit")).strip().lower() == "withdrawal":
            amount = -amount
        pairs.append((d, amount))
    return sorted(pairs, key=lambda x: x[0]), errors


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
    st.subheader("Transaction History")
    st.caption(
        "Enter every deposit and withdrawal. "
        "Click **Save** to persist changes between sessions."
    )

    os.makedirs(DATA_DIR, exist_ok=True)
    saved_df = _load_schedule(data_file)

    st.caption("Type dates as **MMDDYY** (e.g. `073126`), `MM/DD/YY`, or `YYYY-MM-DD`. Amount is always positive — use the Type column for withdrawals.")

    edited_df = st.data_editor(
        saved_df,
        column_config={
            "date":   st.column_config.TextColumn("Date", help="MMDDYY, MM/DD/YY, or YYYY-MM-DD"),
            "type":   st.column_config.SelectboxColumn("Type", options=["Deposit", "Withdrawal"], required=True, default="Deposit"),
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
        clean = edited_df.dropna(subset=["date", "amount"]).copy()
        # Parse and normalise dates to ISO before writing
        clean["date"] = clean["date"].apply(
            lambda s: _parse_date_str(str(s)).strftime("%Y-%m-%d") if _parse_date_str(str(s)) else s
        )
        bad_dates = clean[clean["date"].apply(lambda s: _parse_date_str(str(s)) is None)]
        if not bad_dates.empty:
            st.error(f"Could not parse {len(bad_dates)} date(s) — check format and try again.")
        else:
            clean.to_csv(data_file, index=False)
            st.success("Saved!")

    if not run:
        st.stop()

    # ---- Build schedule from edited table ----
    clean_df = edited_df.dropna(subset=["date", "amount"]).copy()
    if "type" not in clean_df.columns:
        clean_df["type"] = "Deposit"
    if clean_df.empty:
        st.warning("No transactions to calculate.")
        st.stop()

    schedule, parse_errors = _to_schedule(clean_df)
    if parse_errors:
        for err in parse_errors:
            st.warning(err)
    if not schedule:
        st.error("No valid transactions to calculate.")
        st.stop()

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
        st.metric("Total Deposits",    f"${actual['total_deposits']:,.2f}")
        st.metric("Total Withdrawals", f"${actual['total_withdrawals']:,.2f}")
        st.metric("Net Invested",      f"${actual['total_invested']:,.2f}")
        st.metric("Current Value",     f"${actual['final_value']:,.2f}")
        st.metric("Gain / Loss",       f"${actual['gain']:,.2f}",
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

    # Cumulative net invested — build from the parsed schedule
    sched_df = pd.DataFrame(schedule, columns=["date", "signed_amount"]).sort_values("date")
    sched_df["cum_invested"] = sched_df["signed_amount"].cumsum()
    fig.add_trace(go.Scatter(
        x=sched_df["date"],
        y=sched_df["cum_invested"],
        mode="lines",
        name="Net Invested",
        line=dict(color="#2196F3", width=1, dash="dot"),
        hovertemplate="Net invested: $%{y:,.2f}<extra></extra>",
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

    # ---- Transaction breakdown ----
    with st.expander("Transaction breakdown"):
        disp = sched_df.copy()
        # Re-join notes/type from clean_df by matching on parsed date
        type_notes = clean_df.copy()
        type_notes["_date"] = type_notes["date"].apply(lambda s: _parse_date_str(str(s)))
        type_notes = type_notes.dropna(subset=["_date"])
        type_map  = dict(zip(type_notes["_date"], type_notes.get("type",  pd.Series(dtype=str))))
        notes_map = dict(zip(type_notes["_date"], type_notes.get("notes", pd.Series(dtype=str))))
        disp["type"]  = disp["date"].map(type_map).fillna("Deposit")
        disp["notes"] = disp["date"].map(notes_map).fillna("")
        disp["date"]  = disp["date"].apply(lambda d: d.strftime("%Y-%m-%d"))
        disp["amount_disp"] = disp["signed_amount"].abs().map("${:,.2f}".format)
        disp["cum_disp"]    = disp["cum_invested"].map("${:,.2f}".format)
        disp = disp[["date", "type", "amount_disp", "notes", "cum_disp"]]
        disp.columns = ["Date", "Type", "Amount ($)", "Notes", "Net Invested ($)"]
        st.dataframe(disp, use_container_width=True, hide_index=True)
