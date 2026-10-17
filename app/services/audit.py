"""RF-030: registro de auditoría.

Uso: `audit.record('exam.archive', 'exam', exam.id, title=exam.title)` ANTES del
`db.session.commit()` de la operación, para que el evento y el cambio se guarden juntos.
Si la operación no hace commit (p. ej. una descarga), usa `commit=True`.
"""
from flask import has_request_context, request
from flask_login import current_user

from app.extensions import db


def record(action, entity=None, entity_id=None, commit=False, **details):
    from app.models import AuditLog
    user_id = user_role = ip = None
    if has_request_context():
        ip = request.remote_addr
        if current_user.is_authenticated:
            user_id, user_role = current_user.id, current_user.role
    db.session.add(AuditLog(user_id=user_id, user_role=user_role, action=action, entity=entity,
                            entity_id=entity_id, details=details or None, ip=ip))
    if commit:
        db.session.commit()
