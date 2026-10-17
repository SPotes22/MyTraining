"""RNF-09: ¿los eventos de sala (pausa, reanudación, fin) llegan a todos en < 2 s?

N estudiantes y el profesor se conectan por Socket.IO (websocket) a la sala LOAD01
sembrada por seed_load.py. El profesor pausa, reanuda y finaliza; se mide cuánto tarda
cada evento en llegar a cada estudiante. Con --answers, todos los estudiantes envían
una respuesta justo antes de cada evento (sala ocupada, el peor caso realista).

Uso (con LOADTEST_PASSWORD y la base sembrada, ver docs/AUDITORIA_PREPRODUCCION.md §6):
    python scripts/loadtest/room_events.py http://127.0.0.1:8080 100 <session_id> [--answers]
Requiere requirements-dev.txt (python-socketio como cliente: requests + websocket-client).
"""
import os
import re
import statistics
import sys
import threading
import time

import requests
import socketio

base, N, session_id = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
with_answers = '--answers' in sys.argv
PW = os.environ['LOADTEST_PASSWORD']
ROOM = 'LOAD01'
EVENTS = ('exam_paused', 'exam_resumed', 'exam_closed')
received = {ev: {} for ev in EVENTS}
lock = threading.Lock()


def login(email):
    http = requests.Session()
    page = http.get(base + '/login', timeout=30).text
    token = re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)
    http.post(base + '/login', data={'email': email, 'password': PW, 'csrf_token': token},
              allow_redirects=False, timeout=30)
    return http, token


def student(i, ready):
    http, _ = login(f's{i}@x.com')
    sio = socketio.Client(http_session=http, reconnection=False)
    for ev in EVENTS:
        sio.on(ev, (lambda ev: lambda *_: _mark(ev, i))(ev))
    sio.connect(base, transports=['websocket'], wait_timeout=30)
    sio.emit('student_join', {'room_code': ROOM})
    ready.append(sio)
    return sio


def _mark(ev, i):
    with lock:
        received[ev].setdefault(i, time.perf_counter())


def answer_all(clients, qid, opt):
    for sio in clients:
        sio.emit('answer_submitted', {'room_code': ROOM, 'question_id': qid, 'answer': {'selected_option_id': opt}})


def measure(ev, trigger, clients, answer):
    if answer:
        answer_all(clients, *answer)
    t0 = time.perf_counter()
    trigger()
    deadline = t0 + 15
    while time.perf_counter() < deadline and len(received[ev]) < N:
        time.sleep(0.01)
    lat = sorted(t - t0 for t in received[ev].values())
    if not lat:
        return f'{ev:13s} recibido=0/{N}'
    return (f'{ev:13s} recibido={len(lat)}/{N} p50={statistics.median(lat):.3f}s '
            f'p95={lat[int(.95 * (len(lat) - 1))]:.3f}s max={lat[-1]:.3f}s')


ready = []
threads = [threading.Thread(target=student, args=(i, ready)) for i in range(N)]
for t in threads:
    t.start()
for t in threads:
    t.join()
print(f'conectados={len(ready)}/{N}')

thttp, ttoken = login('t@x.com')
teacher = socketio.Client(http_session=thttp, reconnection=False)
teacher.connect(base, transports=['websocket'], wait_timeout=30)
teacher.emit('teacher_join', {'room_code': ROOM})
time.sleep(1.0)  # que se asienten las uniones antes de medir

answer = None
if with_answers:
    # Primera pregunta y opción del examen sembrado (seed_load imprime question:option).
    pairs = [p for p in sys.argv[4:] if ':' in p]
    answer = tuple(int(x) for x in pairs[0].split(':')) if pairs else None

print(measure('exam_paused', lambda: teacher.emit('pause_exam', {'room_code': ROOM}), ready, answer))
print(measure('exam_resumed', lambda: teacher.emit('resume_exam', {'room_code': ROOM}), ready, answer))
print(measure('exam_closed', lambda: thttp.post(f'{base}/exam/close/{session_id}', data={'csrf_token': ttoken},
                                                allow_redirects=False, timeout=30), ready, answer))
for sio in ready + [teacher]:
    sio.disconnect()
