# Manual de usuario — MyTraining

**Fecha:** 15 de octubre de 2026 (actualizado el 17 de octubre: preguntas durante el video) · **Versión de la app:** pre-producción
**Para:** profesores/instructores y estudiantes. La administración de la plataforma está en el [Manual de administrador](MANUAL_ADMINISTRADOR_2026-10-15.md).

---

## Contenido

1. [Primeros pasos](#1-primeros-pasos)
2. [Guía del estudiante](#2-guía-del-estudiante)
3. [Guía del profesor](#3-guía-del-profesor)
   - 3.1 Banco de preguntas · 3.1.1 Preguntas durante un video · 3.2 Importar desde Excel/CSV · 3.3 Crear un examen · 3.4 Aplicar el examen en vivo · 3.5 Resultados y reportes · 3.6 Clases · 3.7 Capacitaciones · 3.8 Refuerzo automático · 3.9 Preguntas rápidas y encuestas
4. [Lo que todavía no hace la plataforma](#4-lo-que-todavía-no-hace-la-plataforma)
5. [Preguntas frecuentes](#5-preguntas-frecuentes)

---

## 1. Primeros pasos

### 1.1 Requisitos

- Un navegador actualizado: Chrome, Firefox, Edge o Safari, en computador, tableta o celular.
- Conexión a Internet estable durante los exámenes en vivo.

### 1.2 Tipos de cuenta

| Cuenta | Cómo se obtiene | Qué puede hacer |
|---|---|---|
| **Estudiante** | **Crear Cuenta** en la página de inicio | Ver capacitaciones publicadas, presentar exámenes y ver sus resultados |
| **Invitado** | **Ingresar con Código**: solo nombre y código de sala, sin cuenta | Presentar el examen de esa sala |
| **Profesor / Instructor** | La crea el administrador. Si la plataforma tiene activo el auto-registro, también aparece la opción **Profesor / Instructor** en **Crear Cuenta** | Todo lo de la sección 3 |

### 1.3 Contraseña

- Mínimo **8 caracteres**.
- Tras **5 intentos fallidos** el inicio de sesión se bloquea **15 minutos**. Espera y vuelve a intentar, o pide ayuda al administrador.
- Por ahora no existe "Olvidé mi contraseña": el administrador debe ayudarte.

### 1.4 Si ves "La página caducó o el formulario no es válido"

Es una protección de seguridad. Recarga la página (F5) y repite la acción.

---

## 2. Guía del estudiante

### 2.1 Entrar a un examen en vivo

1. El profesor te da un **código de sala** de 6 caracteres, por ejemplo `K7Q2ZP`.
2. Entra en **Unirse a Examen** (o **Ingresar con Código** si no has iniciado sesión).
3. Escribe **Tu Nombre Completo** y el **Código de Sala**, y pulsa unirte.
4. Verás **"Esperando al profesor…"** hasta que el profesor inicie el examen.

> Si entras como invitado, cada ingreso crea un registro nuevo: usa siempre el mismo nombre y no cierres la pestaña durante el examen.

### 2.2 Presentar el examen

Según cómo lo configuró el profesor, verás uno de tres modos:

| Modo | Cómo se ve |
|---|---|
| **Feedback inmediato** | Una pregunta a la vez. Al responder ves si acertaste y pasas a la siguiente |
| **Navegación libre** | Puedes moverte entre preguntas con los **puntos de progreso** de arriba y cambiar respuestas antes de enviar |
| **Guiado por profesor** | Todos ven la misma pregunta; el profesor decide cuándo pasar a la siguiente |

Consejos:

- **Preguntas con video:** algunas preguntas aparecen mientras ves un video. Dale *play*: al llegar al minuto indicado el video se pausa y aparece la pregunta. Si recargas la página, las preguntas que ya aparecieron siguen visibles.
- **Tus respuestas se guardan solas.** Si se cae Internet o recargas la página, al volver aparecen como las dejaste.
- Los puntos de progreso muestran qué preguntas te faltan.
- En **selección múltiple** puedes marcar más de una opción.
- En **emparejamiento** elige la pareja de cada elemento; en **ordenamiento**, asigna la posición de cada ítem.
- Si aparece **"Examen pausado"**, espera: el profesor lo reanudará y podrás seguir.
- **No hay temporizador visible todavía.** Pregunta al profesor cuánto tiempo tienes.

### 2.3 Enviar y ver resultados

1. Pulsa el botón de enviar; está visible en todo momento, no solo en la última pregunta.
2. Verás el **Resumen de Evaluación** con tu nota y el **Desglose de Preguntas**: tu respuesta, la correcta y la explicación.
3. Las preguntas abiertas aparecen como **Pendiente**: las revisa el profesor y no suman a la nota automática.

Solo tú (y tu profesor) pueden ver tus resultados. Si la sala ya finalizó, no se reciben más envíos.

### 2.4 Capacitaciones (Mis cursos)

1. En **Mis cursos** ves las capacitaciones publicadas.
2. Abre una y avanza por sus módulos y lecciones: textos, imágenes, videos, PDF, audio y preguntas de práctica.
3. Tu progreso se guarda automáticamente.
4. Si reprobaste un examen con refuerzo activado, aparecerá aquí un **curso de refuerzo** con los temas que fallaste, cuando el profesor lo publique.

---

## 3. Guía del profesor

Menú del profesor: **Exámenes · Clases · Preguntas · Capacitaciones · Resultados · Historial**, y el indicador de **Salas Activas**. Al pulsar el logo vuelves al **Panel**.

### 3.1 Banco de preguntas (menú *Preguntas*)

1. **Crear un banco:** en *1. Crear Banco de Preguntas* escribe el **Nombre del Banco** (debe ser único) y una descripción. Al registrarte ya tienes un banco por defecto.
2. **Crear una pregunta:** en *Crear Pregunta en el Banco* elige el **Tipo de pregunta** y completa los campos:

| Tipo | Qué llenas |
|---|---|
| Opción múltiple / única | Enunciado, opciones y la respuesta correcta |
| Selección múltiple | Enunciado, opciones y todas las correctas |
| Verdadero / Falso | Enunciado y la correcta |
| Emparejamiento | Pares izquierda ↔ derecha (**Agregar par**) |
| Ordenamiento | Ítems en el orden correcto (**Agregar ítem**) |
| Respuesta abierta | Solo el enunciado; se revisa manualmente |
| Video | Como opción múltiple, más una **URL de Video** (YouTube, Vimeo o MP4). Ver §3.1.1 |

En todos los tipos puedes añadir **Categoría**, **Puntos**, **URL de Imagen** y **Retroalimentación** (máximo 3000 caracteres), que el estudiante verá al terminar.

3. **Buscar y filtrar:** usa *Buscar enunciado o categoría*, el filtro por banco y por tipo.
4. **Editar, duplicar o eliminar** desde cada tarjeta. Para borrar varias, marca **Seleccionar todo** o las casillas y elimina.

> **No se puede eliminar** una pregunta (ni el banco que la contiene) si ya tiene respuestas de estudiantes o está en un examen activo. Así se protege el historial. Quítala del examen o archiva el examen primero.

#### 3.1.1 Preguntas durante un video

Cualquier pregunta con **URL de Video** puede aparecer en un minuto concreto del video, en lugar de mostrarse desde el inicio:

1. En **URL de Video** pega un enlace de **YouTube** o **Vimeo**, un **MP4/WEBM** en `https://…`, o un archivo subido (`/static/uploads/…`). Otros tipos de enlace se rechazan por seguridad.
2. En *Pregunta durante el video* completa:
   - **Inicio del video:** desde dónde arranca (por ejemplo `0:30`). Opcional.
   - **Mostrar la pregunta en:** el minuto en que aparece (por ejemplo `1:35`). Debe ser posterior al inicio. Vacío = la pregunta se ve desde el principio.
   - **Pausar el video al mostrarla:** activado por defecto.
3. Guarda. El estudiante verá *"la pregunta aparecerá en el minuto 1:35"*; al llegar ahí, el video se pausa y aparece la pregunta.

Puedes escribir los tiempos en segundos (`95`) o en formato `mm:ss` / `h:mm:ss`. La pregunta no viaja en la página del estudiante: el servidor solo la entrega cuando ya pasó ese tiempo, así que no se puede leer antes adelantando la página.

> **Limitación actual:** el video se pausa al aparecer la pregunta, pero el estudiante puede volver a darle *play* sin responder.

### 3.2 Importar preguntas desde Excel o CSV

En *Importar Preguntas Excel / CSV*, elige el **banco destino** y el archivo (`.xlsx`, `.xls` o `.csv`). La primera fila debe tener exactamente estos encabezados:

| Columna | Obligatoria | Contenido |
|---|---|---|
| `statement` | Sí | Enunciado |
| `question_type` | No (por defecto `multiple_choice`) | `multiple_choice`, `true_false`, `video`, `matching`, `ordering`, `open_answer` |
| `category` | No | Categoría |
| `options` | Para opción múltiple, V/F y video | Opciones separadas por `\|`, por ejemplo `80\|443\|21` |
| `correct_option` | Para opción múltiple, V/F y video | **Posición** de la correcta, **empezando en 0** (`0` = la primera) |
| `pairs` | Para emparejamiento | `izquierda:derecha` separados por `\|`, por ejemplo `HTTP:80\|HTTPS:443` |
| `items` | Para ordenamiento | Ítems **en el orden correcto** separados por `\|` |
| `feedback_text`, `image_url`, `video_url` | No | Retroalimentación y enlaces (`video_url` debe ser `https://…` o `/static/…`; otra cosa se descarta) |
| `video_start`, `video_question_at` | No | Inicio del video y minuto en que aparece la pregunta (§3.1.1). Si los tiempos no son válidos, la pregunta se importa sin ellos |

Ejemplo (CSV):

```csv
statement,question_type,category,options,correct_option,feedback_text
¿Puerto por defecto de HTTP?,multiple_choice,Redes,80|443|21,0,El 80 es el estándar web sin cifrar.
Ordena las capas de abajo hacia arriba,ordering,Redes,,,
```

> **Cuidado (limitación actual):** el archivo no se valida antes de importar. Si una fila tiene un error, la importación puede detenerse a mitad y el mensaje no dice qué fila falló. Prueba primero con 2 o 3 filas. Las preguntas de **selección múltiple** no se pueden importar todavía.

### 3.3 Crear un examen (menú *Exámenes*)

1. Pulsa **Crear mi primer examen** (o crear nuevo examen), escribe el **Nombre del examen** y la **Duración sugerida**, y pulsa **Crear examen vacío**.
2. En el **constructor**:
   - Edita el título directamente arriba.
   - Agrega preguntas con los botones tipo píldora:
     - **Agregar desde el banco:** marca las preguntas y pulsa **Agregar seleccionadas**. No se duplican.
     - **Selección Aleatoria / Agregar al azar:** elige un banco y cuántas preguntas; no puedes pedir más de las disponibles.
     - **Agregar pregunta en blanco:** crea una pregunta nueva que queda en el banco y en el examen (**Guardar y agregar al examen**).
   - En cada pregunta, el riel de íconos permite **Editar pregunta**, **Mover arriba**, **Mover abajo**, **Duplicar en examen** y **Quitar del examen**.
   - Ajusta los **Puntos** de cada pregunta: el mismo reactivo puede valer distinto en exámenes distintos.
3. Configura el examen:
   - **Instrucciones para los alumnos**.
   - **Modo de Evaluación:** *Feedback Inmediato*, *Navegación Libre* o *Guiado por Profesor* (ver §2.2).
   - **Permitir múltiples intentos por estudiante** y **Límite de intentos**.
   - **Retroalimentación automática:** activa el curso de refuerzo (§3.8).
4. Desde la biblioteca puedes **Duplicar**, **Editar**, **Exportar** (*Sin respuestas (Para imprimir)* o *Con respuestas (Plantilla clave)*) y **Eliminar**.

**Eliminar vs. borrar definitivamente:**

- **Eliminar** mueve el examen a *Eliminados*; con **Restaurar** vuelve a la lista.
- **Eliminar de la BD** lo borra para siempre, **solo si nadie lo ha presentado**. Si tiene intentos, se queda archivado para no perder el historial.

> **No edites un examen ni sus preguntas mientras una sala suya está abierta.** Los estudiantes siguen viendo el texto original, pero la calificación usa la respuesta correcta actual: si cambias la clave a mitad de sala, quienes envíen después se califican con la nueva. Las notas ya enviadas no cambian.

### 3.4 Aplicar el examen en vivo

1. En la biblioteca pulsa **Iniciar sala en vivo** (o **Crear sala**).
2. Elige el **orden de las preguntas** (original o aleatorio) y, si quieres, cuántos estudiantes esperas (sirve para ver el avance y cerrar sola la sala cuando todos envíen). Pulsa **Crear sala**.
3. En el **lobby** verás:
   - el **código de sala** para compartir (en el tablero o por chat);
   - **Estudiantes en Vivo**, que aparecen al conectarse, con cuántas preguntas ha respondido cada uno;
   - **Exámenes Entregados**;
   - el panel **Alertas Anti-Cheat**, que por ahora queda vacío: la detección todavía no está conectada (§4).
4. Pulsa **Iniciar Examen**. Durante la sala:
   - **Pausar / Reanudar:** congela la pantalla de todos al instante.
   - **Siguiente Pregunta:** solo en modo *Guiado por Profesor*.
   - **Finalizar:** cierra la sala; nadie más puede entrar ni enviar.

> **Tamaño de sala recomendado en esta fase:** hasta 100 estudiantes conectados. Si más de ~45 envían en el mismo segundo, los envíos tardan más de 2 s (no se pierden). Ver el [SRS §10](SRS_2026-10-15.md#10-límites-de-la-fase-pre-producción).

> **Finaliza solo cuando todos hayan enviado.** Tras finalizar, los envíos se rechazan.

### 3.5 Resultados y reportes

- **Historial:** todas tus salas. Abre una para ver su **reporte**:
  - indicadores (promedio, mínimo, máximo, aprobación);
  - **matriz de resultados en vivo**: estudiante × pregunta, verde = correcta, rojo = incorrecta. Haz clic en una celda para ver el **Detalle de Respuesta**;
  - interruptores **Mostrar nombres / Mostrar respuestas / Mostrar resultados**, para proyectar en clase sin revelar datos antes de tiempo;
  - descarga en **Excel** de toda la sala o de un estudiante.
- **Resultados:** todos los intentos, filtrables por asignatura (clase).

### 3.6 Clases (menú *Clases*)

Las clases son **carpetas** para organizar exámenes por grupo o asignatura:

1. **Nueva Carpeta de Clase**: escribe el nombre, la asignatura y una descripción, y pulsa **Crear Carpeta**.
2. En la carpeta, *Guardar un examen en esta carpeta* → **Guardar aquí**. El examen no se duplica: solo se relaciona.
3. **Quitar de esta carpeta** o **Eliminar Carpeta** no borran los exámenes.

### 3.7 Capacitaciones (menú *Capacitaciones*)

1. **Nueva Capacitación**: nombre, descripción y portada opcional.
2. **Abrir Editor de Bloques** para construir la **Estructura del Curso**: módulos → lecciones → bloques.
3. **Agregar Bloque** → *Seleccionar Tipo de Bloque*: título, texto, imagen, video, pregunta, separador, cita, PDF, descarga, audio o embebido. Cada bloque se configura en *Configurar Bloque*; puedes duplicarlo, reordenarlo u ocultarlo.
4. Los archivos se suben desde el bloque (máximo **50 MB**). Para videos largos usa YouTube o Vimeo.
5. **Vista Previa / Previsualizar** muestra el curso como lo verá el estudiante.
6. Cambia el estado a **publicado** para que aparezca en *Mis cursos*. En borrador solo lo ves tú.
7. **Exportar** descarga el curso completo en JSON; **Importar (JSON)** lo trae a tu cuenta. Sirve para copiar cursos entre plataformas. Las preguntas dentro de videos se conservan al duplicar o importar.

**Preguntas dentro de un video de la lección:**

1. Crea en la misma lección el bloque de **video** (YouTube, Vimeo o MP4/WEBM) y uno o más bloques de **pregunta**.
2. En la configuración del bloque de video, en **Preguntas dentro del video**, indica el **Inicio del video (mm:ss)** y, para cada pregunta, el minuto en que aparece y si se pausa el video (**Pausar el video al mostrar la pregunta**).
3. Al estudiante, esas preguntas se le muestran solo cuando el video llega a su minuto. Si ya las respondió antes, aparecen directamente.

> Solo tú (y los administradores) pueden editar tus capacitaciones. Mientras estén en borrador, sus preguntas no se entregan a nadie más.

### 3.8 Refuerzo automático

Si el examen tiene activada **Retroalimentación automática**, al **finalizar** la sala se crea una capacitación con las preguntas más falladas, organizadas por categoría, con explicación y práctica. Se asigna a quienes sacaron **menos del 40 %**.

El curso se crea en **borrador** para que lo revises: búscalo en *Capacitaciones* y **publícalo** para que los estudiantes lo vean en *Mis cursos*.

También puedes generarla a mano desde el reporte de la sala con **Generar Capacitación Automática**, y añadir estudiantes adicionales. Si se genera dos veces para la misma sala, no se duplica.

> El umbral de 40 % es fijo por ahora; no usa el puntaje mínimo del examen.

### 3.9 Preguntas rápidas y encuestas

Desde el **Panel** puedes lanzar a una sala activa (necesitas su código):

- **Pregunta rápida · V / F**
- **Pregunta rápida · Selección múltiple**
- **Pregunta rápida · Respuesta abierta**
- **Ticket de salida**, para cerrar la clase

Los estudiantes de esa sala la ven encima del examen y votan una sola vez. Tú ves los resultados en vivo y la cierras con **Cerrar poll**.

---

## 4. Lo que todavía no hace la plataforma

Conviene saberlo antes de usarla con nota real:

| Función | Situación | Qué hacer mientras tanto |
|---|---|---|
| Temporizador del examen | No hay contador ni cierre automático por tiempo | Controla el tiempo tú y usa **Finalizar** |
| Calificar respuestas abiertas | Quedan "Pendiente" y en 0 | Revísalas en el reporte y ajusta fuera de la plataforma |
| Respuesta corta autocalificada | No existe | Usa opción múltiple o abierta |
| Bloquear el video hasta responder | El video se pausa y aparece la pregunta, pero el estudiante puede reanudarlo sin contestar | Indica en las instrucciones que deben responder antes de continuar |
| Alertas antifraude | El panel existe, pero el examen no detecta el cambio de pestaña | Supervisa presencialmente |
| Validación de importación | No previsualiza ni detalla errores | Importa en lotes pequeños |
| Vista "Mis intentos" del estudiante | No existe | El estudiante ve su resultado al enviar |
| Recuperar contraseña | No existe | Pide ayuda al administrador |
| Puntaje mínimo de aprobación configurable | Fijo en 60 % (y 40 % para el refuerzo) | — |

---

## 5. Preguntas frecuentes

**Un estudiante dice que su respuesta desapareció.** Que recargue la página: las respuestas se restauran solas. Si entró como invitado con otro nombre, se le creó un registro distinto.

**Un estudiante no puede entrar a la sala.** Revisa que el código esté bien escrito y que la sala no esté finalizada.

**No puedo borrar una pregunta.** Tiene respuestas o está en un examen activo (§3.1). Archiva el examen o quítala de él.

**No me deja borrar definitivamente un examen.** Ya tiene intentos; queda archivado en *Eliminados* para proteger el historial.

**Subí un archivo y dice "Archivo demasiado grande".** El límite es 50 MB. Comprime el archivo o usa YouTube/Vimeo para el video.

**Me salió "Demasiados intentos fallidos".** Espera 15 minutos.

**¿Quién ve mis resultados?** Solo tú, el profesor dueño del examen y el administrador.
