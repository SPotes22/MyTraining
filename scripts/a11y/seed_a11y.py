"""Base para la auditoría de accesibilidad (RNF-11): profesor, estudiante y admin, examen con
todos los tipos de pregunta, sala abierta, intento calificado y una capacitación publicada.

Uso: DATABASE_URL=sqlite:////tmp/a11y.db APP_ENV=development SEED_DEMO_DATA=0 \
     A11Y_PASSWORD=<clave generada> python scripts/a11y/seed_a11y.py
Imprime: <sala> <intento> <sala_finalizada> <examen> <capacitación> (argumentos de axe_audit.js).
La base se BORRA y se vuelve a crear: nunca la apuntes a datos reales.
"""
import os, sys
sys.path.insert(0, os.getcwd())
from app import create_app
from app.extensions import db
from app.models import ExamAttempt, StudentAnswer, User, Bank, Exam, Question, QuestionOption, QuestionMatching, QuestionOrder, ExamQuestion, ExamSession
from app.services.exam_content import create_session_question_snapshots
PW = os.environ['A11Y_PASSWORD']
app = create_app()
with app.app_context():
    db.drop_all(); db.create_all()
    t = User(username='Profe', email='t@x.com', role='instructor'); t.set_password(PW)
    s = User(username='Ana', email='s@x.com', role='student'); s.set_password(PW)
    db.session.add_all([t, s]); db.session.commit()
    b = Bank(name='Redes', created_by=t.id); db.session.add(b); db.session.commit()
    e = Exam(title='Redes básicas', instructor_id=t.id, exam_mode='open_navigation'); db.session.add(e); db.session.commit()
    qs = []
    q = Question(bank_id=b.id, statement='¿Puerto de HTTP?', question_type='multiple_choice'); db.session.add(q); db.session.flush()
    db.session.add_all([QuestionOption(question_id=q.id, option_text='80', is_correct=True), QuestionOption(question_id=q.id, option_text='443')]); qs.append(q)
    q = Question(bank_id=b.id, statement='TCP es orientado a conexión', question_type='true_false'); db.session.add(q); db.session.flush()
    db.session.add_all([QuestionOption(question_id=q.id, option_text='Verdadero', is_correct=True), QuestionOption(question_id=q.id, option_text='Falso')]); qs.append(q)
    q = Question(bank_id=b.id, statement='Empareja', question_type='matching'); db.session.add(q); db.session.flush()
    db.session.add_all([QuestionMatching(question_id=q.id, left_text='HTTP', right_text='80'), QuestionMatching(question_id=q.id, left_text='HTTPS', right_text='443')]); qs.append(q)
    q = Question(bank_id=b.id, statement='Ordena las capas', question_type='ordering'); db.session.add(q); db.session.flush()
    db.session.add_all([QuestionOrder(question_id=q.id, item_text='Física', correct_position=1), QuestionOrder(question_id=q.id, item_text='Enlace', correct_position=2)]); qs.append(q)
    q = Question(bank_id=b.id, statement='Explica qué es DNS', question_type='open_answer'); db.session.add(q); db.session.flush(); qs.append(q)
    for i, q in enumerate(qs, 1):
        db.session.add(ExamQuestion(exam_id=e.id, question_id=q.id, points=1, order_index=i))
    sess = ExamSession(exam_id=e.id, session_code='A11Y01', status='in_progress'); db.session.add(sess); db.session.commit()
    create_session_question_snapshots(sess)
    a = User(username='Admin', email='a@x.com', role='admin'); a.set_password(PW); db.session.add(a)
    done = ExamSession(exam_id=e.id, session_code='A11Y02', status='finished'); db.session.add(done); db.session.commit()
    att = ExamAttempt(student_id=s.id, session_id=done.id, score=50, earned_points=2, max_points=4); db.session.add(att); db.session.flush()
    for i, q in enumerate(qs):
        db.session.add(StudentAnswer(attempt_id=att.id, question_id=q.id, question_statement=q.statement,
                                     answer_text='Resuelve nombres' if q.question_type == 'open_answer' else 'x',
                                     is_correct=None if q.question_type == 'open_answer' else i % 2 == 0, points_awarded=i % 2))
    from app.services import learning_service
    l = learning_service.create_default_learning(t.id, 'Curso de redes'); l.estado = 'published'
    db.session.commit()
    print(sess.id, att.id, done.id, e.id, l.id)
