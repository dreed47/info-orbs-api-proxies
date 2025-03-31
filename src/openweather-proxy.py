import os
from datetime import datetime, timedelta
from typing import Dict, Optional
import json
from fastapi import HTTPException, Request
from pydantic import BaseModel
from slowapi.util import get_remote_address
from .common import setup_logger, create_app, fetch_data

logger = setup_logger("OPENWEATHER")
app = create_app("openweather_proxy")
OPENWEATHER_API_BASE = "https://api.openweathermap.org/data/3.0/onecall"
SECRETS_DIR = "/secrets"
OPENWEATHER_DEFAULT_API_KEY_PATH = os.path.join(SECRETS_DIR, "OPENWEATHER_DEFAULT_API_KEY")

# Cache configuration
CACHE_LIFE_MINUTES = int(os.getenv("OPENWEATHER_PROXY_CACHE_LIFE", "5"))  # 0 disables caching
weather_cache: Dict[str, dict] = {}
cache_expiry: Dict[str, datetime] = {}

@app.on_event("startup")
async def startup_event():
    logger.info("="*50)
    logger.info(f"{'OpenWeather Service Configuration':^50}")
    logger.info("="*50)
    logger.info(f"→ Rate limiting: {os.getenv('OPENWEATHER_PROXY_REQUESTS_PER_MINUTE', '5')} requests/minute per IP")
    logger.info(f"→ Cache lifetime: {CACHE_LIFE_MINUTES} minutes ({'enabled' if CACHE_LIFE_MINUTES > 0 else 'disabled'})")
    logger.info("="*50 + "\n")

class WeatherRequest(BaseModel):
    lat: float
    lon: float
    units: str = "imperial"
    exclude: str = "minutely,hourly,alerts"
    lang: str = "en"
    cnt: int = 3
    appid: str

def transform_data(data: dict, cached: bool = False) -> dict:
    """Add proxy-info to the full OpenWeather response"""
    if not data:
        raise HTTPException(status_code=502, detail="Empty API response")
    
    # Include the full original response plus proxy-info
    transformed = dict(data)
    transformed["proxy-info"] = {
        "cachedResponse": cached,
        "status_code": 200,
        "timestamp": datetime.utcnow().isoformat()
    }
    return transformed

def get_cache_key(params: dict) -> str:
    """Generate a unique cache key from request parameters"""
    return json.dumps(params, sort_keys=True)

async def proxy_endpoint(request: Request):
    # Get query parameters
    lat = request.query_params.get("lat")
    lon = request.query_params.get("lon")
    units = request.query_params.get("units", "imperial")
    exclude = request.query_params.get("exclude", "minutely,hourly,alerts")
    lang = request.query_params.get("lang", "en")
    cnt = request.query_params.get("cnt", "3")
    appid = request.query_params.get("appid")
    
    if not lat or not lon:
        raise HTTPException(status_code=400, detail="Latitude and longitude parameters are required")
    
    if not appid:
        raise HTTPException(status_code=400, detail="API key is required")
    
    if appid == "OPENWEATHER_DEFAULT_API_KEY":
        try:
            with open(OPENWEATHER_DEFAULT_API_KEY_PATH, "r") as secret_file:
                appid = secret_file.read().strip()
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="OPENWEATHER_DEFAULT_API_KEY secret file not found")

    params = {
        "lat": lat,
        "lon": lon,
        "units": units,
        "exclude": exclude,
        "lang": lang,
        "cnt": cnt,
        "appid": appid
    }
    cache_key = get_cache_key(params)
    
    # Check cache if enabled
    if CACHE_LIFE_MINUTES > 0:
        cached_data = weather_cache.get(cache_key)
        cache_valid = cache_expiry.get(cache_key, datetime.min) > datetime.utcnow()
        
        if cached_data and cache_valid:
            logger.info(f"Returning cached data for location {lat},{lon}")
            return transform_data(cached_data, cached=True)

    # Fetch fresh data
    logger.info(f"Fetching live data for location {lat},{lon}")
    try:
        raw_data = await fetch_data(OPENWEATHER_API_BASE, logger, method="GET", 
                                  params=params, app_name="openweather")
        
        # Update cache if enabled
        if CACHE_LIFE_MINUTES > 0:
            weather_cache[cache_key] = raw_data
            cache_expiry[cache_key] = datetime.utcnow() + timedelta(minutes=CACHE_LIFE_MINUTES)
            logger.info(f"Cached data for location {lat},{lon} for {CACHE_LIFE_MINUTES} minutes")
        
        return transform_data(raw_data, cached=False)
    except HTTPException as e:
        # If we have cached data and the API fails, return cached data
        if CACHE_LIFE_MINUTES > 0 and cache_key in weather_cache:
            logger.warning(f"API failed, returning cached data for location {lat},{lon}")
            return transform_data(weather_cache[cache_key], cached=True)
        raise e

# Custom route handler
@app.api_route("/proxy", methods=["GET"])
@app.state.limiter.limit(os.getenv("OPENWEATHER_PROXY_REQUESTS_PER_MINUTE", "5") + "/minute")
async def openweather_proxy(request: Request):
    logger.info(f"{datetime.now().isoformat()} Received {request.method} request: {request.url} from {get_remote_address(request)}")
    return await proxy_endpoint(request)
