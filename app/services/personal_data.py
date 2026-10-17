"""RF-029 / RL-03: derechos del titular (consultar, exportar y suprimir sus datos)."""
from datetime import datetime

from app.extensions import db
from app.models import (Bank, BlockAnswer, Consent, Exam, ExamAttempt, ExamClass, ExamGroup, Learning,
                        LearningProgress, LiveAnswer, PollVote)


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def export_user_data(user):
    """Todo lo que la plataforma guarda asociado a la persona, en un dict serializable a JSON."""
    attempts = ExamAttempt.query.filter_by(student_id=user.id).order_by(ExamAttempt.completed_at).all()
    return {
        'generado_el': datetime.utcnow().isoformat() + 'Z',
        'perfil': {
            'id': user.id, 'nombre': user.first_name, 'apellido': user.last_name,
            'nombre_visible': user.username, 'correo': user.email, 'telefono': user.phone,
            'institucion': user.institution, 'rol': user.role,
        },
        'intentos_de_examen': [{
            'examen': a.session.exam.title if a.session and a.session.exam else None,
            'sala': a.session.session_code if a.session else None,
            'fecha': _iso(a.completed_at), 'intento': a.attempt_number,
            'nota': a.score, 'puntos': a.earned_points, 'puntos_posibles': a.max_points,
            'respuestas': [{
                'pregunta': ans.display_statement, 'respuesta': ans.display_student_answer,
                'correcta': ans.is_correct, 'puntos': ans.points_awarded,
            } for ans in a.answers],
        } for a in attempts],
        'progreso_en_capacitaciones': [{
            'capacitacion': p.learning.nombre if p.learning else None, 'avance_pct': p.progress_percent,
            'completada': p.completed, 'ultima_actividad': _iso(p.last_activity),
        } for p in LearningProgress.query.filter_by(user_id=user.id)],
        'respuestas_en_capacitaciones': [{
            'bloque': b.block_id, 'respuesta': b.answer_data, 'correcta': b.is_correct, 'fecha': _iso(b.submitted_at),
        } for b in BlockAnswer.query.filter_by(user_id=user.id)],
        'votos_en_encuestas': [{
            'encuesta': v.poll.question_text if v.poll else None, 'respuesta': v.answer_text, 'fecha': _iso(v.voted_at),
        } for v in PollVote.query.filter_by(student_id=user.id)],
        'autorizaciones': [{
            'version': c.version, 'origen': c.source, 'aceptada': _iso(c.accepted_at),
            'ip': c.ip, 'revocada': _iso(c.revoked_at),
        } for c in Consent.query.filter_by(user_id=user.id).order_by(Consent.accepted_at)],
    }


def owns_content(user):
    """Profesores con exámenes, bancos, clases o capacitaciones: su supresión la gestiona un administrador."""
    return any(model.query.filter_by(**{field: user.id}).first() for model, field in [
        (Exam, 'instructor_id'), (Bank, 'created_by'), (ExamClass, 'instructor_id'),
        (ExamGroup, 'instructor_id'), (Learning, 'autor_id'),
    ])


def anonymize_user(user):
    """Suprime los datos personales y deja la cuenta inutilizable.

    Los intentos y respuestas se conservan sin identidad (la cuenta ya no tiene nombre,
    correo ni contraseña) para que el profesor no pierda las estadísticas de la sala; el
    progreso guardado a medio examen (LiveAnswer) se borra. No se borra la fila del usuario:
    SQLite reutilizaría su id (ver Auditoría S-16).
    """
    user.username = f'Usuario eliminado #{user.id}'
    user.first_name = user.last_name = user.phone = user.institution = None
    user.email = None
    user.password_hash = None
    LiveAnswer.query.filter_by(student_id=user.id).delete()
    db.session.add(user)


def stale_guests(days):
    """Invitados (sin correo ni contraseña, no anonimizados) creados hace más de `days` días.

    Las cuentas anteriores al 17 oct 2026 no tienen `created_at`: se usa su último envío de
    examen y, si no tienen ninguno, se consideran vencidas.
    """
    from datetime import timedelta
    from app.models import User
    cutoff = datetime.utcnow() - timedelta(days=days)
    guests = User.query.filter(User.role == 'student', User.email.is_(None), User.password_hash.is_(None),
                               ~User.username.like('Usuario eliminado #%')).all()
    stale = []
    for g in guests:
        reference = g.created_at
        if reference is None:
            last = (ExamAttempt.query.filter_by(student_id=g.id)
                    .order_by(ExamAttempt.completed_at.desc()).first())
            reference = last.completed_at if last else None
        if reference is None or reference < cutoff:
            stale.append(g)
    return stale


def anonymize_stale_guests(days):
    """RL-10: anonimiza los invitados vencidos. Devuelve cuántos. El llamador hace commit."""
    from app.services import audit
    guests = stale_guests(days)
    for g in guests:
        anonymize_user(g)
    if guests:
        audit.record('user.anonymize_guests', 'user', None, count=len(guests), days=days)
    return len(guests)
