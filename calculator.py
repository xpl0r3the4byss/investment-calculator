"""
ETF Dollar-Cost Averaging (DCA) Calculator

Core calculation logic — no UI dependencies.
"""

from datetime import date, timedelta
from typing import Optional
import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Acorns portfolio definitions
# ---------------------------------------------------------------------------
ACORNS_PORTFOLIOS = {
    "Aggressive (100% stocks)": {
        "VOO": 0.55,
        "IXUS": 0.30,
        "IJH": 0.10,
        "IJR": 0.05,
    },
    "Moderately Aggressive (80% stocks / 20% bonds)": {
        "VOO": 0.47,
        "IXUS": 0.24,
        "IJH": 0.06,
        "IJR": 0.03,
        "AGG": 0.14,
        "ISTB": 0.06,
    },
    "Moderate (70% stocks / 30% bonds)": {
        "VOO": 0.35,
        "IXUS": 0.18,
        "IJH": 0.05,
        "IJR": 0.02,
        "AGG": 0.28,
        "ISTB": 0.12,
    },
    "Moderately Conservative (40% stocks / 60% bonds)": {
        "VOO": 0.20,
        "IXUS": 0.12,
        "IJH": 0.05,
        "IJR": 0.03,
        "AGG": 0.40,
        "ISTB": 0.20,
    },
    "Conservative (100% bonds)": {
        "AGG": 0.60,
        "ISTB": 0.40,
    },
}


def _investment_dates(start_date: date, end_date: date) -> list[date]:
    """
    Generate the list of monthly investment dates.

    Starting from start_date, produce one date per month on the same day-of-month
    as start_date (e.g. the 25th), up to and including any month whose target date
    falls on or before end_date.
    """
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        # Advance by one month, keeping the same day where possible
        month = current.month + 1
        year = current.year
        if month > 12:
            month = 1
            year += 1
        # Clamp to the last day of the new month (e.g. Jan 31 → Feb 28)
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        day = min(start_date.day, last_day)
        current = date(year, month, day)
    return dates


def calculate_dca(
    ticker: str,
    monthly_amount: float,
    start_date: date,
    end_date: date,
) -> Optional[dict]:
    """
    Calculate the outcome of investing `monthly_amount` every month from
    `start_date` to `end_date` in `ticker`.

    Returns a dict with:
        ticker          – str
        total_invested  – float
        final_value     – float
        gain            – float  (final_value - total_invested)
        gain_pct        – float  (gain / total_invested * 100)
        purchases       – pd.DataFrame with columns:
                            date, price, shares_bought, cumulative_shares,
                            portfolio_value

    Returns None if price data cannot be fetched.
    """
    # Fetch adjusted daily closes (a few days buffer on either side)
    fetch_start = start_date - timedelta(days=7)
    fetch_end = end_date + timedelta(days=1)

    raw = yf.download(
        ticker,
        start=fetch_start.strftime("%Y-%m-%d"),
        end=fetch_end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )

    if raw.empty:
        return None

    # Flatten MultiIndex columns if present (yfinance ≥0.2 with single ticker)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    closes = raw["Close"].dropna()
    closes.index = pd.to_datetime(closes.index).normalize()

    # Forward-fill so we can look up any calendar date and get the next
    # available trading-day price.
    full_index = pd.date_range(start=closes.index.min(), end=closes.index.max(), freq="D")
    closes = closes.reindex(full_index).ffill()

    investment_days = _investment_dates(start_date, end_date)

    rows = []
    cumulative_shares = 0.0

    for inv_date in investment_days:
        ts = pd.Timestamp(inv_date)
        if ts < closes.index.min() or ts > closes.index.max():
            continue
        price = float(closes.loc[ts])
        shares = monthly_amount / price
        cumulative_shares += shares
        rows.append(
            {
                "date": inv_date,
                "price": round(price, 4),
                "shares_bought": round(shares, 6),
                "cumulative_shares": round(cumulative_shares, 6),
                "portfolio_value": round(cumulative_shares * price, 2),
            }
        )

    if not rows:
        return None

    purchases = pd.DataFrame(rows)

    # Final value uses the latest available price on or before end_date
    end_ts = pd.Timestamp(end_date)
    if end_ts > closes.index.max():
        end_ts = closes.index.max()
    final_price = float(closes.loc[end_ts])
    final_value = round(cumulative_shares * final_price, 2)
    total_invested = round(len(rows) * monthly_amount, 2)
    gain = round(final_value - total_invested, 2)
    gain_pct = round(gain / total_invested * 100, 2) if total_invested else 0.0

    return {
        "ticker": ticker,
        "total_invested": total_invested,
        "final_value": final_value,
        "gain": gain,
        "gain_pct": gain_pct,
        "purchases": purchases,
    }


# ---------------------------------------------------------------------------
# Acorns portfolio DCA
# ---------------------------------------------------------------------------

