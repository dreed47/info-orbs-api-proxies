# API Proxies for InfoOrbs

## Proxies

### Parqet

http://localhost/parqet/proxy?id=66bf0c987debfb4f2bfd6539&timeframe=1w&perf=totalReturnGross&perfChart=perfHistory

### Tempest Weather

http://localhost/tempest/proxy?station_id=<YOUR_STATION_ID>&units_temp=f&units_wind=mph&units_pressure=mb&units_precip=in&units_distance=mi&api_key=<API_KEY>

### Time Zone

http://localhost/timezone/timezone?timeZone=America/Bogota&force=false

## INSTALL

### Build

```
docker build -t infoorb-proxies .
```

### Install

```
docker run -d -p 80:80 --restart unless-stopped --name infoorb-proxies infoorb-proxies
```

## UPDATE

```
docker stop infoorb-proxies
docker rm infoorb-proxies
docker build -t infoorb-proxies .
docker run -d -p 80:80 --restart unless-stopped --name infoorb-proxies infoorb-proxies
```

## OPTIONAL: USE DOCKER VOLUMES for faster development (this will use the .py directly)

```
docker run -d -p 80:80 --restart unless-stopped --name infoorb-proxies -v "$(pwd):/app" infoorb-proxies
```

## See

- https://github.com/brettdottech/info-orbs

## License

This software is distributed under MIT license. See LICENSE.txt for details.
