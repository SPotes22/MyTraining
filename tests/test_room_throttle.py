"""RNF-09: la lista de estudiantes al profesor se agrupa (máx. 1 envío por sala cada 0,5 s)."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app  # noqa: E402
from app.realtime import sockets  # noqa: E402


def test_burst_sends_one_now_and_one_deferred(monkeypatch, tmp_path):
    from app.config import Config
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'t.db'}"
    app = create_app()
    sent, deferred = [], []
    monkeypatch.setattr(sockets, '_emit_students', lambda s: sent.append(s.room_code))
    monkeypatch.setattr(sockets.socketio, 'start_background_task', lambda fn: deferred.append(fn))
    monkeypatch.setattr(sockets.socketio, 'sleep', lambda _s: None)
    sockets._last_students_emit.clear()
    sockets._pending_students_emit.clear()
    room = SimpleNamespace(room_code='R1')
    with app.app_context():
        for _ in range(100):  # 100 respuestas casi simultáneas
            sockets._emit_students_throttled(room)
        assert sent == ['R1'] and len(deferred) == 1
        sockets._emit_students_throttled(SimpleNamespace(room_code='R2'))  # otra sala no espera
        assert sent == ['R1', 'R2']
    deferred[0]()  # el envío diferido lleva el estado final
    assert sent == ['R1', 'R2', 'R1'] and not sockets._pending_students_emit


def test_gunicorn_threads_cover_a_full_room(monkeypatch):
    import runpy
    monkeypatch.delenv('GUNICORN_THREADS', raising=False)
    conf = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'gunicorn.conf.py'))
    assert conf['workers'] == 1 and conf['threads'] >= 200
