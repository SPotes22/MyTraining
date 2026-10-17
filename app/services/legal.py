"""RL-01, RL-02, RL-11, RL-12: términos, política de tratamiento y autorización registrada.

Cambiar el texto de `templates/legal/` obliga a subir LEGAL_VERSION: al hacerlo, cada
usuario debe aceptar de nuevo en su próximo ingreso (ver `consent_gate` en auth/routes.py).
"""
from datetime import datetime

from flask import request

from app.extensions import db
from app.models import Consent
from app.services import audit

LEGAL_VERSION = '2026-10-17'


def current_consent(user):
    """Autorización vigente (no revocada) para la versión actual, o None."""
    return (Consent.query.filter_by(user_id=user.id, version=LEGAL_VERSION, revoked_at=None)
            .order_by(Consent.accepted_at.desc()).first())


def has_current_consent(user):
    return current_consent(user) is not None


def record_consent(user, source):
    """Registra la aceptación (fecha, versión, IP). Llamar antes del commit, con user.id asignado."""
    consent = Consent(user_id=user.id, version=LEGAL_VERSION, source=source,
                      ip=request.remote_addr, accepted_at=datetime.utcnow())
    db.session.add(consent)
    audit.record('consent.accept', 'user', user.id, version=LEGAL_VERSION, source=source)
    return consent


def revoke_consent(user):
    """RL-03: revocar la autorización. Queda la evidencia con su fecha de revocación."""
    now = datetime.utcnow()
    count = Consent.query.filter_by(user_id=user.id, revoked_at=None).update({'revoked_at': now})
    audit.record('consent.revoke', 'user', user.id, version=LEGAL_VERSION)
    return count


def accepted_from_form(form):
    """La casilla debe venir marcada explícitamente (no se acepta por omisión)."""
    return form.get('accept_terms') in ('on', '1', 'true', 'yes')
