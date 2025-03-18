# Use an official Python runtime as a parent image
FROM python:3.11

# Set the working directory in the container
WORKDIR /app

# Copy the scripts and dependencies
COPY requirements.txt ./
COPY src/tempest-proxy.py ./
COPY src/parqet-proxy.py ./

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install supervisord
RUN pip install --no-cache-dir supervisor

# Copy the supervisord configuration file
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose the ports the scripts listen on
EXPOSE 8080 8081

# Run supervisord to manage both applications
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
