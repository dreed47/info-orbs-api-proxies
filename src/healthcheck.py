import logging
from fastapi import FastAPI, HTTPException
import httpx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Map of proxy names to their health endpoints
PROXY_HEALTH_ENDPOINTS = {
    "timezone": "http://127.0.0.1/timezone/health",
    "visualcrossing": "http://127.0.0.1/visualcrossing/health",
    "twelvedata": "http://127.0.0.1/twelvedata/health",
    "tempest": "http://127.0.0.1/tempest/health",
    "openweather": "http://127.0.0.1/openweather/health",
    "parqet": "http://127.0.0.1/parqet/health",
    "zoneinfo": "http://127.0.0.1/zoneinfo/health",
    "mlbdata": "http://127.0.0.1/mlbdata/health",
    #"nfldata": "http://127.0.0.1/nfldata/health",
}

@app.get("/health")
async def health():
    results = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for proxy_name, url in PROXY_HEALTH_ENDPOINTS.items():
            try:
                response = await client.get(url)
                response.raise_for_status()
                results[proxy_name] = {"status": "OK", "detail": response.json()}
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                results[proxy_name] = {"status": "ERROR", "detail": str(e)}
                logger.error(f"Health check failed for {proxy_name}: {str(e)}")
    
    # Return 503 if any proxy is unhealthy
    if any(result["status"] == "ERROR" for result in results.values()):
        raise HTTPException(status_code=503, detail={"health": results})
    return {"health": results}
