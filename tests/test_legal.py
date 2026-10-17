"""Requisitos legales: RL-01 (autorización con registro), RL-02/RL-11 (textos publicados),
RL-03 (revocar), RL-10 (anonimizar invitados) y RL-12 (aceptación con versión y fecha)."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support import TEST_PASSWORD  # noqa: E402
from app import create_app  # noqa: E402
from app.config import Config, validate_config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import AuditLog, Bank, Consent, Exam, ExamAttempt, ExamSession, User  # noqa: E402
from app.services import legal, personal_data  # noqa: E402

pytestmark = pytest.mark.consent_gate


@pytest.fixture()
def app_ctx(tmp_path):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'test_legal.db'}"
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                      LEGAL_ENTITY_NAME='Responsable de Prueba', LEGAL_CONTACT_EMAIL='datos@example.com')
    with app.app_context():
        db.drop_all()
        db.create_all()
        ids = {}
        for name, role in (('ana', 'student'), ('profe', 'instructor')):
            u = User(username=name.title(), email=f'{name}@example.com', role=role)
            u.set_password(TEST_PASSWORD)
            db.session.add(u)
            db.session.flush()
            ids[name] = u.id
        exam = Exam(title='Redes', instructor_id=ids['profe'])
        db.session.add(exam)
        db.session.flush()
        room = ExamSession(exam_id=exam.id, session_code='LEG001', status='in_progress')
        db.session.add(room)
        db.session.commit()
        ids['room'] = room.id
    yield app, ids


def _login(app, who):
    c = app.test_client()
    c.post('/login', data={'email': f'{who}@example.com', 'password': TEST_PASSWORD})
    return c


def test_legal_pages_are_public_and_show_the_responsible(app_ctx):
    app, _ = app_ctx
    c = app.test_client()
    for url, title in (('/terminos', 'Términos y condiciones'), ('/politica-de-datos', 'Política de tratamiento')):
        page = c.get(url).get_data(as_text=True)
        assert title in page and legal.LEGAL_VERSION in page
        assert 'Responsable de Prueba' in page and 'datos@example.com' in page
    # Enlazadas desde los formularios y el pie de página.
    for url in ('/register', '/student/join', '/'):
        html = c.get(url).get_data(as_text=True)
        assert '/terminos' in html and '/politica-de-datos' in html


def test_register_requires_explicit_consent_and_records_it(app_ctx):
    app, _ = app_ctx
    c = app.test_client()
    form = {'first_name': 'Luis', 'last_name': 'P', 'email': 'luis@example.com',
            'password': TEST_PASSWORD, 'password_confirm': TEST_PASSWORD}
    page = c.post('/register', data=form).get_data(as_text=True)
    assert 'Debes aceptar' in page
    assert 'name="accept_terms"' in page and 'checked' not in page.split('name="accept_terms"')[1].split('>')[0]
    with app.app_context():
        assert User.query.filter_by(email='luis@example.com').first() is None

    c.post('/register', data={**form, 'accept_terms': 'on'})
    with app.app_context():
        user = User.query.filter_by(email='luis@example.com').one()
        consent = Consent.query.filter_by(user_id=user.id).one()
        assert consent.version == legal.LEGAL_VERSION and consent.source == 'registro'
        assert consent.ip and consent.accepted_at and consent.revoked_at is None
        assert AuditLog.query.filter_by(action='consent.accept', entity_id=user.id).count() == 1
        assert user.created_at is not None


def test_guest_join_requires_consent(app_ctx):
    app, ids = app_ctx
    c = app.test_client()
    c.post('/student/join', data={'student_name': 'Invitado', 'session_code': 'LEG001'})
    with app.app_context():
        assert User.query.filter_by(username='Invitado').first() is None
    resp = c.post('/student/join', data={'student_name': 'Invitado', 'session_code': 'LEG001', 'accept_terms': 'on'})
    assert f"/exam/presentar/{ids['room']}" in resp.headers['Location']
    with app.app_context():
        guest = User.query.filter_by(username='Invitado').one()
        assert Consent.query.filter_by(user_id=guest.id, source='invitado').count() == 1


def test_existing_user_must_accept_before_using_the_platform(app_ctx):
    app, _ = app_ctx
    c = _login(app, 'ana')
    resp = c.get('/learning/student/catalog')
    assert resp.status_code == 302 and '/aceptar-terminos' in resp.headers['Location']
    # Las APIs responden 403 en JSON, no una redirección.
    api = c.post('/learning/api/progress/update', json={'learning_id': 1})
    assert api.status_code == 403 and 'aceptar' in api.get_json()['error']
    # Sin autorización sí puede ver los textos, su perfil, exportar y eliminar sus datos.
    for url in ('/terminos', '/politica-de-datos', '/perfil', '/perfil/exportar'):
        assert c.get(url).status_code == 200, url

    page = c.get('/aceptar-terminos?next=/learning/student/catalog').get_data(as_text=True)
    assert 'Eliminar mi cuenta' in page
    c.post('/aceptar-terminos', data={'next': '/learning/student/catalog'})       # sin marcar
    assert c.get('/learning/student/catalog').status_code == 302
    resp = c.post('/aceptar-terminos', data={'accept_terms': 'on', 'next': '/learning/student/catalog'})
    assert resp.headers['Location'].endswith('/learning/student/catalog')
    assert c.get('/learning/student/catalog').status_code == 200


def test_accept_next_parameter_is_not_an_open_redirect(app_ctx):
    app, _ = app_ctx
    c = _login(app, 'ana')
    for evil in ('https://malo.example', '//malo.example', '/\\malo.example'):
        resp = c.post('/aceptar-terminos', data={'accept_terms': 'on', 'next': evil})
        assert 'malo.example' not in resp.headers['Location']


def test_new_version_requires_accepting_again(app_ctx, monkeypatch):
    app, ids = app_ctx
    c = _login(app, 'ana')
    c.post('/aceptar-terminos', data={'accept_terms': 'on'})
    assert c.get('/learning/student/catalog').status_code == 200
    monkeypatch.setattr(legal, 'LEGAL_VERSION', '2099-01-01')
    assert c.get('/learning/student/catalog').status_code == 302
    c.post('/aceptar-terminos', data={'accept_terms': 'on'})
    with app.app_context():
        versions = sorted(x.version for x in Consent.query.filter_by(user_id=ids['ana']))
        assert len(versions) == 2 and versions[-1] == '2099-01-01'


def test_revoke_consent_blocks_use_keeps_evidence_and_exports_it(app_ctx):
    app, ids = app_ctx
    c = _login(app, 'ana')
    c.post('/aceptar-terminos', data={'accept_terms': 'on'})
    assert 'Revocar mi autorización' in c.get('/perfil').get_data(as_text=True)
    c.post('/perfil/revocar-autorizacion', data={'confirm': 'no'})
    assert c.get('/learning/student/catalog').status_code == 200          # sin confirmar, no revoca
    resp = c.post('/perfil/revocar-autorizacion', data={'confirm': 'REVOCAR'})
    assert '/aceptar-terminos' in resp.headers['Location']
    assert c.get('/learning/student/catalog').status_code == 302
    data = json.loads(c.get('/perfil/exportar').data)
    assert data['autorizaciones'][0]['revocada'] is not None
    with app.app_context():
        assert Consent.query.filter_by(user_id=ids['ana']).one().revoked_at is not None
        assert AuditLog.query.filter_by(action='consent.revoke').count() == 1
    # Tras revocar puede eliminar su cuenta desde la misma pantalla.
    c.post('/perfil/eliminar', data={'confirm': 'ELIMINAR', 'current_password': TEST_PASSWORD})
    with app.app_context():
        assert db.session.get(User, ids['ana']).email is None


def test_stale_guests_are_anonymized(app_ctx):
    app, ids = app_ctx
    with app.app_context():
        old = User(username='Viejo', role='student', created_at=datetime.utcnow() - timedelta(days=120))
        new = User(username='Nuevo', role='student')
        legacy_active = User(username='Legado activo', role='student')
        legacy_idle = User(username='Legado inactivo', role='student')
        db.session.add_all([old, new, legacy_active, legacy_idle])
        db.session.flush()
        db.session.add(ExamAttempt(student_id=legacy_active.id, session_id=ids['room'], completed_at=datetime.utcnow()))
        # Cuentas anteriores a la columna: created_at nulo (el ORM pondría la fecha actual).
        User.query.filter(User.id.in_([legacy_active.id, legacy_idle.id])).update({'created_at': None})
        db.session.commit()
        assert {u.username for u in personal_data.stale_guests(90)} == {'Viejo', 'Legado inactivo'}
        assert personal_data.anonymize_stale_guests(90) == 2
        db.session.commit()
        names = {u.username for u in User.query.filter_by(role='student')}
        assert {'Nuevo', 'Legado activo', 'Ana'} <= names
        assert 'Viejo' not in names and 'Legado inactivo' not in names
        # Cuentas con correo nunca se tocan, y una segunda pasada no repite.
        assert personal_data.anonymize_stale_guests(90) == 0


def test_production_requires_responsible_party_data():
    from support import TEST_PASSWORD as pw
    good = {'APP_ENV': 'preproduction', 'SECRET_KEY_FROM_ENV': True, 'SECRET_KEY': 'x' * 40,
            'SUPERUSER_PASSWORD': pw, 'MIN_PASSWORD_LENGTH': 8, 'LEGAL_ENTITY_NAME': 'R',
            'LEGAL_ENTITY_ID': '900000000-0', 'LEGAL_CONTACT_EMAIL': 'datos@example.com', 'LEGAL_ADDRESS': 'Calle 1'}
    validate_config(good)
    for key in ('LEGAL_ENTITY_NAME', 'LEGAL_ENTITY_ID', 'LEGAL_CONTACT_EMAIL', 'LEGAL_ADDRESS'):
        with pytest.raises(RuntimeError, match=key):
            validate_config({**good, key: ''})
