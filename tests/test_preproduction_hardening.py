import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support import OTHER_PASSWORD, TEST_PASSWORD  # noqa: E402
from app.config import Config, validate_config
from app import create_app
from app.extensions import db, socketio
from app.models import (Bank, Question, QuestionOption, Exam, ExamQuestion, ExamSession,
                        ExamAttempt, StudentAnswer, User)
from app.blueprints.auth import routes as auth_routes


@pytest.fixture()
def app_ctx(tmp_path):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'test_hardening.db'}"
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    auth_routes._failed_logins.clear()
    with app.app_context():
        db.drop_all()
        db.create_all()
        teacher = User(username='Profe', email='profe@example.com', role='instructor')
        other = User(username='Otro', email='otro@example.com', role='instructor')
        alumno = User(username='Alumno', email='alumno@example.com', role='student')
        intruso = User(username='Intruso', email='intruso@example.com', role='student')
        for u in (teacher, other, alumno, intruso):
            u.set_password(TEST_PASSWORD)
        db.session.add_all([teacher, other, alumno, intruso])
        db.session.commit()

        bank = Bank(name='Banco', created_by=teacher.id)
        db.session.add(bank)
        db.session.commit()
        q = Question(bank_id=bank.id, statement='¿2+2?', question_type='multiple_choice')
        db.session.add(q)
        db.session.commit()
        db.session.add(QuestionOption(question_id=q.id, option_text='4', is_correct=True))
        exam = Exam(title='Examen', instructor_id=teacher.id)
        db.session.add(exam)
        db.session.commit()
        db.session.add(ExamQuestion(exam_id=exam.id, question_id=q.id, points=1.0))
        session = ExamSession(exam_id=exam.id, session_code='ABC123', status='in_progress')
        db.session.add(session)
        db.session.commit()
        attempt = ExamAttempt(student_id=alumno.id, session_id=session.id, score=100)
        db.session.add(attempt)
        db.session.commit()
        db.session.add(StudentAnswer(attempt_id=attempt.id, question_id=q.id, is_correct=True))
        db.session.commit()
        ids = dict(teacher=teacher.id, alumno=alumno.id, intruso=intruso.id, question=q.id,
                   exam=exam.id, session=session.id, attempt=attempt.id)
    yield app, ids
    auth_routes._failed_logins.clear()


def login(client, email, password=TEST_PASSWORD):
    return client.post('/login', data={'email': email, 'password': password})


def test_results_only_visible_to_owner_and_exam_instructor(app_ctx):
    app, ids = app_ctx
    url = f"/resultados/{ids['attempt']}"
    for email, expected in [('alumno@example.com', 200), ('profe@example.com', 200),
                            ('intruso@example.com', 403), ('otro@example.com', 403)]:
        c = app.test_client()
        login(c, email)
        assert c.get(url).status_code == expected, email


def test_lobby_and_close_require_session_owner(app_ctx):
    app, ids = app_ctx
    c = app.test_client()
    login(c, 'otro@example.com')
    assert c.get(f"/instructor/lobby/{ids['session']}").status_code == 403
    assert c.post(f"/exam/close/{ids['session']}").status_code == 403
    with app.app_context():
        assert db.session.get(ExamSession, ids['session']).status == 'in_progress'


def test_question_with_history_cannot_be_deleted(app_ctx):
    """RN-13 (RN-04 del SRS V2)"""
    app, ids = app_ctx
    c = app.test_client()
    login(c, 'profe@example.com')
    c.post(f"/instructor/question/delete/{ids['question']}")
    c.post('/instructor/questions/bulk-delete', data={'question_ids[]': [str(ids['question'])]})
    with app.app_context():
        bank_id = db.session.get(Question, ids['question']).bank_id
    c.post(f'/instructor/bank/delete/{bank_id}')
    with app.app_context():
        assert db.session.get(Question, ids['question']) is not None


def test_login_lockout_after_repeated_failures(app_ctx):
    app, _ = app_ctx
    c = app.test_client()
    for _ in range(app.config['LOGIN_MAX_ATTEMPTS']):
        assert login(c, 'profe@example.com', 'mala').status_code == 200
    # Incluso con la contraseña correcta, queda bloqueado durante la ventana.
    assert login(c, 'profe@example.com').status_code == 429


