# ===========
# INSTALL
# ===========
# Build
docker build -t infoorb-proxies .

# Install 
docker run -d -p 8080:8080 -p 8081:8081 --restart unless-stopped --name infoorb-proxies infoorb-proxies


# ===========
# UPDATE
# ===========
docker stop infoorb-proxies
docker rm infoorb-proxies
docker build -t infoorb-proxies .
docker run -d -p 8080:8080 -p 8081:8081 --restart unless-stopped --name infoorb-proxies infoorb-proxies


# OPTIONAL: USE DOCKER VOLUMES for faster development (this will use the .py directly)
docker run -d -p 8080:8080 -p 8081:8081 --restart unless-stopped --name infoorb-proxies -v "$(pwd):/app" infoorb-proxies




# ===========
# CHECK
# ===========
# Check logs
docker logs infoorb-proxies

# Check running processes
docker ps
