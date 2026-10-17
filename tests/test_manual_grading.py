"""RF-027 / RN-08: calificación manual de respuestas abiertas."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support import TEST_PASSWORD  # noqa: E402
from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (AuditLog, Bank, Exam, ExamAttempt, ExamQuestion, ExamSession, Question,  # noqa: E402
                        QuestionOption, StudentAnswer, User)


@pytest.fixture()
def app_ctx(tmp_path):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'test_grading.db'}"
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        users = {}
        for name, role in [('profe', 'instructor'), ('otro', 'instructor'), ('ana', 'student')]:
            u = User(username=name, email=f'{name}@example.com', role=role)
            u.set_password(TEST_PASSWORD)
            db.session.add(u)
            users[name] = u
        db.session.commit()
        bank = Bank(name='B', created_by=users['profe'].id)
        db.session.add(bank)
        db.session.commit()
        mc = Question(bank_id=bank.id, statement='¿2+2?', question_type='multiple_choice')
        op = Question(bank_id=bank.id, statement='Explica TCP', question_type='open_answer')
        db.session.add_all([mc, op])
        db.session.commit()
        ok = QuestionOption(question_id=mc.id, option_text='4', is_correct=True)
        db.session.add(ok)
        exam = Exam(title='Mixto', instructor_id=users['profe'].id, exam_mode='open_navigation')
        db.session.add(exam)
        db.session.commit()
        db.session.add_all([ExamQuestion(exam_id=exam.id, question_id=mc.id, points=2, order_index=1),
                            ExamQuestion(exam_id=exam.id, question_id=op.id, points=8, order_index=2)])
        session = ExamSession(exam_id=exam.id, session_code='GRA001', status='in_progress')
        db.session.add(session)
        db.session.commit()
        yield app, session.id, mc.id, ok.id, op.id


def _client(app, who):
    c = app.test_client()
    c.post('/login', data={'email': f'{who}@example.com', 'password': TEST_PASSWORD})
    return c


def _submit(app, session_id, mc_id, ok_id, op_id):
    _client(app, 'ana').post(f'/exam/submit/{session_id}', data={
        f'question_{mc_id}': ok_id, f'question_{op_id}': 'Protocolo orientado a conexión'})
    with app.app_context():
        attempt = ExamAttempt.query.one()
        answer = StudentAnswer.query.filter_by(question_id=op_id).one()
        return attempt.id, answer.id


def test_ungraded_open_answer_does_not_count(app_ctx):
    """RN-08: con la abierta sin calificar, la nota sale solo de lo calificado (2/2 = 100 %)."""
    app, session_id, mc_id, ok_id, op_id = app_ctx
    attempt_id, answer_id = _submit(app, session_id, mc_id, ok_id, op_id)
    with app.app_context():
        attempt = db.session.get(ExamAttempt, attempt_id)
        assert (attempt.earned_points, attempt.max_points, attempt.score) == (2, 2, 100)
        assert db.session.get(StudentAnswer, answer_id).is_pending_review


def test_grading_recalculates_score_and_is_audited(app_ctx):
    app, session_id, mc_id, ok_id, op_id = app_ctx
    attempt_id, answer_id = _submit(app, session_id, mc_id, ok_id, op_id)
    res = _client(app, 'profe').post(f'/instructor/answer/{answer_id}/grade', data={'points': '4'})
    assert res.status_code == 302
    with app.app_context():
        attempt = db.session.get(ExamAttempt, attempt_id)
        assert (attempt.earned_points, attempt.max_points, attempt.score) == (6, 10, 60)
        answer = db.session.get(StudentAnswer, answer_id)
        assert not answer.is_pending_review and answer.points_awarded == 4 and answer.is_correct is False
        assert AuditLog.query.filter_by(action='answer.grade', entity_id=answer_id).count() == 1
    # Re-calificar con el total la marca como correcta.
    _client(app, 'profe').post(f'/instructor/answer/{answer_id}/grade', data={'points': '8'})
    with app.app_context():
        assert db.session.get(ExamAttempt, attempt_id).score == 100
        assert db.session.get(StudentAnswer, answer_id).is_correct is True


@pytest.mark.parametrize('points', ['-1', '9', 'abc'])
def test_invalid_points_are_rejected(app_ctx, points):
    app, session_id, mc_id, ok_id, op_id = app_ctx
    attempt_id, answer_id = _submit(app, session_id, mc_id, ok_id, op_id)
    _client(app, 'profe').post(f'/instructor/answer/{answer_id}/grade', data={'points': points})
    with app.app_context():
        assert db.session.get(StudentAnswer, answer_id).is_pending_review


def test_only_exam_owner_can_grade(app_ctx):
    app, session_id, mc_id, ok_id, op_id = app_ctx
    attempt_id, answer_id = _submit(app, session_id, mc_id, ok_id, op_id)
    for who in ('otro', 'ana'):
        assert _client(app, who).post(f'/instructor/answer/{answer_id}/grade', data={'points': '8'}).status_code == 403
    with app.app_context():
        assert db.session.get(StudentAnswer, answer_id).is_pending_review


def test_report_and_results_show_review_state(app_ctx):
    app, session_id, mc_id, ok_id, op_id = app_ctx
    attempt_id, answer_id = _submit(app, session_id, mc_id, ok_id, op_id)
    report = _client(app, 'profe').get(f'/instructor/session/{session_id}/report').get_data(as_text=True)
    assert 'Protocolo orientado a conexión' in report and '1 por calificar' in report
    result = _client(app, 'ana').get(f'/resultados/{attempt_id}').get_data(as_text=True)
    assert 'pendiente(s) de revisión' in result
    _client(app, 'profe').post(f'/instructor/answer/{answer_id}/grade', data={'points': '8'})
    result = _client(app, 'ana').get(f'/resultados/{attempt_id}').get_data(as_text=True)
    assert 'Calificada por el profesor' in result and 'pendiente(s) de revisión' not in result
