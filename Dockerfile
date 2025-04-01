FROM python:3.11

RUN apt-get update && \
    apt-get install -y nginx && \
    apt-get install -y sqlite3 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt supervisor

COPY src/ ./src/
COPY nginx.conf /etc/nginx/nginx.conf
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

COPY scripts/ /app/scripts/
RUN chmod -R +x /app/scripts/

EXPOSE 80
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
