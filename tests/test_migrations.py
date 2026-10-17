"""RNF-13: migraciones versionadas con Alembic."""
import sqlite3
import sys
from pathlib import Path

import pytest

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.config import Config as AlembicConfig

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import MIGRATIONS_DIR, create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402


def _head():
    cfg = AlembicConfig()
    cfg.set_main_option('script_location', MIGRATIONS_DIR)
    return ScriptDirectory.from_config(cfg).get_current_head()


@pytest.mark.sqlite_only
def test_new_database_is_created_by_migrations(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'SQLALCHEMY_DATABASE_URI', f"sqlite:///{tmp_path/'nueva.db'}")
    create_app()
    con = sqlite3.connect(tmp_path / 'nueva.db')
    assert con.execute('select version_num from alembic_version').fetchall() == [(_head(),)]


def test_models_match_migrations(tmp_path, monkeypatch):
    """Si falla: cambiaste un modelo sin migración. Corre `flask --app run db migrate -m ...`."""
    monkeypatch.setattr(Config, 'SQLALCHEMY_DATABASE_URI', f"sqlite:///{tmp_path/'check.db'}")
    app = create_app()
    with app.app_context(), db.engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={'compare_type': True, 'render_as_batch': True})
        diff = compare_metadata(ctx, db.metadata)
    assert diff == []


@pytest.mark.sqlite_only
def test_legacy_database_is_stamped_and_completed(tmp_path, monkeypatch):
    """Una base creada antes de Alembic (create_all + ensure_schema) no se recrea: se completa y se marca."""
    path = tmp_path / 'vieja.db'
    monkeypatch.setattr(Config, 'SQLALCHEMY_DATABASE_URI', f"sqlite:///{path}")
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.session.execute(db.text('DROP TABLE alembic_version'))
        db.session.commit()
        db.create_all()
        # Simula una base vieja: a users le falta una columna que ensure_schema agrega.
        db.session.execute(db.text('ALTER TABLE users DROP COLUMN institution'))
        db.session.execute(db.text("INSERT INTO users (username, email, role) VALUES ('viejo', 'viejo@example.com', 'student')"))
        db.session.commit()
    create_app()
    con = sqlite3.connect(path)
    assert con.execute('select version_num from alembic_version').fetchall() == [(_head(),)]
    assert 'institution' in [r[1] for r in con.execute('pragma table_info(users)')]
    assert con.execute("select count(*) from users where email='viejo@example.com'").fetchone() == (1,)
