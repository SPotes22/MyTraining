"""Encuestas en vivo (RF-023) y sus permisos."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support import TEST_PASSWORD  # noqa: E402
from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Exam, ExamSession, Poll, User  # noqa: E402


@pytest.fixture()
def app_ctx(tmp_path):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'test_polls.db'}"
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        ids = {}
        for name, role in [('profe', 'instructor'), ('otro', 'instructor'), ('ana', 'student'), ('luis', 'student')]:
            u = User(username=name, email=f'{name}@example.com', role=role)
            u.set_password(TEST_PASSWORD)
            db.session.add(u)
            db.session.flush()
            ids[name] = u.id
        exam = Exam(title='E', instructor_id=ids['profe'])
        db.session.add(exam)
        db.session.flush()
        db.session.add(ExamSession(exam_id=exam.id, session_code='POL001', status='in_progress'))
        db.session.commit()
        yield app, ids


def _c(app, who):
    c = app.test_client()
    c.post('/login', data={'email': f'{who}@example.com', 'password': TEST_PASSWORD})
    return c


def _create(client, **data):
    payload = {'room_code': 'pol001', 'question_text': '¿Entendieron?', 'poll_type': 'true_false', **data}
    return client.post('/polls/create', json=payload)


def test_true_false_poll_vote_and_close(app_ctx):
    app, _ = app_ctx
    res = _create(_c(app, 'profe'))
    assert res.status_code == 201
    poll = res.get_json()['poll']
    ana = _c(app, 'ana')
    assert ana.post(f"/polls/{poll['id']}/vote", json={'answer': 'Quizás'}).status_code == 400
    assert ana.post(f"/polls/{poll['id']}/vote", json={'answer': 'Verdadero'}).get_json()['vote_count'] == 1
    assert ana.post(f"/polls/{poll['id']}/vote", json={'answer': 'Falso'}).status_code == 409   # RN-11
    assert ana.get(f"/polls/{poll['id']}/results").status_code == 200
    assert _c(app, 'otro').post(f"/polls/{poll['id']}/close").status_code == 403
    assert _c(app, 'profe').post(f"/polls/{poll['id']}/close").status_code == 200
    assert _c(app, 'luis').post(f"/polls/{poll['id']}/vote", json={'answer': 'Falso'}).status_code == 409


def test_multiple_choice_requires_options(app_ctx):
    app, _ = app_ctx
    c = _c(app, 'profe')
    assert _create(c, poll_type='multiple_choice').status_code == 400
    res = _create(c, poll_type='multiple_choice', options=['A', 'B', ' '])
    assert res.get_json()['poll']['options'] == ['A', 'B']
    assert _create(c, question_text='').status_code == 400


def test_poll_only_in_own_room(app_ctx):
    """Antes cualquier profesor podía lanzar encuestas en salas ajenas."""
    app, _ = app_ctx
    assert _create(_c(app, 'otro')).status_code == 403
    assert _create(_c(app, 'profe'), room_code='NOEXISTE').status_code == 403
    assert _create(_c(app, 'ana')).status_code == 403
    with app.app_context():
        assert Poll.query.count() == 0


def test_open_answers_visible_only_to_owner_and_voters(app_ctx):
    app, _ = app_ctx
    poll_id = _create(_c(app, 'profe'), poll_type='open_answer').get_json()['poll']['id']
    _c(app, 'ana').post(f'/polls/{poll_id}/vote', json={'answer': 'Me perdí en la parte 2'})
    assert _c(app, 'luis').get(f'/polls/{poll_id}/results').status_code == 403
    assert _c(app, 'otro').get(f'/polls/{poll_id}/results').status_code == 403
    assert 'Me perdí' in str(_c(app, 'profe').get(f'/polls/{poll_id}/results').get_json())
