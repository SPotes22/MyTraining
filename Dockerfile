# Imagen pre-producción: un solo contenedor Flask + Gunicorn + SQLite (SAD V3 §11).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=preproduction \
    PORT=8080 \
    DATABASE_URL=sqlite:////data/mytraining.db

WORKDIR /srv/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# /data: base SQLite.  app/static/uploads: material subido por instructores.
# Ambos DEBEN montarse en volúmenes persistentes (disco persistente de GCE / volumen Docker).
RUN useradd --system --uid 10001 app \
    && mkdir -p /data /srv/app/app/static/uploads \
    && chown -R app /data /srv/app/app/static/uploads
USER app
VOLUME ["/data", "/srv/app/app/static/uploads"]

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8080\")}/healthz', timeout=4)"

CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
