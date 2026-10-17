"""Respaldo en caliente de la base SQLite (RNF-15) con retención por días.

Usa la API de backup de sqlite3, segura con la app corriendo en modo WAL.
Uso (cron diario en el host, p. ej. 03:10):
    python scripts/backup_sqlite.py /data/mytraining.db /backups --keep-days 30
Restaurar: detener la app, copiar el .db respaldado sobre el original y arrancar.
Probar que el respaldo sirve sin tocar la base real: scripts/restore_drill.py (semanal).
"""
import argparse
import sqlite3
import time
from datetime import datetime
from pathlib import Path


def backup(db_path, dest_dir, keep_days):
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / f"{Path(db_path).stem}_{datetime.now():%Y%m%d_%H%M%S}.db"
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    out = sqlite3.connect(target)
    with out:
        src.backup(out)
    ok = out.execute("PRAGMA integrity_check").fetchone()[0]
    src.close()
    out.close()
    if ok != 'ok':
        target.unlink(missing_ok=True)
        raise SystemExit(f"Respaldo corrupto ({ok}); no se conservó.")

    cutoff = time.time() - keep_days * 86400
    removed = 0
    for old in dest.glob(f"{Path(db_path).stem}_*.db"):
        if old.stat().st_mtime < cutoff:
            old.unlink()
            removed += 1
    print(f"Respaldo: {target} ({target.stat().st_size // 1024} KB). Eliminados por retención: {removed}.")
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('db_path')
    parser.add_argument('dest_dir')
    parser.add_argument('--keep-days', type=int, default=30)
    args = parser.parse_args()
    backup(args.db_path, args.dest_dir, args.keep_days)
