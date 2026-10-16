from flask import request
from flask_login import current_user
from flask_socketio import emit, join_room
from app.extensions import db, socketio
from app.models import ExamSession as DbExamSession, LiveAnswer
from app.modes import registry
from app.realtime import events
from app.realtime.manager import session_manager
from app.services.exam_content import normalize_room_code, socket_room


def _owns_db_session(db_session):
    """True si el usuario del socket es el profesor dueño del examen (o admin)."""
    if not db_session or not current_user.is_authenticated:
        return False
    if current_user.role in ['superuser', 'admin']:
        return True
    return current_user.role == 'instructor' and db_session.exam.instructor_id == current_user.id


def _owns_room(room_code):
    return _owns_db_session(DbExamSession.query.filter_by(session_code=room_code).first())


def _mode(session):
    return registry.get(session.mode, socketio, session_manager)


def _emit_students(session):
    payload = {
        'students': session_manager.students_payload(session),
        'room_code': session.room_code,
    }
    socketio.emit(events.STUDENTS_UPDATED, payload,
                  to=session.teacher_sid or socket_room(session.room_code))
    _emit_teacher_stats_update(session)


def _emit_teacher_stats_update(session=None, instructor_id=None):
    try:
        if not instructor_id and session:
            db_session = DbExamSession.query.filter_by(
                session_code=session.room_code).first()
            if db_session and db_session.exam:
                instructor_id = db_session.exam.instructor_id
        if instructor_id:
            from app.blueprints.exams.routes import get_instructor_active_sessions_summary
            summary = get_instructor_active_sessions_summary(instructor_id)
            socketio.emit('teacher_live_stats_updated', summary,
                          to=f"teacher_{instructor_id}")
    except Exception as e:
        print(f"[ERROR] stats del profesor: {e}")


# ── Instructor: suscribirse a stats ─────────────────────────────────────────
@socketio.on('subscribe_teacher_stats')
def handle_subscribe_teacher_stats(data=None):
    # Antes se aceptaba data['instructor_id'] sin sesión: cualquiera podía espiar
    # las salas de otro profesor. Ahora solo el profesor autenticado.
    if not current_user.is_authenticated or current_user.role not in ['instructor', 'superuser', 'admin']:
        emit(events.ERROR, {'message': 'No autorizado'})
        return
    instructor_id = current_user.id
    if instructor_id:
        join_room(f"teacher_{instructor_id}")
        from app.blueprints.exams.routes import get_instructor_active_sessions_summary
        summary = get_instructor_active_sessions_summary(instructor_id)
        emit('teacher_live_stats_updated', summary)


# ── Teacher join ─────────────────────────────────────────────────────────────
@socketio.on(events.TEACHER_JOIN)
def handle_teacher_join(data):
    room_code = normalize_room_code(data.get('room_code'))
    if not _owns_room(room_code):
        emit(events.ERROR, {'message': 'Profesor no autorizado'})
        return
    session = session_manager.set_teacher(room_code, request.sid)
    if not session:
        emit(events.ERROR, {'message': 'Sesión no encontrada'})
        return
    join_room(socket_room(room_code))
    if current_user.is_authenticated and current_user.role in ['instructor', 'superuser', 'admin']:
        join_room(f"teacher_{current_user.id}")
    print(f"[JOIN] Profesor -> {room_code}")
    _emit_students(session)


# ── Student join ─────────────────────────────────────────────────────────────
@socketio.on(events.STUDENT_JOIN)
@socketio.on(events.JOIN_SESSION_ROOM)
def handle_student_join(data):
    room_code  = normalize_room_code(data.get('room_code') or data.get('session_code'))
    # La identidad sale de la cookie de sesión, nunca del payload del cliente
    # (antes un estudiante podía enviar el student_id de otro y suplantarlo).
    if not current_user.is_authenticated:
        emit(events.ERROR, {'message': 'Estudiante no autenticado'})
        return
    student_id = current_user.id
    username   = current_user.username or 'Estudiante'
    if not student_id:
        emit(events.ERROR, {'message': 'Estudiante no autenticado'})
        return
    result = session_manager.add_student(room_code, student_id, username, request.sid)
    if not result:
        emit(events.ERROR, {'message': 'Sesión no encontrada'})
        return
    session, student = result
    join_room(socket_room(room_code))
    print(f"[JOIN] Alumno {student.id} -> {room_code}")
    _emit_students(session)

    # Restaurar respuestas guardadas (LiveAnswer) para que la UI las precargue
    db_session = DbExamSession.query.filter_by(session_code=room_code).first()
    saved = {}
    if db_session:
        rows = LiveAnswer.query.filter_by(
            session_id=db_session.id, student_id=int(student_id)).all()
        saved = {str(r.question_id): r.answer_json for r in rows}

    _mode(session).on_join(session, student)

    # Emitir progreso guardado al estudiante (puede estar vacío)
    if saved:
        emit('saved_progress', {'answers': saved})


# ── Start exam ───────────────────────────────────────────────────────────────
@socketio.on(events.START_EXAM_SESSION)
def handle_start_exam_session(data):
    session_id = data.get('session_id')
    db_session = DbExamSession.query.get(session_id)
    if not db_session:
        emit(events.ERROR, {'message': 'Sesión no encontrada'})
        return
    if not _owns_db_session(db_session):
        emit(events.ERROR, {'message': 'Profesor no autorizado'})
        return
    db_session.status = 'in_progress'
    db.session.commit()
    session = session_manager.get_or_create_by_db_session(db_session)
    session.status = 'in_progress'
    print(f"[START] Profesor inició {session.room_code}")
    _mode(session).on_start(session)
    _emit_teacher_stats_update(session)


