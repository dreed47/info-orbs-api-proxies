# Use an official Python runtime as a parent image
FROM python:3.11

# Install Nginx
RUN apt-get update && apt-get install -y nginx

# Set the working directory
WORKDIR /app

# Copy the requirements file
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install supervisord
RUN pip install --no-cache-dir supervisor

# Copy the Python scripts from the src folder
COPY src/ ./src/

# Copy Nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Copy supervisord configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose port 80 for Nginx
EXPOSE 80

# Run supervisord to manage Nginx and Python apps
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
