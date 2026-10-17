# Auditoría pre-producción — MyTraining

**Fecha:** 16 de octubre de 2026, actualizada el 17 de octubre (requisitos no funcionales) · **Rama:** `ccr-58c67f87-ovb3cp` · **Base:** SAD V2, SRS V2 y SRS V3 + Auditoría (29 sep 2026)

Este documento resume qué se revisó, qué se corrigió en el código, qué límites tiene hoy la plataforma (medidos, no estimados) y cuándo conviene pagar PostgreSQL.

---

## 1. Resumen

| | Antes | Ahora |
|---|---|---|
| Hallazgos de seguridad de la Fase 1 (SRS V3 §9) | 6 abiertos | **6 cerrados** |
| Otros hallazgos de seguridad encontrados en esta auditoría | — | 21 cerrados |
| Tests automatizados | 19 | **176** (todos pasan), cobertura 82 % |
| Integración continua | no existía | GitHub Actions: tests en SQLite y en PostgreSQL 16, cobertura mínima 70 %, escaneo de secretos |
| Prueba de carga | no existía | envío de examen y eventos de sala con 100 y 200 clientes (§4) |
| Arranque de producción | `debug=True` en `0.0.0.0` | Gunicorn, 1 worker, `/healthz`, Dockerfile |
| Esquema de la base | `create_all()` + `ensure_schema()` | Migraciones de Alembic, aplicadas al arrancar |
| Respaldo de la base | no existía | `scripts/backup_sqlite.py` con retención y simulacro de restauración automatizado |
| Logs | `print()` con nombres de estudiantes | JSON por línea, nivel configurable, sin datos personales |
| Accesibilidad | sin medir (200+ fallos de contraste y etiquetas) | 0 violaciones WCAG 2.1 AA en 22 páginas (axe-core) |

**Conclusión:** la app puede salir a pre-producción sobre **SQLite en un solo contenedor**, con un tope operativo de **~100 estudiantes enviando a la vez** y **~220 conectados por instancia** (§4). PostgreSQL no hace falta todavía. Lo que sí bloquea el uso con datos personales reales es la parte legal (política de tratamiento y autorización, SRS V3 §7), no la base de datos.

---

## 2. Hallazgos de seguridad corregidos

### 2.1 Fase 1 del SRS V3 (bloqueantes)

| # | Hallazgo | Corrección | Archivo |
|---|---|---|---|
| S-01 | Cualquiera podía registrarse como instructor (RN-09) | El selector de rol solo aparece si `ALLOW_INSTRUCTOR_SIGNUP=true` (por defecto solo en desarrollo); si no, el servidor fuerza `student` | `auth/routes.py`, `register.html`, `config.py` |
| S-02 | `/resultados/<id>` mostraba intentos ajenos con las respuestas correctas | Solo el estudiante dueño, el profesor del examen o un admin; el resto recibe 403 | `exams/routes.py` |
| S-03 | Lobby, cierre de sala y `/session/status` sin control de propiedad | 403 si no eres el profesor dueño; `/session/status` ya no lista nombres a no-dueños | `exams/routes.py` |
| S-04 | Sin CSRF | `CSRFProtect` global; `base.html` inyecta el token en todo POST (formularios, `form.submit()` y `fetch`). Verificado en Chromium real | `extensions.py`, `__init__.py`, `base.html` |
| S-05 | `SECRET_KEY` y contraseña de superusuario fijas por defecto; la clave del superusuario se reescribía en cada arranque; profesor semilla con contraseña fija | Fuera de `APP_ENV=development` la app **no arranca** con secretos de ejemplo o `SECRET_KEY` de menos de 32 caracteres. La clave del superusuario y los datos demo quedan apagados por defecto | `config.py`, `__init__.py` |
| S-06 | Los sockets usaban el `student_id` que mandaba el navegador: un estudiante podía suplantar a otro. Cualquiera podía iniciar, pausar o reanudar una sala ajena y espiar las estadísticas de otro profesor | La identidad sale de la cookie de sesión. `teacher_join`, `start`, `pause`, `resume` y `subscribe_teacher_stats` exigen ser el profesor dueño | `realtime/sockets.py` |

### 2.2 Encontrados en esta auditoría

