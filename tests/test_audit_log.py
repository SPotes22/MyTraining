"""RF-030: registro de auditoría."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support import TEST_PASSWORD  # noqa: E402
from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import AuditLog, Exam, ExamSession, User  # noqa: E402


@pytest.fixture()
def app_ctx(tmp_path):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'test_audit.db'}"
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        users = {}
        for name, role in [('profe', 'instructor'), ('admin', 'superuser'), ('ana', 'student')]:
            u = User(username=name, email=f'{name}@example.com', role=role)
            u.set_password(TEST_PASSWORD)
            db.session.add(u)
            users[name] = u
        db.session.commit()
        exam = Exam(title='Redes', instructor_id=users['profe'].id)
        db.session.add(exam)
        db.session.commit()
        session = ExamSession(exam_id=exam.id, session_code='AUD001', status='in_progress')
        db.session.add(session)
        db.session.commit()
        yield app, {k: v.id for k, v in users.items()}, exam.id, session.id


def _client(app, who):
    c = app.test_client()
    c.post('/login', data={'email': f'{who}@example.com', 'password': TEST_PASSWORD})
    return c


def _logs(app, action):
    with app.app_context():
        return [(l.user_id, l.entity, l.entity_id, l.details) for l in AuditLog.query.filter_by(action=action)]


def test_exam_lifecycle_is_audited(app_ctx):
    app, ids, exam_id, _ = app_ctx
    c = _client(app, 'profe')
    c.post('/instructor/exam/new', data={'title': 'Nuevo'})
    c.post(f'/instructor/exam/{exam_id}/delete')
    c.post(f'/instructor/exam/{exam_id}/restore')
    assert _logs(app, 'exam.create')[0][0] == ids['profe']
    assert _logs(app, 'exam.archive') == [(ids['profe'], 'exam', exam_id, {'title': 'Redes'})]
    assert len(_logs(app, 'exam.restore')) == 1


def test_results_export_and_session_finish_are_audited(app_ctx):
    app, ids, exam_id, session_id = app_ctx
    c = _client(app, 'profe')
    c.get(f'/instructor/session/{session_id}/results.xlsx')
    c.post(f'/instructor/session/{session_id}/finish')
    assert _logs(app, 'results.export')[0][:3] == (ids['profe'], 'session', session_id)
    assert _logs(app, 'session.finish')[0][2] == session_id


def test_user_management_is_audited(app_ctx):
    app, ids, *_ = app_ctx
    c = _client(app, 'admin')
    c.post('/admin/instructor/create', data={'username': 'Nuevo', 'email': 'nuevo@example.com',
                                             'password': TEST_PASSWORD})
    created = _logs(app, 'user.create')
    assert created and created[0][0] == ids['admin'] and created[0][2] is not None
    c.post(f'/admin/instructor/delete/{created[0][2]}')
    assert _logs(app, 'user.delete')[0][2] == created[0][2]


def test_audit_view_is_admin_only(app_ctx):
    app, *_ = app_ctx
    _client(app, 'profe').post('/instructor/exam/new', data={'title': 'Visible'})
    assert _client(app, 'ana').get('/admin/audit').status_code == 302
    assert _client(app, 'profe').get('/admin/audit').status_code == 302
    page = _client(app, 'admin').get('/admin/audit?action=exam.')
    assert page.status_code == 200 and b'exam.create' in page.data


def test_audit_log_stores_no_email(app_ctx):
    """Minimización: el registro guarda el id, no el correo ni el nombre."""
    app, *_ = app_ctx
    _client(app, 'profe').post('/instructor/exam/new', data={'title': 'X'})
    with app.app_context():
        row = AuditLog.query.first()
        assert 'profe@example.com' not in str(row.details) and not hasattr(row, 'user_email')
