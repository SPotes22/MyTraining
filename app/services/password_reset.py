"""RF-028: enlaces de recuperación de contraseña de un solo uso.

El token firma el id del usuario y una huella de su hash de contraseña actual: en cuanto
la contraseña cambia, el enlace deja de servir (un solo uso). Caduca a los
PASSWORD_RESET_MAX_AGE segundos (30 min por defecto).
"""
import hashlib

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_SALT = 'password-reset-v1'


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=_SALT)


def _fingerprint(user):
    return hashlib.sha256((user.password_hash or '').encode('utf-8')).hexdigest()[:16]


def make_token(user):
    return _serializer().dumps({'uid': user.id, 'fp': _fingerprint(user)})


def verify_token(token):
    """Devuelve el usuario si el enlace es válido, vigente y no se ha usado; si no, None."""
    from app.extensions import db
    from app.models import User
    try:
        data = _serializer().loads(token, max_age=current_app.config.get('PASSWORD_RESET_MAX_AGE', 1800))
    except (SignatureExpired, BadSignature):
        return None
    user = db.session.get(User, data.get('uid'))
    if not user or not user.email or not user.password_hash or data.get('fp') != _fingerprint(user):
        return None
    return user