| # | Hallazgo | Corrección |
|---|---|---|
| S-07 | `run.py` con `debug=True` y `host=0.0.0.0`: el depurador de Werkzeug permite **ejecutar código remoto** | `debug` solo en desarrollo y escuchando en `127.0.0.1`. Pre-producción usa `gunicorn` (`wsgi.py`) |
| S-08 | Contraseña mínima de 4 caracteres y sin límite de intentos de login | Mínimo 8 (`MIN_PASSWORD_LENGTH`); bloqueo tras 5 fallos en 15 min por IP+correo (429) |
| S-09 | Socket.IO con `cors_allowed_origins="*"` | Solo mismo origen; lista explícita con `SOCKETIO_CORS_ORIGINS` |
| S-10 | Cookies sin `Secure`/`SameSite` | `HttpOnly`, `SameSite=Lax`, `Secure` fuera de desarrollo; cabecera HSTS |
| S-11 | La alerta antifraude se difundía a toda la sala (los compañeros la veían) | Solo al profesor |
| S-12 | Exportar una capacitación la escribía en `static/uploads/exports/`, **carpeta pública** | Se genera en memoria |
| S-13 | Cualquier usuario, incluso invitados, podía subir archivos de 50 MB a `/learning/api/upload` (riesgo de llenar el disco) | Solo instructores/admin. `MAX_CONTENT_LENGTH` (antes declarado pero nunca aplicado) ahora es global, con respuesta 413 legible |
| S-14 | Un video MP4 y un JSON de usuarios versionados en git | Retirados del índice; `app/static/uploads/` en `.gitignore` |
| S-15 | Nombre del estudiante embebido en JS sin `tojson` | Escapado con `tojson` |
| S-19 | *(17 oct, revisión de RF-011)* La API del editor de capacitaciones (`/learning/api/*` de módulos, lecciones y bloques) no verificaba dueño: **cualquier usuario con sesión, incluso un invitado, podía editar, borrar o reordenar cursos ajenos**. Existía en `main` antes de RF-011 | Solo el autor o un administrador (`_can_edit_learning`); 403 en los demás casos. Test de acceso cruzado sobre las 11 rutas |
| S-18 | *(17 oct, revisión de RF-011)* La URL de video del profesor llegaba sin validar al `src` de un `<iframe>`/`<video>`: un `javascript:` o `data:` era XSS almacenado contra los estudiantes. Existía en `main` | Lista blanca de esquemas (`http(s)` o rutas `/…`) en preguntas, importación y bloques de video; las URLs inseguras ya guardadas no se renderizan |
| S-17 | *(16 oct, GitGuardian)* Dos detecciones de usuario + contraseña fijos: la contraseña del profesor demo en `app/__init__.py` (desde el commit inicial `1435619`) y la de un usuario de prueba en `tests/test_preproduction_hardening.py` (commit `da3f78f`). Ninguna daba acceso real | Sin contraseñas literales en código, tests, docs ni `env.example`: en desarrollo se generan aleatorias, los tests las generan en `tests/support.py`, y fuera de desarrollo se exigen y se rechazan las ya publicadas (comparación por SHA-256). Incidentes resueltos en el panel; `ggshield secret scan repo .` sin secretos activos en los 13 commits |
| S-16 | *(15 oct)* Borrar un profesor con contenido y crear otro: SQLite reutiliza el id y **el nuevo profesor hereda los exámenes, bancos y resultados del anterior** | El panel rechaza borrar profesores con exámenes, bancos, clases o capacitaciones |
| S-20 | *(17 oct, tests de RNF-16)* Encuestas: un profesor podía lanzar una encuesta en la sala de otro, y **cualquier usuario con sesión podía leer las respuestas abiertas** de cualquier encuesta | Lanzar exige ser dueño de la sala; los resultados solo los ven el profesor, un admin o quien votó |
| S-21 | *(17 oct)* Redirección abierta: el campo `next` al crear o editar una pregunta aceptaba cualquier URL (`https://sitio-falso…`) | Solo rutas propias (`/…`, sin `//` ni `\`) |
| S-22 | *(17 oct)* Capacitaciones: cada respuesta de un estudiante (nombre y nota) se **difundía a todos los sockets conectados**, de cualquier curso | Solo al autor del curso (`teacher_<id>`). Verificado que todo `socketio.emit` de la app tiene destinatario |
| S-23 | *(17 oct)* Capacitaciones no publicadas: se aceptaban progreso y respuestas; y **duplicar un curso ajeno** entregaba una copia con las respuestas correctas | 404 si el curso no está publicado (salvo autor/admin); duplicar exige ser autor o admin |
| S-24 | *(17 oct)* Preguntas de completar (`fill_blank`) en capacitaciones: el servidor calificaba con las "respuestas esperadas" que **enviaba el propio navegador** | Las respuestas salen de la configuración del profesor (`[[...]]` en el texto) |
| S-25 | *(17 oct, RNF-17)* Los logs escribían el nombre del estudiante en cada alerta antitrampa, y el access log de Gunicorn guardaba el **token de restablecimiento de contraseña** que viaja en la URL | Logs con ids, no nombres; correos y tokens de `/reset-password/` redactados, también en el access log |
| S-26 | *(17 oct, RNF-07)* Subidas: bastaba renombrar un archivo para cambiar su tipo (un HTML como `.png`), la portada aceptaba video y PDF y una imagen podía pesar 50 MB | Se verifica la firma del contenido; tope por tipo (imagen 10 MB, video 200 MB); portada solo imagen |
| S-27 | *(17 oct, RNF-09)* Disponibilidad: cada conexión en vivo ocupa un hilo de Gunicorn y había 64. **Desde el estudiante 65, nadie más podía conectarse** a la sala (medido); el resto de peticiones quedaba en cola | 256 hilos (`GUNICORN_THREADS`); medido con 200 estudiantes conectados |

Además: cabeceras `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`; `ProxyFix` para correr detrás de Nginx o del balanceador de GCP.

### 2.3 Reglas de integridad cerradas

| Regla | Cambio |
|---|---|
| RN-10 (SRS V3) | Un examen con intentos no se borra definitivamente; queda archivado |
| RN-12 (SRS V3) | Una sala finalizada rechaza envíos, no solo ingresos |
| RN-13 (= RN-04 del SRS V2) | No se borra una pregunta, ni un banco, si tiene respuestas o está en un examen activo. **También es requisito para migrar:** PostgreSQL sí aplica las llaves foráneas que SQLite ignora, y estos borrados fallarían allí |

### 2.4 Bug preexistente corregido

Los handlers de Socket.IO se importaban después de `socketio.init_app()`. Con Flask-SocketIO 5.3 eso los registra solo en el primer servidor: una segunda app en el mismo proceso (tests, recarga) se quedaba sin eventos en vivo. Ahora se importan antes.

Encontrados el 17 de octubre al escribir tests y al correrlos en PostgreSQL:

- Editar un módulo o una lección sin descripción daba error 500.
- El borrado masivo de preguntas comparaba el id (entero) con texto: SQLite lo acepta, **PostgreSQL responde error 500**. Habría aparecido el día de la migración.
- Dos clics seguidos en "Enviar" podían crear dos intentos del mismo examen (la verificación y la escritura no eran atómicas). El candado de §4.1 lo impide.

---

## 3. Lo que sigue abierto

**Seguridad y legal, sin resolver en código:**

- **RL-01 a RL-12 (Ley 1581 de 2012):** falta la política de tratamiento, la casilla de autorización y el registro de consentimientos (la vista de derechos del titular, RF-029, ya existe). **Es lo que bloquea operar con datos reales**, más que cualquier punto técnico. Requiere texto validado por un abogado.
- **RF-028, recuperar contraseña:** implementado (17 oct); falta configurar el servidor de correo (`MAIL_*`) en pre-producción.
- **RL-10, invitados:** cada ingreso por código crea un `User` nuevo que nunca se borra. Hace falta un trabajo periódico que los anonimice a los 90 días.

**Funcionales "Must", sin cambios en esta auditoría** (detalle en `SRS_2026-10-15.md`):

- RF-007 y RN-05: no hay temporizador visible ni validación del tiempo en el servidor.
- RF-014 y RN-03: la importación CSV/Excel no valida antes de insertar.
- RN-04 (V3): se puede editar un examen con una sala en curso.
- RN-07: el refuerzo usa un umbral fijo de 40 %.

**No funcionales:**

- RNF-12: solo se probó en Chromium. Falta la matriz manual en Firefox, Edge y Safari.
- RNF-11: falta una pasada con lector de pantalla (NVDA o VoiceOver) antes de un cliente público.
- RNF-14 (Redis, varios workers): aplazado a propósito, ver §5.

---

## 4. Límites de la plataforma (medidos)

### 4.1 Envío de examen (RNF-08)

Escenario del peor caso: **todos los estudiantes de una sala pulsan "Enviar" en el mismo instante**, lo que pasará cuando exista el autoenvío al terminar el tiempo (RN-05). Examen de 20 preguntas, Gunicorn con 1 worker, SQLite en WAL, contenedor de prueba de 4 vCPU. Mismo hardware antes y después.

| Envíos simultáneos | p95 el 16 oct | p95 el 17 oct | ¿Cumple CA-01 (≤ 2 s)? |
|---:|---:|---:|---|
| 10 | 0,49 s | 0,20 s | Sí |
| 30 | 1,39 s | 0,56 s | Sí |
| 50 | 2,25 s | 0,83 s | Sí |
| 100 | 4,14 s | 1,80–1,99 s | Sí, en el límite |
| 200 | 7,89 s | 3,54 s | No |

En todos los casos, cero errores y tantos `exam_attempts` como envíos.

**Qué cambió y por qué:**

- La lectura del 16 de octubre ("el cuello de botella es el proceso único, no SQLite") **era incompleta**. Un envío solo cuesta ~14 ms; el resto era **contención por el candado de escritura de SQLite**: con decenas de hilos escribiendo a la vez, los que no lo obtienen reintentan con esperas crecientes (`busy_timeout`) y compiten por el GIL. Al hacer que los envíos hagan fila en un `threading.Lock` del proceso (`app/services/write_lock.py`, solo con SQLite), cada uno entra apenas sale el anterior: p95 con 50 envíos pasó de 2,56 s a 0,83 s.
- Además, el envío hacía 72 consultas (1 + 2 por pregunta + 1 INSERT por respuesta); ahora hace 17 (`selectinload` y un solo INSERT). Un test impide que vuelva a crecer.
- El candado es válido porque hay exactamente un worker. Con PostgreSQL no se usa.
- En 1 vCPU (máquina pequeña de GCP) se esperan cifras peores; hay que repetir la prueba en el host real antes de prometer un tamaño de sala.

### 4.2 Eventos de sala (RNF-09)

`scripts/loadtest/room_events.py`: N estudiantes y el profesor conectados por websocket; el profesor pausa, reanuda y finaliza, y se mide cuánto tarda cada evento en llegar a cada estudiante. "Respondiendo" = todos envían una respuesta justo antes de cada evento.

| Escenario | Pausa (p95) | Reanudación (p95) | Fin (p95) |
|---|---:|---:|---:|
| 100 en reposo | 0,07 s | 0,06 s | 0,06 s |
| 100 respondiendo | 0,77 s | 0,38 s | 0,64 s |
| 200 respondiendo | 0,94 s | 1,02 s | 2,74 s |

**Hallazgos de la medición:**

- Con `GUNICORN_THREADS=64` **solo se conectaban 64 estudiantes** (S-27): cada websocket ocupa un hilo mientras está abierto. Ahora son 256.
- Con 200 estudiantes respondiendo, solo 90 recibían la pausa, 14 s tarde: cada respuesta enviaba al profesor la lista completa de la sala (trabajo cuadrático) y competía por el candado de SQLite. Ahora esa lista se agrupa (como máximo una vez cada 0,5 s por sala; el último estado siempre llega) y el guardado usa el mismo candado de §4.1.

### 4.3 Límites operativos de pre-producción

| Límite | Valor | Origen |
|---|---|---|
| Estudiantes enviando a la vez (ráfaga) por instancia | **~100** para p95 ≤ 2 s | §4.1 |
| Estudiantes conectados a la vez por instancia | **~220** (`GUNICORN_THREADS=256` menos ~30 para HTTP); medido con 200 | §4.2 |
| Workers de Gunicorn | **exactamente 1** | Estado de salas en memoria + escritor único de SQLite |
| Instancias | **1** | Archivo SQLite local; sin Redis para Socket.IO |
| Disponibilidad alcanzable | ~99 % mensual (un solo nodo, reinicios = caída) | El 99,5 % del SRS V2 no es alcanzable sin 2 instancias |
| Subida de archivos | Imagen 10 MB, video 200 MB, audio y PDF 20 MB, importaciones 5 MB; 201 MB por petición | RNF-07 (`UPLOAD_*_MB`, `MAX_UPLOAD_MB`) |
| Almacenamiento de video | Disco local del contenedor (volumen) | Videos pesados → YouTube/Vimeo (suposición del SRS V3) |
| Intentos de login | 5 fallos / 15 min por IP+correo | RNF-06 |
| Respaldo | Diario, 30 días de retención, verificación de integridad; simulacro de restauración semanal automatizado | RNF-15 |

---

## 5. Cuándo pasar a PostgreSQL

El SAD (ADR-003) ya prevé la migración sin tocar la lógica de negocio. La pregunta es cuándo se paga sola. Conviene migrar **cuando se cumpla cualquiera de estos disparadores**, no antes:

**Disparadores técnicos (medibles en producción):**

1. Un cliente necesita salas con **más de ~100 envíos simultáneos** con p95 ≤ 2 s, o **más de ~220 estudiantes conectados** por instancia. Ojo: esto exige **PostgreSQL + Redis + más de un worker a la vez**. PostgreSQL solo no basta.
2. Un contrato exige **SLA ≥ 99,5 %**: hacen falta dos instancias, y una base compartida es obligatoria.
3. Aparece `database is locked` en los logs o el archivo `.db` supera unos pocos GB y el respaldo diario empieza a pesar.

**Disparador de negocio:**

4. El ingreso recurrente cubre con holgura el costo nuevo, por ejemplo **≥ 3× el costo mensual** de Cloud SQL + Memorystore (Redis) en la región elegida. Consultar la [calculadora de precios de GCP](https://cloud.google.com/products/calculator) antes de comprometer cifras: no se cotizó en esta auditoría.

**Preparación barata**, para que la migración sea un cambio de `DATABASE_URL` y no un proyecto:

- ✅ Flask-Migrate/Alembic en lugar de `ensure_schema()` (RNF-13, 17 oct).
- ✅ Tests en CI también contra PostgreSQL 16 (17 oct). Ya encontró un error 500 que solo ocurría en PostgreSQL (§2.4).
- ✅ Optimizar `submit_exam` (17 oct): el tope pasó de ~45 a ~100 envíos simultáneos **sin gastar un peso**.
- ✅ Driver `psycopg` incluido en la imagen.
- Pendiente: unificar las cuatro grafías del estado "finalizada" (`finished`, `FINISHED`, `closed`, `CLOSED`).
- Al migrar: quitar el candado de `write_lock.py` no hace falta (no se aplica fuera de SQLite), pero sí repetir §4.1 y §4.2.

---

## 6. Cómo reproducir

```bash
pytest                                   # 176 tests, cobertura con --cov=app
TEST_DATABASE_URL=postgresql+psycopg://usuario@localhost/mytraining_test pytest   # misma suite en PostgreSQL
APP_ENV=preproduction SECRET_KEY=<CLAVE> SUPERUSER_PASSWORD=<CLAVE> \
  gunicorn -c gunicorn.conf.py wsgi:app  # arranque pre-producción (aplica migraciones)
curl localhost:8080/healthz              # {"status":"ok","env":"preproduction"}
python scripts/backup_sqlite.py instance/database.db backups/
python scripts/restore_drill.py backups/ --compare instance/database.db

# Pruebas de carga (§4.1 y §4.2) — repetirlas en el host real antes de fijar el tamaño de sala.
# Base desechable: seed_load.py la BORRA y la vuelve a crear.
export LOADTEST_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(12))")
export DATABASE_URL=sqlite:////tmp/load.db APP_ENV=preproduction SESSION_COOKIE_SECURE=0 SECRET_KEY=<CLAVE> SUPERUSER_PASSWORD=<CLAVE>
SEED=$(python scripts/loadtest/seed_load.py 100 | tail -1)
gunicorn -c gunicorn.conf.py wsgi:app &
python scripts/loadtest/submit_burst.py http://127.0.0.1:8080 100 $SEED
# Eventos de sala (con otra base sembrada; la sala debe estar abierta):
python scripts/loadtest/room_events.py http://127.0.0.1:8080 100 ${SEED%% *} --answers ${SEED#* }

# Accesibilidad (§1): ver scripts/a11y (axe-core + Playwright en Chromium)
```

La prueba E2E de CSRF en Chromium (Playwright) no se versionó: se usó una vez para esta auditoría. Las de accesibilidad sí (`scripts/a11y`).
