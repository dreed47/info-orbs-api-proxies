import os
from datetime import datetime
from typing import Literal
from fastapi import HTTPException, Request
from pydantic import BaseModel
from .common import setup_logger, create_app, fetch_data, handle_request

logger = setup_logger("TEMPEST")
app = create_app("tempest_proxy")
WEATHER_API_BASE = "https://swd.weatherflow.com/swd/rest/better_forecast"
SECRETS_DIR = "/secrets"  # Directory where secrets are mounted
TEMPEST_DEFAULT_API_KEY_PATH = os.path.join(SECRETS_DIR, "TEMPEST_DEFAULT_API_KEY")

@app.on_event("startup")
async def startup_event():
    logger.info("="*50)
    logger.info(f"{'TEMPEST Service Configuration':^50}")
    logger.info("="*50)
    logger.info(f"→ Rate limiting: {os.getenv('TEMPEST_PROXY_REQUESTS_PER_MINUTE', '5')} requests/minute per IP")
    logger.info("="*50 + "\n")

class WeatherRequest(BaseModel):
    station_id: str
    units_temp: Literal["c", "f"]
    units_wind: Literal["mph", "kph", "m/s"]
    units_pressure: Literal["mb", "inHg"]
    units_precip: Literal["in", "mm"]
    units_distance: Literal["mi", "km"]
    api_key: str


def transform_data(data: dict) -> dict:
    filtered_data = {"current_conditions": {}, "forecast": {"daily": []}}
    if "current_conditions" in data:
        cc = data["current_conditions"]
        filtered_data["current_conditions"] = {
            "air_temperature": cc.get("air_temperature"),
            "icon": cc.get("icon"),
            "conditions": cc.get("conditions"),
            "feels_like": cc.get("feels_like"),
            "relative_humidity": cc.get("relative_humidity"),
            "station_pressure": cc.get("station_pressure"),
            "precip_probability": cc.get("precip_probability"),
            "wind_gust": cc.get("wind_gust")
        }

    if "forecast" in data and "daily" in data["forecast"]:
        for daily_forecast in data["forecast"]["daily"][:4]:
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


async def proxy_endpoint(request: Request):
    if request.method == "GET":
        station_id = request.query_params.get("station_id")
        units_temp = request.query_params.get("units_temp")
        units_wind = request.query_params.get("units_wind")
        units_pressure = request.query_params.get("units_pressure")
        units_precip = request.query_params.get("units_precip")
        units_distance = request.query_params.get("units_distance")
        api_key = request.query_params.get("api_key")
        if not all([station_id, units_temp, units_wind, units_pressure, units_precip, units_distance, api_key]):
            raise HTTPException(status_code=400, detail="Missing required query parameters")
        
        # Replace "TEMPEST_DEFAULT_API_KEY" with the value from the secrets file
        if api_key == "TEMPEST_DEFAULT_API_KEY":
            try:
                with open(TEMPEST_DEFAULT_API_KEY_PATH, "r") as secret_file:
                    api_key = secret_file.read().strip()
            except FileNotFoundError:
                raise HTTPException(status_code=500, detail="TEMPEST_DEFAULT_API_KEY secret file not found")
        
        request_data = WeatherRequest(
            station_id=station_id, units_temp=units_temp, units_wind=units_wind,
            units_pressure=units_pressure, units_precip=units_precip, units_distance=units_distance,
            api_key=api_key
        )
    else:  # POST
        body = await request.json()
        request_data = WeatherRequest(**body)
        if request_data.api_key == "TEMPEST_DEFAULT_API_KEY":
            try:
                with open(TEMPEST_DEFAULT_API_KEY_PATH, "r") as secret_file:
                    request_data.api_key = secret_file.read().strip()
            except FileNotFoundError:
                raise HTTPException(status_code=500, detail="TEMPEST_DEFAULT_API_KEY secret file not found")

    params = request_data.dict()
    raw_data = await fetch_data(WEATHER_API_BASE, logger, method="GET", params=params, app_name="tempest")
    return transform_data(raw_data)

handle_request(app, logger, proxy_endpoint)
