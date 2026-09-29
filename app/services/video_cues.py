# app/services/video_cues.py
"""
RF-011 · Preguntas en videos.

Cada pregunta con video guarda un JSON de metadatos (`video_metadata`) que describe
cómo reproducirlo y en qué segundo debe aparecer la pregunta:

    {
      "version": 1,
      "provider": "youtube" | "vimeo" | "file" | "other",
      "video_id": "dQw4w9WgXcQ",          # solo youtube / vimeo
      "embed_url": "https://www.youtube.com/embed/dQw4w9WgXcQ",
      "source_url": "https://youtu.be/dQw4w9WgXcQ",
      "start": 30,                          # segundo en que arranca la reproducción
      "question_at": 95,                    # segundo en que aparece la pregunta (None = sin cue)
      "pause_on_question": true             # pausar el video cuando aparece la pregunta
    }

`video_timestamp` (columna heredada) se mantiene sincronizado con `question_at`.
"""
import re
from urllib.parse import urlparse, parse_qs

VIDEO_METADATA_VERSION = 1
TRACKABLE_PROVIDERS = {'youtube', 'vimeo', 'file'}
VIDEO_FILE_EXTENSIONS = ('.mp4', '.webm', '.ogg', '.ogv', '.mov', '.m4v')

_YT_ID = re.compile(r'^[A-Za-z0-9_-]{6,20}$')


def parse_timestamp(value):
    """Convierte '95', '1:35' o '01:01:35' a segundos. Vacío → None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = int(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        parts = text.split(':')
        if len(parts) > 3 or not all(p.strip().isdigit() for p in parts):
            raise ValueError(f'Tiempo de video inválido: "{text}". Usa segundos o mm:ss.')
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + int(part)
    if seconds < 0:
        raise ValueError('Los tiempos del video no pueden ser negativos.')
    return seconds


def format_timestamp(seconds):
    """95 → '1:35', 3695 → '1:01:35'."""
    if seconds is None:
        return ''
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f'{hours}:{minutes:02d}:{secs:02d}'
    return f'{minutes}:{secs:02d}'


def parse_video_source(url):
    """Detecta el proveedor del video y arma la URL embebible."""
    url = (url or '').strip()
    if not url:
        return None
    parsed = urlparse(url)
    host = (parsed.netloc or '').lower()
    if host.startswith('www.'):
        host = host[4:]
    if host.startswith('m.'):
        host = host[2:]
    path = parsed.path or ''

    video_id = None
    if host == 'youtu.be':
        video_id = path.strip('/').split('/')[0]
    elif host in ('youtube.com', 'youtube-nocookie.com'):
        if path == '/watch':
            video_id = (parse_qs(parsed.query).get('v') or [None])[0]
        else:
            for prefix in ('/embed/', '/shorts/', '/live/', '/v/'):
                if path.startswith(prefix):
                    video_id = path[len(prefix):].split('/')[0]
                    break
    if video_id and _YT_ID.match(video_id):
        return {
            'provider': 'youtube',
            'video_id': video_id,
            'embed_url': f'https://www.youtube.com/embed/{video_id}',
        }

    if host in ('vimeo.com', 'player.vimeo.com'):
        match = re.search(r'/(?:video/)?(\d+)', path)
        if match:
            vid = match.group(1)
            return {'provider': 'vimeo', 'video_id': vid, 'embed_url': f'https://player.vimeo.com/video/{vid}'}

    if path.lower().endswith(VIDEO_FILE_EXTENSIONS):
        return {'provider': 'file', 'video_id': None, 'embed_url': url}

    return {'provider': 'other', 'video_id': None, 'embed_url': url}


def build_video_metadata(video_url, start=None, question_at=None, pause_on_question=True):
    """Valida los tiempos y arma el JSON de metadatos. Sin video → None."""
    source = parse_video_source(video_url)
    if not source:
        return None
    start = parse_timestamp(start) or 0
    question_at = parse_timestamp(question_at)
    if question_at is not None and question_at <= start:
        raise ValueError('La pregunta debe aparecer después del inicio del video.')
    if question_at is not None and source['provider'] not in TRACKABLE_PROVIDERS:
        raise ValueError('Solo se puede mostrar la pregunta durante la reproducción en videos de '
                         'YouTube, Vimeo o archivos MP4/WEBM.')
    return {
        'version': VIDEO_METADATA_VERSION,
        'provider': source['provider'],
        'video_id': source['video_id'],
        'embed_url': source['embed_url'],
        'source_url': video_url.strip(),
        'start': start,
        'question_at': question_at,
        'pause_on_question': bool(pause_on_question),
    }


def resolve_video_metadata(video_url, video_metadata=None, video_timestamp=None):
    """
    Metadatos listos para las plantillas. Si la pregunta es anterior a RF-011
    (sin JSON) se reconstruyen a partir de `video_url` y `video_timestamp`.
    """
    if not video_url:
        return None
    meta = dict(video_metadata) if isinstance(video_metadata, dict) else None
    if not meta or meta.get('source_url') != video_url.strip():
        source = parse_video_source(video_url)
        legacy_at = video_timestamp if video_timestamp and source['provider'] in TRACKABLE_PROVIDERS else None
        meta = {
            'version': VIDEO_METADATA_VERSION,
            **source,
            'source_url': video_url.strip(),
            'start': 0,
            'question_at': legacy_at,
            'pause_on_question': True,
        }
    meta['start'] = int(meta.get('start') or 0)
    meta['has_cue'] = bool(meta.get('question_at')) and meta.get('provider') in TRACKABLE_PROVIDERS
    meta['question_at_label'] = format_timestamp(meta.get('question_at'))
    meta['start_label'] = format_timestamp(meta['start']) if meta['start'] else ''
    return meta


def embed_src(meta):
    """URL del iframe respetando el segundo de inicio (para vistas sin cue, p. ej. reportes)."""
    if not meta:
        return ''
    url = meta['embed_url']
    start = meta.get('start') or 0
    if meta['provider'] == 'youtube':
        return f'{url}?start={start}&rel=0' if start else f'{url}?rel=0'
    if meta['provider'] == 'vimeo':
        return f'{url}#t={start}s' if start else url
    if meta['provider'] == 'file':
        return f'{url}#t={start}' if start else url
    return url
