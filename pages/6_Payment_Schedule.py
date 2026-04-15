"""
Payment Schedule — consolidated view of deposits and withdrawals across all children.
Shows the last 3 past transaction dates and all future planned dates.
"""

import os
from datetime import date

import pandas as pd
import streamlit as st

from child_page import _load_schedule, _parse_date_str
from children_config import CHILDREN

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

TRACKED_TYPES = {"deposit", "withdrawal"}


def _load_all() -> pd.DataFrame:
    """Load deposit/withdrawal rows for every child into a single long dataframe."""
    rows = []
    for child in CHILDREN:
        name = child["name"]
        data_file = os.path.join(DATA_DIR, f"{name.lower()}.csv")
        df = _load_schedule(data_file)
        if df.empty:
            continue
        df = df[df["type"].str.strip().str.lower().isin(TRACKED_TYPES)].copy()
        if df.empty:
            continue
        df["parsed_date"] = df["date"].apply(lambda s: _parse_date_str(str(s)))
        df = df.dropna(subset=["parsed_date"])
        df["signed_amount"] = df.apply(
            lambda r: -float(r["amount"])
            if str(r["type"]).strip().lower() == "withdrawal"
            else float(r["amount"]),
            axis=1,
        )
        daily = (
            df.groupby("parsed_date")["signed_amount"]
            .sum()
            .reset_index()
            .rename(columns={"parsed_date": "date", "signed_amount": name})
        )
        rows.append(daily)

    if not rows:
        return pd.DataFrame()

    combined = rows[0]
    for df in rows[1:]:
        combined = combined.merge(df, on="date", how="outer")
    return combined.sort_values("date").reset_index(drop=True)


def _fmt(v) -> str:
    if pd.isna(v):
        return ""
    return f"${v:,.2f}" if v >= 0 else f"-${abs(v):,.2f}"


st.title("Payment Schedule")
st.caption(
    "Deposits and withdrawals only — last 3 past dates plus all future planned transactions. "
    "Withdrawals shown as negative amounts."
)

today = date.today()
combined = _load_all()

if combined.empty:
    st.info("No transaction data found. Add transactions on the individual child pages first.")
    st.stop()

child_cols = [c["name"] for c in CHILDREN if c["name"] in combined.columns]
combined["date"] = pd.to_datetime(combined["date"]).dt.date

past_dates  = sorted(combined[combined["date"] <= today]["date"].unique(), reverse=True)[:3]
future_dates = sorted(combined[combined["date"] >  today]["date"].unique())

def _make_table(dates: list) -> pd.DataFrame:
    sub = combined[combined["date"].isin(dates)].copy()
    sub = sub.sort_values("date")
    sub["Date"] = sub["date"].apply(lambda d: d.strftime("%Y-%m-%d"))
    # Add a Total column
    numeric = sub[child_cols].fillna(0)
    sub["Total"] = numeric.sum(axis=1)
    display_cols = ["Date"] + child_cols + ["Total"]
    sub = sub[display_cols].set_index("Date")
    return sub.map(_fmt)


if past_dates:
    st.subheader("Recent")
    st.dataframe(_make_table(past_dates), width="stretch")
else:
    st.subheader("Recent")
    st.caption("No past transactions recorded yet.")

st.subheader("Planned")
if future_dates:
    st.dataframe(_make_table(future_dates), width="stretch")
else:
    st.caption(
        "No future transactions planned. Add a future-dated deposit on a child's page to see it here."
    )
