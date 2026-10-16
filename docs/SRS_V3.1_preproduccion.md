# Especificación de Requisitos de Software (SRS) — V3.1 pre-producción

**Proyecto:** Plataforma de Capacitación y Evaluación En Línea (MyTraining)
**Fecha:** 16 de octubre de 2026
**Versión:** 3.1. Actualiza el *SRS V3 y Auditoría* del 29 de septiembre de 2026; los requisitos se conservan con su numeración.
**Documentos relacionados:** `SAD_V3_preproduccion.md`, `AUDITORIA_PREPRODUCCION.md`

---

## 1. Qué cambia respecto al V3

1. **Nueva fase: pre-producción.** El sistema opera con usuarios reales sobre una sola instancia y SQLite, hasta que la base de usuarios pague PostgreSQL (SAD V3 §12.3). Algunos RNF del V3 se separan en *meta de pre-producción* y *meta de producción* (§4).
2. **Estados actualizados.** Se cerró la Fase 1 de seguridad del V3 §9 completa y las reglas RN-09, RN-10 y RN-12.
3. **Nueva regla RN-13.** Recupera la RN-04 del SRS V2 (protección contra borrado de preguntas con historial), que el V3 había reemplazado por otra regla con el mismo número.
4. **Límites medidos.** RNF-08 ya tiene medición (§4).

**Resumen:**

| Grupo | Cumple | Parcial | No cumple / no existe | Sin medir |
|---|---:|---:|---:|---:|
| RF (30) | 14 | 11 | 5 | — |
| RNF (18) | 8 | 3 | 4 | 3 |
| RN (13) | 6 | 3 | 4 | — |

---

## 2. Alcance de la fase pre-producción

**Entra:** todo lo marcado como *Cumple*, con los límites de §5. Una organización piloto, salas de hasta ~45 envíos simultáneos y archivos de hasta 50 MB.

**Bloquea abrir a usuarios reales (ver §6):** los requisitos legales RL-01, RL-02 y RL-03.

**Se aplaza a producción:** RNF-13 (Alembic), RNF-14 (multi-worker con Redis) y la disponibilidad del 99,5 %.

---

## 3. Requisitos funcionales — estado

| ID | Requisito | Prioridad | V3 (29 sep) | **V3.1 (16 oct)** | Nota |
|---|---|---|---|---|---|
| RF-001 | Crear examen | Must | Parcial | Parcial | `passing_score` aún no editable en la UI |
| RF-002 | Editar examen | Must | Parcial | Parcial | Falta bloquear la edición con sala en curso (RN-04) |
| RF-003 | Archivar / eliminar | Must | Parcial | **Cumple** | El borrado definitivo se rechaza si hay intentos (RN-10) |
| RF-004 | Crear preguntas | Must | Parcial | Parcial | `short_answer` sin calificación |
| RF-005 | Banco de preguntas | Should | Parcial | Parcial | Sin etiquetas ni dificultad |
| RF-006 | Asociar preguntas | Must | Cumple | Cumple | |
| RF-007 | Presentar examen | Must | Parcial | Parcial | **Sin temporizador** visible ni validado en el servidor |
| RF-008 | Calificar automáticamente | Must | Cumple | Cumple | Medido: 40 ms por envío aislado |
| RF-009 | Retroalimentación | Must | Parcial | **Cumple** | `/resultados/<id>` solo para el dueño, su profesor o un admin |
| RF-010 | Recursos multimedia | Should | Parcial | Parcial | Subida restringida a instructores; sin biblioteca de recursos |
| RF-011 | Preguntas en video | Must | No cumple | No cumple | |
| RF-012 | Mostrar resultados | Must | Cumple | Cumple | |
| RF-013 | Historial | Must | Parcial | Parcial | Sin vista "Mis intentos" |
| RF-014 | Importar CSV/Excel | Must | Parcial | Parcial | Sin validación previa (RN-03) |
| RF-015 | Salas en vivo | Must | Cumple | Cumple | Control de sala restringido al profesor dueño, también por socket |
| RF-016 | Modos de examen | Should | Cumple | Cumple | |
| RF-017 | Ingreso como invitado | Should | Parcial | Parcial | Falta aceptar el aviso de privacidad (RL-01) |
| RF-018 | Monitoreo de sala | Should | Cumple | Cumple | Estadísticas solo para el profesor autenticado |
| RF-019 | Instantánea de preguntas | Must | Cumple | Cumple | |
| RF-020 | Capacitaciones | Must | Cumple | Cumple | |
| RF-021 | Importar / exportar capacitaciones | Could | Cumple | Cumple | La exportación ya no deja copias en una carpeta pública |
| RF-022 | Refuerzo automático | Should | Parcial | Parcial | Umbral fijo de 40 % (RN-07) |
| RF-023 | Encuestas en vivo | Could | Cumple | Cumple | |
| RF-024 | Clases y grupos | Should | Cumple | Cumple | |
| RF-025 | Exportaciones | Should | Cumple | Cumple | |
| RF-026 | Gestión de usuarios | Must | Parcial | Parcial | RN-09 aplicada; falta desactivar y cambiar el rol desde el panel |
| RF-027 | Calificación manual | Should | No existe | No existe | |
| RF-028 | Recuperar contraseña | Must | No existe | No existe | Requiere un proveedor de correo |
| RF-029 | Derechos del titular | Must | No existe | No existe | Bloqueante legal (RL-03) |
| RF-030 | Auditoría | Should | No existe | No existe | |

