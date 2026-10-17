# Manual de desarrollo, depuración y modificación de código — MyTraining

**Fecha:** 15 de octubre de 2026
**Para:** desarrolladores y agentes de código (Claude Code u otros) que van a leer, depurar o cambiar este repositorio.
**Relacionados:** [SRS](SRS_2026-10-15.md) (qué debe hacer) · [Arquitectura](SAD_2026-10-15.md) (por qué está así) · [Auditoría](AUDITORIA_PREPRODUCCION.md) (qué se corrigió y los límites medidos)

> **Para agentes:** lee primero §1 completo. Son las reglas cuya violación rompe producción o reabre un hueco de seguridad ya cerrado. El resto del manual es referencia: ve a la sección que necesites.

---

## Contenido

1. [Invariantes: lo que no se rompe](#1-invariantes-lo-que-no-se-rompe)
2. [Entorno y comandos](#2-entorno-y-comandos)
3. [Mapa del código](#3-mapa-del-código)
4. [Flujos principales](#4-flujos-principales)
5. [Recetas de modificación](#5-recetas-de-modificación)
6. [Depuración: síntoma → causa → dónde mirar](#6-depuración-síntoma--causa--dónde-mirar)
7. [Pruebas](#7-pruebas)
8. [Deuda técnica y trampas conocidas](#8-deuda-técnica-y-trampas-conocidas)
9. [Flujo de trabajo para agentes](#9-flujo-de-trabajo-para-agentes)

---

## 1. Invariantes: lo que no se rompe

| # | Invariante | Por qué | Dónde se aplica |
|---|---|---|---|
| I-1 | **Gunicorn con 1 worker.** No subas `workers` | El estado de las salas vive en memoria (`SessionManager`); con 2 procesos cada uno ve salas distintas | `gunicorn.conf.py` |
| I-2 | **No instales `eventlet` ni `gevent`** | Flask-SocketIO elige el modo async automáticamente (eventlet → gevent → threading). Instalar uno cambia el modo en silencio y rompe la configuración `gthread` | `requirements.txt` |
| I-3 | **Los módulos de sockets se importan antes de `socketio.init_app()`** | Si se importan después, solo la primera app creada en el proceso recibe los handlers (tests y recargas quedan sin eventos) | `app/__init__.py:create_app` |
| I-4 | **En sockets, la identidad sale de `current_user`, nunca del payload** | Antes un estudiante podía mandar el `student_id` de otro | `app/realtime/sockets.py` |
| I-5 | **Toda acción de profesor por socket verifica la propiedad** con `_owns_room` / `_owns_db_session` | Evita que cualquiera pause o inicie salas ajenas | `app/realtime/sockets.py` |
| I-6 | **Toda ruta que muestre o cambie datos de un examen, sala, intento o capacitación verifica propiedad**, no solo el rol. En la API del editor de capacitaciones usa `_can_edit_learning` | Varios IDOR cerrados (resultados, lobby, cierre; el 17 oct, toda la API `/learning/api/*` del editor, que cualquier usuario podía modificar) | `app/blueprints/*/routes.py` |
| I-7 | **No desactives CSRF.** Los POST nuevos funcionan solos si la plantilla extiende `base.html` (inyección automática) | RNF-03 | `app/templates/base.html` |
| I-8 | **Variables de servidor dentro de `<script>` van con `\|tojson`** | Autoescape HTML no basta en contexto JS | Plantillas |
| I-14 | **Toda URL que el usuario escribe y termina en un `src`/`href` pasa por una lista blanca de esquemas** (`video_cues.is_safe_video_url`: solo `http(s)://` o rutas `/…`) | `javascript:`/`data:` en un `<iframe src>` es XSS almacenado | `app/services/video_cues.py` |
| I-9 | **No borres en cascada datos con historial**: preguntas o bancos con respuestas, exámenes con intentos, profesores con contenido | RN-10 y RN-13, y SQLite reutiliza ids (§8) | `questions/routes.py`, `exams/routes.py`, `admin/routes.py` |
| I-10 | **No versiones datos de usuario**: `app/static/uploads/`, `*.db`, `.env` | Fuga de datos | `.gitignore` |
| I-11 | **Nada de secretos por defecto fuera de desarrollo.** Si agregas un secreto, exígelo en `validate_config`; si un valor llegó a publicarse, agrega su SHA-256 a `LEAKED_SECRET_SHA256` | `validate_config` bloquea el arranque inseguro | `app/config.py` |
| I-13 | **Ningún secreto literal en el repositorio**: ni contraseñas de ejemplo en código, tests, `env.example` o documentación. Usa marcadores (`<CLAVE>`), valores generados (`secrets.token_urlsafe`) o hashes, como `LEAKED_SECRET_SHA256` | GitGuardian marcó usuario + contraseña fijos en `app/__init__.py` y en un test (incidentes del 16 oct 2026). En tests usa `TEST_PASSWORD` de `tests/support.py` | Todo el repo |
| I-12 | **Código portable a PostgreSQL**: nada de SQL específico de SQLite fuera de `extensions.py` y `ensure_schema`; respeta las llaves foráneas aunque SQLite no las aplique | La migración prevista debe ser un cambio de `DATABASE_URL` | Modelos y servicios |

---

## 2. Entorno y comandos

### 2.1 Puesta en marcha

```bash
python3.13 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt   # app + pytest + pre-commit
pre-commit install                     # escaneo de secretos antes de commit y push (§2.4)
cp env.example .env          # APP_ENV=development por defecto
python run.py                # http://127.0.0.1:5000 , debug activo, datos demo
```

En desarrollo se crean el superusuario (correo `SUPERUSER_EMAIL`) y un profesor demo (`profesor@capacitacion.com`) con un banco y un examen. **No hay contraseñas fijas:**

- si `SUPERUSER_PASSWORD` o `DEMO_INSTRUCTOR_PASSWORD` están vacías en tu `.env`, la app genera contraseñas aleatorias y las imprime **una sola vez** en la consola al crear las cuentas;
- si las pierdes, borra `instance/database.db` o restablece la clave con la consola (§2.2);
- nunca escribas credenciales reales ni de ejemplo en código, tests o documentación (I-13).

La base queda en `instance/database.db`: las rutas `sqlite:///` relativas se resuelven contra `instance/`.

### 2.2 Comandos frecuentes

| Tarea | Comando |
|---|---|
| Todos los tests | `pytest` (116 tests, ~70 s) |
| Un archivo / un test | `pytest tests/test_preproduction_hardening.py -k socket -s` |
| Arrancar como pre-producción en local | `APP_ENV=preproduction SESSION_COOKIE_SECURE=0 SECRET_KEY=$(python -c 'import secrets;print(secrets.token_hex(32))') SUPERUSER_PASSWORD="$(python -c 'import secrets;print(secrets.token_urlsafe(16))')" gunicorn -c gunicorn.conf.py wsgi:app` |
| Salud | `curl localhost:8080/healthz` |
| Prueba de carga | `scripts/loadtest/` (instrucciones en la Auditoría §6) |
| Respaldo | `python scripts/backup_sqlite.py instance/database.db backups/` |
| Consola con la app cargada | `python -i -c "from app import create_app; from app.extensions import db; from app.models import *; app=create_app(); ctx=app.app_context(); ctx.push()"` |

### 2.3 Navegador real (Playwright)

En los contenedores de Claude Code hay Chromium en `/opt/pw-browsers` y Playwright en Node (`/opt/node22/lib/node_modules/playwright`). Úsalo para verificar cambios de JS, de CSRF o de sockets que los tests de Flask no ejecutan. No ejecutes `playwright install`.

### 2.4 Escaneo de secretos (GitGuardian / ggshield)

El repositorio revisa secretos en dos puntos, ambos con ggshield 1.56.0 y la misma configuración (`.gitguardian.yaml`):

| Dónde | Archivo | Cuándo corre | Qué revisa |
|---|---|---|---|
| Tu máquina | `.pre-commit-config.yaml` | Al hacer `git commit` y `git push` | Lo que vas a commitear y los commits que vas a subir |
| GitHub Actions | `.github/workflows/secret-scan.yml` | En cada push y pull request | Los commits nuevos del push o del PR |

**Puesta en marcha (una vez por clon):**

```bash
git checkout main && git pull         # los archivos deben existir en tu rama
python -m venv venv && source venv/bin/activate   # Windows Git Bash: source venv/Scripts/activate
pip install -r requirements-dev.txt   # instala app, pytest, pre-commit y ggshield
pre-commit install                    # instala los hooks pre-commit y pre-push
ggshield auth login                   # o: export GITGUARDIAN_API_KEY=<CLAVE>
```

**Sin clave de API el hook falla y bloquea el commit**: es intencional.

**Si sale `pre-commit: command not found` o `ggshield: command not found`:**

- El entorno virtual no está activo: vuelve a ejecutar `source venv/bin/activate` (en Windows Git Bash, `source venv/Scripts/activate`); el prompt debe empezar por `(venv)`.
- `requirements-dev.txt` no existe en tu rama: revisa con `ls requirements-dev.txt` y haz `git pull`.
- Instalaste sin entorno virtual: pip dejó los programas en `~/.local/bin`, que puede no estar en el `PATH`. Úsalos como módulo: `python -m pre_commit install` y `python -m ggshield auth login`.

**Si el escaneo detecta algo:**

1. **No lo silencies.** Quita el valor del archivo y sustitúyelo por un marcador `<CLAVE>` o por una variable de entorno (invariante I-13).
2. Si el valor era real, **rótalo**: cámbialo en el servicio correspondiente. Quitarlo del archivo no basta, porque puede seguir en el historial.
3. Si ya se publicó y es un secreto de la app, agrega su SHA-256 a `LEAKED_SECRET_SHA256` en `app/config.py`.
4. Solo si es un falso positivo comprobado, agrega en `.gitguardian.yaml` → `ignored_matches` el **SHA-256 que muestra ggshield** (nunca el valor), con un comentario que explique por qué.

**Escanear todo el historial** (por ejemplo, tras un incidente): `ggshield secret scan repo .`

> **Agentes:** en entornos sin `GITGUARDIAN_API_KEY` el hook no se puede ejecutar. No lo desinstales ni uses `--no-verify` / `SKIP=` para saltarlo. Deja que el CI haga el escaneo y avisa al usuario de que no se ejecutó en local.

---

## 3. Mapa del código

```
run.py                 Servidor de desarrollo (debug solo con APP_ENV=development)
wsgi.py                Entrada de gunicorn
gunicorn.conf.py       1 worker gthread, 64 hilos, timeout 0 (websockets)
Dockerfile             Imagen pre-producción (python:3.13-slim, usuario 10001, /data)
app/
  __init__.py          create_app(): config → validate_config → ProxyFix → db/csrf/login
                       → import sockets → socketio.init_app → init_db → blueprints
                       → cabeceras de seguridad, errores 413 y CSRF, /healthz
                       ensure_schema(): ALTER TABLE ADD COLUMN para bases antiguas
  config.py            Config por entorno (APP_ENV), límites, validate_config()
  extensions.py        db, login_manager, socketio, csrf + PRAGMAs de SQLite (WAL)
  models.py            Todos los modelos (ver SAD §7)
  blueprints/
    auth/              /, /login, /register, /logout, /student/join; bloqueo de login
    admin/             /admin/dashboard, crear y eliminar profesores
    questions/         Bancos, preguntas, importación Excel/CSV, question_in_use (RN-13)
    exams/             Constructor, biblioteca, clases, salas, submit_exam, reportes, Excel
    learning/          Capacitaciones, API de módulos/lecciones/bloques, subida de archivos
    polls/             Encuestas en vivo (routes + sockets)
    media/             /media/video/<archivo>
    exams/events.py    ⚠ Código muerto: no se importa y no funciona. No lo uses (§8)
  realtime/
    manager.py         SessionManager: salas en memoria, índice sid → sala
    session.py         dataclasses ExamSession / StudentSession (estado en memoria)
    sockets.py         Handlers Socket.IO de salas (autorización, LiveAnswer)
    events.py          Nombres de eventos
  modes/               Estrategias por modo de examen (instant_feedback, open_navigation,
                       teacher_paced) registradas en registry
  services/
    exam_content.py    normalize_room_code, socket_room, serialize_question,
                       load_session_questions, grade_answer (calificación en vivo),
                       create_session_question_snapshots
    exam_builder.py    Guardar, duplicar y validar preguntas; agregar al examen
    learning_service.py   Crear, exportar e importar capacitaciones
    remediation_service.py Curso de refuerzo (PASSING_SCORE = 40)
    audit.py           RF-030: audit.record(acción, entidad, id, **detalles) antes del commit
    grading.py         RF-027/RN-08: calificación manual de abiertas y recálculo del intento
    mailer.py          SMTP (MAIL_*); sin servidor imprime en consola en desarrollo
    password_reset.py  RF-028: token firmado de un solo uso (ligado al hash de la contraseña)
    personal_data.py   RF-029: exportar y anonimizar los datos de un usuario
    video_cues.py      RF-011: URL → proveedor (YouTube/Vimeo/archivo) y validación de esquema,
                       metadatos JSON del cue (questions.video_metadata), tiempos mm:ss,
                       desbloqueo en servidor (cue_wait_seconds) y cues de bloques de video
  templates/           Jinja2; base.html = diseño + inyección CSRF + navegación por rol
  static/js/           instructor_lobby.js, learning_builder.js, learning_student.js,
                       video_cues.js (sigue la reproducción y revela/pide la pregunta en su minuto)
scripts/               backup_sqlite.py, loadtest/
tests/                 pytest (ver §7)
docs/                  SRS, SAD, Auditoría, manuales
```

### 3.1 Roles

`users.role` vale `superuser`, `admin`, `instructor` o `student`. El patrón en las rutas:

```python
if current_user.role != 'instructor' or exam.instructor_id != current_user.id:
    return 'Acceso denegado', 403
```

Los admin/superuser pasan donde la ruta lo permite explícitamente (`current_user.role in ['superuser', 'admin']`).

---

## 4. Flujos principales

### 4.1 Ciclo de vida de una sala

```
Profesor: POST /instructor/session/start/<exam_id>  (o configure_session)
  → ExamSession(status='waiting', session_code=6 chars)
  → create_session_question_snapshots(sesión)        # textos congelados
  → redirect /instructor/lobby/<id>   → socket 'teacher_join'  (exige dueño)

Estudiante: /student/join (nombre + código) → crea User invitado → login_user
  → /exam/presentar/<session_id> → socket 'student_join' (identidad = current_user)
  → SessionManager.add_student; 'saved_progress' si hay LiveAnswer

Profesor: 'start_exam_session' → status 'in_progress' → modo.on_start → 'exam_started'
Estudiante: 'answer_submitted' → upsert LiveAnswer → modo.on_answer → 'feedback' / 'student_answered'
Profesor: 'pause_exam' / 'resume_exam' / 'next_question' (teacher_paced)
Estudiante: POST /exam/submit/<id> → califica → ExamAttempt + StudentAnswer → /resultados/<attempt>
Cierre: POST /instructor/session/<id>/finish | /exam/close/<id> | expected_students alcanzado
  → status 'FINISHED' / 'finished' → maybe_generate_remediation
```

### 4.2 Dos caminos de calificación ⚠

| Camino | Función | Cuándo | Qué califica |
|---|---|---|---|
| En vivo | `services/exam_content.py:grade_answer` | Cada `answer_submitted` (feedback inmediato) | **Solo** opción múltiple, V/F y video; el resto siempre es "incorrecta" en vivo |
| Final | `blueprints/exams/routes.py:submit_exam` | Al enviar el examen | Todos los tipos; la nota que se guarda |

**Preguntas pendientes (RN-14):** "respondida" se define en dos sitios que deben coincidir: `isStepAnswered` (JS, `presentar_examen.html`) y `unanswered_question_ids` (servidor, `exams/routes.py`). Si agregas un tipo de pregunta, actualiza ambos.

Si cambias reglas de calificación, **cambia los dos** o el feedback en vivo contradirá la nota final. Ambos usan **el banco vivo**, no la instantánea (§8).

### 4.3 Estado en memoria y persistencia

| Dato | Dónde vive | Sobrevive a un reinicio |
|---|---|---|
| Quién está conectado, pregunta actual, respuestas de la sesión en vivo | `SessionManager.sessions` (memoria) | No |
| Lista de preguntas de la sala en memoria | `load_session_questions` → `exam.questions` **vivo**, cacheado al primer acceso | No (se recarga) |
| Última respuesta por estudiante y pregunta | Tabla `live_answers` | Sí |
| Textos congelados | `session_question_snapshots` | Sí |
| Intento y nota | `exam_attempts`, `student_answers` | Sí |
| Bloqueo de login | `_failed_logins` en `auth/routes.py` (memoria) | No |

### 4.4 Estados de sala

Se escriben con varias grafías según la ruta: `waiting`, `READY`, `in_progress`, `RUNNING`, `PAUSED`, `paused`, `finished`, `FINISHED`, `closed`, `CLOSED`. **Compara siempre contra el conjunto completo**, como hace `exam_reports`, o normaliza. Unificarlas es deuda pendiente (§8).

---

## 5. Recetas de modificación

### 5.1 Agregar una ruta HTTP

1. Ponla en el blueprint que corresponda, con `@login_required`.
2. Verifica el rol **y** la propiedad del recurso (I-6). Devuelve 403, no un redirect silencioso, cuando el acceso es indebido.
3. Si la plantilla extiende `base.html`, el CSRF ya funciona en formularios y `fetch`. Para JSON de otro cliente envía la cabecera `X-CSRFToken`.
4. Agrega un test de acceso cruzado: otro profesor u otro estudiante → 403.

### 5.2 Agregar un evento de Socket.IO

1. Define el nombre en `realtime/events.py` y el handler en `realtime/sockets.py` (o en el módulo de sockets del blueprint, importado en `create_app` **antes** de `init_app`, I-3).
2. Identidad: `current_user`. Para acciones de profesor: `if not _owns_room(room_code): emit(events.ERROR, ...); return`.
3. Emite a la sala con `socket_room(room_code)`, al profesor con `session.teacher_sid` o `f"teacher_{instructor_id}"`, y a un estudiante con su `sid`.
4. Prueba con `socketio.test_client(app, flask_test_client=client)` (ejemplo en `tests/test_preproduction_hardening.py`).

### 5.3 Agregar un tipo de pregunta

Toca **todos** estos puntos; si falta uno, el tipo se guarda pero no se presenta o no se califica:

| Paso | Archivo |
|---|---|
| Guardado y validación | `services/exam_builder.py:save_question_payload` (y `QUESTION_TYPES_WITH_OPTIONS` si usa opciones) |
| Formulario | `templates/_question_form_fields.html` y selects de `mis_preguntas.html` / `exam_builder.html` |
| Etiqueta legible | `SessionQuestionSnapshot.type_label` y `correct_answer_display` en `models.py` |
| Instantánea | `services/exam_content.py:create_session_question_snapshots` |
| Serialización para sockets | `services/exam_content.py:serialize_question` |
| Presentación | `templates/presentar_examen.html` (HTML y JS) y `presentar_examen` en `exams/routes.py` |
| Calificación final | `exams/routes.py:submit_exam` |
| Pendientes (RN-14) | `isStepAnswered` en `presentar_examen.html` y `unanswered_question_ids` en `exams/routes.py` |
| Calificación en vivo | `services/exam_content.py:grade_answer` |
| Reporte | `templates/session_report.html` |
| Importación | `questions/routes.py:import_questions_excel` |
| Refuerzo | `services/remediation_service.py` (`_build_quiz_content`) |
| Tests | Crear, presentar, enviar y verificar el puntaje |

### 5.4 Agregar un modo de examen

1. Crea `app/modes/<nombre>.py` con una clase que herede de `ExamMode`, con `name = '<nombre>'` y los 5 métodos, decorada con `@registry.register`.
2. Impórtala en `app/modes/__init__.py`.
3. Agrega la `<option>` en el select **Modo de Evaluación** de `exam_builder.html`.
4. Un nombre desconocido cae en `instant_feedback` (`registry.get`).

### 5.5 Agregar una columna a un modelo

Mientras no exista Alembic:

1. Agrega el `db.Column` en `models.py`.
2. Agrega una línea `_add_column_if_missing(conn, <cols>, '<tabla>', '<columna>', '<DDL>')` en `ensure_schema()`. Las bases existentes no se recrean.
3. Usa DDL portable (`INTEGER`, `VARCHAR(n)`, `TEXT`, `FLOAT`, `BOOLEAN DEFAULT 0`) y no `NOT NULL` sin default.
4. Una tabla nueva la crea sola `db.create_all()`. Impórtala en `init_db` si no se importa en otro lado.

### 5.6 Agregar una variable de configuración

1. Agrégala en `Config` (`app/config.py`) con `_env_bool` / `_env_int` y un default seguro por entorno.
2. Si es un secreto, súmala a `INSECURE_DEFAULTS`.
3. Documéntala en `env.example` y en el Manual de administrador §3.

### 5.7 Agregar un tipo de bloque de capacitación

- Render del editor: `static/js/learning_builder.js`.
- Render del estudiante: `static/js/learning_student.js` (`blk.tipo === '<tipo>'`).
- Valores por defecto: `services/learning_service.py`.
- La configuración se guarda en `Block.configuracion` (JSON): no hacen falta columnas nuevas.
- Si el bloque sube archivos, usa `/learning/api/upload` (solo instructores, `MAX_CONTENT_LENGTH`).
- Toda ruta nueva de `/learning/api/*` que edite contenido llama a `_can_edit_learning(...)` y devuelve `_forbidden()` (I-6). Si el bloque guarda una URL que se renderiza, valídala con `is_safe_video_url` o equivalente (I-14).

### 5.8 Preguntas durante un video (RF-011)

Flujo: el profesor guarda `video_url` + tiempos → `exam_builder.save_video_cue` arma `questions.video_metadata` (JSON con proveedor, `start`, `question_at`, `pause_on_question`) y sincroniza `video_timestamp` → la instantánea de la sala copia `video_metadata` → `presentar_examen.html` dibuja el reproductor **sin** el enunciado → `video_cues.js` sigue el tiempo y, al llegar al cue, pide `GET /exam/presentar/<sala>/video-question/<pregunta>` → el servidor responde 425 con `retry_after` si aún no pasó ese tiempo desde que el estudiante abrió la página (marca guardada en la sesión firmada), o el HTML de la pregunta.

En capacitaciones el equivalente es `Block.configuracion` del bloque de video (`start`, `cues: [{at, question_block_id, pause}]`), validado por `normalize_learning_video_cues` y servido por `GET /learning/api/block/<id>/video-question` sin las respuestas correctas (`sanitize_question_block_config`).

Para cambiarlo: los tiempos y la validación están en `services/video_cues.py`; la lógica del reproductor en `static/js/video_cues.js`; los tests en `tests/test_video_cues.py`.


### 5.9 Registrar una acción en la auditoría (RF-030)

Toda acción que cree, edite, archive o borre exámenes, usuarios o resultados se registra:

```python
from app.services import audit
audit.record('exam.archive', 'exam', exam.id, title=exam.title)   # antes del commit
db.session.commit()
```

- Nombres de acción `entidad.verbo` (`exam.create`, `user.anonymize`, `answer.grade`…), para poder filtrar por prefijo en `/admin/audit`.
- En los detalles **no pongas correos, nombres ni contraseñas** (minimización): basta el id.
- Si la ruta no hace commit (una descarga), usa `audit.record(..., commit=True)`.

---

## 6. Depuración: síntoma → causa → dónde mirar

| Síntoma | Causa probable | Dónde mirar / qué hacer |
|---|---|---|
| Los eventos de socket no llegan en tests (sin respuesta, sin error) | Sockets importados después de `init_app` (I-3) | Orden de imports en `create_app` |
| `exam_error: Profesor no autorizado` | El usuario del socket no es el dueño, o no hay sesión | Cookie de sesión del cliente; `_owns_room` |
| `exam_error: Estudiante no autenticado` | El socket conectó sin cookie de sesión | En tests usa `flask_test_client=` al crear el `test_client` de socket |
| Un POST redirige con "La página caducó…" | Falta el token CSRF | La plantilla debe extender `base.html`; los clientes externos mandan `X-CSRFToken`; en tests, `WTF_CSRF_ENABLED=False` o token real |
| Test de login devuelve 429 inesperado | El bloqueo en memoria persiste entre tests | `auth_routes._failed_logins.clear()` en el fixture |
| Un test ve salas de otro test | `session_manager` es global | `session_manager.sessions.pop(code, None)` al final |
| `database is locked` | Más escrituras simultáneas de las que aguanta un proceso | Ver Auditoría §4. Con WAL y `busy_timeout=30000` no debería aparecer bajo carga normal |
| La app no arranca: `Configuración insegura…` | `APP_ENV` ≠ development con secretos de ejemplo | `validate_config`; para pruebas locales usa `APP_ENV=development` |
| El login no persiste en local con gunicorn | Cookie `Secure` sobre http | `SESSION_COOKIE_SECURE=0` en local |
| Un reporte no lista una sala finalizada | Grafía de estado no contemplada | §4.4 |
| El feedback en vivo dice "incorrecta" pero la nota final dice correcta | Tipo no soportado por `grade_answer` | §4.2 |
| Un profesor nuevo ve exámenes que no creó | Se borró un usuario con contenido y SQLite reutilizó el id | Ya bloqueado en el admin; no borres usuarios por consola sin revisar sus dependencias |
| Cambios del banco aparecen en una sala abierta | La sala en memoria y la calificación usan el banco vivo | §8 |
| `LegacyAPIWarning: Query.get()` | API legado de SQLAlchemy 2.0 | Inofensivo; en código nuevo usa `db.session.get(Model, id)` |

**Herramientas útiles:**

- Logs de sala: el código usa `print` con prefijos `[JOIN]`, `[START]`, `[PAUSE]`, `[ALERT]`, `[WARN]`, `[ERROR]`. Fíltralos con `docker logs mytraining 2>&1 | grep '\[WARN\]'`.
- Inspeccionar una sala en memoria (consola, §2.2): `from app.realtime.manager import session_manager; session_manager.sessions['ABC123'].__dict__`.
- Respuestas guardadas: `LiveAnswer.query.filter_by(session_id=..., student_id=...).all()`.

---

## 7. Pruebas

### 7.1 Estructura

| Archivo | Cubre |
|---|---|
| `test_auth_and_live_counters.py` | Registro, login, contadores de salas activas |
| `test_socrative_module.py` | Constructor, bancos, clases, papelera, autorización de salas |
| `test_session_report_and_snapshots.py` | Instantáneas e integridad del reporte |
| `test_remediation_service.py` | Curso de refuerzo y no duplicación |
| `test_audit_log.py` | RF-030: eventos registrados, vista solo para admin, sin correos en el registro |
| `test_manual_grading.py` | RF-027/RN-08: abiertas fuera de la nota hasta calificarlas, recálculo, permisos |
| `test_password_reset.py` | RF-028: flujo completo, un solo uso, caducidad, manipulación, límite de solicitudes |
| `test_personal_data.py` | RF-029: ver/corregir, exportar solo lo propio, anonimizar, restricciones |
| `test_pending_questions.py` | RN-14: envío rechazado con pendientes (incluidas preguntas de video no vistas), respuestas guardadas por socket, excepción del modo guiado |
| `test_video_cues.py` | RF-011: tiempos y URLs de video, entrega diferida de preguntas, cues en capacitaciones, permisos del editor de capacitaciones |
| `test_preproduction_hardening.py` | Seguridad y reglas: IDOR, sockets, CSRF, bloqueo de login, RN-09, RN-10, RN-12, RN-13, borrado de profesores, `validate_config`, `/healthz` |

### 7.2 Patrón de fixture

```python
@pytest.fixture()
def app_ctx(tmp_path):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'t.db'}"   # ANTES de create_app
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)          # CSRF se prueba aparte
    with app.app_context():
        db.drop_all(); db.create_all()                               # borra también el superusuario
        ...                                                          # crea tus usuarios
        yield app, ...
```

- **Contraseñas de test con 8 caracteres o más.**
- Para probar CSRF, actívalo en el test y toma el token del `<meta name="csrf-token">` de cualquier página.
- Sockets: `socketio.test_client(app, flask_test_client=client)` después de hacer login con `client`.

### 7.3 Qué debe tener todo cambio

- Un test del camino feliz.
- **Un test de acceso cruzado** si la ruta o el evento toca datos de otro usuario.
- `pytest` completo en verde antes de hacer commit.

---

## 8. Deuda técnica y trampas conocidas

| Tema | Situación | Impacto | Referencia |
|---|---|---|---|
| Calificación sobre el banco vivo | `submit_exam` y `grade_answer` leen `Question`/`QuestionOption` actuales, no la instantánea | Editar la clave con la sala abierta cambia la nota de los envíos posteriores | RF-019 / RN-06 (Parcial) |
| Dos caminos de calificación | §4.2 | Inconsistencias en el feedback en vivo | — |
| `submit_exam` lento | Una consulta por opción y llamada a instantáneas en cada envío | Tope de ~25 envíos/s; optimizarlo es la mejora más barata de capacidad | Auditoría §5 |
| Estados con varias grafías | §4.4 | Filtros incompletos | SRS §12 |
| `ensure_schema` en vez de Alembic | Solo agrega columnas | Bloquea la migración limpia a PostgreSQL | RNF-13 |
| Llaves foráneas no aplicadas en SQLite | Borrados que en PostgreSQL fallarían | Probar contra PostgreSQL antes de migrar | I-12 |
| SQLite reutiliza ids | El último id borrado se reasigna | Herencia de datos si se borra un usuario con contenido (ya bloqueado en el panel) | Auditoría S-16 |
| Desbloqueo de preguntas de video por tiempo de reloj | El servidor mide el tiempo desde que se abrió la página, no la reproducción real; con la tolerancia de 3 s, un estudiante que espera sin reproducir también recibe la pregunta | Aceptado: evita leerla antes, no garantiza haber visto el video | `CUE_UNLOCK_TOLERANCE_SECONDS` |
| `exams/events.py` | Código muerto que referencia un `socketio` inexistente | Confusión | Borrar en una limpieza |
| Alertas antifraude | Existe el handler `anti_cheat_alert`, pero ningún cliente lo emite | El panel del lobby queda vacío | RF-018 |
| `PASSING_SCORE = 40` fijo | No usa `exam.passing_score` | Umbrales inconsistentes | RN-07 |
| Invitados sin limpieza | Cada `/student/join` crea un `User` | Crecimiento de la tabla; requisito legal RL-10 | — |
| Logging con `print` | Sin niveles ni estructura | RNF-17 | — |
| Bloqueo de login y salas en memoria | No sobreviven a reinicios y no escalan a varios workers | Llevarlos a Redis en producción | RNF-06, RNF-14 |
| CDN externos | Bootstrap y Socket.IO cliente se cargan de jsDelivr / cdn.socket.io | Dependencia externa y bloqueo de una futura CSP | — |

---

## 9. Flujo de trabajo para agentes

**Antes de cambiar código:**

1. Lee §1 y la fila del SRS del requisito que vas a tocar.
2. Ubica los archivos con §3 y, para tipos de pregunta, la lista de §5.3.
3. Corre `pytest` para tener una línea base.

**Mientras cambias:**

- Cambios mínimos y en el estilo del archivo: comentarios en español, el mismo patrón de autorización y sin abstracciones nuevas si no hacen falta.
- No toques `gunicorn.conf.py` (workers), el orden de imports de `create_app` ni la inyección CSRF de `base.html` salvo que esa sea la tarea.
- Si agregas una dependencia, fíjala con versión exacta en `requirements.txt`.

**Antes de hacer commit:**

- [ ] `pytest` en verde, con tests nuevos para lo cambiado (incluido el acceso cruzado).
- [ ] Para cambios de JS, CSRF o sockets: verificación en navegador real (§2.3).
- [ ] Sin archivos de `uploads/`, `.db` ni `.env` en el commit, ni secretos literales; el hook de ggshield (§2.4) pasa, o el CI lo revisará si no hay clave local.
- [ ] Si cerraste o cambiaste un requisito, actualiza su estado en el SRS (y los conteos de §1.6).
- [ ] Si cambiaste un límite, una variable o el despliegue, actualiza el Manual de administrador y `env.example`.
- [ ] Mensaje de commit que diga **qué** y **por qué**, citando el requisito (RF-, RN-, RNF-).

**Nunca:**

- Saltar, desactivar o marcar como `skip` un test para poner el CI en verde.
- Desactivar CSRF o la verificación de propiedad "temporalmente".
- Subir `workers` o instalar `eventlet`/`gevent` sin el plan de Redis del SAD §11.2.
