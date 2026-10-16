"""Siembra una base para la prueba de carga: 1 examen de 20 preguntas, sala LOAD01 y N estudiantes.

Uso: DATABASE_URL=sqlite:////tmp/load.db python scripts/loadtest/seed_load.py 100
Imprime: <session_id> <question_id:option_id correcta> ...  (entrada para submit_burst.py)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from app import create_app
from app.extensions import db
from app.models import (User, Bank, Exam, Question, QuestionOption, ExamQuestion, ExamSession)
from app.services.exam_content import create_session_question_snapshots
N = int(sys.argv[1])
app = create_app()
with app.app_context():
    t = User(username='T', email='t@x.com', role='instructor'); t.set_password('secret123')
    db.session.add(t); db.session.commit()
    b = Bank(name='B', created_by=t.id); db.session.add(b); db.session.commit()
    e = Exam(title='Carga', instructor_id=t.id); db.session.add(e); db.session.commit()
    for i in range(20):
        q = Question(bank_id=b.id, statement=f'Q{i}', question_type='multiple_choice'); db.session.add(q); db.session.commit()
        db.session.add_all([QuestionOption(question_id=q.id, option_text='a', is_correct=True), QuestionOption(question_id=q.id, option_text='b')])
        db.session.add(ExamQuestion(exam_id=e.id, question_id=q.id, points=1, order_index=i+1))
    s = ExamSession(exam_id=e.id, session_code='LOAD01', status='in_progress'); db.session.add(s); db.session.commit()
    create_session_question_snapshots(s)
    from werkzeug.security import generate_password_hash
    h = generate_password_hash('secret123')
    for i in range(N):
        db.session.add(User(username=f's{i}', email=f's{i}@x.com', role='student', password_hash=h))
    db.session.commit()
    print(s.id, ' '.join(f'{o.question_id}:{o.id}' for o in QuestionOption.query.filter_by(is_correct=True)))