def test_short_password_rejected_on_register(app_ctx):
    app, _ = app_ctx
    c = app.test_client()
    c.post('/register', data={'first_name': 'A', 'last_name': 'B', 'email': 'corta@example.com',
                              'password': '1234', 'password_confirm': '1234', 'role': 'student'})
    with app.app_context():
        assert User.query.filter_by(email='corta@example.com').first() is None


def test_healthz_and_security_headers(app_ctx):
    app, _ = app_ctx
    res = app.test_client().get('/healthz')
    assert res.status_code == 200
    assert res.get_json()['status'] == 'ok'
    assert res.headers['X-Content-Type-Options'] == 'nosniff'


def test_students_cannot_upload_media(app_ctx):
    app, _ = app_ctx
    c = app.test_client()
    login(c, 'alumno@example.com')
    assert c.post('/learning/api/upload').status_code == 403


def test_validate_config_requires_own_secrets(monkeypatch):
    import hashlib
    from app import config as config_module
    good = {'APP_ENV': 'preproduction', 'SECRET_KEY_FROM_ENV': True, 'SECRET_KEY': 'x' * 40,
            'SUPERUSER_PASSWORD': TEST_PASSWORD, 'MIN_PASSWORD_LENGTH': 8,
            'LEGAL_ENTITY_NAME': 'R', 'LEGAL_ENTITY_ID': '1', 'LEGAL_CONTACT_EMAIL': 'datos@example.com',
            'LEGAL_ADDRESS': 'Calle 1'}
    validate_config(good)

    # Secretos ausentes, generados al vuelo o demasiado cortos: no arranca.
    for bad in ({'SECRET_KEY_FROM_ENV': False}, {'SECRET_KEY': 'corta'},
                {'SUPERUSER_PASSWORD': None}, {'SUPERUSER_PASSWORD': '1234'}):
        with pytest.raises(RuntimeError):
            validate_config({**good, **bad})

    # Un valor que ya se publicó (su hash está en la lista) tampoco se acepta.
    leaked = OTHER_PASSWORD
    monkeypatch.setattr(config_module, 'LEAKED_SECRET_SHA256',
                        frozenset({hashlib.sha256(leaked.encode()).hexdigest()}))
    with pytest.raises(RuntimeError):
        validate_config({**good, 'SUPERUSER_PASSWORD': leaked})

    # En desarrollo no se exige nada.
    validate_config({'APP_ENV': 'development'})


def test_dev_superuser_gets_random_password_when_none_configured(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Config, 'SQLALCHEMY_DATABASE_URI', f"sqlite:///{tmp_path/'dev.db'}")
    monkeypatch.setattr(Config, 'SUPERUSER_PASSWORD', None)
    app = create_app()
    printed = capsys.readouterr().out
    assert 'Contraseña temporal generada' in printed
    temp = printed.split('(no se volverá a mostrar): ')[1].split()[0]
    with app.app_context():
        su = User.query.filter_by(role='superuser').first()
        assert su.check_password(temp)
        assert len(temp) >= 12


def test_socket_student_cannot_impersonate_or_control_room(app_ctx):
    app, ids = app_ctx
    c = app.test_client()
    assert login(c, 'intruso@example.com').status_code == 302
    sio = socketio.test_client(app, flask_test_client=c)
    assert sio.is_connected()

    # Intentar unirse como el alumno legítimo: el servidor ignora student_id del payload.
    sio.emit('student_join', {'room_code': 'ABC123', 'student_id': ids['alumno'], 'username': 'Alumno'})
    from app.realtime.manager import session_manager
    room = session_manager.sessions['ABC123']
    assert ids['alumno'] not in room.students
    assert ids['intruso'] in room.students

    # Un estudiante no puede pausar ni unirse como profesor.
    sio.get_received()
    sio.emit('pause_exam', {'room_code': 'ABC123'})
    sio.emit('teacher_join', {'room_code': 'ABC123'})
    errors = [m for m in sio.get_received() if m['name'] == 'exam_error']
    assert len(errors) == 2
    with app.app_context():
        assert db.session.get(ExamSession, ids['session']).status == 'in_progress'
    sio.disconnect()
    session_manager.sessions.pop('ABC123', None)


