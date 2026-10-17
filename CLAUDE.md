# MyTraining — guía rápida para agentes

Plataforma Flask (SSR con Jinja2) + Socket.IO + SQLite para capacitaciones y exámenes en vivo. Fase: **pre-producción**.

**Autor y responsable del proyecto: Santiago Potes Giraldo** (`potesdev@gmail.com`). En el historial ese correo aparece también como "Manuel Potes" o "SPotes22" por configuraciones locales de git; `.mailmap` los unifica. Los commits de "Claude" son trabajo asistido por IA hecho a pedido del autor.

**Antes de cambiar código, lee `docs/MANUAL_DESARROLLO_Y_DEPURACION_2026-10-15.md` §1 (invariantes).** Resumen:

- Gunicorn con **1 worker** (las salas viven en memoria). No subas `workers` ni instales `eventlet`/`gevent`.
- En `create_app`, los módulos de sockets se importan **antes** de `socketio.init_app()`.
- Sockets: identidad desde `current_user`, nunca del payload; acciones de profesor con `_owns_room`.
- Rutas: verifica rol **y** propiedad del recurso; agrega un test de acceso cruzado (403).
- CSRF siempre activo; `base.html` inyecta el token en formularios y `fetch`.
- No borres en cascada datos con historial (RN-10, RN-13); no versiones `uploads/`, `*.db` ni `.env`.
- **Ningún secreto literal** (ni de ejemplo) en código, tests, `env.example` o docs: usa marcadores `<CLAVE>` o valores generados. Un valor filtrado se agrega como SHA-256 a `LEAKED_SECRET_SHA256`.
- Hay **dos caminos de calificación** (`grade_answer` en vivo y `submit_exam` final): cambia ambos.

Comandos: `pip install -r requirements-dev.txt` · `pre-commit install` (escaneo de secretos con ggshield; requiere `GITGUARDIAN_API_KEY`, nunca lo saltes con `--no-verify`) · `pytest` (debe quedar en verde) · `python run.py` (dev).

Documentación: `docs/SRS_2026-10-15.md` (requisitos y estado) · `docs/SAD_2026-10-15.md` (arquitectura) · `docs/AUDITORIA_PREPRODUCCION.md` (límites medidos) · `docs/MANUAL_ADMINISTRADOR_2026-10-15.md` · `docs/MANUAL_USUARIO_2026-10-15.md`.

Al cerrar un requisito, actualiza su estado en el SRS.
