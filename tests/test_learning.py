"""Capacitaciones (RF-020..RF-026): editor, catálogo, progreso, calificación de bloques y permisos."""
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support import TEST_PASSWORD  # noqa: E402
from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Block, BlockAnswer, Learning, LearningProgress, Lesson, User  # noqa: E402
from app.services import learning_service  # noqa: E402


@pytest.fixture()
def app_ctx(tmp_path):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'test_learning.db'}"
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        ids = {}
        for name, role in (('profe', 'instructor'), ('otro', 'instructor'), ('ana', 'student')):
            u = User(username=name, email=f'{name}@example.com', role=role)
            u.set_password(TEST_PASSWORD)
            db.session.add(u)
            db.session.flush()
            ids[name] = u.id
        db.session.commit()
        learning = learning_service.create_default_learning(ids['profe'], 'Redes')
        ids['learning'] = learning.id
        ids['lesson'] = learning.modules[0].lessons[0].id
    # Fuera del contexto: así cada petición abre su propia sesión y no lee una
    # transacción vieja de SQLite (WAL) que no ve los cambios de los helpers.
    yield app, ids


def _c(app, who='profe'):
    c = app.test_client()
    c.post('/login', data={'email': f'{who}@example.com', 'password': TEST_PASSWORD})
    return c


def _question(app, lesson_id, cfg):
    with app.app_context():
        base = learning_service.default_block_config('question')
        base.update(cfg)
        blk = Block(lesson_id=lesson_id, tipo='question', orden=9, visible=True, configuracion=base)
        db.session.add(blk)
        db.session.commit()
        return blk.id


def _publish(app, learning_id):
    with app.app_context():
        db.session.get(Learning, learning_id).estado = 'published'
        db.session.commit()


def test_builder_crud_and_reorder(app_ctx):
    app, ids = app_ctx
    c = _c(app)
    assert c.get('/learning/instructor/dashboard').status_code == 200
    assert c.get(f"/learning/instructor/builder/{ids['learning']}").status_code == 200

    mod = c.post('/learning/api/module/create', data={'learning_id': ids['learning'], 'titulo': 'M2'}).get_json()
    assert mod['success']
    mod_id = mod['module']['id']
    assert c.post(f'/learning/api/module/update/{mod_id}', data={'titulo': 'Módulo 2'}).get_json()['success']
    les = c.post('/learning/api/lesson/create', data={'module_id': mod_id, 'titulo': 'L1'}).get_json()
    les_id = les['lesson']['id']
    assert c.post(f'/learning/api/lesson/update/{les_id}', data={'titulo': 'Lección 1'}).get_json()['success']

    created = [c.post('/learning/api/block/create', data={'lesson_id': les_id, 'tipo': t}).get_json()['block']
               for t in ('title', 'text', 'image', 'video', 'question')]
    assert [b['orden'] for b in created] == [1, 2, 3, 4, 5]
    cfg = dict(created[1]['configuracion'], content='<p>Hola</p>')
    assert c.post(f"/learning/api/block/update/{created[1]['id']}",
                  data={'configuracion': json.dumps(cfg), 'visible': 'false'}).get_json()['success']
    assert c.post(f"/learning/api/block/update/{created[1]['id']}", data={'configuracion': '{'}).status_code == 400
    dup = c.post(f"/learning/api/block/duplicate/{created[1]['id']}").get_json()
    assert dup['success']
    order = [b['id'] for b in reversed(created)]
    assert c.post('/learning/api/block/reorder', json={'block_ids': order}).get_json()['success']
    with app.app_context():
        assert db.session.get(Block, created[-1]['id']).orden == 1
    assert c.post(f"/learning/api/block/delete/{created[0]['id']}").get_json()['success']
    assert c.post(f'/learning/api/lesson/delete/{les_id}').get_json()['success']
    assert c.post(f'/learning/api/module/delete/{mod_id}').get_json()['success']


