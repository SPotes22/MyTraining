"""RF-029 / RL-03: derechos del titular (consultar, exportar y suprimir sus datos)."""
from datetime import datetime

from app.extensions import db
from app.models import (Bank, BlockAnswer, Exam, ExamAttempt, ExamClass, ExamGroup, Learning,
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
