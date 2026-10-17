"""Ráfaga de envíos: N estudiantes inician sesión y envían el examen en el mismo instante.

Uso: python scripts/loadtest/submit_burst.py http://127.0.0.1:8080 100 $(python scripts/loadtest/seed_load.py 100 | tail -1)
Requiere la misma LOADTEST_PASSWORD que seed_load.py.
Reporta errores y latencias p50/p95/máx. del POST /exam/submit (CA-01: <= 2 s).
"""
import os, re, sys, time, threading, urllib.request, urllib.parse, http.cookiejar, statistics
base, N, sid, pairs = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4:]
PW = os.environ['LOADTEST_PASSWORD']
answers = {f'question_{p.split(":")[0]}': p.split(":")[1] for p in pairs}
lat, errs = [], []
barrier = threading.Barrier(N)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
def run(i):
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), NoRedirect)
    # Token CSRF de la página (la app lo exige en todo POST).
    page = op.open(base + '/login', timeout=60).read().decode()
    token = re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)
    try: op.open(base+'/login', urllib.parse.urlencode({'email': f's{i}@x.com', 'password': PW, 'csrf_token': token}).encode(), timeout=60)
    except urllib.error.HTTPError as e: pass
    form = urllib.parse.urlencode({**answers, 'csrf_token': token}).encode()
    barrier.wait()
    t = time.perf_counter()
    try:
        op.open(base+f'/exam/submit/{sid}', form, timeout=120)
    except urllib.error.HTTPError as e:
        if e.code != 302 or '/resultados/' not in (e.headers.get('Location') or ''):
            errs.append(e.code)
    except Exception as e: errs.append(repr(e)[:60])
    lat.append(time.perf_counter()-t)
ts = [threading.Thread(target=run, args=(i,)) for i in range(N)]
[t.start() for t in ts]; [t.join() for t in ts]
lat.sort()
print(f"N={N} ok={N-len(errs)} err={len(errs)} {set(map(str,errs)) if errs else ''} p50={statistics.median(lat):.2f}s p95={lat[int(.95*(N-1))]:.2f}s max={lat[-1]:.2f}s")
