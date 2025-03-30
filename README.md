# API Proxies for InfoOrbs

## Proxies

### Parqet

- test url=http://localhost/parqet/proxy?id=66bf0c987debfb4f2bfd6539&timeframe=1w&perf=totalReturnGross&perfChart=perfHistory
- These environment variables can be set
  ```bash
  PARQET_PROXY_REQUESTS_PER_MINUTE="5"
  ```

### Visual Crossing Weather

- test url=http://localhost/visualcrossing/proxy/Stow,%20OH/next3days?key=VISUALCROSSING_DEFAULT_API_KEY&unitGroup=us&include=days,current&iconSet=icons1&lang=en
- These environment variables can be set
  ```bash
  VISUALCROSSING_PROXY_REQUESTS_PER_MINUTE="5"
  ```
- NOTE: <i>URL can contain a valid API key or an API key set to "VISUALCROSSING_DEFAULT_API_KEY" If its set to "VISUALCROSSING_DEFAULT_API_KEY" then the app will look for a file called /secrets/VISUALCROSSING_DEFAULT_API_KEY to get the API key</I>

### Tempest Weather

- test url=http://localhost/tempest/proxy?station_id=<YOUR_STATION_ID>&units_temp=f&units_wind=mph&units_pressure=mb&units_precip=in&units_distance=mi&api_key=<TEMPEST_DEFAULT_API_KEY>
- These environment variables can be set
  ```bash
  TEMPEST_PROXY_REQUESTS_PER_MINUTE="5"
  ```
- NOTE: <i>URL can contain a valid API key or an API key set to "TEMPEST_DEFAULT_API_KEY" If its set to "TEMPEST_DEFAULT_API_KEY" then the app will look for a file called /secrets/TEMPEST_DEFAULT_API_KEY to get the API key</I>

### Time Zone

- test url=http://localhost/timezone/proxy?timeZone=America/Bogota&force=false
- These environment variables can be set
  ```bash
  TIMEZONE_PROXY_REQUESTS_PER_MINUTE="10"
  TIMEZONE_RETRY_DELAY="3"
  TIMEZONE_MAX_RETRIES="1"
  ```

## Secrets Management

The /secrets folder is ignored by git so it's not checked into the repo. It can be used to store things like API keys. Files in the secrets folder should be named the same as the secret (e.g. VISUALCROSSING_DEFAULT_API_KEY)

## INSTALL

### Build

```
docker build -t infoorb-proxies .
```

### Install

```
docker run -d -p 80:80 --restart unless-stopped --name infoorb-proxies -v "$(pwd)/secrets:/secrets" infoorb-proxies
```

## UPDATE

```
docker stop infoorb-proxies
docker rm infoorb-proxies
docker build -t infoorb-proxies .
docker run -d -p 80:80 --restart unless-stopped --name infoorb-proxies -v "$(pwd)/secrets:/secrets" infoorb-proxies
```

## OPTIONAL: USE DOCKER VOLUMES for faster development (this will use the .py directly)

```
docker run -d -p 80:80 --restart unless-stopped --name infoorb-proxies -v "$(pwd):/app" -v "$(pwd)/secrets:/secrets" infoorb-proxies
```

## See

- https://github.com/brettdottech/info-orbs

## License

This software is distributed under MIT license. See LICENSE.txt for details.
