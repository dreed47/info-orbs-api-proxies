import os
from datetime import datetime
from typing import Literal
from fastapi import HTTPException, Request
from pydantic import BaseModel
from slowapi.util import get_remote_address  # Add this import
from .common import setup_logger, create_app, fetch_data

logger = setup_logger("VISUALCROSSING")
app = create_app("visualcrossing_proxy")
VISUALCROSSING_API_BASE = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"
SECRETS_DIR = "/secrets"
VISUALCROSSING_DEFAULT_API_KEY_PATH = os.path.join(SECRETS_DIR, "VISUALCROSSING_DEFAULT_API_KEY")

@app.on_event("startup")
async def startup_event():
    logger.info("="*50)
    logger.info(f"{'Visual Crossing Service Configuration':^50}")
    logger.info("="*50)
    logger.info(f"→ Rate limiting: {os.getenv('VISUALCROSSING_PROXY_REQUESTS_PER_MINUTE', '5')} requests/minute per IP")
    logger.info("="*50 + "\n")

class WeatherRequest(BaseModel):
    location: str
    timeframe: str
    unit_group: Literal["us", "uk", "metric", "base"]
    include: str = "days,current"
    icon_set: str = "icons1"
    lang: str = "en"
    api_key: str

def transform_data(data: dict) -> dict:
    """Transform Visual Crossing API response to maintain all days but only required fields"""
    filtered_data = {
        "resolvedAddress": data.get("resolvedAddress"),
        "currentConditions": {
            "temp": data.get("currentConditions", {}).get("temp"),
            "icon": data.get("currentConditions", {}).get("icon")
        },
        "days": []
    }

    # Process all days while maintaining only required fields
    if "days" in data:
        for day in data["days"]:
            filtered_day = {
                "description": day.get("description"),
                "icon": day.get("icon"),
                "tempmax": day.get("tempmax"),
                "tempmin": day.get("tempmin")
            }
            filtered_data["days"].append(filtered_day)

    return filtered_data

async def proxy_endpoint(request: Request):
    # Get path parameters
    path_parts = request.url.path.split('/')
    if len(path_parts) < 4 or not path_parts[2] or not path_parts[3]:
        raise HTTPException(status_code=400, detail="Path must be /proxy/{location}/{timeframe}")
    
    location = path_parts[2]
    timeframe = path_parts[3]

    # Get query parameters
    unit_group = request.query_params.get("unitGroup", "us")
    include = request.query_params.get("include", "days,current")
    icon_set = request.query_params.get("iconSet", "icons1")
    lang = request.query_params.get("lang", "en")
    api_key = request.query_params.get("key")
    
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")
    
    if api_key == "VISUALCROSSING_DEFAULT_API_KEY":
        try:
            with open(VISUALCROSSING_DEFAULT_API_KEY_PATH, "r") as secret_file:
                api_key = secret_file.read().strip()
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="VISUALCROSSING_DEFAULT_API_KEY secret file not found")

    params = {
        "key": api_key,
        "unitGroup": unit_group,
        "include": include,
        "iconSet": icon_set,
        "lang": lang
    }
    
    url = f"{VISUALCROSSING_API_BASE}/{location}/{timeframe}"
    raw_data = await fetch_data(url, logger, method="GET", params=params, app_name="visualcrossing")
    return transform_data(raw_data)

# Custom route handler with all required imports
@app.api_route("/proxy/{location}/{timeframe}", methods=["GET"])
@app.state.limiter.limit(os.getenv("VISUALCROSSING_PROXY_REQUESTS_PER_MINUTE", "5") + "/minute")
async def visualcrossing_proxy(request: Request):
    logger.info(f"{datetime.now().isoformat()} Received {request.method} request: {request.url} from {get_remote_address(request)}")
    return await proxy_endpoint(request)
