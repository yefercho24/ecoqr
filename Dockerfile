FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /data
EXPOSE 8000

# --proxy-headers: detrás de Render/Railway/nginx usa la IP real del estudiante para el límite de envíos
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
