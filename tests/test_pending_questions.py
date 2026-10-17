"""El examen no se envía con preguntas sin responder (incluidas las de video que no
aparecieron), salvo en el modo "Guiado por profesor"."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support import TEST_PASSWORD  # noqa: E402
from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (Bank, Exam, ExamAttempt, ExamQuestion, ExamSession, LiveAnswer,  # noqa: E402
                        Question, QuestionOption, User)


@pytest.fixture()
def app_ctx(tmp_path):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'test_pending.db'}"
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        teacher = User(username='Profe', email='profe@example.com', role='instructor')
        student = User(username='Ana', email='ana@example.com', role='student')
        for u in (teacher, student):
            u.set_password(TEST_PASSWORD)
        db.session.add_all([teacher, student])
        db.session.commit()
        bank = Bank(name='Banco', created_by=teacher.id)
        db.session.add(bank)
        db.session.commit()
        yield app, teacher, student, bank


def _exam(teacher, bank, mode='open_navigation', video_cue_on_second=False):
    questions = []
    for i in range(3):
        q = Question(bank_id=bank.id, statement=f'P{i}', question_type='multiple_choice')
        if video_cue_on_second and i == 1:
            q.video_url = 'https://youtu.be/dQw4w9WgXcQ'
            q.video_metadata = {'version': 1, 'provider': 'youtube', 'video_id': 'dQw4w9WgXcQ',
                                'embed_url': 'https://www.youtube.com/embed/dQw4w9WgXcQ',
                                'source_url': 'https://youtu.be/dQw4w9WgXcQ', 'start': 0,
                                'question_at': 600, 'pause_on_question': True}
        db.session.add(q)
        db.session.flush()
        ok = QuestionOption(question_id=q.id, option_text='bien', is_correct=True)
        db.session.add_all([ok, QuestionOption(question_id=q.id, option_text='mal')])
        db.session.flush()
        questions.append((q.id, ok.id))
    exam = Exam(title='Examen', instructor_id=teacher.id, exam_mode=mode)
    db.session.add(exam)
    db.session.flush()
    for order, (qid, _) in enumerate(questions, 1):
        db.session.add(ExamQuestion(exam_id=exam.id, question_id=qid, points=1, order_index=order))
    session = ExamSession(exam_id=exam.id, session_code='PEND01', status='in_progress')
    db.session.add(session)
    db.session.commit()
    return session.id, questions


def _client(app):
    c = app.test_client()
    c.post('/login', data={'email': 'ana@example.com', 'password': TEST_PASSWORD})
    return c


def _attempts(app):
    with app.app_context():
        return ExamAttempt.query.count()


def test_submit_with_missing_answer_is_rejected_and_points_to_it(app_ctx):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        session_id, qs = _exam(teacher, bank)
    form = {f'question_{qs[0][0]}': qs[0][1], f'question_{qs[2][0]}': qs[2][1]}  # falta la 2.ª
    res = _client(app).post(f'/exam/submit/{session_id}', data=form)
    assert res.status_code == 302
    assert f'pendiente={qs[1][0]}' in res.headers['Location']
    assert _attempts(app) == 0


def test_submit_with_all_answers_is_graded(app_ctx):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        session_id, qs = _exam(teacher, bank)
    form = {f'question_{qid}': opt for qid, opt in qs}
    res = _client(app).post(f'/exam/submit/{session_id}', data=form)
    assert '/resultados/' in res.headers['Location']
    assert _attempts(app) == 1


def test_answer_saved_live_counts_as_answered(app_ctx):
    """Una respuesta guardada por socket (LiveAnswer) también cuenta."""
    app, teacher, student, bank = app_ctx
    with app.app_context():
        session_id, qs = _exam(teacher, bank)
        db.session.add(LiveAnswer(session_id=session_id, student_id=student.id, question_id=qs[1][0],
                                  answer_json={'selected_option_id': qs[1][1]}))
        db.session.commit()
    form = {f'question_{qs[0][0]}': qs[0][1], f'question_{qs[2][0]}': qs[2][1]}
    _client(app).post(f'/exam/submit/{session_id}', data=form)
    assert _attempts(app) == 1


def test_unseen_video_question_blocks_submit(app_ctx):
    """La pregunta de video que no apareció no tiene campos en el formulario: queda pendiente."""
    app, teacher, student, bank = app_ctx
    with app.app_context():
        session_id, qs = _exam(teacher, bank, video_cue_on_second=True)
    form = {f'question_{qs[0][0]}': qs[0][1], f'question_{qs[2][0]}': qs[2][1]}
    res = _client(app).post(f'/exam/submit/{session_id}', data=form)
    assert f'pendiente={qs[1][0]}' in res.headers['Location']
    assert _attempts(app) == 0


def test_teacher_paced_mode_allows_partial_submit(app_ctx):
    """En "Guiado por profesor" el profesor puede saltarse preguntas: no se bloquea el envío."""
    app, teacher, student, bank = app_ctx
    with app.app_context():
        session_id, qs = _exam(teacher, bank, mode='teacher_paced')
    _client(app).post(f'/exam/submit/{session_id}', data={f'question_{qs[0][0]}': qs[0][1]})
    assert _attempts(app) == 1


def test_exam_page_opens_pending_question_from_redirect(app_ctx):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        session_id, qs = _exam(teacher, bank)
    html = _client(app).get(f'/exam/presentar/{session_id}?pendiente={qs[1][0]}').get_data(as_text=True)
    assert f'const PENDING_QID = {qs[1][0]};' in html
