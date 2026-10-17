"""RF-027 / RN-08: calificación manual de respuestas abiertas.

Una respuesta abierta sin calificar no cuenta en la nota: ni sus puntos obtenidos ni
sus puntos posibles. Al calificarla, la nota del intento se recalcula con todas las
respuestas que ya tienen calificación.
"""
from datetime import datetime

from app.models import ExamQuestion


def answer_max_points(answer):
    """Puntos que vale la pregunta en ESTE intento (instantánea de la sala si existe)."""
    if answer.snapshot and answer.snapshot.points is not None:
        return float(answer.snapshot.points)
    attempt = answer.attempt
    eq = ExamQuestion.query.get((attempt.session.exam_id, answer.question_id)) if attempt and attempt.session else None
    return float(eq.points) if eq and eq.points is not None else 1.0


def recalculate_attempt(attempt):
    earned = possible = 0.0
    for answer in attempt.answers:
        if answer.is_pending_review:
            continue
        possible += answer_max_points(answer)
        earned += float(answer.points_awarded or 0.0)
    attempt.earned_points = round(earned, 2)
    attempt.max_points = round(possible, 2)
    attempt.score = round(earned / possible * 100.0, 2) if possible > 0 else 0.0
    return attempt


def grade_open_answer(answer, points, grader_id):
    """Asigna `points` (0 .. valor de la pregunta) y recalcula el intento."""
    max_points = answer_max_points(answer)
    try:
        points = float(points)
    except (TypeError, ValueError):
        raise ValueError('El puntaje debe ser un número.')
    if points < 0 or points > max_points:
        raise ValueError(f'El puntaje debe estar entre 0 y {max_points:g}.')
    answer.points_awarded = round(points, 2)
    answer.is_correct = points >= max_points
    answer.graded_at = datetime.utcnow()
    answer.graded_by = grader_id
    return recalculate_attempt(answer.attempt)
