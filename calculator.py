"""
ETF Dollar-Cost Averaging (DCA) Calculator

Core calculation logic — no UI dependencies.
"""

from datetime import date, timedelta
from typing import Optional
import pandas as pd
import yfinance as yf


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
