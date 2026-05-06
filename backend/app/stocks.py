from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.ticker_util import normalize_equity_symbol

router = APIRouter(prefix="/stocks", tags=["stocks"])

# Static catalog for search (real symbols + company names). Quotes are fetched live via yfinance.
_TICKERS: list[tuple[str, str]] = [
    ("AAPL", "Apple Inc."),
    ("MSFT", "Microsoft Corporation"),
    ("GOOGL", "Alphabet Inc. Class A"),
    ("GOOG", "Alphabet Inc. Class C"),
    ("AMZN", "Amazon.com Inc."),
    ("META", "Meta Platforms Inc."),
    ("NVDA", "NVIDIA Corporation"),
    ("TSLA", "Tesla Inc."),
    ("JPM", "JPMorgan Chase & Co."),
    ("V", "Visa Inc."),
    ("JNJ", "Johnson & Johnson"),
    ("WMT", "Walmart Inc."),
    ("MA", "Mastercard Inc."),
    ("PG", "Procter & Gamble Co."),
    ("UNH", "UnitedHealth Group Inc."),
    ("HD", "Home Depot Inc."),
    ("DIS", "Walt Disney Co."),
    ("BAC", "Bank of America Corp."),
    ("XOM", "Exxon Mobil Corporation"),
    ("KO", "Coca-Cola Co."),
    ("PFE", "Pfizer Inc."),
    ("CSCO", "Cisco Systems Inc."),
    ("COST", "Costco Wholesale Corp."),
    ("ABBV", "AbbVie Inc."),
    ("PEP", "PepsiCo Inc."),
    ("MRK", "Merck & Co. Inc."),
    ("TMO", "Thermo Fisher Scientific Inc."),
    ("AVGO", "Broadcom Inc."),
    ("ACN", "Accenture plc"),
    ("MCD", "McDonald's Corporation"),
    ("ABT", "Abbott Laboratories"),
    ("NFLX", "Netflix Inc."),
    ("ADBE", "Adobe Inc."),
    ("CRM", "Salesforce Inc."),
    ("NKE", "Nike Inc."),
    ("DHR", "Danaher Corporation"),
    ("TXN", "Texas Instruments Inc."),
    ("LIN", "Linde plc"),
    ("NEE", "NextEra Energy Inc."),
    ("WFC", "Wells Fargo & Co."),
    ("PM", "Philip Morris International"),
    ("ORCL", "Oracle Corporation"),
    ("AMD", "Advanced Micro Devices"),
    ("INTC", "Intel Corporation"),
    ("IBM", "International Business Machines"),
    ("QCOM", "Qualcomm Inc."),
    ("HON", "Honeywell International Inc."),
    ("UPS", "United Parcel Service Inc."),
    ("LOW", "Lowe's Companies Inc."),
    ("SBUX", "Starbucks Corporation"),
    ("BA", "Boeing Co."),
    ("CAT", "Caterpillar Inc."),
    ("GE", "GE Aerospace / GE Vernova"),
    ("GS", "Goldman Sachs Group Inc."),
    ("BLK", "BlackRock Inc."),
    ("SPY", "SPDR S&P 500 ETF Trust"),
    ("QQQ", "Invesco QQQ Trust"),
    ("IWM", "iShares Russell 2000 ETF"),
    ("BRK-B", "Berkshire Hathaway Inc. Class B"),
    ("T", "AT&T Inc."),
    ("VZ", "Verizon Communications Inc."),
    ("PYPL", "PayPal Holdings Inc."),
    ("SHOP", "Shopify Inc."),
    ("COIN", "Coinbase Global Inc."),
    ("PLTR", "Palantir Technologies Inc."),
    ("RIVN", "Rivian Automotive Inc."),
    ("F", "Ford Motor Company"),
    ("GM", "General Motors Co."),
]


class StockSearchItem(BaseModel):
    symbol: str
    name: str


class StockQuoteResponse(BaseModel):
    symbol: str
    name: str | None = None
    currency: str | None = None
    last_close: float = Field(description="Most recent adjusted close in the series")
    previous_close: float = Field(description="Prior trading session close")
    change_amount: float
    change_percent: float
    is_profitable: bool = Field(
        description="True if last_close is above previous_close (prior session comparison)"
    )
    as_of: str = Field(description="ISO date of the latest close (UTC calendar date)")


def _normalize_symbol(raw: str) -> str:
    try:
        return normalize_equity_symbol(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/search", response_model=list[StockSearchItem])
def search_stocks(
    q: str = Query(..., min_length=1, max_length=64, description="Substring of symbol or name"),
    limit: int = Query(20, ge=1, le=50),
) -> list[StockSearchItem]:
    needle = q.strip().lower()
    if not needle:
        return []
    matches: list[StockSearchItem] = []
    for sym, name in _TICKERS:
        if needle in sym.lower() or needle in name.lower():
            matches.append(StockSearchItem(symbol=sym, name=name))
        if len(matches) >= limit:
            break
    return matches


@router.get("/quote/{symbol}", response_model=StockQuoteResponse)
def stock_quote(symbol: str) -> StockQuoteResponse:
    sym = _normalize_symbol(symbol)
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="yfinance is not installed") from exc

    ticker = yf.Ticker(sym)
    hist = ticker.history(period="1mo", auto_adjust=True)
    if hist is None or hist.empty:
        raise HTTPException(status_code=404, detail=f"No market data for {sym}")

    closes = hist["Close"].dropna()
    if len(closes) < 2:
        raise HTTPException(status_code=404, detail=f"Not enough history for {sym}")

    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-2])
    change = last - prev
    change_pct = (change / prev * 100) if prev else 0.0

    idx = closes.index[-1]
    if hasattr(idx, "date"):
        as_of_d: date = idx.date()  # type: ignore[assignment]
    else:
        as_of_d = datetime.now(timezone.utc).date()

    name: str | None = None
    currency: str | None = None
    try:
        info = ticker.info or {}
        name = info.get("longName") or info.get("shortName")
        currency = info.get("currency")
    except Exception:
        pass

    return StockQuoteResponse(
        symbol=sym,
        name=name,
        currency=currency,
        last_close=round(last, 4),
        previous_close=round(prev, 4),
        change_amount=round(change, 4),
        change_percent=round(change_pct, 4),
        is_profitable=last > prev,
        as_of=as_of_d.isoformat(),
    )
