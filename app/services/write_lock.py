"""Serializa en el proceso las escrituras pesadas cuando la base es SQLite (RNF-08).

SQLite admite un solo escritor. Con 64 hilos enviando a la vez, los que no obtienen el
candado de escritura reintentan con esperas crecientes (busy_timeout) y compiten por
el GIL: medido, 50 envíos simultáneos tardaban p95 2,5 s. Haciendo fila en un
threading.Lock, cada envío entra apenas sale el anterior: p95 0,85 s con el mismo
hardware (docs/AUDITORIA_PREPRODUCCION.md §4.1).

Vale porque hay exactamente un worker de Gunicorn (CLAUDE.md). Con PostgreSQL no se
aplica: ahí las escrituras concurrentes sí escalan.
"""
import threading
from contextlib import nullcontext
from functools import wraps

from flask import current_app

_lock = threading.RLock()  # reentrante: una vista serializada puede llamar código que también lo pide


def sqlite_write_lock():
    """Context manager: el candado del proceso si la base es SQLite; nada en otro caso."""
    if str(current_app.config.get('SQLALCHEMY_DATABASE_URI', '')).startswith('sqlite'):
        return _lock
    return nullcontext()


def serialize_on_sqlite(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        with sqlite_write_lock():
            return view(*args, **kwargs)
    return wrapper
