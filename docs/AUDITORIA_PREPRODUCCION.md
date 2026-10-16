# Auditoría pre-producción — MyTraining

**Fecha:** 16 de octubre de 2026 · **Rama:** `ccr-58c67f87-ovb3cp` · **Base:** SAD V2, SRS V2 y SRS V3 + Auditoría (29 sep 2026)

Este documento resume qué se revisó, qué se corrigió en el código, qué límites tiene hoy la plataforma (medidos, no estimados) y cuándo conviene pagar PostgreSQL.

---

## 1. Resumen

| | Antes | Ahora |
|---|---|---|
| Hallazgos de seguridad de la Fase 1 (SRS V3 §9) | 6 abiertos | **6 cerrados** |
| Otros hallazgos de seguridad encontrados en esta auditoría | — | 11 cerrados |
| Tests automatizados | 19 | **35** (todos pasan) |
| Prueba de carga | no existía | hecha (§4) |
| Arranque de producción | `debug=True` en `0.0.0.0` | Gunicorn, 1 worker, `/healthz`, Dockerfile |
| Respaldo de la base | no existía | `scripts/backup_sqlite.py` con retención |

**Conclusión:** la app puede salir a pre-producción sobre **SQLite en un solo contenedor**, con un tope operativo de **~45 estudiantes enviando a la vez por instancia** (§4). PostgreSQL no hace falta todavía. Lo que sí bloquea el uso con datos personales reales es la parte legal (política de tratamiento y autorización, SRS V3 §7), no la base de datos.

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
| S-17 | *(16 oct, GitGuardian)* Dos detecciones de usuario + contraseña fijos: la contraseña del profesor demo en `app/__init__.py` (desde el commit inicial `1435619`) y la de un usuario de prueba en `tests/test_preproduction_hardening.py` (commit `da3f78f`). Ninguna daba acceso real | Sin contraseñas literales en código, tests, docs ni `env.example`: en desarrollo se generan aleatorias, los tests las generan en `tests/support.py`, y fuera de desarrollo se exigen y se rechazan las ya publicadas (comparación por SHA-256). Incidentes resueltos en el panel; `ggshield secret scan repo .` sin secretos activos en los 13 commits |
| S-16 | *(15 oct)* Borrar un profesor con contenido y crear otro: SQLite reutiliza el id y **el nuevo profesor hereda los exámenes, bancos y resultados del anterior** | El panel rechaza borrar profesores con exámenes, bancos, clases o capacitaciones |

Además: cabeceras `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`; `ProxyFix` para correr detrás de Nginx o del balanceador de GCP.

### 2.3 Reglas de integridad cerradas

| Regla | Cambio |
|---|---|
| RN-10 (SRS V3) | Un examen con intentos no se borra definitivamente; queda archivado |
| RN-12 (SRS V3) | Una sala finalizada rechaza envíos, no solo ingresos |
| RN-13 (= RN-04 del SRS V2) | No se borra una pregunta, ni un banco, si tiene respuestas o está en un examen activo. **También es requisito para migrar:** PostgreSQL sí aplica las llaves foráneas que SQLite ignora, y estos borrados fallarían allí |

### 2.4 Bug preexistente corregido

Los handlers de Socket.IO se importaban después de `socketio.init_app()`. Con Flask-SocketIO 5.3 eso los registra solo en el primer servidor: una segunda app en el mismo proceso (tests, recarga) se quedaba sin eventos en vivo. Ahora se importan antes.

---

## 3. Lo que sigue abierto

**Seguridad y legal, sin resolver en código:**

- **RL-01 a RL-12 (Ley 1581 de 2012):** falta la política de tratamiento, la casilla de autorización, el registro de consentimientos y la vista de derechos del titular (RF-029). **Es lo que bloquea operar con datos reales**, más que cualquier punto técnico. Requiere texto validado por un abogado.
- **RF-028, recuperar contraseña:** necesita un proveedor de correo.
- **RL-10, invitados:** cada ingreso por código crea un `User` nuevo que nunca se borra. Hace falta un trabajo periódico que los anonimice a los 90 días.

**Funcionales "Must", sin cambios en esta auditoría** (detalle en `SRS_2026-10-15.md`):

- RF-007 y RN-05: no hay temporizador visible ni validación del tiempo en el servidor.
- RF-011 y RN-02: el video no se pausa en la marca de tiempo.
- RF-014 y RN-03: la importación CSV/Excel no valida antes de insertar.
- RN-04 (V3): se puede editar un examen con una sala en curso.
- RN-07: el refuerzo usa un umbral fijo de 40 %.

---

## 4. Límites de la plataforma (medidos)

### 4.1 Prueba de carga

Escenario del peor caso: **todos los estudiantes de una sala pulsan "Enviar" en el mismo instante**, lo que pasará cuando exista el autoenvío al terminar el tiempo (RN-03 del V2). Examen de 20 preguntas, Gunicorn con 1 worker y 64 hilos, SQLite en WAL, contenedor de prueba de 4 vCPU.

| Envíos simultáneos | Errores | p50 | p95 | Máx. | ¿Cumple CA-01 (≤ 2 s)? |
|---:|---:|---:|---:|---:|---|
| 1 | 0 | 0,04 s | 0,04 s | 0,04 s | Sí |
| 10 | 0 | 0,47 s | 0,49 s | 0,52 s | Sí |
| 30 | 0 | 1,24 s | 1,39 s | 1,45 s | Sí |
| 50 | 0 | 1,71 s | 2,25 s | 2,30 s | Límite |
| 100 | 0 | 2,73 s | 4,14 s | 4,28 s | No |
| 200 | 0 | 4,50 s | 7,89 s | 8,12 s | No |

