"""Logs estructurados (RNF-17).

Una línea JSON por evento en stdout: `ts`, `level`, `logger`, `msg` y los campos que
se pasen en `extra=` (por ejemplo `room`, `user_id`, `event`). Nivel con LOG_LEVEL y
formato con LOG_FORMAT (`json` por defecto fuera de desarrollo, `text` en desarrollo).

Regla: identificar personas solo por id. Nada de correos, nombres, contraseñas ni
tokens en los mensajes ni en `extra`; `_redact` es una red de seguridad, no el control.
"""
import json
import os
import logging
import re
import sys
from datetime import datetime, timezone

_STANDARD_ATTRS = set(vars(logging.LogRecord('', 0, '', 0, '', (), None))) | {'message', 'asctime'}
_EMAIL = re.compile(r'[\w.+-]+@[\w-]+(\.[\w-]+)+')
# Tokens que viajan en la URL (restablecer contraseña) y que gunicorn escribiría en el access log.
_URL_TOKEN = re.compile(r'(/(?:reset-password)/)[^/\s?"]+')


def default_format():
    """`text` en desarrollo y `json` en el resto, salvo que LOG_FORMAT diga otra cosa."""
    env = os.environ.get('APP_ENV', 'development').strip().lower()
    return (os.environ.get('LOG_FORMAT') or ('text' if env == 'development' else 'json')).strip().lower()


def redact(text):
    text = _EMAIL.sub('<correo>', str(text))
    return _URL_TOKEN.sub(r'\1<token>', text)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {
            'ts': datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec='milliseconds'),
            'level': record.levelname,
            'logger': record.name,
            'msg': redact(record.getMessage()),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and not key.startswith('_'):
                data[key] = value if isinstance(value, (int, float, bool)) or value is None else redact(value)
        if record.exc_info:
            data['exc'] = redact(self.formatException(record.exc_info))
        return json.dumps(data, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def __init__(self):
        super().__init__('%(asctime)s %(levelname)s %(name)s: %(message)s')

    def format(self, record):
        return redact(super().format(record))


def configure_logging(level='info', fmt='json'):
    """Instala un único handler en el logger raíz. Idempotente (create_app se llama en cada test)."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, '_mytraining', False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler._mytraining = True
    handler.setFormatter(JsonFormatter() if fmt == 'json' else TextFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    # Werkzeug ya tiene su access log en desarrollo; engineio/socketio son muy verbosos.
    for noisy in ('engineio', 'socketio', 'engineio.server', 'socketio.server'):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def gunicorn_logger_class():
    """Logger de Gunicorn con el mismo formato y la misma redacción (lo usa gunicorn.conf.py).

    Se importa tarde para que la app no dependa de Gunicorn en desarrollo ni en los tests.
    """
    from gunicorn import glogging

    class RedactingLogger(glogging.Logger):
        def setup(self, cfg):
            super().setup(cfg)
            if default_format() != 'text':
                for handler in self.error_log.handlers:
                    handler.setFormatter(JsonFormatter())

        def atoms(self, resp, req, environ, request_time):
            atoms = super().atoms(resp, req, environ, request_time)
            for key in ('r', 'U', 'f'):
                atoms[key] = redact(atoms[key]).replace('"', "'")
            return atoms

    return RedactingLogger
