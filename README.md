# API Proxies for InfoOrbs

This repository contains API proxies for the [InfoOrbs project](https://github.com/brettdottech/info-orbs).

## Proxies Provided

- **ZoneInfo Timezone Proxy URL:**  
  Example: `http://localhost/zoneinfo/proxy?timeZone=America/Bogota`

  - Timezone info using the python's built-in [zoneinfo library](https://docs.python.org/3/library/zoneinfo.html)
  - Uses the IANA Time Zone Database (tzdata) shipped with Python or the OS
  - The timezone data is fixed at the time Python/your app was installed or compiled
  - To update timezone rules (e.g., for new DST changes), you must update the tzdata package

- **Timezone Database Proxy URL:**  
  Example: `http://localhost/timezone/proxy?timeZone=America/Bogota&force=false`

  - Real-time timezone offset from timeapi.io, requests are cached in a SQLite database
  - Data is only refreshed when a time zone update is detected
  - Database can be pre-loaded after initial installation
  - Data persists across container restarts
  - [Additional TimeZone proxy commands](/README-docker.md#timezone-proxy-commands)

- **Visual Crossing Proxy URL:**  
  Example: `http://localhost/visualcrossing/proxy/Stow,%20OH/next3days?key=&unitGroup=us&include=days,current&iconSet=icons1&lang=en&force=false`

- **Twelve Data Proxy URL:**  
  Example: `http://localhost/twelvedata/proxy?apikey=&symbol=AAPL&force=false`

- **Tempest Proxy URL:**  
  Example: `http://localhost/tempest/proxy?station_id=<YOUR_STATION_ID>&units_temp=f&units_wind=mph&units_pressure=mb&units_precip=in&units_distance=mi&api_key=&force=false`

- **OpenWeather Proxy URL:**  
  Example: `http://localhost/openweather/proxy?lat=41.9795&lon=-87.8865&appid=&units=imperial&exclude=minutely,hourly,alerts&lang=en&cnt=3&force=false`

- **Parqet Proxy URL:**  
  Example: `http://localhost/parqet/proxy?id=66bf0c987debfb4f2bfd6539&timeframe=1w&perf=totalReturnGross&perfChart=perfHistory&force=false`

> All proxies (except zoneinfo) support `force=true` parameter to bypass cache.

## Installation

**Note:** Consider aliasing `docker-compose` to `dc` for convenience:

```bash
alias dc="docker-compose"
```

If not using this alias, replace all `dc` commands with `docker-compose`.

### Clone the Repository

```bash
git clone https://github.com/dreed47/info-orbs-api-proxies.git
cd info-orbs-api-proxies
```

### Set Up Environment Variables

Either:

1. Copy `sample.env` to `.env` and modify values, or
2. Manually configure environment variables

### Build and Start

```bash
dc up -d --build
```

### Preload Timezones (Optional)

Preloads top 50 timezones (covers 95% of world population):

```bash
dc exec proxy python -m scripts.preload_timezones
```

### Common Commands

| Command              | Description     |
| -------------------- | --------------- |
| `dc down`            | Stop containers |
| `dc logs -f`         | View logs       |
| `dc ps`              | List services   |
| `dc restart proxy`   | Restart service |
| `dc exec proxy bash` | Enter container |

## Resources

- [InfoOrbs GitHub](https://github.com/brettdottech/info-orbs)

## License

MIT License - See [LICENSE.txt](LICENSE.txt)
