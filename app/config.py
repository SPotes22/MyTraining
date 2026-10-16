# app/config.py
import os

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


# Valores de ejemplo que NUNCA deben llegar a pre-producción/producción.
INSECURE_DEFAULTS = {
    'SECRET_KEY': 'clave-secreta-capacitacion-2026',
    'SUPERUSER_PASSWORD': 'admin1234',
}


class Config:
    # development | preproduction | production
    APP_ENV = os.environ.get('APP_ENV', 'development').strip().lower()

    SECRET_KEY = os.environ.get('SECRET_KEY', INSECURE_DEFAULTS['SECRET_KEY'])
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # SQLite: esperar hasta 30 s por el bloqueo de escritura en vez de fallar
    # de inmediato con "database is locked" cuando varios estudiantes envían a la vez.
    SQLALCHEMY_ENGINE_OPTIONS = (
        {'connect_args': {'timeout': 30}}
        if SQLALCHEMY_DATABASE_URI.startswith('sqlite') else {'pool_pre_ping': True}
    )

    SUPERUSER_EMAIL = os.environ.get('SUPERUSER_EMAIL', 'admin@capacitacion.com')
    SUPERUSER_PASSWORD = os.environ.get('SUPERUSER_PASSWORD', INSECURE_DEFAULTS['SUPERUSER_PASSWORD'])
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
    """Falla al arrancar si un entorno no-dev usa secretos de ejemplo."""
    if config.get('APP_ENV', 'development') == 'development' or config.get('TESTING'):
        return
    problems = [
        key for key, insecure in INSECURE_DEFAULTS.items()
        if not config.get(key) or config.get(key) == insecure
    ]
    if len(config.get('SECRET_KEY') or '') < 32:
        problems.append('SECRET_KEY (mínimo 32 caracteres)')
    if problems:
        raise RuntimeError(
            'Configuración insegura para APP_ENV=%s: define %s en el entorno.'
            % (config.get('APP_ENV'), ', '.join(sorted(set(problems))))
        )
