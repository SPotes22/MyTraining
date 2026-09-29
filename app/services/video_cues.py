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
import time
from urllib.parse import urlparse, parse_qs

from flask import session as flask_session

VIDEO_METADATA_VERSION = 1
TRACKABLE_PROVIDERS = {'youtube', 'vimeo', 'file'}
VIDEO_FILE_EXTENSIONS = ('.mp4', '.webm', '.ogg', '.ogv', '.mov', '.m4v')
# Margen para buffering / latencia entre que el video llega al cue y el servidor responde.
CUE_UNLOCK_TOLERANCE_SECONDS = 3
_CUE_VIEWS_KEY = 'video_cue_views'

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


# ── Desbloqueo en servidor ───────────────────────────────────────────────────
# El contenido de una pregunta con cue no viaja en el HTML: el navegador lo pide
# cuando la reproducción llega al cue. Como el servidor no ve el reproductor, exige
# al menos que haya pasado el tiempo de video correspondiente desde que el
# estudiante abrió la página (se guarda en la sesión firmada de Flask).

def mark_cue_viewed(key):
    views = flask_session.get(_CUE_VIEWS_KEY) or {}
    if key not in views:
        views[key] = time.time()
        flask_session[_CUE_VIEWS_KEY] = views


def cue_wait_seconds(key, start, question_at):
    """Segundos que faltan para poder entregar la pregunta (0 = ya se puede)."""
    required = max(0, (question_at or 0) - (start or 0) - CUE_UNLOCK_TOLERANCE_SECONDS)
    views = flask_session.get(_CUE_VIEWS_KEY) or {}
    first_view = views.get(key)
    if first_view is None:
        mark_cue_viewed(key)
        return required
    return max(0, int(round(first_view + required - time.time())))


# ── Learning Builder: preguntas dentro de un bloque de video ─────────────────
# configuracion del bloque de video:
#   {"url": ..., "start": 30, "cues": [{"at": 95, "question_block_id": 12, "pause": true}]}

def normalize_learning_video_cues(cfg, lesson_blocks):
    """Valida `start`/`cues` de un bloque de video contra los bloques de su lección."""
    cfg = dict(cfg or {})
    start = parse_timestamp(cfg.get('start')) or 0
    cues_in = cfg.get('cues') or []
    if not isinstance(cues_in, list):
        raise ValueError('Las preguntas del video deben ser una lista.')
    question_ids = {b.id for b in lesson_blocks if b.tipo == 'question'}
    source = parse_video_source(cfg.get('url'))
    cues, used = [], set()
    for cue in cues_in:
        at = parse_timestamp((cue or {}).get('at'))
        try:
            qid = int(cue.get('question_block_id'))
        except (TypeError, ValueError):
            raise ValueError('Cada pregunta del video debe apuntar a un bloque de pregunta.')
        if at is None:
            raise ValueError('Indica en qué minuto aparece cada pregunta del video.')
        if at <= start:
            raise ValueError('Las preguntas deben aparecer después del inicio del video.')
        if qid not in question_ids:
            raise ValueError('La pregunta elegida no es un bloque de pregunta de esta lección.')
        if qid in used:
            raise ValueError('Una misma pregunta no puede aparecer dos veces en el video.')
        used.add(qid)
        cues.append({'at': at, 'question_block_id': qid, 'pause': bool(cue.get('pause', True))})
    if cues and (not source or source['provider'] not in TRACKABLE_PROVIDERS):
        raise ValueError('Solo se pueden poner preguntas dentro de videos de YouTube, Vimeo o archivos MP4/WEBM.')
    cfg['start'] = start
    cfg['cues'] = sorted(cues, key=lambda c: c['at'])
    return cfg


def learning_video_player(cfg, question_blocks):
    """
    Metadatos para el reproductor del estudiante: solo los cues cuyo bloque de
    pregunta sigue existiendo y es visible en la lección.
    """
    source = parse_video_source((cfg or {}).get('url'))
    if not source or source['provider'] not in TRACKABLE_PROVIDERS:
        return None
    start = int(cfg.get('start') or 0)
    cues = [
        {'at': int(c['at']), 'pause': bool(c.get('pause', True)),
         'question_block_id': int(c['question_block_id']),
         'target': f"#block_{int(c['question_block_id'])}", 'label': format_timestamp(c['at'])}
        for c in (cfg.get('cues') or [])
        if int(c.get('question_block_id') or 0) in question_blocks and int(c.get('at') or 0) > start
    ]
    if not cues:
        return None
    return {**source, 'embed_src': embed_src({**source, 'start': start}), 'start': start, 'cues': cues}


def remap_learning_video_cues(cfg, id_map):
    """Tras copiar/importar bloques, apunta los cues a los nuevos IDs (descarta los huérfanos)."""
    if not cfg or not cfg.get('cues'):
        return cfg
    cfg = dict(cfg)
    cfg['cues'] = [
        {**c, 'question_block_id': id_map[c.get('question_block_id')]}
        for c in cfg['cues'] if c.get('question_block_id') in id_map
    ]
    return cfg


def sanitize_question_block_config(cfg):
    """Configuración de una pregunta sin las respuestas correctas (para el estudiante)."""
    cfg = dict(cfg or {})
    cfg['options'] = [{'id': o.get('id'), 'text': o.get('text')} for o in cfg.get('options') or []]
    for key in ('correct_answer_tf', 'short_answers', 'feedback', 'explanation'):
        cfg.pop(key, None)
    cfg['order_items'] = [{'id': i.get('id'), 'text': i.get('text')} for i in cfg.get('order_items') or []]
    cfg['matching_pairs'] = [{'id': p.get('id'), 'left': p.get('left')} for p in cfg.get('matching_pairs') or []]
    cfg.pop('fill_text', None)
    return cfg