def test_other_instructor_and_student_cannot_edit(app_ctx):
    app, ids = app_ctx
    for who in ('otro', 'ana'):
        c = _c(app, who)
        assert c.post('/learning/api/module/create', data={'learning_id': ids['learning']}).status_code == 403
        assert c.post('/learning/api/block/create', data={'lesson_id': ids['lesson'], 'tipo': 'text'}).status_code == 403
        assert c.post(f"/learning/instructor/toggle-publish/{ids['learning']}").status_code == 403
        c.post(f"/learning/instructor/duplicate/{ids['learning']}")
        c.get(f"/learning/instructor/export/{ids['learning']}")
    with app.app_context():
        # La copia de un curso ajeno revelaría las respuestas correctas de sus preguntas.
        assert Learning.query.count() == 1
        assert db.session.get(Learning, ids['learning']).estado == 'draft'


def test_create_edit_publish_duplicate_export_import(app_ctx):
    app, ids = app_ctx
    c = _c(app)
    assert c.post('/learning/instructor/create', data={'nombre': ''}).status_code == 302
    resp = c.post('/learning/instructor/create', data={'nombre': 'Seguridad', 'descripcion': 'Básico'})
    assert '/learning/instructor/builder/' in resp.headers['Location']
    c.post(f"/learning/instructor/edit/{ids['learning']}", data={'nombre': 'Redes 2', 'descripcion': 'x'})
    assert c.post(f"/learning/instructor/toggle-publish/{ids['learning']}").get_json()['nuevo_estado'] == 'published'

    c.post(f"/learning/instructor/duplicate/{ids['learning']}")
    exported = c.get(f"/learning/instructor/export/{ids['learning']}")
    assert exported.status_code == 200 and exported.mimetype == 'application/json'
    data = json.loads(exported.data)
    assert data['nombre'] == 'Redes 2' and data['modules'][0]['lessons'][0]['blocks']

    resp = c.post('/learning/instructor/import', data={'json_file': (io.BytesIO(exported.data), 'curso.json')},
                  content_type='multipart/form-data')
    assert '/learning/instructor/builder/' in resp.headers['Location']
    c.post('/learning/instructor/import', data={'json_file': (io.BytesIO(b'{'), 'roto.json')},
           content_type='multipart/form-data')
    c.post('/learning/instructor/import', data={'json_file': (io.BytesIO(b'x'), 'curso.txt')},
           content_type='multipart/form-data')
    with app.app_context():
        names = sorted(l.nombre for l in Learning.query.all())
        assert names == ['Redes 2', 'Redes 2 (Copia)', 'Redes 2 (Importado)', 'Seguridad']
        assert all(l.estado == 'draft' for l in Learning.query.all() if l.id != ids['learning'])


def test_unpublished_course_is_hidden_from_students(app_ctx):
    app, ids = app_ctx
    qid = _question(app, ids['lesson'], {'question_type': 'true_false', 'correct_answer_tf': True})
    c = _c(app, 'ana')
    assert 'Redes' not in c.get('/learning/student/catalog').get_data(as_text=True)
    assert c.get(f"/learning/student/view/{ids['learning']}").status_code == 302
    assert c.post('/learning/api/progress/update', json={'learning_id': ids['learning']}).status_code == 404
    assert c.post('/learning/api/block/submit-answer',
                  json={'block_id': qid, 'answer': {'true_false_val': True}}).status_code == 404
    with app.app_context():
        assert LearningProgress.query.count() == 0 and BlockAnswer.query.count() == 0


def test_student_flow_and_activity_goes_only_to_author(app_ctx):
    app, ids = app_ctx
    qid = _question(app, ids['lesson'], {'question_type': 'true_false', 'correct_answer_tf': True, 'points': 5})
    _publish(app, ids['learning'])
    c = _c(app, 'ana')
    assert 'Redes' in c.get('/learning/student/catalog').get_data(as_text=True)
    page = c.get(f"/learning/student/view/{ids['learning']}")
    assert page.status_code == 200
    assert '"correct_answer_tf"' not in page.get_data(as_text=True)

    assert c.post('/learning/api/progress/update', json={}).status_code == 400
    prog = c.post('/learning/api/progress/update', json={'learning_id': ids['learning'], 'lesson_id': ids['lesson'],
                                                         'time_delta': 30}).get_json()
    assert prog['success'] and prog['time_spent'] == 30

    with app.app_context():
        title_block = Block.query.filter_by(tipo='title').first().id
    assert c.post('/learning/api/block/submit-answer',
                  json={'block_id': title_block, 'answer': {}}).status_code == 400
    with patch('app.blueprints.learning.routes.socketio.emit') as emit:
        res = c.post('/learning/api/block/submit-answer',
                     json={'block_id': qid, 'answer': {'true_false_val': True}}).get_json()
    assert res['result']['is_correct'] and res['result']['score'] == 5
    assert emit.call_args.kwargs['to'] == f"teacher_{ids['profe']}"
    # Reintento: actualiza la misma respuesta, no crea otra.
    c.post('/learning/api/block/submit-answer', json={'block_id': qid, 'answer': {'true_false_val': False}})
    with app.app_context():
        answers = BlockAnswer.query.filter_by(block_id=qid).all()
        assert len(answers) == 1 and answers[0].is_correct is False


