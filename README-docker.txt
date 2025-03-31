# ===========
# INSTALL
# ===========
# Build
docker build -t infoorb-proxies .

# Install 
docker run -d \
  -p 80:80 \
  --restart unless-stopped \
  --name infoorb-proxies \
  -v "$(pwd)/secrets:/secrets" \
  --log-driver json-file \
  --log-opt max-size=1m \
  --log-opt max-file=3 \
  infoorb-proxies


# ===========
# UPDATE
# ===========
docker stop infoorb-proxies
docker rm infoorb-proxies
docker build -t infoorb-proxies .
docker run -d \
  -p 80:80 \
  --restart unless-stopped \
  --name infoorb-proxies \
  -v "$(pwd)/secrets:/secrets" \
  --log-driver json-file \
  --log-opt max-size=1m \
  --log-opt max-file=3 \
  infoorb-proxies


# OPTIONAL: USE DOCKER VOLUMES for faster development (this will use the .py directly)

docker run -d \
  -p 80:80 \
  --restart unless-stopped \
  --name infoorb-proxies \
  -v "$(pwd):/app" \
  -v "$(pwd)/secrets:/secrets" \
  --log-driver json-file \
  --log-opt max-size=1m \
  --log-opt max-file=3 \
  infoorb-proxies


# ===========
# CHECK
# ===========
# Check logs
docker logs infoorb-proxies

# Check running processes
docker ps