---

## 4. Requisitos no funcionales — estado y metas por fase

| ID | Requisito (resumen) | V3 | **V3.1** | Meta pre-producción | Meta producción |
|---|---|---|---|---|---|
| RNF-01 | Hash estándar y mínimo de 8 caracteres | Parcial | **Cumple** | `scrypt`, mínimo 8 | = |
| RNF-02 | Secretos solo por entorno; arranque bloqueado con valores de ejemplo; superusuario sin reescritura | No cumple | **Cumple** | = | = |
| RNF-03 | CSRF en todo POST | No cumple | **Cumple** | Verificado con test y en Chromium (formularios, `form.submit()`, `fetch`) | = |
| RNF-04 | Acceso por rol y propiedad en rutas y sockets | Parcial | **Cumple** | Tests de acceso cruzado = 403, también por socket | = |
| RNF-05 | Cookies `Secure`, `HttpOnly`, `SameSite=Lax`; HTTPS | No configurado | **Cumple** | HTTPS en el proxy inverso; HSTS | = |
| RNF-06 | 5 fallos de login en 15 min | No existe | **Cumple** | Por IP+correo, en memoria | En Redis (varios workers) |
| RNF-07 | Lista blanca y tamaño máximo de archivos | Parcial | Parcial | 50 MB por petición para todo tipo | 200 MB video / 10 MB imagen |
| RNF-08 | p95 < 1,5 s con 100 estudiantes simultáneos | Sin medir | **Medido: no cumple en ráfaga** | **p95 ≤ 2 s hasta ~45 envíos simultáneos** (medido: 50 → 2,2 s; 30 → 1,4 s) | 100 simultáneos con p95 < 1,5 s (requiere RNF-14) |
| RNF-09 | Eventos de sala en < 2 s | Sin medir | Sin medir | = | = |
| RNF-10 | Usable desde 360 px | Cumple | Cumple | | |
| RNF-11 | WCAG 2.1 AA | Sin medir | Sin medir | | Obligatorio si el cliente es público (RL-13) |
| RNF-12 | Compatibilidad de navegadores | Sin verificar | Sin verificar | Chromium verificado en E2E | Matriz completa |
| RNF-13 | Migraciones con Alembic | No cumple | No cumple | Aplazado; preparar antes de migrar | Obligatorio |
| RNF-14 | Estado de salas compartido entre workers | No cumple | No cumple (**por diseño**) | 1 worker (SAD ADR-005/006) | Redis |
| RNF-15 | Disponibilidad, `/health`, respaldos | No cumple | Parcial | **~99 % mensual**; `/healthz`; respaldo diario con 30 días de retención (`scripts/backup_sqlite.py`). Falta el simulacro de restauración | 99,5 % con 2 instancias |
| RNF-16 | Cobertura ≥ 70 % y CI | Parcial | Parcial | 33 tests; sin `__pycache__` versionado; sin CI ni cobertura | = |
| RNF-17 | Logs estructurados | No existe | No existe | | |
| RNF-18 | Python 3.13, dependencias fijadas, Gunicorn, debug desactivado | Parcial | **Cumple** | `Dockerfile`, `gunicorn.conf.py`, `requirements.txt` fijado | = |

---

## 5. Límites de la fase pre-producción

Estos límites son parte del contrato de servicio de la fase y deben comunicarse al cliente piloto.

| Límite | Valor | Configurable con |
|---|---|---|
| Envíos simultáneos de examen por instancia (ráfaga) | ~45 para p95 ≤ 2 s | — (escala solo al pasar a producción) |
| Estudiantes por sala con envíos escalonados | 100 | — |
| Instancias / workers | 1 / 1 (64 hilos) | `GUNICORN_THREADS` |
| Tamaño máximo por archivo subido | 50 MB | `MAX_UPLOAD_MB` |
| Intentos de login | 5 fallos / 15 min | `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_SECONDS` |
| Contraseña mínima | 8 caracteres | `MIN_PASSWORD_LENGTH` |
| Disponibilidad | ~99 % mensual | — |
| Retención de respaldos | 30 días | `--keep-days` |
| Auto-registro de profesores | Desactivado | `ALLOW_INSTRUCTOR_SIGNUP` |

