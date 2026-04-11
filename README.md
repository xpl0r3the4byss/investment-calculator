# ETF Dollar-Cost Averaging Calculator

Calculate the outcome of investing a fixed amount every month into any ETF, using real historical price data from Yahoo Finance.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the URL printed in your terminal (usually `http://localhost:8501`).

## CLI mode

Run a quick calculation directly in your terminal:

```bash
python calculator.py
```

This prints results for the default scenario: **$5/month** from **2015-08-25** to today across **SMH**, **SOXX**, and **VGT** — the top 3 performing ETFs over that period.

## How it works

Each month, on the same day-of-month as the start date (e.g. the 25th), a fixed dollar amount is used to "buy" shares at the adjusted closing price for that day. If that day falls on a weekend or market holiday, the next available trading day's price is used. Prices are split- and dividend-adjusted.

## Inputs (Streamlit sidebar)

| Setting | Default | Description |
|---|---|---|
| Monthly investment | $5.00 | Amount invested each month |
| Start date | 2015-08-25 | First purchase date |
| End date | today | Last possible purchase date |
| Tickers | SMH, SOXX, VGT | Comma-separated list of ETF tickers |

## Default ETFs

The defaults are the three best-performing ETFs from August 2015 to April 2026:

| Ticker | Fund | ~Total Return |
|---|---|---|
| SMH | VanEck Semiconductor ETF | ~1,450% |
| SOXX | iShares Semiconductor ETF | ~1,090% |
| VGT | Vanguard Information Technology ETF | ~620% |

## Dependencies

- [yfinance](https://github.com/ranaroussi/yfinance) — free Yahoo Finance historical data
- [Streamlit](https://streamlit.io) — interactive web UI
- [pandas](https://pandas.pydata.org) — data manipulation
- [Plotly](https://plotly.com/python/) — interactive charts
