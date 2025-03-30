import logging
import sys
from datetime import datetime
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

app = FastAPI()

# Configure logger with app-specific prefix
logger = logging.getLogger("uvicorn")
logger.handlers.clear()  # Clear default handlers to avoid duplicates
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("PARQET-PROXY:%(levelname)s:%(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Initialize Rate Limiter (5 requests per minute per IP)
limiter = Limiter(key_func=get_remote_address, default_limits=["5/minute"])
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

PARQET_API_BASE = "https://api.parqet.com/v1/portfolios/assemble?useInclude=true&include=ttwror&include=performance_charts&resolution=200"


class PortfolioRequest(BaseModel):
    id: str
    timeframe: Literal["today", "1d", "1w", "1m", "3m", "6m", "1y", "5y", "10y", "mtd", "ytd", "max"]
    perf: Literal["returnGross", "returnNet", "totalReturnGross", "totalReturnNet", "ttwror", "izf"]
    perfChart: Literal["perfHistory", "perfHistoryUnrealized", "ttwror", "drawdown"]


async def fetch_parqet_data(url: str, payload: dict):
    """Helper function to send a request to Parqet."""
    logger.info(f"Sending request to {url} with payload {payload}")
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"Parqet API error: {e.response.text}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")


def transform_data(data: dict, perf, perf_chart):
    """Filters and restructures JSON to keep only specified fields."""
    filtered_data = {"holdings": [], "performance": {}, "chart": []}

    if "holdings" in data:
        for holding in data["holdings"]:
            asset_type = holding.get("assetType", "").lower()
            if asset_type not in ["security", "crypto"]:
                continue
            is_sold = holding.get("position", {}).get("isSold")
            shares = holding.get("position", {}).get("shares")
            if is_sold or shares == 0:
                continue
            filtered_holding = {
                "assetType": asset_type,
                "currency": holding.get("currency"),
                "id": holding.get("asset", {}).get("identifier"),
                "name": holding.get("sharedAsset", {}).get("name"),
                "priceStart": holding.get("performance", {}).get("priceAtIntervalStart"),
                "valueStart": holding.get("performance", {}).get("purchaseValueForInterval"),
                "priceNow": holding.get("position", {}).get("currentPrice"),
                "valueNow": holding.get("position", {}).get("currentValue"),
                "shares": holding.get("position", {}).get("shares"),
                "perf": get_perf(holding.get("performance", {}), perf)
            }
            filtered_data["holdings"].append(filtered_holding)

    performance_data = data.get("performance", {})
    filtered_data["performance"] = {
        "valueStart": performance_data.get("purchaseValueForInterval"),
        "valueNow": performance_data.get("value"),
    }
    filtered_data["performance"]["perf"] = get_perf(performance_data, perf)

    if "charts" in data:
        first = True
        for chart in data["charts"]:
            if first:
                # skip first
                first = False
                continue
            filtered_data["chart"].append(get_perf_chart(chart, perf_chart))

    return filtered_data


def get_perf(data, perf):
    return data.get(perf, 0)


def get_perf_chart(data, perf_chart):
    values = data.get("values", {})
    return values.get(perf_chart, 0)


@app.post("/proxy")
@app.get("/proxy")
@limiter.limit("5/minute")  # Apply rate limit (5 requests per minute per IP)
async def proxy_request(request: Request):
    """Secure JSON proxy with rate limiting."""
    logger.info(
        f"{datetime.now().isoformat()} Received {request.method} request: {request.url} from {get_remote_address(request)}")
    if request.method == "GET":
        id = request.query_params.get("id")
        timeframe = request.query_params.get("timeframe")
        perf = request.query_params.get("perf")
        perf_chart = request.query_params.get("perfChart")

        if not id or not timeframe or not perf or not perf_chart:
            raise HTTPException(status_code=400,
                                detail="Missing required query parameters")

        request_data = PortfolioRequest(id=id, timeframe=timeframe, perf=perf, perfChart=perf_chart)
    elif request.method == "POST":  # POST
        try:
            body = await request.json()
            request_data = PortfolioRequest(**body)
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid JSON body.") from e
    else:
        raise HTTPException(status_code=400, detail="Unsupported")

    # Construct API URL and payload
    url = PARQET_API_BASE
    payload = {
        "portfolioIds": [request_data.id],
        "holdingIds": [],
        "assetTypes": [],
        "timeframe": request_data.timeframe
    }

    # Fetch the data
    raw_data = await fetch_parqet_data(url, payload)
    return transform_data(raw_data, request_data.perf, request_data.perfChart)
