# Manual de administrador — MyTraining

**Fecha:** 15 de octubre de 2026 · **Fase:** pre-producción (una instancia, SQLite)
**Para:** el superusuario de la plataforma y quien la opera (despliegue, respaldos, soporte).
**Relacionados:** [Manual de usuario](MANUAL_USUARIO_2026-10-15.md) · [Arquitectura](SAD_2026-10-15.md) · [Manual de desarrollo y depuración](MANUAL_DESARROLLO_Y_DEPURACION_2026-10-15.md)

---

## Contenido

1. [Rol del administrador](#1-rol-del-administrador)
2. [Instalación en pre-producción](#2-instalación-en-pre-producción)
3. [Variables de entorno](#3-variables-de-entorno)
4. [Gestión de usuarios](#4-gestión-de-usuarios)
5. [Respaldos y restauración](#5-respaldos-y-restauración)
6. [Monitoreo y logs](#6-monitoreo-y-logs)
7. [Actualizar la aplicación](#7-actualizar-la-aplicación)
8. [Capacidad y límites](#8-capacidad-y-límites)
9. [Solución de problemas](#9-solución-de-problemas)
10. [Listas de verificación](#10-listas-de-verificación)

---

## 1. Rol del administrador

El **superusuario** se crea automáticamente en el primer arranque, con los datos de `SUPERUSER_EMAIL` y `SUPERUSER_PASSWORD`. Al iniciar sesión entra al **Panel de Superusuario** (menú **Administración**). Desde allí:

- ve los totales: **Total Profesores**, **Exámenes Creados**, **Salas de Examen** y estudiantes;
- crea cuentas de profesor (**Crear Cuenta de Profesor**);
- elimina profesores **sin contenido** (§4.3).

Las demás tareas (contraseñas, cambios de rol, respaldos, actualizaciones) se hacen desde el servidor con los comandos de este manual: el panel aún no las ofrece.

---

## 2. Instalación en pre-producción

### 2.1 Arquitectura recomendada en Google Cloud

| Pieza | Recomendación | Por qué |
|---|---|---|
| Servidor | Una VM de **Compute Engine** pequeña con Docker | Un solo proceso es obligatorio en esta fase |
| Disco | **Disco persistente** con la base (`/data`) y los archivos subidos | SQLite es un archivo local |
| HTTPS | Nginx o Caddy en la misma VM, o el balanceador HTTPS de GCP | Las cookies son `Secure`: sin HTTPS no se puede iniciar sesión |
| Respaldos | Cron diario + copia a Cloud Storage + snapshot del disco | §5 |

> **No uses Cloud Run en esta fase.** Su disco es temporal (perderías la base) y puede levantar varias copias de la app, lo que rompe las salas en vivo.

### 2.2 Construir y arrancar

```bash
git clone <repo> mytraining && cd mytraining
docker build -t mytraining .

docker run -d --name mytraining --restart unless-stopped \
  -p 127.0.0.1:8080:8080 \
  -e APP_ENV=preproduction \
  -e SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')" \
  -e SUPERUSER_EMAIL=admin@tu-dominio.com \
  -e SUPERUSER_PASSWORD="$(cat /ruta/segura/superuser_password)" \
  -e PROXY_FIX_HOPS=1 \
  -v mytraining-data:/data \
  -v mytraining-uploads:/srv/app/app/static/uploads \
  mytraining
```

Notas:

- **Guarda la `SECRET_KEY`** en un gestor de secretos (por ejemplo Secret Manager). Si cambia, se cierran todas las sesiones.
- El puerto se publica solo en `127.0.0.1`: el tráfico de Internet debe pasar por el proxy HTTPS (§2.3).
- Si falta `SECRET_KEY` o `SUPERUSER_PASSWORD`, si son demasiado cortas o si coinciden con un valor que alguna vez se publicó en el repositorio, el contenedor **no arranca** y el log dice `Configuración insegura para APP_ENV=preproduction`. Es intencional.
- Guarda la contraseña del superusuario en un archivo con permisos `600` fuera del repositorio, o en Secret Manager, nunca en el historial del shell.
- Comprueba con `curl -s localhost:8080/healthz`. La respuesta esperada es `{"env":"preproduction","status":"ok"}`.

### 2.3 Proxy inverso (Nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name capacitacion.tu-dominio.com;
    # ssl_certificate / ssl_certificate_key (por ejemplo con certbot)

    client_max_body_size 201m;         # igual a MAX_UPLOAD_MB; el default de Nginx (1 MB) rompe las subidas

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;   # sin esto Socket.IO rechaza el origen https
        proxy_set_header Upgrade $http_upgrade;       # WebSocket
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;                     # conexiones de sala largas
    }
}
server { listen 80; server_name capacitacion.tu-dominio.com; return 301 https://$host$request_uri; }
```

---

## 3. Variables de entorno

Lista completa con comentarios en [`env.example`](../env.example).

| Variable | Obligatoria | Valor en pre-producción | Para qué |
|---|---|---|---|
| `APP_ENV` | Sí | `preproduction` | Activa los valores seguros por defecto |
| `SECRET_KEY` | Sí | 64 caracteres aleatorios | Firma de cookies y tokens CSRF |
| `SUPERUSER_EMAIL` / `SUPERUSER_PASSWORD` / `SUPERUSER_USERNAME` | Sí | Tus datos | Superusuario inicial (solo se crea si no existe) |
| `DATABASE_URL` | No | `sqlite:////data/mytraining.db` (ya en la imagen) | Base de datos |
| `LEGAL_ENTITY_NAME`, `LEGAL_ENTITY_ID`, `LEGAL_CONTACT_EMAIL`, `LEGAL_ADDRESS` | **Sí** | Nombre o razón social del responsable del tratamiento, NIT o cédula, correo para consultas y reclamos, dirección | Aparecen en `/terminos` y `/politica-de-datos` (Ley 1581). **Sin ellos la app no arranca** fuera de desarrollo |
| `GUEST_RETENTION_DAYS` | No | `90` | Días tras los cuales se anonimizan los invitados (§4.5) |
| `PROXY_FIX_HOPS` | No | `1` | Número de proxies delante de la app |
| `ALLOW_INSTRUCTOR_SIGNUP` | No | `false` | `true` permite que cualquiera se registre como profesor |
| `SESSION_COOKIE_SECURE` | No | `true` | Ponlo en `false` **solo** para pruebas locales sin HTTPS |
| `MAX_UPLOAD_MB` | No | `201` | Tope por petición; debe cubrir el mayor de los de abajo (ajusta también Nginx) |
| `UPLOAD_IMAGE_MB` / `UPLOAD_VIDEO_MB` / `UPLOAD_AUDIO_MB` / `UPLOAD_DOCUMENT_MB` / `UPLOAD_IMPORT_MB` | No | `10` / `200` / `20` / `20` / `5` | Tope por tipo de archivo (importación = CSV, Excel y JSON) |
| `MIN_PASSWORD_LENGTH` | No | `8` | Contraseña mínima |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCKOUT_SECONDS` | No | `5` / `900` | Bloqueo por intentos fallidos |
| `SOCKETIO_CORS_ORIGINS` | No | vacío | Solo si el frontend se sirve desde otro dominio |
| `GUNICORN_THREADS` | No | `256` | Hilos del único worker. **Es el tope de estudiantes conectados a la vez** (cada conexión en vivo ocupa uno) más ~30 para páginas |
| `LOG_LEVEL` | No | `info` | `debug`, `info`, `warning` o `error` (app y Gunicorn) |
| `LOG_FORMAT` | No | `json` | `json` (una línea por evento, para Cloud Logging) o `text` |
| `SUPERUSER_RESET_ON_BOOT` | No | `false` | `true` reescribe la clave del superusuario desde el entorno en cada arranque (§4.4) |
| `SEED_DEMO_DATA` | No | `false` | Crea un profesor y un examen de demostración |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM` | **Sí, para recuperar contraseñas** | Los de tu proveedor SMTP | Correo de "¿Olvidaste tu contraseña?". Sin `MAIL_SERVER` no se envía nada y queda una advertencia en el log. `MAIL_PASSWORD` va en el gestor de secretos |
| `PASSWORD_RESET_MAX_AGE` / `PASSWORD_RESET_MAX_REQUESTS` | No | `1800` / `3` | Vigencia del enlace (s) y solicitudes por correo y hora |

Para cambiar una variable hay que recrear el contenedor (`docker rm -f mytraining` y repetir `docker run` con los mismos volúmenes). Los datos están en los volúmenes y no se pierden.

---

## 4. Gestión de usuarios

### 4.1 Crear profesores

En **Administración** → **Crear Cuenta de Profesor**: nombre, correo y contraseña (mínimo 8 caracteres). Entrega las credenciales por un canal seguro y pide al profesor que las cambie cuando exista esa función.

> El profesor creado desde el panel no recibe un banco de preguntas por defecto: lo crea él en **Preguntas → Crear Banco**.

### 4.2 Auto-registro de profesores

Por defecto está **apagado** (regla RN-09). Si el negocio decide abrirlo como embudo de adquisición, define `ALLOW_INSTRUCTOR_SIGNUP=true`. Ten en cuenta que aún no hay verificación de correo ni recuperación de contraseña.

### 4.3 Eliminar profesores

Solo se puede eliminar un profesor **sin contenido** (sin exámenes, bancos, clases ni capacitaciones). Si lo intentas con uno que tiene contenido, el panel lo rechaza.

Motivo: SQLite reutiliza el número de usuario y el siguiente profesor creado heredaría los exámenes y los resultados de estudiantes del anterior. Para quitarle el acceso a un profesor con contenido, **cámbiale la contraseña** (§4.4).

### 4.4 Tareas sin pantalla: contraseñas y roles

**Contraseñas:** cada usuario con correo puede recuperarla solo desde **¿Olvidaste tu contraseña?** (requiere `MAIL_*`, §3) o cambiarla en **Mi perfil y mis datos**. Usa el comando de abajo solo si el correo no funciona.

**Roles:** el panel aún no permite cambiarlos. Igual que las contraseñas de emergencia, se hace desde el servidor:

```bash
docker exec -i mytraining python - <<'PY'
from app import create_app
from app.extensions import db
from app.models import User
app = create_app()
with app.app_context():
    u = User.query.filter_by(email='persona@correo.com').first()
    u.set_password(input('Nueva contraseña: '))   # restablecer contraseña (no la dejes en el historial del shell)
    # u.role = 'instructor'                     # promover estudiante a profesor
    db.session.commit()
    print('Listo:', u.email, u.role)
PY
```

**Cambiar la clave del superusuario:** usa el mismo comando con su correo. Otra vía es recrear el contenedor con `SUPERUSER_RESET_ON_BOOT=true` y la nueva `SUPERUSER_PASSWORD`; en ese caso, recréalo después **sin** esa variable.

### 4.5 Invitados

Cada ingreso por código crea un usuario estudiante sin correo. La política de datos promete anonimizarlos a los `GUEST_RETENTION_DAYS` días (90; RL-10), así que programa el script:

```bash
# crontab -e en la VM (todos los días a las 03:40)
40 3 * * * docker exec mytraining python scripts/anonymize_guests.py >> /var/log/mytraining-guests.log 2>&1
```

Borra el nombre del invitado y conserva sus respuestas sin identidad, igual que cuando alguien elimina su cuenta. Con `--dry-run` solo cuenta cuántos anonimizaría.

### 4.5.1 Términos, política y autorizaciones

- Los textos están en `/terminos` y `/politica-de-datos` (plantillas en `app/templates/legal/`). Son un **borrador técnico: deben validarse con un abogado** antes de abrir a usuarios reales.
- Al registrarse o entrar como invitado, la persona marca una casilla (nunca viene marcada). Queda registrada la versión aceptada, la fecha y la IP (tabla `consents`) y una entrada `consent.accept` en la auditoría.
- **Usuarios que ya existían:** la primera vez que entren después de la actualización verán una pantalla para aceptar; hasta hacerlo solo pueden ver los textos, su perfil, descargar sus datos o eliminar su cuenta. Incluye a los administradores.
- **Si cambias el texto:** sube `LEGAL_VERSION` en `app/services/legal.py` (por ejemplo, a la fecha del cambio). Todos deberán aceptar la nueva versión en su próximo ingreso.
- **Revocaciones:** quien revoca desde su perfil queda en la misma situación que un usuario sin autorización. Se registran como `consent.revoke`.

---

### 4.6 Solicitudes de los titulares de datos

Los usuarios consultan, corrigen, descargan y eliminan sus datos desde **Mi perfil y mis datos**. Quedan para ti:

- **Profesores con contenido y administradores que piden su supresión:** la página no les deja hacerlo solos. Reasigna o archiva su contenido y cámbiales la contraseña (§4.4); la anonimización completa de un profesor con contenido está pendiente de definir con el responsable legal.
- **Plazos legales (Ley 1581):** consultas en máximo 10 días hábiles y reclamos en 15, contados desde que llega el correo a `LEGAL_CONTACT_EMAIL`. Lleva un registro de cada solicitud (fecha de llegada, quién, qué pide, fecha y sentido de la respuesta), por ejemplo en una hoja de cálculo compartida (RL-04). Cada exportación, supresión, aceptación y revocación hecha desde la app queda en la auditoría (`user.export`, `user.anonymize`, `consent.accept`, `consent.revoke`).
- **Prueba de la autorización de alguien:** está en su archivo de *Descargar mis datos* (sección `autorizaciones`) o en la tabla `consents`.

## 5. Respaldos y restauración

### 5.1 Respaldo diario

El script hace una copia consistente con la app encendida, verifica su integridad y borra copias de más de 30 días.

```bash
# crontab -e en la VM (todos los días a las 03:10)
10 3 * * * docker exec mytraining python scripts/backup_sqlite.py /data/mytraining.db /data/backups --keep-days 30 >> /var/log/mytraining-backup.log 2>&1
```

Las copias quedan en el mismo disco (`/data/backups`). **Sácalas del servidor** también:

```bash
# todos los días a las 03:30: copia la carpeta de respaldos a Cloud Storage
30 3 * * * docker cp mytraining:/data/backups /tmp/mt-backups && gsutil -m rsync -r /tmp/mt-backups gs://TU-BUCKET/mytraining/ && rm -rf /tmp/mt-backups
```

Programa además **snapshots del disco persistente** en GCP: cubren los archivos subidos, que el script no copia.

### 5.2 Restaurar

```bash
docker stop mytraining
docker run --rm -v mytraining-data:/data alpine sh -c \
  'cp /data/backups/mytraining_AAAAMMDD_HHMMSS.db /data/mytraining.db && rm -f /data/mytraining.db-wal /data/mytraining.db-shm && chown 10001 /data/mytraining.db'
docker start mytraining
curl -s localhost:8080/healthz
```

> Borra los archivos `-wal` y `-shm` al restaurar; si no, SQLite intentaría aplicar cambios de la base anterior.

### 5.3 Simulacro de restauración automático (semanal)

Un respaldo que nunca se restauró no está probado. `scripts/restore_drill.py` toma el último respaldo, lo copia aparte (no toca la base real), revisa su integridad, arranca la app contra la copia, pide `/healthz` y compara el número de filas con la base viva. Falla si algo no cuadra **o si el respaldo más reciente tiene más de 26 horas** (así te enteras de que el respaldo diario dejó de correr).

```bash
# crontab -e en la VM (domingos a las 04:10)
10 4 * * 0 docker exec mytraining python scripts/restore_drill.py /data/backups --compare /data/mytraining.db >> /var/log/mytraining-drill.log 2>&1 || echo "Falló el simulacro de restauración" | mail -s "MyTraining: simulacro fallido" <CORREO_ADMIN>
```

La salida es un JSON con `"ok": true` y el tiempo que tomó (`segundos`). Si falla, el campo `error` dice por qué. Una vez por trimestre conviene además una restauración completa en una VM de prueba (§5.2), incluyendo los archivos subidos.

---

## 6. Monitoreo y logs

| Qué | Cómo |
|---|---|
| Disponibilidad | Chequeo de disponibilidad de GCP (*Uptime check*) contra `https://<dominio>/healthz`, cada minuto, con alerta por correo |
| Logs | `docker logs -f mytraining`: una línea JSON por evento (`ts`, `level`, `logger`, `msg`, `event`, `room`, `user_id`). Cloud Logging los indexa solos; filtra, por ejemplo, por `jsonPayload.level="ERROR"`. No contienen correos, nombres ni tokens: las personas aparecen por id |
| Eventos de sala | Campo `event`: `room.student_join`, `room.start`, `room.pause`, `room.resume`, `room.student_leave`, `room.anti_cheat`. Las respuestas en vivo (`room.answer`) solo salen con `LOG_LEVEL=debug` |
| Disco | Alerta de GCP al 80 % de uso del disco persistente |
| Señales de que toca crecer | `database is locked` en los logs; quejas de envíos lentos con salas grandes (§8) |
| Secretos en el código | Panel de GitGuardian y el job **Secret scan (GitGuardian)** de GitHub Actions (§6.1) |
| Quién hizo qué | **Administración → Auditoría** (`/admin/audit`): creación, edición, archivo y borrado de exámenes; inicio/pausa/fin de salas; exportación de resultados; calificaciones manuales; alta y baja de profesores; recuperación y cambio de contraseñas; exportación y supresión de datos personales. Filtra por acción o por ID de usuario. Guarda el ID y la IP, no el correo |

### 6.1 Escaneo de secretos con GitGuardian

El repositorio escanea secretos en cada push y pull request con GitHub Actions y, en local, antes de cada commit (detalle técnico en el Manual de desarrollo §2.4). Para que el CI funcione:

1. En [dashboard.gitguardian.com](https://dashboard.gitguardian.com) → **API** → **Personal access tokens**, crea un token con permiso de escaneo (`scan`).
2. En GitHub → repositorio → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**, crea `GITGUARDIAN_API_KEY` con ese token.
3. Haz un push y comprueba que el job **Secret scan (GitGuardian)** termine en verde.

Mientras no exista ese secreto, el job falla en cada push: es la señal de que falta configurarlo.

**Ante un incidente:** rota la credencial afectada, quítala del código (ver el Manual de desarrollo §2.4) y cierra el incidente en el panel de GitGuardian como *resuelto*.

### 6.2 Incidentes de seguridad con datos personales (RL-07)

Ejemplos: acceso no autorizado a resultados o cuentas, base o respaldo expuestos, un secreto filtrado.

1. **Contener:** cambia las claves afectadas (`SECRET_KEY` cierra todas las sesiones; contraseñas de administradores), corta el acceso expuesto y conserva los logs y el registro de auditoría de esas fechas.
2. **Evaluar:** qué datos, de cuántas personas y desde cuándo. `/admin/audit` y los logs JSON (`docker logs`) ayudan a reconstruir lo ocurrido.
3. **Reportar a la SIC** en el Registro Nacional de Bases de Datos (módulo de reporte de incidentes) dentro de los 15 días hábiles siguientes a detectarlo, como pide la Circular Externa 003 de 2018 de la SIC. Confirma el plazo vigente con el abogado.
4. **Avisar a las personas afectadas** cuando el incidente pueda afectarlas, con qué pasó, qué datos y qué hacer.
5. **Registrar** el incidente (fecha, alcance, acciones, reporte) y corregir la causa.

Designa a una persona responsable de este procedimiento antes de abrir a usuarios reales.

---

## 7. Actualizar la aplicación

**Hazlo fuera del horario de clases.** El estado de las salas en vivo está en memoria: un reinicio desconecta a todos. Las respuestas ya dadas se conservan y se restauran al reconectar.

```bash
cd mytraining && git pull
docker exec mytraining python scripts/backup_sqlite.py /data/mytraining.db /data/backups   # respaldo previo
docker build -t mytraining .
docker rm -f mytraining && docker run ...            # mismo comando de §2.2, mismos volúmenes
curl -s localhost:8080/healthz
```

Los cambios de la base se aplican solos al arrancar (migraciones de Alembic, carpeta `migrations/`); en el log verás `Running upgrade ...`. La primera vez, una base anterior al 17 de octubre se completa y se marca en la revisión `0001` sin recrear nada. Si una actualización falla, vuelve a la versión anterior con `git checkout <commit>`, reconstruye y restaura el respaldo previo (§5.2): las migraciones no se deshacen solas.

---

## 8. Capacidad y límites

| Límite | Valor | Qué decir al cliente |
|---|---|---|
| Envíos simultáneos por instancia | ~100 en el mismo segundo con respuesta ≤ 2 s | "Salas de hasta 100 estudiantes, aunque todos envíen a la vez" |
| Estudiantes conectados a la vez | ~220 por instancia (`GUNICORN_THREADS=256`) | Sumando todas las salas abiertas |
| Workers / instancias | 1 / 1 | **Nunca subas `workers` en `gunicorn.conf.py`:** las salas dejarían de funcionar |
| Archivos | Imagen 10 MB, video 200 MB, audio y PDF 20 MB | Videos largos en YouTube/Vimeo |
| Disponibilidad | ~99 % mensual | Mantenimientos fuera de horario |

**Cuándo pasar a PostgreSQL + Redis + varias instancias:** cuando se cumpla cualquiera de los disparadores del [SAD §12.3](SAD_2026-10-15.md#123-disparadores-para-pasar-a-producción): salas que necesiten más de ~100 envíos simultáneos o más de ~220 estudiantes conectados, un contrato con SLA ≥ 99,5 %, errores `database is locked`, o ingresos que cubran al menos 3 veces el costo mensual nuevo.

---

## 9. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| El contenedor se detiene al arrancar con `Configuración insegura…` | `SECRET_KEY` o `SUPERUSER_PASSWORD` de ejemplo, o `SECRET_KEY` de menos de 32 caracteres | Define valores reales (§2.2) |
| El login "no hace nada" y vuelve a pedir credenciales | Se entra por `http://`; la cookie `Secure` no se guarda | Entra por HTTPS. Solo en pruebas locales: `SESSION_COOKIE_SECURE=false` |
| "Demasiados intentos fallidos" (429) | 5 fallos en 15 min | Esperar. Reiniciar el contenedor también limpia el bloqueo |
| Las salas no se actualizan en vivo / el estudiante no ve "Conectado a la sala" | El proxy no reenvía `Upgrade`/`Connection` o `X-Forwarded-Proto` | Revisa la configuración de §2.3 |
| "La página caducó o el formulario no es válido" | Token CSRF ausente o sesión expirada; o la `SECRET_KEY` cambió | Recargar la página. Si le pasa a todos tras un despliegue, revisa que la `SECRET_KEY` sea la misma |
| Error 413 o "Archivo demasiado grande" | Archivo mayor que el tope de su tipo (`UPLOAD_*_MB`), o Nginx con `client_max_body_size` menor que `MAX_UPLOAD_MB` | Ajusta el tope del tipo y, si hace falta, `MAX_UPLOAD_MB` y Nginx |
| "El contenido del archivo no corresponde a su extensión" | Archivo renombrado (p. ej. un `.webp` guardado como `.png`) | Exportarlo de nuevo en el formato correcto |
| Estudiantes que no logran conectarse a la sala con muchas personas | Más conexiones que `GUNICORN_THREADS` | Sube `GUNICORN_THREADS` (no `workers`) |
| La subida falla sin mensaje de la app | Nginx corta en 1 MB por defecto | `client_max_body_size 201m;` |
| `database is locked` en el log | Más escrituras simultáneas de las que soporta la fase | Revisa §8; es un disparador de migración |
| `/healthz` responde `db_unavailable` (503) | Disco lleno o volumen no montado | `df -h`; revisa el montaje de `/data` |
| No se puede borrar un profesor | Tiene contenido (§4.3) | Cámbiale la contraseña |
| No se puede borrar una pregunta o un examen | Protección del historial (RN-10, RN-13) | Explicado en el Manual de usuario |

---

## 10. Listas de verificación

### Antes de abrir a usuarios reales

- [ ] `APP_ENV=preproduction` y secretos reales guardados en un gestor de secretos
- [ ] HTTPS funcionando y redirección de `http` a `https`
- [ ] `/healthz` monitoreado con alerta
- [ ] Respaldo diario + copia a Cloud Storage + snapshot de disco; **simulacro semanal programado (§5.3) y una restauración completa hecha**
- [ ] Prueba de carga repetida en la VM real (`scripts/loadtest/`, ver la Auditoría §6) para confirmar el tope de envíos simultáneos
- [ ] Variables `LEGAL_*` con los datos reales del responsable; revisar cómo se ven `/terminos` y `/politica-de-datos`
- [ ] **Términos y política validados por un abogado** (Ley 1581; SRS §8). Si cambian, subir `LEGAL_VERSION`
- [ ] Cron de anonimización de invitados (§4.5) y persona responsable de incidentes designada (§6.2)
- [ ] Decidido si habrá menores de edad (RL-05)
- [ ] Decidido si se abre el auto-registro de profesores (§4.2)
- [ ] Profesores informados de las limitaciones (Manual de usuario §4), en especial que no hay temporizador
- [ ] `MAIL_*` configurado y probado: pide una recuperación de contraseña y comprueba que llega el correo
- [ ] Secreto `GITGUARDIAN_API_KEY` configurado en GitHub y job **Secret scan (GitGuardian)** en verde (§6.1)
- [ ] Incidentes abiertos en GitGuardian revisados y cerrados

### Cada mes

- [ ] Revisar el uso de disco y el tamaño de la base
- [ ] Revisar los logs en busca de `database is locked` o errores 500
- [ ] Contrastar el uso real con los disparadores de migración (§8)

### Cada semana

- [ ] Revisar que el simulacro automático (§5.3) haya salido `"ok": true`

### Cada trimestre

- [ ] Restauración completa en una VM de prueba, con archivos subidos (§5.2)
- [ ] Actualizar dependencias con parches de seguridad y correr `pytest`
