"""Logs estructurados (RNF-17): JSON por línea, nivel configurable y sin datos personales."""
import io
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.logging_setup import JsonFormatter, configure_logging, redact  # noqa: E402


def _emit(logger_name, level, msg, *args, **extra):
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger(logger_name)
    logger.addHandler(handler)
    try:
        logger.log(level, msg, *args, extra=extra)
    finally:
        logger.removeHandler(handler)
    return buf.getvalue()


def test_json_line_with_extra_fields():
    line = _emit('t.json', logging.WARNING, 'Alerta antitrampa', event='room.anti_cheat', room='ABC123', user_id=7)
    data = json.loads(line)
    assert data['level'] == 'WARNING' and data['logger'] == 't.json' and data['msg'] == 'Alerta antitrampa'
    assert data['event'] == 'room.anti_cheat' and data['room'] == 'ABC123' and data['user_id'] == 7
    assert data['ts'].endswith('+00:00')


def test_emails_and_reset_tokens_are_redacted():
    line = _emit('t.redact', logging.ERROR, 'fallo para %s en /reset-password/abc.def-123?x=1',
                 'ana@example.com', reason='escribe a ana@example.com')
    assert 'ana@example.com' not in line and 'abc.def-123' not in line
    assert '<correo>' in line and '/reset-password/<token>' in line
    assert redact('/reset-password/') == '/reset-password/'


def test_exception_is_serialized():
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger('t.exc')
    logger.addHandler(handler)
    try:
        raise ValueError('roto')
    except ValueError:
        logger.exception('Error', extra={'event': 'x'})
    finally:
        logger.removeHandler(handler)
    data = json.loads(buf.getvalue())
    assert 'ValueError: roto' in data['exc']


def test_configure_logging_level_and_single_handler():
    root = logging.getLogger()
    before = len(root.handlers)
    configure_logging('warning', 'json')
    configure_logging('debug', 'text')
    ours = [h for h in root.handlers if getattr(h, '_mytraining', False)]
    assert len(ours) == 1 and len(root.handlers) <= before + 1
    assert root.level == logging.DEBUG
    configure_logging('nivel-raro', 'json')
    assert root.level == logging.INFO
    assert logging.getLogger('engineio').level == logging.WARNING


def test_app_code_has_no_print_except_console_secrets():
    """Los print() solo quedan para secretos de desarrollo que no deben ir al log."""
    root = Path(__file__).resolve().parents[1] / 'app'
    offenders = []
    for path in root.rglob('*.py'):
        for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if line.strip().startswith('print('):
                offenders.append(f'{path.relative_to(root).as_posix()}:{n}')
    assert len(offenders) == 3 and {o.split(':')[0] for o in offenders} == {'__init__.py', 'services/mailer.py'}, offenders
