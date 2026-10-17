"""Subida de archivos (RNF-07): lista blanca, firma del contenido, tope por tipo y nombre aleatorio.

MAX_CONTENT_LENGTH (MAX_UPLOAD_MB) sigue siendo el tope por petición; aquí se aplica
el de cada tipo (UPLOAD_*_MB). Antes cualquier archivo permitido podía pesar 50 MB,
incluidas las imágenes, y bastaba con renombrar un archivo para cambiar su tipo.
"""
import os
import uuid

from flask import current_app

# extensión -> tipo
KINDS = {
    'jpg': 'image', 'jpeg': 'image', 'png': 'image', 'webp': 'image', 'gif': 'image',
    'mp4': 'video', 'webm': 'video',
    'mp3': 'audio',
    'pdf': 'document',
}


class UploadError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _matches_signature(ext, head):
    """Comprueba los primeros bytes: un .png debe ser un PNG, no un HTML renombrado."""
    if ext in ('jpg', 'jpeg'):
        return head.startswith(b'\xff\xd8\xff')
    if ext == 'png':
        return head.startswith(b'\x89PNG\r\n\x1a\n')
    if ext == 'gif':
        return head.startswith((b'GIF87a', b'GIF89a'))
    if ext == 'webp':
        return head[:4] == b'RIFF' and head[8:12] == b'WEBP'
    if ext == 'mp4':
        return head[4:8] == b'ftyp'
    if ext == 'webm':
        return head.startswith(b'\x1a\x45\xdf\xa3')
    if ext == 'mp3':
        return head.startswith(b'ID3') or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)
    if ext == 'pdf':
        return head.startswith(b'%PDF-')
    return False


def limit_bytes(kind):
    return current_app.config['UPLOAD_LIMITS_MB'][kind] * 1024 * 1024


def file_size(file):
    stream = file.stream
    pos = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(pos)
    return size


def validate(file, allowed_kinds):
    """Devuelve (extensión, tipo) o lanza UploadError con un mensaje para el usuario."""
    if not file or not file.filename or '.' not in file.filename:
        raise UploadError('No se seleccionó ningún archivo.')
    ext = file.filename.rsplit('.', 1)[1].lower()
    kind = KINDS.get(ext)
    if kind not in allowed_kinds:
        valid = ', '.join(sorted(e for e, k in KINDS.items() if k in allowed_kinds))
        raise UploadError(f'Tipo de archivo no permitido. Tipos válidos: {valid}.')
    size = file_size(file)
    if size == 0:
        raise UploadError('El archivo está vacío.')
    if size > limit_bytes(kind):
        mb = current_app.config['UPLOAD_LIMITS_MB'][kind]
        raise UploadError(f'Archivo demasiado grande. Límite para este tipo: {mb} MB.', 413)
    head = file.stream.read(16)
    file.stream.seek(0)
    if not _matches_signature(ext, head):
        raise UploadError('El contenido del archivo no corresponde a su extensión.')
    return ext, kind


def save(file, allowed_kinds, prefix, subdir='learning'):
    """Valida y guarda en static/uploads/<subdir>/ con nombre aleatorio. Devuelve la ruta relativa a static."""
    ext, _kind = validate(file, allowed_kinds)
    fname = f'{prefix}_{uuid.uuid4().hex}.{ext}'
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', subdir)
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, fname))
    return f'uploads/{subdir}/{fname}'


def check_import_size(file):
    """Archivos de importación (CSV/Excel/JSON): solo el tope de tamaño; el formato lo valida quien los lee."""
    size = file_size(file)
    if size > limit_bytes('import'):
        mb = current_app.config['UPLOAD_LIMITS_MB']['import']
        raise UploadError(f'Archivo demasiado grande. Límite para importar: {mb} MB.', 413)
