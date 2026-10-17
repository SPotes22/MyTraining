"""RF-028: recuperar contraseña con enlace de un solo uso, válido 30 minutos."""
import re
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support import TEST_PASSWORD, OTHER_PASSWORD  # noqa: E402
from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import AuditLog, User  # noqa: E402
from app.blueprints.auth import routes as auth_routes  # noqa: E402


@pytest.fixture()
def app_ctx(tmp_path, monkeypatch):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'test_reset.db'}"
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    sent = []
    monkeypatch.setattr(auth_routes, 'send_mail', lambda to, subject, body: sent.append((to, body)) or True)
    auth_routes._reset_requests.clear()
    auth_routes._failed_logins.clear()
    with app.app_context():
        db.drop_all()
        db.create_all()
        u = User(username='Ana', email='ana@example.com', role='student')
        u.set_password(TEST_PASSWORD)
        db.session.add(u)
        db.session.commit()
    yield app, sent
    auth_routes._reset_requests.clear()


def _link(sent):
    return re.search(r'http://localhost(/reset-password/\S+)', sent[-1][1]).group(1)


def _can_login(app, password):
    c = app.test_client()
    return c.post('/login', data={'email': 'ana@example.com', 'password': password}).status_code == 302


def test_full_reset_flow_and_single_use(app_ctx):
    app, sent = app_ctx
    c = app.test_client()
    c.post('/forgot-password', data={'email': 'ana@example.com'})
    assert sent and sent[0][0] == 'ana@example.com'
    link = _link(sent)
    assert c.get(link).status_code == 200
    res = c.post(link, data={'password': OTHER_PASSWORD, 'password_confirm': OTHER_PASSWORD})
    assert res.status_code == 302 and '/login' in res.headers['Location']
    assert _can_login(app, OTHER_PASSWORD) and not _can_login(app, TEST_PASSWORD)
    # Un solo uso: tras cambiar la contraseña el mismo enlace ya no sirve.
    again = c.post(link, data={'password': TEST_PASSWORD, 'password_confirm': TEST_PASSWORD})
    assert '/olvide-contrasena' in again.headers['Location']
    assert _can_login(app, OTHER_PASSWORD)
    with app.app_context():
        assert AuditLog.query.filter_by(action='auth.password_reset').count() == 1


def test_unknown_email_gets_same_answer_and_no_mail(app_ctx):
    app, sent = app_ctx
    res = app.test_client().post('/forgot-password', data={'email': 'nadie@example.com'}, follow_redirects=True)
    assert 'Si el correo está registrado' in res.get_data(as_text=True)
    assert sent == []


def test_expired_link_is_rejected(app_ctx):
    app, sent = app_ctx
    app.test_client().post('/forgot-password', data={'email': 'ana@example.com'})
    link = _link(sent)
    app.config['PASSWORD_RESET_MAX_AGE'] = -1
    res = app.test_client().get(link)
    assert '/olvide-contrasena' in res.headers['Location']


def test_tampered_link_is_rejected(app_ctx):
    app, sent = app_ctx
    app.test_client().post('/forgot-password', data={'email': 'ana@example.com'})
    res = app.test_client().get(_link(sent)[:-3] + 'abc')
    assert '/olvide-contrasena' in res.headers['Location']


def test_short_or_mismatched_password_is_rejected(app_ctx):
    app, sent = app_ctx
    c = app.test_client()
    c.post('/forgot-password', data={'email': 'ana@example.com'})
    link = _link(sent)
    c.post(link, data={'password': '1234', 'password_confirm': '1234'})
    c.post(link, data={'password': OTHER_PASSWORD, 'password_confirm': TEST_PASSWORD})
    assert _can_login(app, TEST_PASSWORD)


def test_reset_requests_are_rate_limited(app_ctx):
    app, sent = app_ctx
    c = app.test_client()
    for _ in range(5):
        c.post('/forgot-password', data={'email': 'ana@example.com'})
    assert len(sent) == app.config['PASSWORD_RESET_MAX_REQUESTS']


def test_login_page_links_to_recovery(app_ctx):
    app, _ = app_ctx
    assert b'/olvide-contrasena' in app.test_client().get('/login').data
