# ── Kutubxona.uz — Django backend (ASGI: HTTP + WebSocket) ───────────────────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# PyMuPDF / Pillow / psycopg uchun runtime kutubxonalar + pg_isready (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        postgresql-client \
        libjpeg62-turbo \
        zlib1g \
        curl \
        dos2unix \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Media va static uchun kataloglar (volume bilan almashtiriladi)
RUN mkdir -p /app/media /app/staticfiles

# Windows'da CRLF bilan saqlangan bo'lsa ham skript ishlashi uchun
COPY entrypoint.sh /entrypoint.sh
RUN dos2unix /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "config.asgi:application", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
