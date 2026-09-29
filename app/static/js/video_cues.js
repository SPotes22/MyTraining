/* ═══════════════════════════════════════════════════════════════════════════
   video_cues.js — RF-011 · Preguntas en videos
   Cada reproductor `.video-cue-player[data-video-cue]` trae un JSON con el
   proveedor y una lista de cues: [{at, pause, target}]. Se sigue el tiempo de
   reproducción (YouTube IFrame API, Vimeo Player API o <video> HTML5) y, al
   llegar a `at`, se pausa el video (si `pause`) y se revela `target`:
   su `.video-cue-waiting` se oculta y cada `.video-cue-gate` se muestra. Si el
   gate tiene `data-cue-src`, su contenido se pide al servidor en ese momento
   (la pregunta no viaja en el HTML inicial).
═══════════════════════════════════════════════════════════════════════════ */
(function () {
  let entries = [];
  const PLAYER_LOAD_TIMEOUT_MS = 10000;
  let renderGate = json => json.html || '';
  let ytReady = null;
  let vimeoReady = null;

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const tag = document.createElement('script');
      tag.src = src;
      tag.async = true;
      tag.onload = resolve;
      tag.onerror = reject;
      document.head.appendChild(tag);
    });
  }

  function withTimeout(promise) {
    return Promise.race([
      promise,
      new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), PLAYER_LOAD_TIMEOUT_MS)),
    ]);
  }

  function loadYouTubeApi() {
    if (!ytReady) {
      ytReady = new Promise((resolve, reject) => {
        if (window.YT && window.YT.Player) return resolve(window.YT);
        const previous = window.onYouTubeIframeAPIReady;
        window.onYouTubeIframeAPIReady = function () {
          if (typeof previous === 'function') previous();
          resolve(window.YT);
        };
        loadScript('https://www.youtube.com/iframe_api').catch(reject);
      });
    }
    return withTimeout(ytReady);
  }

  function loadVimeoApi() {
    if (!vimeoReady) {
      vimeoReady = window.Vimeo && window.Vimeo.Player
        ? Promise.resolve(window.Vimeo)
        : loadScript('https://player.vimeo.com/api/player.js').then(() => window.Vimeo);
    }
    return withTimeout(vimeoReady);
  }

  function remember(target) {
    const key = target.dataset.cueKey;
    if (!key) return;
    try { sessionStorage.setItem(`mt-video-cue-${key}`, '1'); } catch (e) { /* modo privado */ }
  }

  function wasSeen(target) {
    const key = target.dataset.cueKey;
    if (!key) return false;
    try { return sessionStorage.getItem(`mt-video-cue-${key}`) === '1'; } catch (e) { return false; }
  }

  function setWaiting(target, html, tone) {
    const waiting = target.querySelector('.video-cue-waiting');
    if (!waiting) return;
    if (!html) { waiting.classList.add('d-none'); return; }
    waiting.classList.remove('d-none', 'alert-primary', 'alert-warning', 'alert-danger');
    waiting.classList.add(`alert-${tone}`);
    waiting.innerHTML = html;
  }

  function loadGate(target, gate) {
    return fetch(gate.dataset.cueSrc, { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
      .then(r => r.json().then(json => ({ status: r.status, json })))
      .then(({ status, json }) => {
        if (status === 425 && json.retry_after) {
          // El servidor aún no la entrega: reintenta cuando se cumpla el tiempo.
          setWaiting(target, '<i class="bi bi-hourglass-split fs-4"></i>'
            + `<div>La pregunta estará disponible en ${json.retry_after} s.</div>`, 'primary');
          return new Promise(resolve => setTimeout(resolve, json.retry_after * 1000))
            .then(() => loadGate(target, gate));
        }
        if (status >= 400) throw new Error(json.error || `HTTP ${status}`);
        gate.innerHTML = renderGate(json);
        delete gate.dataset.cueSrc;
      });
  }

  function reveal(target, reason) {
    if (!target || target.dataset.videoRevealed === '1') return;
    target.dataset.videoRevealed = '1';
    const gates = [...target.querySelectorAll('.video-cue-gate')];
    Promise.all(gates.map(gate => (gate.dataset.cueSrc ? loadGate(target, gate) : null)))
      .then(() => {
        gates.forEach(gate => gate.classList.remove('d-none'));
        if (reason === 'fallback') {
          setWaiting(target, '<i class="bi bi-exclamation-triangle-fill fs-4"></i>'
            + '<div>No se pudo seguir la reproducción del video, así que la pregunta se muestra directamente.</div>', 'warning');
        } else {
          setWaiting(target, null);
        }
        remember(target);
        target.dispatchEvent(new CustomEvent('videocue:revealed', { bubbles: true, detail: { reason } }));
      })
      .catch(() => {
        target.dataset.videoRevealed = '';
        setWaiting(target, '<i class="bi bi-x-octagon-fill fs-4"></i>'
          + '<div>No se pudo cargar la pregunta. Revisa tu conexión y vuelve a reproducir el video.</div>', 'danger');
      });
  }

  function onTime(entry, seconds) {
    entry.cues.forEach(cue => {
      if (cue.done || seconds < cue.at) return;
      cue.done = true;
      const target = document.querySelector(cue.target);
      if (!target || target.dataset.videoRevealed === '1') return;
      if (cue.pause) entry.pause();
      reveal(target, 'cue');
      if (cue.pause) target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
  }

  function fallback(entry) {
    entry.cues.forEach(cue => reveal(document.querySelector(cue.target), 'fallback'));
  }

  function setupYouTube(entry, mount) {
    loadYouTubeApi().then(YT => {
      let timer = null;
      const player = new YT.Player(mount, {
        videoId: entry.meta.video_id,
        playerVars: { start: entry.meta.start || 0, rel: 0, playsinline: 1 },
        events: {
          onStateChange(ev) {
            clearInterval(timer);
            if (ev.data === YT.PlayerState.PLAYING) {
              timer = setInterval(() => onTime(entry, player.getCurrentTime()), 250);
            }
          },
          onError() { fallback(entry); },
        },
      });
      entry.pause = () => { if (player.pauseVideo) player.pauseVideo(); };
    }).catch(() => fallback(entry));
  }

  function setupVimeo(entry, iframe) {
    loadVimeoApi().then(Vimeo => {
      const player = new Vimeo.Player(iframe);
      player.on('timeupdate', data => onTime(entry, data.seconds));
      player.on('error', () => fallback(entry));
      entry.pause = () => player.pause().catch(() => {});
    }).catch(() => fallback(entry));
  }

  function setupFile(entry, video) {
    const start = entry.meta.start || 0;
    const seekToStart = () => { if (start && video.currentTime < start) video.currentTime = start; };
    // Con preload="metadata" los metadatos pueden llegar antes de init().
    if (video.readyState >= 1) seekToStart();
    else video.addEventListener('loadedmetadata', seekToStart, { once: true });
    video.addEventListener('timeupdate', () => onTime(entry, video.currentTime));
    video.addEventListener('error', () => fallback(entry));
    entry.pause = () => video.pause();
  }

  function init(root, options) {
    if (options && options.render) renderGate = options.render;
    entries = entries.filter(e => document.contains(e.container));
    (root || document).querySelectorAll('.video-cue-player[data-video-cue]:not([data-cue-ready])').forEach(container => {
      container.dataset.cueReady = '1';
      let meta;
      try { meta = JSON.parse(container.dataset.videoCue); } catch (e) { return; }
      const cues = (meta.cues || []).map(c => ({ ...c, done: false }));
      const entry = { container, meta, cues, pause() {} };
      entries.push(entry);

      cues.forEach(cue => {
        const target = document.querySelector(cue.target);
        if (target && wasSeen(target)) reveal(target, 'restored');
      });

      if (meta.provider === 'youtube') setupYouTube(entry, container.querySelector('.video-cue-yt'));
      else if (meta.provider === 'vimeo') setupVimeo(entry, container.querySelector('iframe'));
      else if (meta.provider === 'file') setupFile(entry, container.querySelector('video'));
      else fallback(entry);
    });
  }

  window.VideoCues = {
    init,
    /** Muestra la pregunta sin esperar el video (p. ej. si ya tenía respuesta guardada). */
    reveal(target) {
      reveal(typeof target === 'string' ? document.querySelector(target) : target, 'restored');
    },
    /** Pausa los videos que no están dentro de `scope` (null = todos). */
    pauseAllExcept(scope) {
      entries.forEach(entry => { if (!scope || !scope.contains(entry.container)) entry.pause(); });
    },
  };
})();