def test_fill_blank_uses_server_answers_not_client(app_ctx):
    app, ids = app_ctx
    qid = _question(app, ids['lesson'], {'question_type': 'fill_blank', 'points': 10,
                                         'fill_text': 'HTTP usa el puerto [[80]] y HTTPS el [[443]].'})
    _publish(app, ids['learning'])
    c = _c(app, 'ana')
    forged = {'blanks': {'0': 'x', '1': 'y'}, 'expected_blanks': {'0': 'x', '1': 'y'}}
    res = c.post('/learning/api/block/submit-answer', json={'block_id': qid, 'answer': forged}).get_json()['result']
    assert res['is_correct'] is False and res['score'] == 0
    half = c.post('/learning/api/block/submit-answer',
                  json={'block_id': qid, 'answer': {'blanks': {'0': '80', '1': 'y'}}}).get_json()['result']
    assert half['score'] == 5
    ok = c.post('/learning/api/block/submit-answer',
                json={'block_id': qid, 'answer': {'blanks': {'0': ' 80 ', '1': '443'}}}).get_json()['result']
    assert ok['is_correct'] and ok['score'] == 10


@pytest.mark.parametrize('cfg, answer, correct', [
    ({'question_type': 'single_choice'}, {'selected_options': 1}, True),
    ({'question_type': 'multiple_choice'}, {'selected_options': [1, 2]}, False),
    ({'question_type': 'short_answer', 'short_answers': ['Router']}, {'text_response': ' router '}, True),
    ({'question_type': 'ordering'}, {'order': [1, 2]}, True),
    ({'question_type': 'ordering'}, {'order': [2, 1]}, False),
    ({'question_type': 'matching'}, {'pairs': {}}, False),
])
def test_grade_question_block_types(app_ctx, cfg, answer, correct):
    app, ids = app_ctx
    qid = _question(app, ids['lesson'], cfg)
    with app.app_context():
        assert learning_service.grade_question_block(db.session.get(Block, qid), answer)['is_correct'] is correct


def test_matching_all_pairs(app_ctx):
    app, ids = app_ctx
    qid = _question(app, ids['lesson'], {'question_type': 'matching'})
    with app.app_context():
        blk = db.session.get(Block, qid)
        pairs = {str(p['id']): p['right'] for p in blk.configuracion['matching_pairs']}
        assert learning_service.grade_question_block(blk, {'pairs': pairs})['is_correct']


def test_upload_rejects_unknown_extension(app_ctx):
    app, ids = app_ctx
    c = _c(app)
    resp = c.post('/learning/api/upload', data={'file': (io.BytesIO(b'x'), 'malo.exe')},
                  content_type='multipart/form-data')
    assert resp.status_code == 400
    assert _c(app, 'ana').post('/learning/api/upload', data={'file': (io.BytesIO(b'x'), 'a.png')},
                               content_type='multipart/form-data').status_code == 403


def test_delete_learning_owner_only(app_ctx):
    app, ids = app_ctx
    _c(app, 'otro').post(f"/learning/instructor/delete/{ids['learning']}")
    with app.app_context():
        assert db.session.get(Learning, ids['learning']) is not None
    _c(app).post(f"/learning/instructor/delete/{ids['learning']}")
    with app.app_context():
        assert db.session.get(Learning, ids['learning']) is None and Lesson.query.count() == 0
