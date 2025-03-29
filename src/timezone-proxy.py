import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional
import httpx
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

app = FastAPI()

# ===================== CONFIGURATION =====================
REQUESTS_PER_MINUTE = 1000
RETRY_DELAY = 3  # seconds to wait before retrying
MAX_RETRIES = 1  # number of retries for 502 errors
# ========================================================

# Configure logging
logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))
logger.addHandler(handler)

# Initialize Rate Limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{REQUESTS_PER_MINUTE}/minute"]
)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    logger.error(f"Rate limit exceeded - {exc.detail}")
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "proxy-info": {
                "status_code": status.HTTP_429_TOO_MANY_REQUESTS,
                "error": "rate_limit_exceeded",
                "message": f"Try again in {exc.detail.retry_after} seconds",
                "limit": exc.detail.limit
            }
        }
    )

TIME_API_BASE = "https://timeapi.io/api/timezone/zone"
timezone_cache: Dict[str, dict] = {}

class TimezoneRequest(BaseModel):
    timeZone: str
    force: Optional[bool] = False

def parse_iso_datetime(dt_str: str) -> datetime:
    if dt_str.endswith('Z'):
        dt_str = dt_str[:-1] + '+00:00'
    try:
        return datetime.fromisoformat(dt_str)
    except ValueError:
        if '.' in dt_str:
            return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%f%z")
        return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S%z")

def should_bypass_cache(cached_data: dict) -> bool:
    if not cached_data.get("hasDayLightSaving") or not cached_data.get("dstInterval"):
        return False
    try:
        dst_data = cached_data["dstInterval"]
        change_time = parse_iso_datetime(
            dst_data["dstEnd"] if cached_data["isDayLightSavingActive"] 
            else dst_data["dstStart"]
        )
        return datetime.now(timezone.utc) >= change_time
    except Exception as e:
        logger.warning(f"Cache validation failed: {str(e)}")
        return False

def create_response(original_data: dict, cached: bool, status_code: int = status.HTTP_200_OK):
    """Create response with original data and proxy metadata"""
    response = dict(original_data)  # Preserve all original fields
    
    # Calculate next timezone update if DST info exists
    next_update = None
    if original_data.get("hasDayLightSaving") and original_data.get("dstInterval"):
        try:
            dst_data = original_data["dstInterval"]
            change_str = dst_data["dstEnd"] if original_data["isDayLightSavingActive"] else dst_data["dstStart"]
            next_update = parse_iso_datetime(change_str).isoformat()
        except Exception as e:
            logger.warning(f"Failed to calculate next update: {str(e)}")
    
    # Add proxy-info field
    response["proxy-info"] = {
        "status_code": status_code,
        "cachedResponse": cached,
        "nextTimeZoneUpdate": next_update
    }
    
    return response

async def fetch_with_retry(timezone: str) -> dict:
    """Fetch data with retry logic for 502 errors"""
    url = f"{TIME_API_BASE}?timeZone={timezone}"
    last_error = None
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
                if response.status_code == 502 and attempt < MAX_RETRIES:
                    logger.warning(f"502 Bad Gateway - Attempt {attempt + 1}/{MAX_RETRIES + 1}")
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            last_error = e
            if e.response.status_code != 502 or attempt >= MAX_RETRIES:
                logger.error(f"API Error {e.response.status_code}: {e.response.text}")
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Time API error: {e.response.text}"
                )
        except httpx.RequestError as e:
            last_error = e
            if attempt >= MAX_RETRIES:
                logger.error(f"Network Error: {str(e)}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Proxy error: {str(e)}"
                )
    
    logger.error("Max retries exhausted")
    raise last_error if last_error else HTTPException(502, "Unknown proxy error")

@app.api_route("/proxy", methods=["GET", "POST"])
@limiter.limit(f"{REQUESTS_PER_MINUTE}/minute")
async def proxy_timezone(request: Request):
    """Proxy endpoint for timezone data"""
    client_ip = get_remote_address(request)
    logger.info(f"Timezone request from {client_ip}")

    try:
        if request.method == "GET":
            timezone = request.query_params.get("timeZone")
            force = request.query_params.get("force", "").lower() == "true"
        else:  # POST
            body = await request.json()
            request_data = TimezoneRequest(**body)
            timezone = request_data.timeZone
            force = request_data.force

        if not timezone:
            logger.error("Missing timeZone parameter")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "proxy-info": {
                        "status_code": status.HTTP_400_BAD_REQUEST,
                        "error": "missing_parameter", 
                        "message": "timeZone parameter is required"
                    }
                }
            )

        # Cache logic
        if not force and timezone in timezone_cache:
            if not should_bypass_cache(timezone_cache[timezone]):
                logger.info(f"Cache hit for {timezone}")
                return create_response(timezone_cache[timezone], True)

        # Fetch with retry logic
        raw_data = await fetch_with_retry(timezone)
        timezone_cache[timezone] = raw_data
        logger.info(f"Data fetched for {timezone}")
        return create_response(raw_data, False)

    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={
                "proxy-info": {
                    "status_code": e.status_code,
                    "error": "api_error" if e.status_code == 502 else "client_error",
                    "message": str(e.detail)
                }
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "proxy-info": {
                    "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "error": "internal_error",
                    "message": str(e)
                }
            }
        )
