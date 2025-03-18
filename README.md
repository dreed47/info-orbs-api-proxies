# API Proxies for InfoOrbs

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
