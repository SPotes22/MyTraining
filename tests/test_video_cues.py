import sys
from pathlib import Path

import pytest
from werkzeug.datastructures import MultiDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.config import Config
from app.extensions import db
from app.models import Bank, Exam, ExamQuestion, ExamSession, Question, User
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


def test_student_view_hides_question_until_cue(app_ctx):
    app, teacher, student, bank = app_ctx
    with app.app_context():
        _, session = _exam_with_video_question(teacher, bank)
        session_id = session.id
    client = app.test_client()
    client.post('/login', data={'email': 'julio@example.com', 'password': 'secret'})
    html = client.get(f'/exam/presentar/{session_id}').get_data(as_text=True)
    assert 'data-video-gated="1"' in html
    assert 'data-video-cue=' in html
    assert '"question_at": 95' in html
    assert 'la pregunta aparecerá en el minuto <strong>1:35</strong>' in html
    assert 'js/video_cues.js' in html
    assert 'class="video-cue-gate d-none"' in html
    # Ya no se usa el iframe con ?start= para las preguntas con cue.
    assert '?start=' not in html
