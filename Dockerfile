FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY bot_sales ./bot_sales
COPY dashboard ./dashboard
COPY maintenance ./maintenance
COPY website ./website
COPY data ./data
COPY config ./config
COPY migrations ./migrations
COPY static ./static
COPY tenants ./tenants
COPY tenants.yaml ./tenants.yaml
COPY faqs.json ./faqs.json
COPY *.py ./

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import os, sys, urllib.request; url = 'http://127.0.0.1:%s/health' % os.environ.get('PORT', '5000'); resp = urllib.request.urlopen(url, timeout=5); sys.exit(0 if resp.status == 200 else 1)"

EXPOSE 5000

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} wsgi:app"]
