# gunicorn.conf.py — despliegue pre-producción (contenedor único, SQLite).
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"

# UN SOLO worker es obligatorio, no una preferencia:
#  1. El estado de las salas en vivo (app/realtime/manager.py) vive en memoria del
#     proceso; con 2+ workers cada uno vería salas distintas.
#  2. SQLite admite un único escritor; más procesos solo aumentan la contención.
# La concurrencia se obtiene con hilos (Flask-SocketIO en modo threading + simple-websocket).
workers = 1
worker_class = 'gthread'
# Cada websocket abierto ocupa un hilo mientras dura la conexión: este número es el TOPE
# de estudiantes conectados a la vez (más ~30 para peticiones HTTP). Con 64 solo
# entraban 64 estudiantes (medido, RNF-09). 256 hilos ociosos cuestan poca memoria.
threads = int(os.environ.get('GUNICORN_THREADS', '256'))

# Los websockets son conexiones largas; no matar el worker por inactividad.
timeout = 0
graceful_timeout = 30
keepalive = 5

accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('LOG_LEVEL', 'info')

# RNF-17: access log en JSON (una línea por petición) y error log con el formato de
# app/logging_setup.py. El logger redacta correos y tokens de /reset-password/ en la URL.
# No incluye User-Agent ni Referer; la IP sí (seguridad), y se conserva poco (ver manual).
_dev = os.environ.get('APP_ENV', 'development').strip().lower() == 'development'
if (os.environ.get('LOG_FORMAT') or ('text' if _dev else 'json')).strip().lower() != 'text':
    access_log_format = ('{"ts": "%(t)s", "level": "INFO", "logger": "gunicorn.access", "ip": "%(h)s", '
                         '"method": "%(m)s", "path": "%(U)s", "status": %(s)s, "bytes": "%(B)s", "ms": %(M)s}')


def _logger_class():
    from app.logging_setup import gunicorn_logger_class
    return gunicorn_logger_class()


logger_class = _logger_class
