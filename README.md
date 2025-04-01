# API Proxies for InfoOrbs

This repo contains API proxies for the [Info Orbs project](https://github.com/brettdottech/info-orbs).

## Proxies Provided

- **Timezone Proxy URL:** [https://HOST/timezone/proxy](http://localhost/timezone/proxy?timeZone=America/Bogota&force=false)
  - Timezone offsets requests are cached in a SQLite DB and are only refreshed when it hits a time zone update
  - Timezone db can be pre-loaded after the initial install
  - Timezone data persists across container restarts
  - See [additional TimeZone proxy commands here](/README-docker.md#timezone-proxy-commands)
- **Visual Crossing Proxy URL:** [https://HOST/visualcrossing/proxy](http://localhost/visualcrossing/proxy/Stow,%20OH/next3days?key=VISUALCROSSING_DEFAULT_API_KEY&unitGroup=us&include=days,current&iconSet=icons1&lang=en)
- **Twelve Data Proxy URL:** [https://HOST/twelvedata/proxy](http://localhost/twelvedata/proxy?apikey=TWELVEDATA_DEFAULT_API_KEY&symbol=AAPL)
- **Tempest Proxy URL:** [https://HOST/tempest/proxy](http://localhost/tempest/proxy?station_id=<YOUR_STATION_ID>&units_temp=f&units_wind=mph&units_pressure=mb&units_precip=in&units_distance=mi&api_key=TEMPEST_DEFAULT_API_KEY)
- **OpenWeather Proxy URL:** [https://HOST/openweather/proxy](http://localhost/openweather/proxy?lat=41.9795&lon=-87.8865&appid=OPENWEATHER_DEFAULT_API_KEY&units=imperial&exclude=minutely,hourly,alerts&lang=en&cnt=3)
- **Parqet Proxy URL:** [https://HOST/parqet/proxy](http://localhost/parqet/proxy?id=66bf0c987debfb4f2bfd6539&timeframe=1w&perf=totalReturnGross&perfChart=perfHistory)

All proxies support passing a force=true in the url to bypass cache.

Check the [sample.env](/sample.env) file for environment variables that you can override using a local .env file or manually setting the environment variables for your deployment.

## Installation

<i>**note:** You may find it useful to alias docker-compose to dc (e.g. alias dc="docker-compose") to save typing. If you choose to not use this shortcut just replace all instacnes of "dc" to docker-compose" in this document.</i>

### Clone repo

```bash
git clone https://github.com/dreed47/info-orbs-api-proxies.git
cd info-orbs-api-proxies
```

### Setup Environment Variables

Either copy sample.env to .env and set your environment variables or manually add the environment variables to your deployment environment.

### Build and Start

```bash
dc up -d --build
```

### Optionally preload Timezones

This script preloads the Timezone db with the 50 most popular timezones (covering 95% of worlds population). The script will take some time to run as it attempts to preload the zones without exceeding the API limits.

```bash
dc exec proxy python -m scripts.preload_timezones
```

### Other commands

`dc down` -- Stop cleanly  
`dc logs -f` -- Tail all service logs  
`dc ps` -- Check running services  
`dc restart proxy` -- Restart just one service  
`dc exec proxy bash` -- Enter container shell

## Additional Resources

- [Info Orbs GitHub Repository](https://github.com/brettdottech/info-orbs)

## License

This software is distributed under the MIT license. See `LICENSE.txt` for details.
