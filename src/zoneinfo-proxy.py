from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Optional
import os
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from .common import setup_logger, create_app, handle_request

logger = setup_logger("ZONEINFO")
app = create_app("zoneinfo_proxy")

@app.on_event("startup")
async def startup_event():
    logger.info("="*50)
    logger.info(f"{'ZoneInfo Service Configuration':^50}")
    logger.info("="*50)
    logger.info(f"→ Rate limiting: {os.getenv('ZONEINFO_PROXY_REQUESTS_PER_MINUTE', '10')} requests/minute per IP")
    logger.info("="*50 + "\n")

class TimezoneRequest(BaseModel):
    timeZone: str

def get_zoneinfo_data(timezone: str) -> Dict:
    """Get timezone information using Python's zoneinfo module."""
    try:
        zone = ZoneInfo(timezone)
        now = datetime.now(zone)
        
        # Get DST information if available
        has_dst = zone.dst(now) is not None
        is_dst_active = has_dst and zone.dst(now).total_seconds() > 0
        
        return {
            "timeZone": timezone,
            "currentLocalTime": now.isoformat(),
            "currentUtcOffset": zone.utcoffset(now).total_seconds() / 3600,
            "hasDayLightSaving": has_dst,
            "isDayLightSavingActive": is_dst_active,
            "dstInterval": None,  # zoneinfo doesn't provide future DST transitions
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_timezone", "message": str(e)}
        )

def create_response(original_data: dict, status_code: int = 200):
    response = dict(original_data)
    response["proxy-info"] = {
        "status_code": status_code,
        "source": "python-zoneinfo"
    }
    return response

async def proxy_endpoint(request: Request):
    if request.method == "GET":
        timezone = request.query_params.get("timeZone")
    else:
        body = await request.json()
        request_data = TimezoneRequest(**body)
        timezone = request_data.timeZone

    if not timezone:
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_parameter", "message": "timeZone parameter is required"}
        )

    zone_data = get_zoneinfo_data(timezone)
    return create_response(zone_data)

handle_request(app, logger, proxy_endpoint)
