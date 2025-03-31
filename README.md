# API Proxies for InfoOrbs

## Proxies

- **Timezone Proxy URL:** [https://HOST/timezone/proxy](http://localhost/timezone/proxy?timeZone=America/Bogota&force=false)
- **Visual Crossing Proxy URL:** [https://HOST/visualcrossing/proxy](http://localhost/visualcrossing/proxy/Stow,%20OH/next3days?key=VISUALCROSSING_DEFAULT_API_KEY&unitGroup=us&include=days,current&iconSet=icons1&lang=en)
- **Twelve Data Proxy URL:** [https://HOST/twelvedata/quote](http://localhost/twelvedata/quote?apikey=TWELVEDATA_DEFAULT_API_KEY&symbol=AAPL)
- **Tempest Proxy URL:** [https://HOST/tempest/proxy](http://localhost/tempest/proxy?station_id=<YOUR_STATION_ID>&units_temp=f&units_wind=mph&units_pressure=mb&units_precip=in&units_distance=mi&api_key=<TEMPEST_DEFAULT_API_KEY>)
- **Parqet Proxy URL:** [https://HOST/parqet/proxy](http://localhost/parqet/proxy?id=66bf0c987debfb4f2bfd6539&timeframe=1w&perf=totalReturnGross&perfChart=perfHistory)

You can override the default settings using the following environment variables:

```bash
TIMEZONE_PROXY_REQUESTS_PER_MINUTE="10"
TIMEZONE_RETRY_DELAY="3"
TIMEZONE_MAX_RETRIES="1"

VISUALCROSSING_PROXY_REQUESTS_PER_MINUTE="5"
VISUALCROSSING_PROXY_CACHE_LIFE="5"  # Set to 0 to disable

TWELVEDATA_PROXY_REQUESTS_PER_MINUTE="5"
TWELVEDATA_PROXY_CACHE_LIFE="5" # Set to 0 to disable

TEMPEST_PROXY_REQUESTS_PER_MINUTE="5"
TEMPEST_PROXY_CACHE_LIFE="5"         # Set to 0 to disable

PARQET_PROXY_REQUESTS_PER_MINUTE="5"
PARQET_PROXY_CACHE_LIFE="5"         # Set to 0 to disable
```

## Secrets Management

The `/secrets` folder is ignored by Git and is not checked into the repository. Use this folder to store sensitive information like API keys. Each file should be named after the secret it contains (e.g., `VISUALCROSSING_DEFAULT_API_KEY`).

When passing an API key in a URL, you can either provide a valid API key or use a placeholder string (e.g., `"PROXYNAME_DEFAULT_API_KEY"`). If set to the placeholder, the app will look for a file named `/secrets/PROXYNAME_DEFAULT_API_KEY` to retrieve the API key.

## Installation

### Build

```bash
docker build -t infoorb-proxies .
```

### Run

```bash
docker run -d -p 80:80 --restart unless-stopped --name infoorb-proxies -v "$(pwd)/secrets:/secrets" infoorb-proxies
```

## Update

```bash
docker stop infoorb-proxies
docker rm infoorb-proxies
docker build -t infoorb-proxies .
docker run -d -p 80:80 --restart unless-stopped --name infoorb-proxies -v "$(pwd)/secrets:/secrets" infoorb-proxies
```

## Optional: Use Docker Volumes for Faster Development

This approach uses the source files directly for quicker iterations:

```bash
docker run -d -p 80:80 --restart unless-stopped --name infoorb-proxies -v "$(pwd):/app" -v "$(pwd)/secrets:/secrets" infoorb-proxies
```

## Additional Resources

- [Info Orbs GitHub Repository](https://github.com/brettdottech/info-orbs)

## License

This software is distributed under the MIT license. See `LICENSE.txt` for details.
