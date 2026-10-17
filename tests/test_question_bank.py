"""Banco de preguntas (RF-004/RF-005), importación CSV (RF-014) y permisos."""
import io
import sys
from pathlib import Path
import pytest
from werkzeug.datastructures import MultiDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support import TEST_PASSWORD  # noqa: E402
from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Bank, Question, User  # noqa: E402


@pytest.fixture()
def app_ctx(tmp_path):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'test_bank.db'}"
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        ids = {}
        for name in ('profe', 'otro'):
            u = User(username=name, email=f'{name}@example.com', role='instructor')
            u.set_password(TEST_PASSWORD)
            db.session.add(u)
            db.session.flush()
            ids[name] = u.id
        bank = Bank(name='Redes', created_by=ids['profe'])
        db.session.add(bank)
        db.session.commit()
        ids['bank'] = bank.id
        yield app, ids


def _c(app, who='profe'):
    c = app.test_client()
    c.post('/login', data={'email': f'{who}@example.com', 'password': TEST_PASSWORD})
    return c


def _questions(app):
    with app.app_context():
        return {q.statement: q for q in Question.query.all()}


@pytest.mark.parametrize('form, check', [
    ({'question_type': 'multiple_choice', 'options[]': ['80', '443'], 'correct_options[]': ['0']},
     lambda q: [o.is_correct for o in q.options] == [True, False]),
    ({'question_type': 'true_false', 'true_false_correct': 'false'},
     lambda q: [(o.option_text, o.is_correct) for o in q.options] == [('Verdadero', False), ('Falso', True)]),
    ({'question_type': 'matching', 'left_text[]': ['HTTP', 'HTTPS'], 'right_text[]': ['80', '443']},
     lambda q: len(q.matching_pairs) == 2),
    ({'question_type': 'ordering', 'order_item[]': ['Física', 'Enlace', 'Red']},
     lambda q: [i.correct_position for i in q.order_items] == [1, 2, 3]),
    ({'question_type': 'open_answer'}, lambda q: q.options == []),
])
def test_create_each_question_type(app_ctx, form, check):
    app, ids = app_ctx
    data = MultiDict({'bank_id': ids['bank'], 'statement': 'P', 'category': 'Redes'})
    for k, v in form.items():
        for item in (v if isinstance(v, list) else [v]):
            data.add(k, item)
    _c(app).post('/instructor/question/create', data=data)
    with app.app_context():
        assert check(Question.query.one())


def test_invalid_question_is_rejected(app_ctx):
    app, ids = app_ctx
    _c(app).post('/instructor/question/create', data={'bank_id': ids['bank'], 'statement': 'P',
                                                      'question_type': 'multiple_choice', 'options[]': ['solo una']})
    assert _questions(app) == {}


def test_edit_duplicate_list_and_filters(app_ctx):
    app, ids = app_ctx
    c = _c(app)
    c.post('/instructor/question/create', data={'bank_id': ids['bank'], 'statement': 'Puerto HTTP',
                                                'question_type': 'open_answer', 'category': 'Redes'})
    qid = _questions(app)['Puerto HTTP'].id
    c.post(f'/instructor/question/edit/{qid}', data={'statement': 'Puerto HTTPS', 'question_type': 'open_answer',
                                                     'category': 'Seguridad'})
    c.post(f'/instructor/question/duplicate/{qid}')
    qs = _questions(app)
    assert 'Puerto HTTPS' in qs and qs['Puerto HTTPS'].category == 'Seguridad'
    with app.app_context():
        assert Question.query.filter_by(statement='Puerto HTTPS (copia)').count() == 1
    page = c.get('/instructor/mis-preguntas?q=https&type=open_answer').get_data(as_text=True)
    assert 'Puerto HTTPS' in page
    assert 'Puerto HTTPS' not in c.get('/instructor/mis-preguntas?type=matching').get_data(as_text=True)


