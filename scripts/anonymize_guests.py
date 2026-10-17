"""RL-10: anonimiza las cuentas de invitado con más de GUEST_RETENTION_DAYS días (90 por defecto).

Se borran el nombre que escribieron al entrar; sus respuestas y notas quedan sin identidad
(igual que al eliminar una cuenta). Uso (cron diario en el host, dentro del contenedor):
    python scripts/anonymize_guests.py            # usa GUEST_RETENTION_DAYS
    python scripts/anonymize_guests.py --days 90 --dry-run
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--days', type=int, default=None)
    parser.add_argument('--dry-run', action='store_true', help='solo cuenta, no cambia nada')
    args = parser.parse_args()
    os.environ.setdefault('SEED_DEMO_DATA', '0')
    from app import create_app
    from app.extensions import db
    from app.services import personal_data
    app = create_app()
    with app.app_context():
        days = args.days or app.config['GUEST_RETENTION_DAYS']
        if args.dry_run:
            n = len(personal_data.stale_guests(days))
        else:
            n = personal_data.anonymize_stale_guests(days)
            db.session.commit()
    print(json.dumps({'dias': days, 'invitados_anonimizados': n, 'simulacion': args.dry_run}))


if __name__ == '__main__':
    main()
