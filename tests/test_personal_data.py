"""RF-029 / RL-03: consultar, corregir, exportar y suprimir los propios datos."""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support import TEST_PASSWORD, OTHER_PASSWORD  # noqa: E402
from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import AuditLog, Exam, ExamAttempt, ExamSession, LiveAnswer, StudentAnswer, User  # noqa: E402


@pytest.fixture()
def app_ctx(tmp_path):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'test_personal.db'}"
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        ids = {}
        for name, role in [('profe', 'instructor'), ('ana', 'student'), ('luis', 'student')]:
            u = User(username=name.title(), first_name=name.title(), email=f'{name}@example.com', role=role,
                     phone='3000000000', institution='Colegio')
            u.set_password(TEST_PASSWORD)
            db.session.add(u)
            db.session.flush()
            ids[name] = u.id
        exam = Exam(title='Redes', instructor_id=ids['profe'])
        db.session.add(exam)
        db.session.flush()
        session = ExamSession(exam_id=exam.id, session_code='PER001', status='in_progress')
        db.session.add(session)
        db.session.flush()
        attempt = ExamAttempt(student_id=ids['ana'], session_id=session.id, score=80)
        db.session.add(attempt)
        db.session.flush()
        db.session.add(StudentAnswer(attempt_id=attempt.id, question_id=1, question_statement='¿Qué es TCP?',
                                     answer_text='Un protocolo', is_correct=True, points_awarded=1))
        db.session.add(LiveAnswer(session_id=session.id, student_id=ids['ana'], question_id=1, answer_json={'text': 'x'}))
        guest = User(username='Invitado', role='student')
        db.session.add(guest)
        db.session.commit()
        ids['guest'] = guest.id
        ids['attempt'] = attempt.id
        yield app, ids


def _client(app, who, password=TEST_PASSWORD):
    c = app.test_client()
    c.post('/login', data={'email': f'{who}@example.com', 'password': password})
    return c


def test_profile_requires_login(app_ctx):
    app, _ = app_ctx
    assert app.test_client().get('/perfil').status_code == 302


def test_view_and_correct_own_data(app_ctx):
    app, ids = app_ctx
    c = _client(app, 'ana')
    assert 'ana@example.com' in c.get('/perfil').get_data(as_text=True)
    c.post('/perfil', data={'first_name': 'Ana María', 'last_name': 'Pérez', 'email': 'ana.maria@example.com',
                            'phone': '', 'institution': 'Universidad'})
    with app.app_context():
        u = db.session.get(User, ids['ana'])
        assert (u.first_name, u.email, u.phone, u.institution) == ('Ana María', 'ana.maria@example.com', None, 'Universidad')
        assert u.username == 'Ana María Pérez'


def test_cannot_take_another_users_email(app_ctx):
    app, ids = app_ctx
    _client(app, 'ana').post('/perfil', data={'first_name': 'Ana', 'email': 'luis@example.com'})
    with app.app_context():
        assert db.session.get(User, ids['ana']).email == 'ana@example.com'


def test_change_password_requires_current(app_ctx):
    app, _ = app_ctx
    c = _client(app, 'ana')
    c.post('/perfil/contrasena', data={'current_password': 'incorrecta', 'password': OTHER_PASSWORD,
                                       'password_confirm': OTHER_PASSWORD})
    c.post('/perfil/contrasena', data={'current_password': TEST_PASSWORD, 'password': OTHER_PASSWORD,
                                       'password_confirm': OTHER_PASSWORD})
    assert _client(app, 'ana', OTHER_PASSWORD).get('/perfil').status_code == 200


def test_export_contains_only_own_data(app_ctx):
    app, ids = app_ctx
    res = _client(app, 'ana').get('/perfil/exportar')
    assert res.headers['Content-Disposition'].startswith('attachment')
    data = json.loads(res.data)
    assert data['perfil']['correo'] == 'ana@example.com'
    assert data['intentos_de_examen'][0]['nota'] == 80
    assert data['intentos_de_examen'][0]['respuestas'][0]['respuesta'] == 'Un protocolo'
    other = json.loads(_client(app, 'luis').get('/perfil/exportar').data)
    assert other['intentos_de_examen'] == []
    with app.app_context():
        assert AuditLog.query.filter_by(action='user.export', entity_id=ids['ana']).count() == 1


def test_delete_account_anonymizes_and_keeps_attempts(app_ctx):
    app, ids = app_ctx
    c = _client(app, 'ana')
    c.post('/perfil/eliminar', data={'confirm': 'ELIMINAR', 'current_password': TEST_PASSWORD})
    with app.app_context():
        u = db.session.get(User, ids['ana'])
        assert u.email is None and u.password_hash is None and u.phone is None and u.first_name is None
        assert u.username.startswith('Usuario eliminado')
        assert db.session.get(ExamAttempt, ids['attempt']).score == 80   # el profesor conserva la estadística
        assert LiveAnswer.query.filter_by(student_id=ids['ana']).count() == 0
        assert AuditLog.query.filter_by(action='user.anonymize', entity_id=ids['ana']).count() == 1
    assert c.get('/perfil').status_code == 302                            # sesión cerrada
    assert _client(app, 'ana').get('/perfil').status_code == 302          # ya no puede entrar


def test_delete_requires_confirmation_and_password(app_ctx):
    app, ids = app_ctx
    c = _client(app, 'ana')
    c.post('/perfil/eliminar', data={'confirm': 'no', 'current_password': TEST_PASSWORD})
    c.post('/perfil/eliminar', data={'confirm': 'ELIMINAR', 'current_password': 'incorrecta'})
    with app.app_context():
        assert db.session.get(User, ids['ana']).email == 'ana@example.com'


def test_instructor_with_content_cannot_self_delete(app_ctx):
    app, ids = app_ctx
    _client(app, 'profe').post('/perfil/eliminar', data={'confirm': 'ELIMINAR', 'current_password': TEST_PASSWORD})
    with app.app_context():
        assert db.session.get(User, ids['profe']).email == 'profe@example.com'


def test_guest_without_password_can_delete(app_ctx):
    """Los invitados (ingreso por código) no tienen contraseña: basta con la confirmación."""
    app, ids = app_ctx
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(ids['guest'])
        sess['_fresh'] = True
    c.post('/perfil/eliminar', data={'confirm': 'ELIMINAR'})
    with app.app_context():
        assert db.session.get(User, ids['guest']).username.startswith('Usuario eliminado')
