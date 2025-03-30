import os
from datetime import datetime
from typing import Literal
from fastapi import HTTPException, Request
from pydantic import BaseModel
from .common import setup_logger, create_app, fetch_data, handle_request

logger = setup_logger("PARQET")
app = create_app("parqet_proxy")
PARQET_API_BASE = "https://api.parqet.com/v1/portfolios/assemble?useInclude=true&include=ttwror&include=performance_charts&resolution=200"

@app.on_event("startup")
async def startup_event():
    logger.info("="*50)
    logger.info(f"{'Parqet Service Configuration':^50}")
    logger.info("="*50)
    logger.info(f"→ Rate limiting: {os.getenv('PARQET_PROXY_REQUESTS_PER_MINUTE', '5')} requests/minute per IP")
    logger.info("="*50 + "\n")


class PortfolioRequest(BaseModel):
    id: str
    timeframe: Literal["today", "1d", "1w", "1m", "3m", "6m", "1y", "5y", "10y", "mtd", "ytd", "max"]
    perf: Literal["returnGross", "returnNet", "totalReturnGross", "totalReturnNet", "ttwror", "izf"]
    perfChart: Literal["perfHistory", "perfHistoryUnrealized", "ttwror", "drawdown"]


def transform_data(data: dict, perf, perf_chart):
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
                "perf": data.get("performance", {}).get(perf, 0)
            }
            filtered_data["holdings"].append(filtered_holding)

    performance_data = data.get("performance", {})
    filtered_data["performance"] = {
        "valueStart": performance_data.get("purchaseValueForInterval"),
        "valueNow": performance_data.get("value"),
        "perf": performance_data.get(perf, 0)
    }

    if "charts" in data:
        first = True
        for chart in data["charts"]:
            if first:
                first = False
                continue
            filtered_data["chart"].append(chart.get("values", {}).get(perf_chart, 0))

    return filtered_data


async def proxy_endpoint(request: Request):
    if request.method == "GET":
        id = request.query_params.get("id")
        timeframe = request.query_params.get("timeframe")
        perf = request.query_params.get("perf")
        perf_chart = request.query_params.get("perfChart")
        if not all([id, timeframe, perf, perf_chart]):
            raise HTTPException(status_code=400, detail="Missing required query parameters")
        request_data = PortfolioRequest(id=id, timeframe=timeframe, perf=perf, perfChart=perf_chart)
    else:
        body = await request.json()
        request_data = PortfolioRequest(**body)

    payload = {
        "portfolioIds": [request_data.id],
        "holdingIds": [],
        "assetTypes": [],
        "timeframe": request_data.timeframe
    }
    raw_data = await fetch_data(PARQET_API_BASE, logger, method="POST", json=payload, app_name="parqet")
    return transform_data(raw_data, request_data.perf, request_data.perfChart)


handle_request(app, logger, proxy_endpoint)
