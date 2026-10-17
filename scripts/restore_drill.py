"""Simulacro de restauración (RNF-15): prueba que el último respaldo sirve, sin tocar la base real.

1. Toma el respaldo más reciente de la carpeta (falla si es más viejo que --max-age-hours:
   así se detecta también que el respaldo diario dejó de correr).
2. Lo copia a una carpeta temporal y revisa integridad (integrity_check y llaves foráneas).
3. Arranca la app contra la copia (aplica migraciones pendientes, como haría una
   restauración real) y pide /healthz.
4. Cuenta filas de las tablas principales y, con --compare, las compara con la base viva:
   el respaldo no puede tener más filas que la base viva ni tablas principales vacías
   si la viva tiene datos.
Imprime un JSON con el resultado y el tiempo que tomó (RTO medido). Sale con código 1 si algo falla.

Uso (cron semanal en el host, dentro del contenedor):
    python scripts/restore_drill.py /data/backups --compare /data/mytraining.db
"""
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TABLES = ('users', 'exams', 'questions', 'exam_sessions', 'exam_attempts', 'student_answers', 'learnings')


def _counts(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        existing = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        return {t: con.execute(f'select count(*) from {t}').fetchone()[0] for t in TABLES if t in existing}
    finally:
        con.close()


def _boot_app(db_path):
    """Arranca la app contra la copia en un proceso aparte (Config lee DATABASE_URL al importarse)."""
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from app import create_app\n"
        "app = create_app()\n"
        "r = app.test_client().get('/healthz')\n"
        "print(r.status_code)\n"
    ) % str(Path(__file__).resolve().parents[1])
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{db_path}', 'SEED_DEMO_DATA': '0',
           'SUPERUSER_RESET_ON_BOOT': '0', 'LOG_LEVEL': 'warning'}
    out = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, timeout=300)
    lines = out.stdout.strip().splitlines()
    return (int(lines[-1]) if out.returncode == 0 and lines and lines[-1].isdigit() else None), out.stderr[-2000:]


def drill(backup_dir, max_age_hours=26, compare=None, backup_file=None):
    started = time.monotonic()
    result = {'ok': False, 'checks': {}}
    backups = sorted(Path(backup_dir).glob('*.db'), key=lambda p: p.stat().st_mtime)
    source = Path(backup_file) if backup_file else (backups[-1] if backups else None)
    if not source or not source.exists():
        result['error'] = f'No hay respaldos en {backup_dir}'
        return result
    result['backup'] = str(source)
    age_h = (time.time() - source.stat().st_mtime) / 3600
    result['checks']['edad_horas'] = round(age_h, 1)
    if age_h > max_age_hours:
        result['error'] = f'El respaldo más reciente tiene {age_h:.0f} h (máximo {max_age_hours} h): revisa el cron de respaldo'
        return result

    with tempfile.TemporaryDirectory(prefix='restore_drill_') as tmp:
        copy = Path(tmp) / 'restaurada.db'
        shutil.copy2(source, copy)
        try:
            con = sqlite3.connect(copy)
            integrity = con.execute('PRAGMA integrity_check').fetchone()[0]
            fk_errors = len(con.execute('PRAGMA foreign_key_check').fetchall())
            con.close()
        except sqlite3.DatabaseError as e:
            result['error'] = f'El respaldo no es una base SQLite válida: {e}'
            return result
        result['checks']['integridad'] = integrity
        result['checks']['llaves_foraneas_rotas'] = fk_errors
        if integrity != 'ok':
            result['error'] = f'integrity_check: {integrity}'
            return result

        status, stderr = _boot_app(copy)
        result['checks']['healthz'] = status
        if status != 200:
            result['error'] = 'La app no arrancó contra la copia restaurada'
            result['stderr'] = stderr
            return result

        restored = _counts(copy)
        result['checks']['filas'] = restored
        if compare:
            live = _counts(compare)
            result['checks']['filas_base_viva'] = live
            for table, n_live in live.items():
                n_backup = restored.get(table, 0)
                if n_backup > n_live:
                    result['error'] = f'{table}: el respaldo tiene más filas ({n_backup}) que la base viva ({n_live})'
                    return result
                if n_live and not n_backup:
                    result['error'] = f'{table}: vacía en el respaldo y con {n_live} filas en la base viva'
                    return result

    result['ok'] = True
    result['segundos'] = round(time.monotonic() - started, 2)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('backup_dir')
    parser.add_argument('--backup', help='respaldo específico en vez del más reciente')
    parser.add_argument('--compare', help='base viva para comparar el número de filas')
    parser.add_argument('--max-age-hours', type=float, default=26)
    args = parser.parse_args()
    res = drill(args.backup_dir, args.max_age_hours, args.compare, args.backup)
    print(json.dumps(res, ensure_ascii=False))
    sys.exit(0 if res['ok'] else 1)
