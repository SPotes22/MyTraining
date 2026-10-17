"""Con TEST_DATABASE_URL (p. ej. postgresql+psycopg://...) toda la suite corre contra ese motor (RNF-13).

Cada fixture fija una base SQLite temporal antes de llamar a create_app(); aquí se
envuelve create_app para usar la base indicada y dejarla vacía antes de cada test. Los
tests marcados `sqlite_only` (leen el archivo .db directamente) se omiten en ese modo.
"""
import os

import pytest

TEST_DATABASE_URL = os.environ.get('TEST_DATABASE_URL')


def pytest_configure(config):
    config.addinivalue_line('markers', 'sqlite_only: el test usa el archivo SQLite directamente')
    config.addinivalue_line('markers', 'consent_gate: el test ejercita la exigencia de autorización (RL-01)')


@pytest.fixture(autouse=True)
def _consent_given(request, monkeypatch):
    """Los fixtures crean usuarios directamente en la base, sin pasar por la casilla de
    autorización. Salvo en los tests marcados `consent_gate`, se dan por autorizados."""
    if 'consent_gate' in request.keywords:
        return
    from app.services import legal
    monkeypatch.setattr(legal, 'has_current_consent', lambda user: True)


def pytest_collection_modifyitems(config, items):
    if not TEST_DATABASE_URL:
        return
    skip = pytest.mark.skip(reason='solo aplica a SQLite')
    for item in items:
        if 'sqlite_only' in item.keywords:
            item.add_marker(skip)


if TEST_DATABASE_URL:
    from sqlalchemy import create_engine, text

    import app as app_pkg
    from app.config import Config
    from app.extensions import db

    _original_create_app = app_pkg.create_app
    _apps = []

    def _reset_database():
        # Cerrar las conexiones de apps anteriores: si no, DROP SCHEMA espera sus bloqueos.
        for old in _apps:
            with old.app_context():
                db.session.remove()
                db.engine.dispose()
        _apps.clear()
        engine = create_engine(TEST_DATABASE_URL)
        with engine.begin() as conn:
            conn.execute(text('DROP SCHEMA public CASCADE'))
            conn.execute(text('CREATE SCHEMA public'))
        engine.dispose()

    def _create_app_on_test_database():
        Config.SQLALCHEMY_DATABASE_URI = TEST_DATABASE_URL
        Config.SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
        _reset_database()
        created = _original_create_app()
        _apps.append(created)
        return created

    app_pkg.create_app = _create_app_on_test_database
