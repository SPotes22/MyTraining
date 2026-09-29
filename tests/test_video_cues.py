import json
import sys
from pathlib import Path

import pytest
from werkzeug.datastructures import MultiDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.config import Config
from app.extensions import db
from app.models import (Bank, Block, BlockAnswer, Exam, ExamQuestion, ExamSession, Learning, LearningModule,
                        Lesson, LiveAnswer, Question, User)
from app.services import learning_service
from app.services import video_cues
from app.services.exam_builder import duplicate_question, save_question_payload
from app.services.exam_content import create_session_question_snapshots
from app.services.video_cues import (build_video_metadata, embed_src, format_timestamp,
                                     parse_timestamp, parse_video_source, resolve_video_metadata)


# ── Unidades: tiempos y proveedores ─────────────────────────────────────────

@pytest.mark.parametrize('raw, expected', [
    ('95', 95), ('1:35', 95), ('01:01:35', 3695), (95.0, 95), ('', None), (None, None),
])
def test_parse_timestamp(raw, expected):
    assert parse_timestamp(raw) == expected


@pytest.mark.parametrize('raw', ['abc', '1:xx', '1:2:3:4', '-5'])
def test_parse_timestamp_rejects_garbage(raw):
    with pytest.raises(ValueError):
        parse_timestamp(raw)


def test_format_timestamp():
    assert format_timestamp(95) == '1:35'
    assert format_timestamp(3695) == '1:01:35'
    assert format_timestamp(None) == ''


@pytest.mark.parametrize('url, provider, video_id', [
    ('https://youtu.be/dQw4w9WgXcQ?t=10', 'youtube', 'dQw4w9WgXcQ'),
    ('https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=x', 'youtube', 'dQw4w9WgXcQ'),
    ('https://www.youtube.com/embed/dQw4w9WgXcQ', 'youtube', 'dQw4w9WgXcQ'),
    ('https://youtube.com/shorts/dQw4w9WgXcQ', 'youtube', 'dQw4w9WgXcQ'),
    ('https://vimeo.com/76979871', 'vimeo', '76979871'),
    ('/static/uploads/learning/clase.mp4', 'file', None),
    ('https://example.com/video', 'other', None),
])
def test_parse_video_source(url, provider, video_id):
    source = parse_video_source(url)
    assert source['provider'] == provider
    assert source['video_id'] == video_id


def test_build_video_metadata_json():
    meta = build_video_metadata('https://youtu.be/dQw4w9WgXcQ', start='0:30', question_at='1:35', pause_on_question=False)
    assert meta == {
        'version': 1,
        'provider': 'youtube',
        'video_id': 'dQw4w9WgXcQ',
        'embed_url': 'https://www.youtube.com/embed/dQw4w9WgXcQ',
        'source_url': 'https://youtu.be/dQw4w9WgXcQ',
        'start': 30,
        'question_at': 95,
        'pause_on_question': False,
    }
    assert embed_src(meta) == 'https://www.youtube.com/embed/dQw4w9WgXcQ?start=30&rel=0'


def test_build_video_metadata_validates_times():
    with pytest.raises(ValueError, match='después del inicio'):
        build_video_metadata('https://youtu.be/dQw4w9WgXcQ', start='2:00', question_at='1:00')
    with pytest.raises(ValueError, match='YouTube, Vimeo'):
        build_video_metadata('https://example.com/video', question_at='10')
    # Sin cue, cualquier proveedor es válido.
    assert build_video_metadata('https://example.com/video')['question_at'] is None


def test_resolve_legacy_question_without_json():
    meta = resolve_video_metadata('https://youtu.be/dQw4w9WgXcQ', None, 40)
    assert meta['has_cue'] is True
    assert meta['question_at'] == 40
    assert meta['question_at_label'] == '0:40'


def test_resolve_ignores_stale_json_when_url_changed():
    stale = build_video_metadata('https://youtu.be/dQw4w9WgXcQ', question_at='10')
    meta = resolve_video_metadata('https://vimeo.com/76979871', stale, None)
    assert meta['provider'] == 'vimeo'
    assert meta['has_cue'] is False


