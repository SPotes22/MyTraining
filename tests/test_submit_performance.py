"""RNF-08: el envío del examen hace un número fijo de consultas, no 2 por pregunta."""
import sys
from pathlib import Path
import pytest
from sqlalchemy import event

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support import TEST_PASSWORD  # noqa: E402
from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (Bank, Exam, ExamAttempt, ExamQuestion, ExamSession, Question,  # noqa: E402
                        QuestionOption, StudentAnswer, User)
from app.services.exam_content import create_session_question_snapshots  # noqa: E402


@pytest.fixture()
def setup(tmp_path):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'test_perf.db'}"
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        t = User(username='t', email='t@example.com', role='instructor')
        s = User(username='s', email='s@example.com', role='student')
        for u in (t, s):
            u.set_password(TEST_PASSWORD)
        db.session.add_all([t, s])
        db.session.flush()
        bank = Bank(name='B', created_by=t.id)
        exam = Exam(title='E', instructor_id=t.id)
        db.session.add_all([bank, exam])
        db.session.flush()
        form = {}
        for i in range(20):
            q = Question(bank_id=bank.id, statement=f'Q{i}', question_type='multiple_choice')
            db.session.add(q)
            db.session.flush()
            ok = QuestionOption(question_id=q.id, option_text='a', is_correct=True)
            bad = QuestionOption(question_id=q.id, option_text='b', is_correct=False)
            db.session.add_all([ok, bad])
            db.session.flush()
            db.session.add(ExamQuestion(exam_id=exam.id, question_id=q.id, points=1, order_index=i + 1))
            form[f'question_{q.id}'] = ok.id
        session = ExamSession(exam_id=exam.id, session_code='PERF01', status='in_progress')
        db.session.add(session)
        db.session.commit()
        create_session_question_snapshots(session)
        sid = session.id
    c = app.test_client()
    c.post('/login', data={'email': 's@example.com', 'password': TEST_PASSWORD})
    return app, c, sid, form


def test_submit_query_count_is_constant(setup):
    app, c, sid, form = setup
    count = [0]
    with app.app_context():
        engine = db.engine
    listener = lambda *a: count.__setitem__(0, count[0] + 1)  # noqa: E731
    event.listen(engine, 'before_cursor_execute', listener)
    try:
        resp = c.post(f'/exam/submit/{sid}', data=form)
    finally:
        event.remove(engine, 'before_cursor_execute', listener)
    assert resp.status_code == 302 and '/resultados/' in resp.headers['Location']
    assert count[0] <= 25, f'{count[0]} consultas para 20 preguntas (antes eran 72)'
    with app.app_context():
        attempt = ExamAttempt.query.one()
        assert attempt.score == 100 and StudentAnswer.query.filter_by(attempt_id=attempt.id).count() == 20


def test_option_from_another_question_does_not_count(setup):
    app, c, sid, form = setup
    qids = list(form)
    # La opción correcta de la pregunta 0 enviada como respuesta de la pregunta 1.
    form = {**form, qids[1]: form[qids[0]]}
    c.post(f'/exam/submit/{sid}', data=form)
    with app.app_context():
        attempt = ExamAttempt.query.one()
        assert attempt.earned_points == 19
        qid1 = int(qids[1].split('_')[1])
        ans = StudentAnswer.query.filter_by(attempt_id=attempt.id, question_id=qid1).one()
        assert ans.is_correct is False and ans.selected_option_text is None


def test_second_submit_does_not_create_another_attempt(setup):
    app, c, sid, form = setup
    c.post(f'/exam/submit/{sid}', data=form)
    c.post(f'/exam/submit/{sid}', data=form)
    with app.app_context():
        assert ExamAttempt.query.count() == 1
