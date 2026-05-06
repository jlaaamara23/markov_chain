import sys
from pathlib import Path

# Allow running this file directly (PyCharm "Python file") as well as `python -m app.main`.
_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.markov import render_graph_png, run_prediction
from app.stocks import router as stocks_router


class StripApiPrefixMiddleware(BaseHTTPMiddleware):
    """So /api/stocks/... works when the dev proxy forwards the path without stripping /api."""

    async def dispatch(self, request, call_next):
        path = request.scope.get("path") or ""
        if path.startswith("/api"):
            suffix = path[4:]
            new_path = "/" if not suffix or suffix == "/" else "/" + suffix.lstrip("/")
            request.scope["path"] = new_path
            request.scope["raw_path"] = new_path.encode("ascii")
        return await call_next(request)


app = FastAPI(title="TradeMind AI Market Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(StripApiPrefixMiddleware)

app.include_router(stocks_router)


@app.get("/predict")
def predict(
    symbol: str = Query("SPY", min_length=1, max_length=12, description="Ticker (yfinance)"),
    period: str = Query(
        "2y",
        description="yfinance history window, e.g. 6mo, 1y, 2y, 5y, max",
    ),
    steps: int = Query(
        1,
        ge=1,
        le=60,
        description="Forecast horizon in trading days (distribution uses P^steps)",
    ),
    context_len: int = Query(
        5,
        ge=1,
        le=10,
        description="How many prior trading days to use as Markov context (default = 5)",
    ),
) -> dict:
    """Markov chain on discretized daily returns; matrix estimated from historical data."""
    try:
        return run_prediction(
            symbol=symbol,
            period=period,
            steps=steps,
            context_len=context_len,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/graph")
def graph(
    symbol: str = Query("SPY", min_length=1, max_length=12),
    period: str = Query("2y"),
    edge_threshold: float = Query(0.05, ge=0.01, le=0.99),
) -> Response:
    try:
        png_image = render_graph_png(
            symbol=symbol,
            period=period,
            edge_threshold=edge_threshold,
        )
        return Response(content=png_image, media_type="image/png")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "TradeMind API is running"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8001,
        reload=True,
    )