---

## 6. Reglas de negocio — estado

| ID | Regla | V3 | **V3.1** |
|---|---|---|---|
| RN-01 | Límite de intentos al abrir y al enviar, por examen | Parcial | Parcial (solo al enviar y por sesión) |
| RN-02 | Pausa del video en la marca de tiempo | No cumple | No cumple |
| RN-03 | Validar la importación antes de insertar | No cumple | No cumple |
| RN-04 | No editar un examen con sala en curso | No cumple | No cumple |
| RN-05 | No calificar envíos fuera de tiempo (+30 s) | No cumple | No cumple (depende de RF-007) |
| RN-06 | Calificar sobre la instantánea | Cumple | Cumple |
| RN-07 | Mismo umbral para aprobar y para el refuerzo | Parcial | Parcial |
| RN-08 | Respuestas abiertas fuera de la nota hasta calificarlas | Parcial | Parcial |
| RN-09 | Solo un admin asigna el rol instructor | No cumple | **Cumple** (configurable con `ALLOW_INSTRUCTOR_SIGNUP` si el negocio lo decide; ver §8) |
| RN-10 | Examen con intentos: se archiva, no se borra | No cumple | **Cumple** |
| RN-11 | Un voto por encuesta | Cumple | Cumple |
| RN-12 | Sala finalizada: sin ingresos ni envíos | Parcial | **Cumple** |
| **RN-13** | *(nueva; = RN-04 del SRS V2)* Una pregunta o un banco con respuestas registradas, o en un examen activo, no se elimina | — | **Cumple** |

---

## 7. Requisitos legales

Sin cambios de estado respecto al V3 §7. Para pre-producción con datos reales son **bloqueantes** RL-01 (autorización), RL-02 (política publicada) y RL-03 (derechos del titular, RF-029). RL-10 (anonimizar invitados a los 90 días) pasa a ser *Should* en esta fase, porque cada ingreso por código crea un usuario nuevo.

> Igual que el V3: esta sección es una guía técnica, no asesoría jurídica.

---

## 8. Decisión pendiente del negocio: auto-registro de profesores

RN-09 protege la plataforma, pero choca con la estrategia de crecimiento: si los profesores son quienes eligen la herramienta, el auto-registro es el embudo de adquisición. El código soporta ambos caminos con `ALLOW_INSTRUCTOR_SIGNUP`:

- **`false` (por defecto en pre-producción):** el administrador crea cada profesor. Adecuado para un piloto con una organización.
- **`true`:** cualquiera se registra como profesor y recibe su banco por defecto. Antes de activarlo conviene tener RF-028 (recuperar contraseña) y una verificación de correo, para no acumular cuentas falsas.

---

## 9. Criterios de aceptación — estado

| ID | Criterio | V3.1 |
|---|---|---|
| CA-01 (V2) | Calificar en menos de 2 s | Cumple hasta ~45 envíos simultáneos (AUDITORIA §4) |
| CA-01 (V3) | Previsualización y reporte de errores CSV | No cumple |
| CA-02 | Video fluido con cuestionarios | Parcial |
| CA-03 | Calificación inmediata | Cumple |
| CA-04 (V2) | Historial refleja cada intento | Parcial (sin vista de estudiante) |

---

## 10. Plan de cierre actualizado

**Fase 1 — Seguridad.** ✅ Completa (ver `AUDITORIA_PREPRODUCCION.md` §2).

**Fase 2 — Legal mínimo.** Bloquea abrir a usuarios reales. Sin avance.

**Fase 3 — Must funcionales**, en orden sugerido por impacto y costo:

1. RF-007 / RN-05: temporizador y validación en el servidor. Hace falta antes de tomar exámenes con nota.
2. RF-014 / RN-03: importación en dos pasos.
3. RN-04 y RN-07.
4. RF-013: vista "Mis intentos".
5. RF-011 / RN-02: pausa del video.
6. RF-028: recuperar contraseña.

**Fase 3b — Rendimiento sin costo.** Optimizar `submit_exam` para subir el tope de §5 antes de gastar en infraestructura.

**Fase 4 — Producción.** Se ejecuta solo al cumplirse un disparador del SAD V3 §12.3: Alembic, PostgreSQL, Redis, 2 o más instancias y Cloud Storage.
