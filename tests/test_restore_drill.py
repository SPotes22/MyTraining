"""RNF-15: respaldo + simulacro de restauración automatizado."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from support import TEST_PASSWORD  # noqa: E402
from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User  # noqa: E402
import backup_sqlite  # noqa: E402

pytestmark = pytest.mark.sqlite_only


def _drill(*args):
    env = {**os.environ, 'APP_ENV': 'development'}
    out = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'restore_drill.py'), *map(str, args)],
                         capture_output=True, text=True, env=env, timeout=300)
    return out.returncode, json.loads(out.stdout.strip().splitlines()[-1])


@pytest.fixture()
def live_db(tmp_path, monkeypatch):
    path = tmp_path / 'viva.db'
    monkeypatch.setattr(Config, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{path}')
    app = create_app()
    with app.app_context():
        for i in range(3):
            u = User(username=f'u{i}', email=f'u{i}@example.com', role='student')
            u.set_password(TEST_PASSWORD)
            db.session.add(u)
        db.session.commit()
        db.engine.dispose()
    return path


def test_backup_and_restore_drill_ok(live_db, tmp_path):
    backups = tmp_path / 'respaldos'
    backup_sqlite.backup(live_db, backups, keep_days=30)
    code, res = _drill(backups, '--compare', live_db)
    assert code == 0, res
    assert res['ok'] and res['checks']['integridad'] == 'ok' and res['checks']['healthz'] == 200
    assert res['checks']['filas']['users'] == res['checks']['filas_base_viva']['users'] >= 3
    # El simulacro trabaja sobre una copia: el respaldo no cambia.
    assert len(list(backups.glob('*.db'))) == 1


def test_drill_fails_on_stale_corrupt_or_missing_backup(live_db, tmp_path):
    backups = tmp_path / 'respaldos'
    target = backup_sqlite.backup(live_db, backups, keep_days=30)
    old = time.time() - 3 * 86400
    os.utime(target, (old, old))
    code, res = _drill(backups)
    assert code == 1 and 'cron' in res['error']

    corrupt = backups / 'viva_corrupto.db'
    corrupt.write_bytes(b'esto no es sqlite' * 100)
    code, res = _drill(backups, '--backup', corrupt)
    assert code == 1 and res['ok'] is False

    code, res = _drill(tmp_path / 'vacia')
    assert code == 1 and 'No hay respaldos' in res['error']


def test_drill_detects_backup_with_more_rows_than_live(live_db, tmp_path):
    backups = tmp_path / 'respaldos'
    backup_sqlite.backup(live_db, backups, keep_days=30)
    import sqlite3
    con = sqlite3.connect(live_db)
    con.execute('delete from users')
    con.commit()
    con.close()
    code, res = _drill(backups, '--compare', live_db)
    assert code == 1 and 'users' in res['error']