Repetida con el código final (CSRF activo) para 10, 30, 50 y 100: mismas cifras ±0,1 s, y en todos los casos el número de `exam_attempts` en la base coincidió con el de envíos.

**Lectura:**

- **Nunca hubo `database is locked`** ni pérdidas, ni siquiera con 200 envíos. Antes de esta auditoría no había `busy_timeout` ni WAL, así que el primer choque de escritura devolvía error 500.
- Cada envío cuesta unos 40 ms y se atienden en serie (un proceso, GIL de Python y un único escritor SQLite): unos **25 envíos por segundo**.
- **El cuello de botella es el proceso único, no SQLite.** Pasar a PostgreSQL sin más workers no mejoraría esta tabla. Y no se pueden agregar workers porque el estado de las salas vive en memoria (`realtime/manager.py`).
- En 1 vCPU (máquina pequeña de GCP) se esperan cifras peores; hay que repetir la prueba en el host real antes de prometer un tamaño de sala.
- Esto no es una ráfaga real: con envíos repartidos en un minuto, 200 estudiantes son unos 3 envíos/s, muy por debajo de la capacidad.

### 4.2 Límites operativos de pre-producción

| Límite | Valor | Origen |
|---|---|---|
| Estudiantes enviando a la vez (ráfaga) por instancia | **~45** para p95 ≤ 2 s | §4.1 |
| Estudiantes conectados por sala | 100 con envíos escalonados (RB-02); con ráfaga, ~45 | §4.1 |
| Workers de Gunicorn | **exactamente 1** | Estado de salas en memoria + escritor único de SQLite |
| Instancias | **1** | Archivo SQLite local; sin Redis para Socket.IO |
| Disponibilidad alcanzable | ~99 % mensual (un solo nodo, reinicios = caída) | El 99,5 % del SRS V2 no es alcanzable sin 2 instancias |
| Subida de archivos | 50 MB por petición (`MAX_UPLOAD_MB`) | SRS V3 RNF-07 pide 200 MB video / 10 MB imagen: pendiente diferenciar por tipo |
| Almacenamiento de video | Disco local del contenedor (volumen) | Videos pesados → YouTube/Vimeo (suposición del SRS V3) |
| Intentos de login | 5 fallos / 15 min por IP+correo | RNF-06 |
| Respaldo | Diario, 30 días de retención, verificación de integridad | RNF-15 (falta automatizar el simulacro trimestral) |

---

## 5. Cuándo pasar a PostgreSQL

El SAD (ADR-003) ya prevé la migración sin tocar la lógica de negocio. La pregunta es cuándo se paga sola. Conviene migrar **cuando se cumpla cualquiera de estos disparadores**, no antes:

**Disparadores técnicos (medibles en producción):**

1. Un cliente necesita salas con **más de ~45 envíos simultáneos** con p95 ≤ 2 s. Ojo: esto exige **PostgreSQL + Redis + más de un worker a la vez**. PostgreSQL solo no basta (§4.1).
2. Un contrato exige **SLA ≥ 99,5 %**: hacen falta dos instancias, y una base compartida es obligatoria.
3. Aparece `database is locked` en los logs o el archivo `.db` supera unos pocos GB y el respaldo diario empieza a pesar.

**Disparador de negocio:**

4. El ingreso recurrente cubre con holgura el costo nuevo, por ejemplo **≥ 3× el costo mensual** de Cloud SQL + Memorystore (Redis) en la región elegida. Consultar la [calculadora de precios de GCP](https://cloud.google.com/products/calculator) antes de comprometer cifras: no se cotizó en esta auditoría.

**Preparación barata que sí conviene hacer ya**, para que la migración sea un cambio de `DATABASE_URL` y no un proyecto:

- Flask-Migrate/Alembic en lugar de `ensure_schema()` (RNF-13).
- Correr los tests en CI también contra PostgreSQL (detecta las llaves foráneas que SQLite ignora; RN-13 ya cubre las más obvias).
- Unificar las cuatro grafías del estado "finalizada" (`finished`, `FINISHED`, `closed`, `CLOSED`).
- Optimizar `submit_exam`: hoy consulta cada opción por separado y recrea instantáneas en cada envío. Bajar de 40 ms a ~15 ms por envío casi triplicaría el tope de §4.2 **sin gastar un peso**.

---

## 6. Cómo reproducir

```bash
pytest                                   # 35 tests
APP_ENV=preproduction SECRET_KEY=... SUPERUSER_PASSWORD=... \
  gunicorn -c gunicorn.conf.py wsgi:app  # arranque pre-producción
curl localhost:8080/healthz              # {"status":"ok","env":"preproduction"}
python scripts/backup_sqlite.py instance/database.db backups/

# Prueba de carga (§4.1) — repetirla en el host real antes de fijar el tamaño de sala:
export DATABASE_URL=sqlite:////tmp/load.db APP_ENV=preproduction SESSION_COOKIE_SECURE=0 SECRET_KEY=... SUPERUSER_PASSWORD=...
SEED=$(python scripts/loadtest/seed_load.py 50 | tail -1)
gunicorn -c gunicorn.conf.py wsgi:app &
python scripts/loadtest/submit_burst.py http://127.0.0.1:8080 50 $SEED
```

La prueba E2E de CSRF en Chromium (Playwright) no se versionó: se usó una vez para esta auditoría.
