"""Subida de archivos (RNF-07): lista blanca, firma, tope por tipo y nombre aleatorio."""
import io
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support import TEST_PASSWORD  # noqa: E402
from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Learning, User  # noqa: E402
from app.services import learning_service  # noqa: E402

PNG = b'\x89PNG\r\n\x1a\n' + b'\0' * 32
MP4 = b'\0\0\0\x18ftypmp42' + b'\0' * 32


@pytest.fixture()
def app_ctx(tmp_path):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'test_uploads.db'}"
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                      UPLOAD_LIMITS_MB={'image': 1, 'video': 2, 'audio': 1, 'document': 1, 'import': 1})
    app.root_path = str(tmp_path)  # los archivos van a tmp_path/static/uploads, no al repo
    with app.app_context():
        db.drop_all()
        db.create_all()
        u = User(username='profe', email='profe@example.com', role='instructor')
        u.set_password(TEST_PASSWORD)
        db.session.add(u)
        db.session.commit()
        learning_id = learning_service.create_default_learning(u.id, 'Redes').id
    c = app.test_client()
    c.post('/login', data={'email': 'profe@example.com', 'password': TEST_PASSWORD})
    yield app, c, tmp_path, learning_id


def _upload(c, content, name):
    return c.post('/learning/api/upload', data={'file': (io.BytesIO(content), name)},
                  content_type='multipart/form-data')


def test_valid_files_get_random_names(app_ctx):
    app, c, tmp, _ = app_ctx
    for content, name in ((PNG, 'Mi Foto.PNG'), (MP4, 'clase.mp4'), (b'%PDF-1.7\n', 'guia.pdf'),
                          (b'ID3\x04', 'audio.mp3'), (b'\xff\xd8\xff\xe0', 'a.jpg')):
        resp = _upload(c, content, name)
        assert resp.status_code == 200, (name, resp.get_json())
        url = resp.get_json()['url']
        assert url.startswith('/static/uploads/learning/media_') and 'Foto' not in url
        assert (tmp / url.removeprefix('/')).exists()


@pytest.mark.parametrize('content, name, status, msg', [
    (b'<html><script>alert(1)</script>', 'falsa.png', 400, 'no corresponde'),
    (PNG, 'imagen.svg', 400, 'no permitido'),
    (PNG, 'sin_extension', 400, 'No se seleccionó'),
    (b'', 'vacia.png', 400, 'vacío'),
    (PNG + b'\0' * (1024 * 1024), 'grande.png', 413, '1 MB'),
])
def test_rejected_uploads(app_ctx, content, name, status, msg):
    _, c, tmp, _ = app_ctx
    resp = _upload(c, content, name)
    assert resp.status_code == status and msg in resp.get_json()['error']
    assert not any(p.is_file() for p in (tmp / 'static').rglob('*'))


def test_video_has_its_own_larger_limit(app_ctx):
    _, c, _, _ = app_ctx
    big = MP4 + b'\0' * (1024 * 1024 + 10)  # > 1 MB de imagen, < 2 MB de video
    assert _upload(c, big, 'clase.mp4').status_code == 200
    assert _upload(c, MP4 + b'\0' * (2 * 1024 * 1024), 'clase.mp4').status_code == 413


def test_cover_must_be_an_image(app_ctx):
    app, c, _, learning_id = app_ctx
    c.post(f'/learning/instructor/edit/{learning_id}', data={'nombre': 'Redes', 'descripcion': '',
           'portada_file': (io.BytesIO(MP4), 'portada.mp4')}, content_type='multipart/form-data')
    with app.app_context():
        assert db.session.get(Learning, learning_id).portada is None
    c.post(f'/learning/instructor/edit/{learning_id}', data={'nombre': 'Redes', 'descripcion': '',
           'portada_file': (io.BytesIO(PNG), 'portada.png')}, content_type='multipart/form-data')
    with app.app_context():
        assert db.session.get(Learning, learning_id).portada.startswith('uploads/learning/cover_')


def test_import_files_have_their_own_limit(app_ctx):
    app, c, _, _ = app_ctx
    big = b'{"nombre": "x", "pad": "' + b'a' * (1024 * 1024) + b'"}'
    c.post('/learning/instructor/import', data={'json_file': (io.BytesIO(big), 'curso.json')},
           content_type='multipart/form-data')
    with app.app_context():
        assert Learning.query.count() == 1


def test_request_cap_covers_largest_type():
    assert Config.MAX_CONTENT_LENGTH >= max(Config.UPLOAD_LIMITS_MB.values()) * 1024 * 1024