def calculate_acorns_dca(
    portfolio_name: str,
    monthly_amount: float,
    start_date: date,
    end_date: date,
) -> Optional[dict]:
    """
    Calculate DCA for an Acorns portfolio by splitting the monthly amount
    across constituent ETFs by their target weights.

    Returns a dict with:
        portfolio_name  – str
        total_invested  – float
        final_value     – float
        gain            – float
        gain_pct        – float
        holdings        – dict of ticker -> individual calculate_dca result
        purchases       – pd.DataFrame with columns:
                            date, portfolio_value
                          (combined value across all holdings on each purchase date)
    """
    weights = ACORNS_PORTFOLIOS[portfolio_name]
    holdings = {}
    errors = []

    for ticker, weight in weights.items():
        allocated = round(monthly_amount * weight, 6)
        result = calculate_dca(ticker, allocated, start_date, end_date)
        if result:
            holdings[ticker] = result
        else:
            errors.append(ticker)

    if not holdings:
        return None

    # Combine per-purchase-date portfolio values across all holdings
    combined = None
    for ticker, result in holdings.items():
        df = result["purchases"][["date", "portfolio_value"]].copy()
        df = df.rename(columns={"portfolio_value": ticker})
        if combined is None:
            combined = df
        else:
            combined = combined.merge(df, on="date", how="outer")

    combined = combined.sort_values("date").fillna(0)
    value_cols = [t for t in holdings]
    combined["portfolio_value"] = combined[value_cols].sum(axis=1)

    total_invested = sum(r["total_invested"] for r in holdings.values())
    final_value = sum(r["final_value"] for r in holdings.values())
    gain = round(final_value - total_invested, 2)
    gain_pct = round(gain / total_invested * 100, 2) if total_invested else 0.0

    return {
        "portfolio_name": portfolio_name,
        "total_invested": round(total_invested, 2),
        "final_value": round(final_value, 2),
        "gain": gain,
        "gain_pct": gain_pct,
        "holdings": holdings,
        "purchases": combined[["date", "portfolio_value"]],
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Catch-up planner helpers
# ---------------------------------------------------------------------------

def should_have_invested(birth_date: date, monthly_contribution: float, end_date: date) -> float:
    """Total that should have been invested at monthly_contribution/month from birth_date to end_date."""
    return round(len(_investment_dates(birth_date, end_date)) * monthly_contribution, 2)


def generate_catchup_plan(
    children: list[dict],
    monthly_budget: float,
    ongoing_per_child: float,
) -> dict | None:
    """
    Generate a month-by-month principal catch-up plan, allocating to oldest child first.

    children: list of {name, birth_date, principal_gap}

    Returns:
        catch_up_budget   – float: monthly amount available after ongoing contributions
        priority_order    – list of names oldest-first
        close_months      – {name: date} when each child's gap closes
        monthly_records   – list of {month, allocations: {name: $}, remaining: {name: $}}
        gap_over_time     – pd.DataFrame with columns: month, <name1>, <name2>, ...
    Returns None if catch_up_budget <= 0.
    """
    n = len(children)
    catch_up_budget = round(monthly_budget - ongoing_per_child * n, 2)
    if catch_up_budget <= 0:
        return None

    sorted_children = sorted(children, key=lambda c: c["birth_date"])
    names = [c["name"] for c in sorted_children]
    remaining = {c["name"]: max(0.0, round(c["principal_gap"], 2)) for c in sorted_children}
    close_months: dict[str, date] = {}

    # Start from next calendar month
    today = date.today()
    m, y = today.month + 1, today.year
    if m > 12:
        m, y = 1, y + 1
    current = date(y, m, 1)

    monthly_records = []
    gap_rows = []

    while any(g > 0.005 for g in remaining.values()):
        allocations: dict[str, float] = {}
        leftover = catch_up_budget

        for c in sorted_children:
            name = c["name"]
            if remaining[name] > 0.005 and leftover > 0.005:
                alloc = round(min(leftover, remaining[name]), 2)
                allocations[name] = alloc
                remaining[name] = round(remaining[name] - alloc, 2)
                leftover = round(leftover - alloc, 2)
                if remaining[name] <= 0.005 and name not in close_months:
                    close_months[name] = current
                    remaining[name] = 0.0

        monthly_records.append({
            "month": current,
            "allocations": allocations,
            "remaining": dict(remaining),
        })
        gap_rows.append({"month": current, **{name: remaining.get(name, 0.0) for name in names}})

        m, y = current.month + 1, current.year
        if m > 12:
            m, y = 1, y + 1
        current = date(y, m, 1)

        if len(monthly_records) > 240:  # 20-year safety cap
            break

    return {
        "catch_up_budget": catch_up_budget,
        "priority_order": names,
        "close_months": close_months,
        "monthly_records": monthly_records,
        "gap_over_time": pd.DataFrame(gap_rows),
    }


# ---------------------------------------------------------------------------
# Quick CLI sanity-check
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    tickers = ["SMH", "SOXX", "VGT"]
    start = date(2015, 8, 25)
    end = date.today()
    amount = 5.0

    print(f"DCA ${amount}/month from {start} to {end}\n")
    print(f"{'Ticker':<8} {'Invested':>12} {'Final Value':>12} {'Gain':>12} {'Gain %':>9}")
    print("-" * 56)

    for t in tickers:
        result = calculate_dca(t, amount, start, end)
        if result:
            print(
                f"{result['ticker']:<8} "
                f"${result['total_invested']:>11,.2f} "
                f"${result['final_value']:>11,.2f} "
                f"${result['gain']:>11,.2f} "
                f"{result['gain_pct']:>8.1f}%"
            )
        else:
            print(f"{t:<8} {'ERROR: could not fetch data':>44}")
