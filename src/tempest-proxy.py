import logging
from datetime import datetime
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

app = FastAPI()

logger = logging.getLogger("uvicorn")

# ✅ Initialize Rate Limiter (5 requests per minute per IP)
limiter = Limiter(key_func=get_remote_address, default_limits=["5/minute"])
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Weather API base URL
WEATHER_API_BASE = "https://swd.weatherflow.com/swd/rest/better_forecast"

# Model for the new query parameters
class WeatherRequest(BaseModel):
    station_id: str
    units_temp: Literal["c", "f"]
    units_wind: Literal["mph", "kph", "m/s"]
    units_pressure: Literal["mb", "inHg"]
    units_precip: Literal["in", "mm"]
    units_distance: Literal["mi", "km"]
    api_key: str


async def fetch_weather_data(url: str, params: dict):
    """Helper function to send a request to the Weather API."""
    logger.info(f"Sending request to {url} with params {params}")
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"Weather API error: {e.response.text}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")


def transform_data(data: dict) -> dict:
    """
    Filters and restructures JSON to include only specified fields.
    Includes the first 4 daily forecast items and adds `day_start_local`.
    """
    filtered_data = {
        "current_conditions": {},
        "forecast": {
            "daily": []  # Initialize an empty list for daily forecasts
        }
    }

    # Filter current conditions
    if "current_conditions" in data:
        current_conditions = data["current_conditions"]
        filtered_data["current_conditions"]["air_temperature"] = current_conditions.get("air_temperature")
        filtered_data["current_conditions"]["icon"] = current_conditions.get("icon")
        filtered_data["current_conditions"]["conditions"] = current_conditions.get("conditions")
        filtered_data["current_conditions"]["feels_like"] = current_conditions.get("feels_like")
        filtered_data["current_conditions"]["relative_humidity"] = current_conditions.get("relative_humidity")
        filtered_data["current_conditions"]["station_pressure"] = current_conditions.get("station_pressure")
        filtered_data["current_conditions"]["precip_probability"] = current_conditions.get("precip_probability")
        filtered_data["current_conditions"]["wind_gust"] = current_conditions.get("wind_gust")

    # Filter forecast data (first 4 days)
    if "forecast" in data and "daily" in data["forecast"]:
        for daily_forecast in data["forecast"]["daily"][:4]:  # Only take the first 4 items
            filtered_daily = {
                "day_start_local": daily_forecast.get("day_start_local"),
                "air_temp_high": daily_forecast.get("air_temp_high"),
                "air_temp_low": daily_forecast.get("air_temp_low"),
                "conditions": daily_forecast.get("conditions"),
                "day_num": daily_forecast.get("day_num"),
                "month_num": daily_forecast.get("month_num"),
                "precip_probability": daily_forecast.get("precip_probability"),
                "precip_type": daily_forecast.get("precip_type"),
                "icon": daily_forecast.get("icon"),
                "precip_icon": daily_forecast.get("precip_icon")

            }
            filtered_data["forecast"]["daily"].append(filtered_daily)

    return filtered_data


@app.post("/proxy")
@app.get("/proxy")
@limiter.limit("5/minute")  # ⏳ Apply rate limit (5 requests per minute per IP)
async def proxy_request(request: Request):
    """Secure JSON proxy with rate limiting."""
    logger.info(
        f"{datetime.now().isoformat()} Received {request.method} request: {request.url} from {get_remote_address(request)}"
    )

    if request.method == "GET":
        # Extract and validate query parameters
        station_id = request.query_params.get("station_id")
        units_temp = request.query_params.get("units_temp")
        units_wind = request.query_params.get("units_wind")
        units_pressure = request.query_params.get("units_pressure")
        units_precip = request.query_params.get("units_precip")
        units_distance = request.query_params.get("units_distance")
        api_key = request.query_params.get("api_key")

        if not all([station_id, units_temp, units_wind, units_pressure, units_precip, units_distance, api_key]):
            raise HTTPException(status_code=400, detail="Missing required query parameters")

        request_data = WeatherRequest(
            station_id=station_id,
            units_temp=units_temp,
            units_wind=units_wind,
            units_pressure=units_pressure,
            units_precip=units_precip,
            units_distance=units_distance,
            api_key=api_key,
        )
    elif request.method == "POST":  # POST
        try:
            body = await request.json()
            request_data = WeatherRequest(**body)
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid JSON body.") from e
    else:
        raise HTTPException(status_code=400, detail="Unsupported request method")

    # Construct API URL and query parameters
    params = {
        "station_id": request_data.station_id,
        "units_temp": request_data.units_temp,
        "units_wind": request_data.units_wind,
        "units_pressure": request_data.units_pressure,
        "units_precip": request_data.units_precip,
        "units_distance": request_data.units_distance,
        "api_key": request_data.api_key,
    }

    # Fetch the data
    raw_data = await fetch_weather_data(WEATHER_API_BASE, params)

    # Transform the data
    return transform_data(raw_data)
