# app/config.py
import hashlib
import os
import secrets

def _load_env_file(dotenv_path='.env'):
    if os.path.exists(dotenv_path):
        with open(dotenv_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key not in os.environ:
                        os.environ[key] = val

_load_env_file()


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on', 'si', 'sí')


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# SHA-256 de secretos de ejemplo que se publicaron en el historial del repositorio
# (SECRET_KEY y contraseñas de superusuario/profesor demo de versiones anteriores).
# Se guardan como hash para no volver a publicar los valores; fuera de desarrollo
# la app se niega a arrancar si alguno sigue en uso (p. ej. un .env viejo copiado).
LEAKED_SECRET_SHA256 = frozenset({
    '8491107a0633480aafe6c324864df6ae92130218dded78061c8975f86e9dd10e',
    'ac9689e2272427085e35b9d3e3e8bed88cb3434828b43b86fc0596cad4c6e270',
    '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9',
})


def is_leaked_secret(value):
    return bool(value) and hashlib.sha256(value.encode('utf-8')).hexdigest() in LEAKED_SECRET_SHA256


def generate_dev_password():
    """Contraseña aleatoria para cuentas creadas en desarrollo sin clave definida."""
    return secrets.token_urlsafe(12)


class Config:
    # development | preproduction | production
    APP_ENV = os.environ.get('APP_ENV', 'development').strip().lower()

    # Sin SECRET_KEY definida se genera una aleatoria por proceso: válido en desarrollo
    # (las sesiones se cierran al reiniciar); fuera de desarrollo validate_config la exige.
    SECRET_KEY_FROM_ENV = bool(os.environ.get('SECRET_KEY'))
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # SQLite: esperar hasta 30 s por el bloqueo de escritura en vez de fallar
    # de inmediato con "database is locked" cuando varios estudiantes envían a la vez.
    SQLALCHEMY_ENGINE_OPTIONS = (
        {'connect_args': {'timeout': 30}}
        if SQLALCHEMY_DATABASE_URI.startswith('sqlite') else {'pool_pre_ping': True}
    )

    SUPERUSER_EMAIL = os.environ.get('SUPERUSER_EMAIL', 'admin@capacitacion.com')
    # Sin valor: en desarrollo se genera una contraseña aleatoria y se muestra una vez en consola.
    SUPERUSER_PASSWORD = os.environ.get('SUPERUSER_PASSWORD') or None
    # Contraseña del profesor demo (SEED_DEMO_DATA). Sin valor: aleatoria, mostrada en consola.
    DEMO_INSTRUCTOR_PASSWORD = os.environ.get('DEMO_INSTRUCTOR_PASSWORD') or None
    SUPERUSER_USERNAME = os.environ.get('SUPERUSER_USERNAME', 'SuperAdmin')
    # Si es true, la contraseña del superusuario se re-sincroniza desde .env en cada arranque.
    SUPERUSER_RESET_ON_BOOT = _env_bool('SUPERUSER_RESET_ON_BOOT', APP_ENV == 'development')
    # RN-09: el rol instructor lo asigna un administrador. Activar solo si el modelo de
    # negocio requiere que los profesores se registren solos (embudo de adquisición).
    ALLOW_INSTRUCTOR_SIGNUP = _env_bool('ALLOW_INSTRUCTOR_SIGNUP', APP_ENV == 'development')
    # Datos de demostración (profesor "profesor@capacitacion.com" / examen de redes).
    SEED_DEMO_DATA = _env_bool('SEED_DEMO_DATA', APP_ENV == 'development')

    # Cookies de sesión
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = _env_bool('SESSION_COOKIE_SECURE', APP_ENV != 'development')
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    PREFERRED_URL_SCHEME = 'https' if APP_ENV != 'development' else 'http'

    # CSRF (Flask-WTF). Sin caducidad propia: el token vive lo que la sesión, para que
    # un examen largo o una pestaña abierta horas no termine en "400 Bad Request".
    WTF_CSRF_TIME_LIMIT = None

    # Límites de la plataforma (ver docs/AUDITORIA_PREPRODUCCION.md §4)
    MAX_CONTENT_LENGTH = _env_int('MAX_UPLOAD_MB', 50) * 1024 * 1024
    MIN_PASSWORD_LENGTH = _env_int('MIN_PASSWORD_LENGTH', 8)
    LOGIN_MAX_ATTEMPTS = _env_int('LOGIN_MAX_ATTEMPTS', 5)
    LOGIN_LOCKOUT_SECONDS = _env_int('LOGIN_LOCKOUT_SECONDS', 15 * 60)

    # Orígenes permitidos para Socket.IO (coma-separados). Vacío = mismo origen.
    SOCKETIO_CORS_ORIGINS = [o.strip() for o in os.environ.get('SOCKETIO_CORS_ORIGINS', '').split(',') if o.strip()]

    # Detrás de Nginx / balanceador de GCP: confiar en X-Forwarded-* de N saltos.
    PROXY_FIX_HOPS = _env_int('PROXY_FIX_HOPS', 0 if APP_ENV == 'development' else 1)


def validate_config(config):
    """Falla al arrancar si un entorno no-dev no define sus secretos o usa uno ya publicado."""
    if config.get('APP_ENV', 'development') == 'development' or config.get('TESTING'):
        return
    problems = []
    secret_key = config.get('SECRET_KEY') or ''
    if not config.get('SECRET_KEY_FROM_ENV', True) or len(secret_key) < 32 or is_leaked_secret(secret_key):
        problems.append('SECRET_KEY (propia, mínimo 32 caracteres)')
    password = config.get('SUPERUSER_PASSWORD') or ''
    if len(password) < config.get('MIN_PASSWORD_LENGTH', 8) or is_leaked_secret(password):
        problems.append('SUPERUSER_PASSWORD (propia, mínimo %d caracteres)' % config.get('MIN_PASSWORD_LENGTH', 8))
    if problems:
        raise RuntimeError(
            'Configuración insegura para APP_ENV=%s: define %s en el entorno.'
            % (config.get('APP_ENV'), ', '.join(problems))
        )
