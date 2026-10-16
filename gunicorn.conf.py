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
threads = int(os.environ.get('GUNICORN_THREADS', '64'))

# Los websockets son conexiones largas; no matar el worker por inactividad.
timeout = 0
graceful_timeout = 30
keepalive = 5

accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('LOG_LEVEL', 'info')
