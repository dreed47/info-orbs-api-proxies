import logging
from datetime import datetime, timezone
from typing import Dict, Optional
import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

app = FastAPI()

logger = logging.getLogger("uvicorn")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Rate Limiter (5 requests per minute per IP)
limiter = Limiter(key_func=get_remote_address, default_limits=["5/minute"])
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Time API base URL
TIME_API_BASE = "https://timeapi.io/api/timezone/zone"

# In-memory storage for timezone data
timezone_cache: Dict[str, dict] = {}

class TimezoneRequest(BaseModel):
    timeZone: str
    force: Optional[bool] = False

def parse_iso_datetime(dt_str: str) -> datetime:
    """Improved ISO datetime string parser that handles various formats"""
    try:
        # Handle the 'Z' timezone indicator
        if dt_str.endswith('Z'):
            dt_str = dt_str[:-1] + '+00:00'
        
        # Try parsing with timezone first
        try:
            return datetime.fromisoformat(dt_str)
        except ValueError:
            # Fallback for different formats
            if '.' in dt_str:  # Contains milliseconds/nanoseconds
                return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%f%z")
            else:
                return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S%z")
    except Exception as e:
        logger.error(f"Failed to parse datetime string '{dt_str}': {str(e)}")
        raise ValueError(f"Invalid datetime format: {dt_str}")

def should_bypass_cache(cached_data: dict) -> bool:
    """Check if we should bypass cache based on next timezone update"""
    if not cached_data.get("hasDayLightSaving") or not cached_data.get("dstInterval"):
        return False
    
    try:
        dst_data = cached_data["dstInterval"]
        if cached_data["isDayLightSavingActive"]:
            next_change_str = dst_data["dstEnd"]
        else:
            next_change_str = dst_data["dstStart"]
        
        next_change = parse_iso_datetime(next_change_str)
        return datetime.now(timezone.utc) >= next_change
    except Exception as e:
        logger.warning(f"Could not check cache bypass time: {str(e)}")
        return False

def transform_timezone_data(data: dict, cached: bool) -> dict:
    """Transform the raw API response with all required fields"""
    transformed = {
        "timeZone": data.get("timeZone"),
        "currentLocalTime": data.get("currentLocalTime"),
        "currentUtcOffset": data.get("currentUtcOffset", {}),
        "standardUtcOffset": data.get("standardUtcOffset", {}),
        "hasDayLightSaving": data.get("hasDayLightSaving"),
        "isDayLightSavingActive": data.get("isDayLightSavingActive"),
        "cachedResponse": cached,
        "dstInterval": data.get("dstInterval")
    }

    # Calculate nextTimeZoneUpdate if DST information exists
    if data.get("hasDayLightSaving") and data.get("dstInterval"):
        try:
            dst_data = data["dstInterval"]
            if data["isDayLightSavingActive"]:
                next_change_str = dst_data["dstEnd"]
            else:
                next_change_str = dst_data["dstStart"]
            
            next_change = parse_iso_datetime(next_change_str)
            transformed["nextTimeZoneUpdate"] = next_change.astimezone(timezone.utc).isoformat()
        except Exception as e:
            logger.error(f"Failed to calculate nextTimeZoneUpdate: {str(e)}")
            transformed["nextTimeZoneUpdate"] = None
    else:
        transformed["nextTimeZoneUpdate"] = None

    return transformed

@app.post("/timezone")
@app.get("/timezone")
@limiter.limit("5/minute")
async def get_timezone(request: Request):
    """Endpoint handler with automatic cache bypass when update is needed"""
    client_ip = get_remote_address(request)
    logger.info(f"🌐 Received {request.method} request from {client_ip}")

    # Get parameters
    if request.method == "GET":
        timezone = request.query_params.get("timeZone")
        force = request.query_params.get("force", "").lower() == "true"
    elif request.method == "POST":
        try:
            body = await request.json()
            request_data = TimezoneRequest(**body)
            timezone = request_data.timeZone
            force = request_data.force
        except Exception as e:
            logger.error(f"❌ Invalid request: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid JSON body or missing timeZone parameter.")
    else:
        logger.error("❌ Unsupported method")
        raise HTTPException(status_code=400, detail="Unsupported request method")

    if not timezone:
        logger.error("❌ Missing timezone parameter")
        raise HTTPException(status_code=400, detail="Missing required timeZone parameter")

    # Check if we should bypass cache (either forced or due to timezone update)
    bypass_cache = force
    if not bypass_cache and timezone in timezone_cache:
        bypass_cache = should_bypass_cache(timezone_cache[timezone])
        if bypass_cache:
            logger.info(f"🟡 CACHE EXPIRED: Bypassing cache for {timezone} due to timezone update")

    if not bypass_cache and timezone in timezone_cache:
        logger.info(f"🟢 CACHE HIT: Returning cached data for {timezone}")
        return transform_timezone_data(timezone_cache[timezone], cached=True)

    # Fetch from API
    try:
        raw_data = await fetch_timezone_data(timezone)
        timezone_cache[timezone] = raw_data
        logger.info(f"✅ CACHE UPDATE: Stored data for {timezone}")
        return transform_timezone_data(raw_data, cached=False)
    except HTTPException as e:
        logger.error(f"🔴 Failed to process {timezone}: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"🔴 Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

async def fetch_timezone_data(timezone: str) -> dict:
    """Fetch timezone data from external API"""
    url = f"{TIME_API_BASE}?timeZone={timezone}"
    logger.info(f"🔵 API CALL: Fetching fresh data for {timezone}")
    
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"🔴 API ERROR {e.response.status_code}: {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=f"Time API error: {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"🔴 NETWORK ERROR: {str(e)}")
            raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")
