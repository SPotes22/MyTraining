# 🐙 MyTraining — exámenes en vivo, con sabor a Socrative

> Módulo de exámenes tipo Socrative, montado sobre Flask + Jinja + Socket.IO, pero con una piel visual rediseñada para que se sienta tan simple e intuitiva como la referencia real que nos pidió el cliente.

![banner](docs/images/banner.svg)

![python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![flask](https://img.shields.io/badge/flask-3.0-000000?logo=flask&logoColor=white)
![socketio](https://img.shields.io/badge/realtime-Socket.IO-2ab6d1?logo=socketdotio&logoColor=white)
![status](https://img.shields.io/badge/estado-en%20construcci%C3%B3n%20activa-f4823a)
![vibes](https://img.shields.io/badge/vibes-asarosas-4caf50)

---

## ✨ ¿Qué es esto?

Es la **segunda versión del frontend** de `modular_exams`: mismo backend, misma base de datos, mismas rutas — pero con el constructor de exámenes, la sala en vivo y los reportes redibujados para que se parezcan (en flujo y en sensación) a la app real de Socrative que el profe ya usa a diario.

No es un clon 1:1 del código de Socrative (eso ni es legal ni el punto). Es **nuestra** app, con **nuestros** datos, imitando lo que sí funciona bien de su UX: título editable, opciones con letras, correcta en verde, botones tipo píldora y una barra de acciones que no marea.

## 🖼️ Cómo se ve

### Constructor de examen
Título editable, preguntas con opciones lettradas (A, B, C…), la correcta resaltada en verde, y un riel de iconos compacto para editar / mover / duplicar / eliminar.

![constructor](docs/images/builder.svg)

### Resultados en vivo (Live Results)
La matriz de la sesión ahora se ve como el "Live Results" real: encabezados de pregunta con color, celdas verde/rojo con la respuesta del estudiante, y tres switches (nombres / respuestas / resultados) para presentar en clase sin regar el chisme antes de tiempo.

![live results](docs/images/live-results.svg)

### Presentar examen (vista del estudiante)
Puntos de progreso clicables arriba de cada pregunta — de un vistazo sabes qué falta, sin importar si el orden es aleatorio. El botón de enviar ya no se esconde en la última pregunta.

![progreso del estudiante](docs/images/student-progress.svg)

> Las imágenes son mockups ilustrativos hechos a mano con los mismos tokens de color de `base.html` — no capturas de la app real de Socrative (esa la dejamos quietecita, allá en su dominio, con copyright y todo).

## 🧠 Qué trae por debajo

- **Banco de preguntas** con 6 tipos: selección única, selección múltiple, verdadero/falso, respuesta abierta, emparejamiento y ordenamiento.
- **Constructor único** por examen: agrega desde el banco, al azar, o crea preguntas nuevas con píldoras de "agregar en blanco".
- **Salas en vivo** con Socket.IO: orden original o aleatorio, pausa/reanuda, preguntas guiadas por el profesor.
- **Reportes** con matriz de resultados, desglose por pregunta y por estudiante, exportación a Excel, y ahora la vista tipo "Live Results".
- **Retroalimentación automática**: genera un curso de refuerzo en Learning Builder para quienes saquen menos del 40%.

## 🛠️ Cómo levantarlo en local

```bash
python -m venv venv
./venv/Scripts/activate        # en Windows (Git Bash: source venv/Scripts/activate)
pip install -r requirements.txt
cp env.example .env
python run.py
```

Y ya, entras a `http://127.0.0.1:5000`. La primera vez créate una cuenta de tipo **Profesor / Instructor** desde "Crear Cuenta".

### Correr las pruebas

```bash
pytest
```

## 🎨 Sistema de diseño

Todo el rediseño vive en un puñado de clases nuevas dentro de [`app/templates/base.html`](app/templates/base.html), con prefijo `soc-` (de socrative, no de "socio" 😉):

| Token | Para qué |
|---|---|
| `--primary` (cian) | botones de acción, iconos, enlaces |
| `--accent-orange` | CTAs principales ("Crear sala en vivo", logo) |
| `--success` (verde) | respuestas correctas, toggles activos |
| `.soc-btn-pill-*` | botones tipo píldora |
| `.soc-opt-badge` | círculos con letras (A, B, C…) de las opciones |
| `.soc-icon-rail` / `.soc-icon-btn` | riel de acciones compacto por pregunta |
| `.soc-live-*` | grilla de resultados en vivo |
| `.step-dot` | puntos de progreso en la vista del estudiante |

## 📌 Notas honestas

- Este repo **no comparte historial ni remoto** con `modular_exams` — se sembró como copia independiente a propósito.
- El diseño se inspira en capturas reales que el cliente compartió de su propia cuenta de Socrative, usadas solo como referencia visual — no se reutiliza marca, logo ni código de Socrative/Showbie.
- Sigue en construcción: biblioteca, clases y salas heredan la paleta nueva pero aún no tienen el mismo rediseño de layout que el constructor y los reportes.

---

Hecho con 🧉, muchos `git commit` y cero paciencia por los botones que se esconden cuando no deberían.