# ── Pause / Resume (nuevo: socket directo, no requiere recarga) ──────────────
@socketio.on('pause_exam')
def handle_pause_exam(data):
    """Instructor pausa el examen. Estudiantes reciben 'exam_paused' y bloquean UI."""
    room_code = normalize_room_code(data.get('room_code'))
    if not _owns_room(room_code):
        emit(events.ERROR, {'message': 'Profesor no autorizado'})
        return
    session   = session_manager.get_or_create_by_code(room_code)
    if not session:
        emit(events.ERROR, {'message': 'Sesión no encontrada'})
        return
    session.status = 'PAUSED'
    db_session = DbExamSession.query.filter_by(session_code=room_code).first()
    if db_session:
        db_session.status = 'PAUSED'
        db.session.commit()
    socketio.emit('exam_paused', {'room_code': room_code}, to=socket_room(room_code))
    print(f"[PAUSE] {room_code}")


@socketio.on('resume_exam')
def handle_resume_exam(data):
    """Instructor reanuda. Estudiantes reciben 'exam_resumed' y desbloquean UI."""
    room_code = normalize_room_code(data.get('room_code'))
    if not _owns_room(room_code):
        emit(events.ERROR, {'message': 'Profesor no autorizado'})
        return
    session   = session_manager.get_or_create_by_code(room_code)
    if not session:
        emit(events.ERROR, {'message': 'Sesión no encontrada'})
        return
    session.status = 'in_progress'
    db_session = DbExamSession.query.filter_by(session_code=room_code).first()
    if db_session:
        db_session.status = 'in_progress'
        db.session.commit()
    socketio.emit('exam_resumed', {'room_code': room_code}, to=socket_room(room_code))
    print(f"[RESUME] {room_code}")


# ── Answer submitted ─────────────────────────────────────────────────────────
@socketio.on(events.ANSWER_SUBMITTED)
def handle_answer_submitted(data):
    room_code  = normalize_room_code(data.get('room_code'))
    session    = session_manager.get_or_create_by_code(room_code)
    student_id = current_user.id if current_user.is_authenticated else None
    try:
        question_id = int(data.get('question_id') or 0)
    except (TypeError, ValueError):
        emit(events.ERROR, {'message': 'Pregunta no reconocida'})
        return

    if not session or session.status not in ['in_progress', 'RUNNING']:
        emit(events.ERROR, {'message': 'Examen no disponible o pausado'})
        return
    student = session.students.get(int(student_id)) if student_id else None
    if not student or student.sid != request.sid:
        emit(events.ERROR, {'message': 'Respuesta rechazada'})
        return
    if question_id not in [q['id'] for q in session.questions]:
        emit(events.ERROR, {'message': 'Pregunta no reconocida'})
        return

    answer = data.get('answer') or {}

    # ── Persistir LiveAnswer (upsert) ────────────────────────────────────────
    try:
        db_session = DbExamSession.query.filter_by(session_code=room_code).first()
        if db_session:
            existing = LiveAnswer.query.filter_by(
                session_id=db_session.id,
                student_id=int(student_id),
                question_id=question_id,
            ).first()
            if existing:
                existing.answer_json = answer
                existing.answered_at = db.func.now()
            else:
                db.session.add(LiveAnswer(
                    session_id=db_session.id,
                    student_id=int(student_id),
                    question_id=question_id,
                    answer_json=answer,
                ))
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[WARN] LiveAnswer upsert: {e}")

    # ── Notificar al instructor que este alumno respondió esta pregunta ───────
    _mode(session).on_answer(session, student, question_id, answer)
    
    try:
        db_session = db_session or DbExamSession.query.filter_by(session_code=room_code).first()
        if db_session and db_session.exam:
            socketio.emit('student_answered', {
                'student_id': int(student_id),
                'username': student.username,
                'question_id': question_id,
                'room_code': room_code,
                'answered_count': len(student.answered_questions),
            }, to=f"teacher_{db_session.exam.instructor_id}")
    except Exception as e:
        print(f"[WARN] student_answered emit: {e}")
    
    _emit_students(session)
    


# ── Next question (teacher_paced) ────────────────────────────────────────────
@socketio.on(events.NEXT_QUESTION)
def handle_next_question(data):
    room_code = normalize_room_code(data.get('room_code'))
    session   = session_manager.get_or_create_by_code(room_code)
    if not session or session.teacher_sid != request.sid:
        emit(events.ERROR, {'message': 'Profesor no autorizado'})
        return
    _mode(session).on_next_question(session)


# ── Anti-cheat ───────────────────────────────────────────────────────────────
@socketio.on(events.ANTI_CHEAT_ALERT)
def handle_anti_cheat_alert(data):
    room_code = normalize_room_code(data.get('room_code') or data.get('session_code'))
    if not current_user.is_authenticated:
        return
    session = session_manager.get_or_create_by_code(room_code)
    if not session:
        return
    username = current_user.username
    reason = str(data.get('reason') or '')[:200]
    print(f"[ALERT] {username} -> {room_code}: {reason}")
    # Solo al profesor: antes se difundía a toda la sala (los compañeros veían la alerta).
    db_session = DbExamSession.query.filter_by(session_code=room_code).first()
    target = session.teacher_sid or (f"teacher_{db_session.exam.instructor_id}" if db_session else None)
    if target:
        socketio.emit(events.CHEAT_WARNING, {'username': username, 'reason': reason}, to=target)


# ── Disconnect ───────────────────────────────────────────────────────────────
@socketio.on('disconnect')
def handle_disconnect():
    info = session_manager.disconnect_sid(request.sid)
    if not info:
        return
    session, role, student_id = info
    if role == 'student':
        print(f"[LEAVE] Alumno {student_id} <- {session.room_code}")
        _emit_students(session)
    else:
        print(f"[LEAVE] Profesor <- {session.room_code}")
