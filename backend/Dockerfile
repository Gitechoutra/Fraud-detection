FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    FLASK_ENV=production \
    TZ=Asia/Kolkata

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p logs portal/uploads

EXPOSE 5000
# Build/upgrade the schema and SQL engine, load demo data (idempotent), then serve.
# One worker with many threads: the live-traffic simulator lives in process memory.
CMD ["sh", "-c", "flask db upgrade && flask seed && gunicorn -w 1 --threads 16 -b 0.0.0.0:5000 --access-logfile - wsgi:app"]