def test_other_instructor_cannot_touch_my_bank(app_ctx):
    app, ids = app_ctx
    _c(app).post('/instructor/question/create', data={'bank_id': ids['bank'], 'statement': 'Mía',
                                                      'question_type': 'open_answer'})
    qid = _questions(app)['Mía'].id
    other = _c(app, 'otro')
    other.post(f'/instructor/question/edit/{qid}', data={'statement': 'Robada', 'question_type': 'open_answer'})
    other.post(f'/instructor/question/delete/{qid}')
    other.post(f"/instructor/bank/edit/{ids['bank']}", data={'name': 'Hackeado'})
    other.post(f"/instructor/bank/delete/{ids['bank']}")
    other.post('/instructor/question/create', data={'bank_id': ids['bank'], 'statement': 'Intrusa',
                                                    'question_type': 'open_answer'})
    qs = _questions(app)
    assert set(qs) == {'Mía'}
    with app.app_context():
        assert db.session.get(Bank, ids['bank']).name == 'Redes'


def test_bank_create_edit_delete(app_ctx):
    app, _ = app_ctx
    c = _c(app)
    c.post('/instructor/bank/create', data={'name': 'Seguridad', 'description': 'd'})
    with app.app_context():
        bank_id = Bank.query.filter_by(name='Seguridad').one().id
    c.post(f'/instructor/bank/edit/{bank_id}', data={'name': 'Ciberseguridad', 'description': 'd2'})
    with app.app_context():
        assert db.session.get(Bank, bank_id).name == 'Ciberseguridad'
    c.post(f'/instructor/bank/delete/{bank_id}')
    with app.app_context():
        assert db.session.get(Bank, bank_id) is None


def test_next_parameter_is_not_an_open_redirect(app_ctx):
    app, ids = app_ctx
    c = _c(app)
    for target in ('https://evil.example', '//evil.example', '/\\evil.example'):
        res = c.post('/instructor/question/create', data={'bank_id': ids['bank'], 'statement': 'X',
                                                          'question_type': 'open_answer', 'next': target})
        assert 'evil.example' not in res.headers['Location']
    res = c.post('/instructor/question/create', data={'bank_id': ids['bank'], 'statement': 'Y',
                                                      'question_type': 'open_answer', 'next': '/instructor/exams'})
    assert res.headers['Location'].endswith('/instructor/exams')


CSV = """statement,question_type,category,options,correct_option,pairs,items,feedback_text
¿Puerto HTTP?,multiple_choice,Redes,80|443|21,0,,,El 80 es el estándar
¿TCP es orientado a conexión?,true_false,Redes,Verdadero|Falso,0,,,
Empareja,matching,Redes,,,HTTP:80|HTTPS:443,,
Ordena las capas,ordering,Redes,,,,Física|Enlace|Red,
Explica DNS,open_answer,Redes,,,,,
,multiple_choice,Redes,a|b,0,,,
"""


def test_import_csv_all_types(app_ctx):
    app, ids = app_ctx
    data = {'bank_id': ids['bank'], 'excel_file': (io.BytesIO(CSV.encode('utf-8')), 'preguntas.csv')}
    _c(app).post('/instructor/question/import-excel', data=data, content_type='multipart/form-data')
    qs = _questions(app)
    assert set(qs) == {'¿Puerto HTTP?', '¿TCP es orientado a conexión?', 'Empareja', 'Ordena las capas', 'Explica DNS'}
    with app.app_context():
        mc = Question.query.filter_by(statement='¿Puerto HTTP?').one()
        assert [o.option_text for o in mc.options if o.is_correct] == ['80']
        assert len(Question.query.filter_by(statement='Empareja').one().matching_pairs) == 2
        assert [i.item_text for i in sorted(Question.query.filter_by(statement='Ordena las capas').one().order_items,
                                            key=lambda i: i.correct_position)] == ['Física', 'Enlace', 'Red']


def test_import_rejects_unsupported_file(app_ctx):
    app, ids = app_ctx
    data = {'bank_id': ids['bank'], 'excel_file': (io.BytesIO(b'x'), 'preguntas.txt')}
    _c(app).post('/instructor/question/import-excel', data=data, content_type='multipart/form-data')
    assert _questions(app) == {}