# ── Integración con el constructor, snapshots y vista del estudiante ────────

@pytest.fixture()
def app_ctx(tmp_path):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'test_video_cues.db'}"
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        teacher = User(username='Profe', email='profe@example.com', role='instructor')
        teacher.set_password('secret')
        student = User(username='Julio', email='julio@example.com', role='student')
        student.set_password('secret')
        db.session.add_all([teacher, student])
        db.session.commit()
        bank = Bank(name='Banco Video', created_by=teacher.id)
        db.session.add(bank)
        db.session.commit()
        yield app, teacher, student, bank


def _video_form(**extra):
    data = MultiDict([
        ('question_type', 'multiple_choice'),
        ('statement', '¿Qué protocolo se explica en el video?'),
        ('options[]', 'TCP'), ('options[]', 'UDP'),
        ('correct_options[]', '0'),
        ('video_url', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'),
        ('video_cue_fields', '1'),
        ('video_start', '0:30'),
        ('video_question_at', '1:35'),
    ])
    for key, value in extra.items():
        data[key] = value
    return data


def test_save_question_payload_stores_cue_json(app_ctx):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        q = Question(bank_id=bank.id)
        save_question_payload(q, _video_form(video_pause_on_question='on'))
        db.session.add(q)
        db.session.commit()
        assert q.video_metadata['question_at'] == 95
        assert q.video_metadata['start'] == 30
        assert q.video_metadata['pause_on_question'] is True
        assert q.video_timestamp == 95

        # Checkbox desmarcado → no se envía → sin pausa.
        save_question_payload(q, _video_form())
        assert q.video_metadata['pause_on_question'] is False

        # Quitar el video limpia los metadatos.
        save_question_payload(q, _video_form(video_url=''))
        assert q.video_metadata is None and q.video_timestamp is None


def test_save_question_payload_rejects_bad_cue(app_ctx):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        q = Question(bank_id=bank.id)
        with pytest.raises(ValueError):
            save_question_payload(q, _video_form(video_question_at='0:10'))


def _exam_with_video_question(teacher, bank):
    q = Question(bank_id=bank.id)
    save_question_payload(q, _video_form(video_pause_on_question='on'))
    db.session.add(q)
    exam = Exam(title='Redes en video', instructor_id=teacher.id)
    db.session.add(exam)
    db.session.commit()
    db.session.add(ExamQuestion(exam_id=exam.id, question_id=q.id, points=1.0))
    session = ExamSession(exam_id=exam.id, session_code='VID011', status='RUNNING')
    db.session.add(session)
    db.session.commit()
    return q, session


def test_snapshot_and_duplicate_keep_cue(app_ctx):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        q, session = _exam_with_video_question(teacher, bank)
        snaps = create_session_question_snapshots(session)
        assert snaps[0].video_metadata['question_at'] == 95
        assert snaps[0].video_cue['has_cue'] is True
        copy = duplicate_question(q)
        assert copy.video_metadata == q.video_metadata


def _login(app, email):
    client = app.test_client()
    client.post('/login', data={'email': email, 'password': 'secret'})
    return client


def test_student_view_does_not_ship_question_before_cue(app_ctx):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        _, session = _exam_with_video_question(teacher, bank)
        session_id = session.id
    html = _login(app, 'julio@example.com').get(f'/exam/presentar/{session_id}').get_data(as_text=True)
    assert 'data-video-gated="1"' in html
    assert '"question_at": 95' in html
    assert 'la pregunta aparecerá en el minuto <strong>1:35</strong>' in html
    assert 'js/video_cues.js' in html
    assert 'data-cue-src="/exam/presentar/' in html
    # El enunciado y las opciones no viajan en el HTML inicial.
    assert '¿Qué protocolo se explica en el video?' not in html
    assert 'TCP' not in html
    assert '?start=' not in html


def test_exam_cue_endpoint_waits_for_video_time(app_ctx, monkeypatch):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        q, session = _exam_with_video_question(teacher, bank)
        session_id, question_id = session.id, q.id
    clock = {'now': 1000.0}
    monkeypatch.setattr(video_cues.time, 'time', lambda: clock['now'])
    client = _login(app, 'julio@example.com')
    client.get(f'/exam/presentar/{session_id}')
    url = f'/exam/presentar/{session_id}/video-question/{question_id}'

    # 95 s (cue) − 30 s (inicio) − 3 s de tolerancia = 62 s de video.
    resp = client.get(url)
    assert resp.status_code == 425
    assert resp.get_json()['retry_after'] == 62

    clock['now'] += 62
    resp = client.get(url)
    assert resp.status_code == 200
    html = resp.get_json()['html']
    assert '¿Qué protocolo se explica en el video?' in html
    assert f'name="question_{question_id}"' in html


def test_exam_cue_endpoint_serves_already_answered_question(app_ctx):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        q, session = _exam_with_video_question(teacher, bank)
        db.session.add(LiveAnswer(session_id=session.id, student_id=student.id, question_id=q.id,
                                  answer_json={'selected_option_id': q.options[0].id}))
        db.session.commit()
        session_id, question_id = session.id, q.id
    resp = _login(app, 'julio@example.com').get(f'/exam/presentar/{session_id}/video-question/{question_id}')
    assert resp.status_code == 200


def test_exam_cue_endpoint_rejects_foreign_question(app_ctx):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        _, session = _exam_with_video_question(teacher, bank)
        other = Question(bank_id=bank.id, statement='Otra', question_type='open_answer')
        db.session.add(other)
        db.session.commit()
        session_id, other_id = session.id, other.id
    resp = _login(app, 'julio@example.com').get(f'/exam/presentar/{session_id}/video-question/{other_id}')
    assert resp.status_code == 404


# ── Learning Builder: preguntas dentro de un bloque de video ───────────────

def _lesson_with_video(teacher, estado='published'):
    learning = Learning(nombre='Ciberseguridad', autor_id=teacher.id, estado=estado)
    db.session.add(learning)
    db.session.flush()
    module = LearningModule(learning_id=learning.id, titulo='M1', orden=1)
    db.session.add(module)
    db.session.flush()
    lesson = Lesson(module_id=module.id, titulo='L1', orden=1)
    db.session.add(lesson)
    db.session.flush()
    video_cfg = learning_service.default_block_config('video')
    video_cfg['url'] = 'https://youtu.be/dQw4w9WgXcQ'
    video = Block(lesson_id=lesson.id, tipo='video', orden=1, configuracion=video_cfg)
    question_cfg = learning_service.default_block_config('question')
    question_cfg.update(question_type='single_choice', question='¿Qué es un vector de ataque?')
    question = Block(lesson_id=lesson.id, tipo='question', orden=2, configuracion=question_cfg)
    text = Block(lesson_id=lesson.id, tipo='text', orden=3, configuracion={'content': 'x'})
    db.session.add_all([video, question, text])
    db.session.commit()
    return learning, lesson, video, question, text


def test_normalize_learning_video_cues(app_ctx):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        _, lesson, video, question, text = _lesson_with_video(teacher)
        cfg = video_cues.normalize_learning_video_cues(
            {'url': video.configuracion['url'], 'start': '0:10',
             'cues': [{'at': '1:35', 'question_block_id': str(question.id), 'pause': False}]},
            lesson.blocks)
        assert cfg['start'] == 10
        assert cfg['cues'] == [{'at': 95, 'question_block_id': question.id, 'pause': False}]
        with pytest.raises(ValueError, match='bloque de pregunta'):
            video_cues.normalize_learning_video_cues(
                {'url': video.configuracion['url'], 'cues': [{'at': 5, 'question_block_id': text.id}]}, lesson.blocks)
        with pytest.raises(ValueError, match='después del inicio'):
            video_cues.normalize_learning_video_cues(
                {'url': video.configuracion['url'], 'start': 20,
                 'cues': [{'at': 5, 'question_block_id': question.id}]}, lesson.blocks)
        with pytest.raises(ValueError, match='YouTube, Vimeo'):
            video_cues.normalize_learning_video_cues(
                {'url': 'https://example.com/v', 'cues': [{'at': 5, 'question_block_id': question.id}]}, lesson.blocks)


def test_learning_block_update_validates_cues(app_ctx):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        _, lesson, video, question, text = _lesson_with_video(teacher)
        video_id, question_id, text_id, url = video.id, question.id, text.id, video.configuracion['url']
    client = _login(app, 'profe@example.com')
    ok = client.post(f'/learning/api/block/update/{video_id}', data={'configuracion': json.dumps(
        {'url': url, 'start': '0:05', 'cues': [{'at': '0:40', 'question_block_id': question_id, 'pause': True}]})})
    assert ok.status_code == 200
    assert ok.get_json()['block']['configuracion']['cues'] == [{'at': 40, 'question_block_id': question_id, 'pause': True}]
    bad = client.post(f'/learning/api/block/update/{video_id}', data={'configuracion': json.dumps(
        {'url': url, 'cues': [{'at': '0:40', 'question_block_id': text_id}]})})
    assert bad.status_code == 400
    with app.app_context():
        assert db.session.get(Block, video_id).configuracion['cues'][0]['at'] == 40


def _set_cue(video, question, at=40, start=5):
    video.configuracion = {**video.configuracion, 'start': start,
                           'cues': [{'at': at, 'question_block_id': question.id, 'pause': True}]}
    db.session.commit()


def test_learning_student_view_hides_cued_question(app_ctx, monkeypatch):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        learning, lesson, video, question, _ = _lesson_with_video(teacher)
        _set_cue(video, question)
        learning_id, question_id = learning.id, question.id
    clock = {'now': 5000.0}
    monkeypatch.setattr(video_cues.time, 'time', lambda: clock['now'])
    client = _login(app, 'julio@example.com')
    html = client.get(f'/learning/student/view/{learning_id}').get_data(as_text=True)
    assert 'js/video_cues.js' in html
    assert 'es un vector de ataque' not in html  # tojson escapa los acentos
    assert f'/learning/api/block/{question_id}/video-question' in html
    assert '"target": "#block_' + str(question_id) + '"' in html

    url = f'/learning/api/block/{question_id}/video-question'
    resp = client.get(url)
    assert resp.status_code == 425
    assert resp.get_json()['retry_after'] == 32  # 40 − 5 − 3
    clock['now'] += 32
    block = client.get(url).get_json()['block']
    assert block['configuracion']['question'] == '¿Qué es un vector de ataque?'
    assert all('is_correct' not in opt for opt in block['configuracion']['options'])


def test_learning_answered_cued_question_is_shipped(app_ctx):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        learning, lesson, video, question, _ = _lesson_with_video(teacher)
        _set_cue(video, question)
        db.session.add(BlockAnswer(user_id=student.id, block_id=question.id, answer_data={}, score=0))
        db.session.commit()
        learning_id = learning.id
    html = _login(app, 'julio@example.com').get(f'/learning/student/view/{learning_id}').get_data(as_text=True)
    assert 'es un vector de ataque' in html
    assert '"is_correct"' not in html


def test_learning_duplicate_and_import_remap_cues(app_ctx):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        learning, lesson, video, question, _ = _lesson_with_video(teacher)
        _set_cue(video, question)

        def cue_points_to_question(copy):
            blocks = copy.modules[0].lessons[0].blocks
            new_video = next(b for b in blocks if b.tipo == 'video')
            new_question = next(b for b in blocks if b.tipo == 'question')
            return new_video.configuracion['cues'][0]['question_block_id'] == new_question.id != question.id

        assert cue_points_to_question(learning_service.duplicate_learning(learning.id, teacher.id))
        exported = json.loads(json.dumps(learning_service.export_learning_json(learning.id)))
        assert cue_points_to_question(learning_service.import_learning_json(exported, teacher.id))
