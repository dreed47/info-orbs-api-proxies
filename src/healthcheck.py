import logging
from fastapi import FastAPI, HTTPException
import httpx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Map of proxy names to their health and test URLs
PROXY_HEALTH_ENDPOINTS = {
    "timezone": {
        "health_url": "http://127.0.0.1/timezone/health",
        "test_url": "https://info-orbs-proxy.onrender.com/timezone/proxy?timeZone=Africa/Bujumbura&force=false"
    },
    "visualcrossing": {
        "health_url": "http://127.0.0.1/visualcrossing/health",
        "test_url": "https://info-orbs-proxy.onrender.com/visualcrossing/proxy/Stow,%20OH/next3days?key=&unitGroup=us&include=days,current&iconSet=icons1&lang=en"
    },
    "twelvedata": {
        "health_url": "http://127.0.0.1/twelvedata/health",
        "test_url": "https://info-orbs-proxy.onrender.com/twelvedata/proxy?apikey=&symbol=AMZN"
    },
    "tempest": {
        "health_url": "http://127.0.0.1/tempest/health",
        "test_url": "https://info-orbs-proxy.onrender.com/tempest/proxy?station_id=93748&units_temp=f&units_wind=mph&units_pressure=mb&units_precip=in&units_distance=mi&api_key="
    },
    "openweather": {
        "health_url": "http://127.0.0.1/openweather/health",
        "test_url": "https://info-orbs-proxy.onrender.com/openweather/proxy?lat=41.9795&lon=-87.8865&appid=&units=imperial&exclude=minutely,hourly,alerts&lang=en&cnt=3"
    },
    "parqet": {
        "health_url": "http://127.0.0.1/parqet/health",
        "test_url": "https://info-orbs-proxy.onrender.com/parqet/proxy?id=66bf0c987debfb4f2bfd6539&timeframe=today&perf=totalReturnGross&perfChart=perfHistory"
    },
    "zoneinfo": {
        "health_url": "http://127.0.0.1/zoneinfo/health",
        "test_url": None
    },
    "mlbdata": {
        "health_url": "http://127.0.0.1/mlbdata/health",
        "test_url": "https://info-orbs-proxy.onrender.com/mlbdata/proxy?teamName=pirates&force=true"
    },
    #"nfldata": {
    #    "health_url": "http://127.0.0.1/nfldata/health",
    #    "test_url": None
    #}
}

@app.get("/health")
async def health():
    results = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for proxy_name, urls in PROXY_HEALTH_ENDPOINTS.items():
            health_url = urls["health_url"]
            test_url = urls["test_url"]
            try:
                response = await client.get(health_url)
                response.raise_for_status()
                results[proxy_name] = {
                    "status": "OK",
                    "detail": response.json(),
                    "test_url": test_url
                }
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                results[proxy_name] = {
                    "status": "ERROR",
                    "detail": str(e),
                    "test_url": test_url
                }
                logger.error(f"Health check failed for {proxy_name}: {str(e)}")
    
    # Return 503 if any proxy is unhealthy
    if any(result["status"] == "ERROR" for result in results.values()):
        raise HTTPException(status_code=503, detail={"health": results})
    return {"health": results}
