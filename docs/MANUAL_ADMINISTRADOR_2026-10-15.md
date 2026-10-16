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

    client_max_body_size 50m;          # igual a MAX_UPLOAD_MB; el default de Nginx (1 MB) rompe las subidas

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
| `PROXY_FIX_HOPS` | No | `1` | Número de proxies delante de la app |
| `ALLOW_INSTRUCTOR_SIGNUP` | No | `false` | `true` permite que cualquiera se registre como profesor |
| `SESSION_COOKIE_SECURE` | No | `true` | Ponlo en `false` **solo** para pruebas locales sin HTTPS |
| `MAX_UPLOAD_MB` | No | `50` | Tamaño máximo por archivo (ajusta también Nginx) |
| `MIN_PASSWORD_LENGTH` | No | `8` | Contraseña mínima |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCKOUT_SECONDS` | No | `5` / `900` | Bloqueo por intentos fallidos |
| `SOCKETIO_CORS_ORIGINS` | No | vacío | Solo si el frontend se sirve desde otro dominio |
| `GUNICORN_THREADS` | No | `64` | Hilos del único worker |
| `SUPERUSER_RESET_ON_BOOT` | No | `false` | `true` reescribe la clave del superusuario desde el entorno en cada arranque (§4.4) |
| `SEED_DEMO_DATA` | No | `false` | Crea un profesor y un examen de demostración |

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

El panel aún no permite restablecer contraseñas ni cambiar roles. Se hace desde el servidor:

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

Cada ingreso por código crea un usuario estudiante sin correo, que no se borra solo. Es normal ver crecer el contador de estudiantes. Política pendiente: anonimizarlos a los 90 días (requisito legal RL-10).

---

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

**Simulacro:** restaura un respaldo en una VM de prueba **cada trimestre** (requisito RNF-15). Un respaldo que nunca se restauró no está probado.

---

## 6. Monitoreo y logs

| Qué | Cómo |
|---|---|
| Disponibilidad | Chequeo de disponibilidad de GCP (*Uptime check*) contra `https://<dominio>/healthz`, cada minuto, con alerta por correo |
| Logs | `docker logs -f mytraining` (accesos y errores de Gunicorn) |
| Eventos de sala | Líneas `[JOIN]`, `[START]`, `[PAUSE]`, `[RESUME]`, `[LEAVE]` y `[ALERT]` en el log |
| Disco | Alerta de GCP al 80 % de uso del disco persistente |
| Señales de que toca crecer | `database is locked` en los logs; quejas de envíos lentos con salas grandes (§8) |

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

Las columnas nuevas de la base se agregan solas al arrancar (`ensure_schema`). Si una actualización falla, vuelve a la versión anterior con `git checkout <commit>`, reconstruye y restaura el respaldo previo (§5.2).

---

## 8. Capacidad y límites

| Límite | Valor | Qué decir al cliente |
|---|---|---|
| Envíos simultáneos por instancia | ~45 en el mismo segundo con respuesta ≤ 2 s | "Salas de hasta 100 estudiantes; si todos envían a la vez, la confirmación puede tardar unos segundos, pero no se pierde" |
| Workers / instancias | 1 / 1 | **Nunca subas `workers` en `gunicorn.conf.py`:** las salas dejarían de funcionar |
| Archivos | 50 MB | Videos largos en YouTube/Vimeo |
| Disponibilidad | ~99 % mensual | Mantenimientos fuera de horario |

**Cuándo pasar a PostgreSQL + Redis + varias instancias:** cuando se cumpla cualquiera de los disparadores del [SAD §12.3](SAD_2026-10-15.md#123-disparadores-para-pasar-a-producción): salas que necesiten más de ~45 envíos simultáneos, un contrato con SLA ≥ 99,5 %, errores `database is locked`, o ingresos que cubran al menos 3 veces el costo mensual nuevo.

---

## 9. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| El contenedor se detiene al arrancar con `Configuración insegura…` | `SECRET_KEY` o `SUPERUSER_PASSWORD` de ejemplo, o `SECRET_KEY` de menos de 32 caracteres | Define valores reales (§2.2) |
| El login "no hace nada" y vuelve a pedir credenciales | Se entra por `http://`; la cookie `Secure` no se guarda | Entra por HTTPS. Solo en pruebas locales: `SESSION_COOKIE_SECURE=false` |
| "Demasiados intentos fallidos" (429) | 5 fallos en 15 min | Esperar. Reiniciar el contenedor también limpia el bloqueo |
| Las salas no se actualizan en vivo / el estudiante no ve "Conectado a la sala" | El proxy no reenvía `Upgrade`/`Connection` o `X-Forwarded-Proto` | Revisa la configuración de §2.3 |
| "La página caducó o el formulario no es válido" | Token CSRF ausente o sesión expirada; o la `SECRET_KEY` cambió | Recargar la página. Si le pasa a todos tras un despliegue, revisa que la `SECRET_KEY` sea la misma |
| Error 413 o "Archivo demasiado grande" | Archivo > `MAX_UPLOAD_MB`, o Nginx con `client_max_body_size` menor | Ajusta ambos valores |
| La subida falla sin mensaje de la app | Nginx corta en 1 MB por defecto | `client_max_body_size 50m;` |
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
- [ ] Respaldo diario + copia a Cloud Storage + snapshot de disco; **un simulacro de restauración hecho**
- [ ] Prueba de carga repetida en la VM real (`scripts/loadtest/`, ver la Auditoría §6) para confirmar el tope de envíos simultáneos
- [ ] **Política de tratamiento de datos publicada y casilla de autorización** (Ley 1581; SRS §8, RL-01 a RL-03). Validada por un abogado
- [ ] Decidido si habrá menores de edad (RL-05)
- [ ] Decidido si se abre el auto-registro de profesores (§4.2)
- [ ] Profesores informados de las limitaciones (Manual de usuario §4), en especial que no hay temporizador

### Cada mes

- [ ] Revisar el uso de disco y el tamaño de la base
- [ ] Revisar los logs en busca de `database is locked` o errores 500
- [ ] Contrastar el uso real con los disparadores de migración (§8)

### Cada trimestre

- [ ] Simulacro de restauración
- [ ] Actualizar dependencias con parches de seguridad y correr `pytest`