def test_csrf_blocks_post_without_token(app_ctx):
    """RNF-03: con CSRF activo un POST sin token no surte efecto; con el token de la página sí."""
    import re
    app, ids = app_ctx
    app.config['WTF_CSRF_ENABLED'] = True
    c = app.test_client()
    page = c.get('/login').get_data(as_text=True)
    token = re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)

    c.post('/login', data={'email': 'profe@example.com', 'password': TEST_PASSWORD})
    assert c.get('/instructor/exams').status_code == 302  # sin token: sigue sin sesión

    res = c.post('/login', data={'email': 'profe@example.com', 'password': TEST_PASSWORD, 'csrf_token': token})
    assert res.status_code == 302
    assert c.get('/instructor/exams').status_code == 200
    # Con sesión iniciada, un POST sin token sigue rechazado; con cabecera X-CSRFToken (fetch) pasa.
    assert c.post('/instructor/exam/new', data={'title': 'Sin token'}).status_code == 302
    with app.app_context():
        assert Exam.query.filter_by(title='Sin token').count() == 0
    c.post('/instructor/exam/new', data={'title': 'Con token'}, headers={'X-CSRFToken': token})
    with app.app_context():
        assert Exam.query.filter_by(title='Con token').count() == 1


def test_instructor_self_signup_disabled_outside_development(app_ctx):
    """RN-09"""
    app, _ = app_ctx
    app.config['ALLOW_INSTRUCTOR_SIGNUP'] = False
    c = app.test_client()
    assert b'value="instructor"' not in c.get('/register').data
    c.post('/register', data={'first_name': 'P', 'last_name': 'Q', 'email': 'nuevo@example.com',
                              'password': TEST_PASSWORD, 'password_confirm': TEST_PASSWORD, 'role': 'instructor',
                              'accept_terms': 'on'})
    with app.app_context():
        assert User.query.filter_by(email='nuevo@example.com').first().role == 'student'


def test_finished_session_rejects_submissions(app_ctx):
    """RN-12"""
    app, ids = app_ctx
    with app.app_context():
        db.session.get(ExamSession, ids['session']).status = 'FINISHED'
        db.session.commit()
    c = app.test_client()
    login(c, 'intruso@example.com')
    c.post(f"/exam/submit/{ids['session']}", data={})
    with app.app_context():
        assert ExamAttempt.query.filter_by(student_id=ids['intruso']).count() == 0


def test_exam_with_attempts_cannot_be_permanently_deleted(app_ctx):
    """RN-10"""
    app, ids = app_ctx
    c = app.test_client()
    login(c, 'profe@example.com')
    c.post(f"/instructor/exam/{ids['exam']}/permanent-delete")
    with app.app_context():
        assert db.session.get(Exam, ids['exam']) is not None


def test_session_status_hides_student_names_from_non_owners(app_ctx):
    app, ids = app_ctx
    c = app.test_client()
    login(c, 'intruso@example.com')
    assert c.get(f"/session/status/{ids['session']}").get_json()['students'] == []
    c = app.test_client()
    login(c, 'profe@example.com')
    assert c.get(f"/session/status/{ids['session']}").get_json()['students'] == ['Alumno']


def test_instructor_with_content_cannot_be_deleted(app_ctx):
    """Evita que un profesor nuevo herede el id (y los exámenes) de uno borrado."""
    app, ids = app_ctx
    with app.app_context():
        admin = User(username='Admin', email='root@example.com', role='superuser')
        admin.set_password(TEST_PASSWORD)
        db.session.add(admin)
        db.session.commit()
    c = app.test_client()
    login(c, 'root@example.com')
    c.post(f"/admin/instructor/delete/{ids['teacher']}")
    with app.app_context():
        assert db.session.get(User, ids['teacher']) is not None
        empty = User(username='Sin contenido', email='vacio@example.com', role='instructor')
        db.session.add(empty)
        db.session.commit()
        empty_id = empty.id
    c.post(f'/admin/instructor/delete/{empty_id}')
    with app.app_context():
        assert db.session.get(User, empty_id) is None
