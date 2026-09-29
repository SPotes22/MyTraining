/* ═══════════════════════════════════════════════════════════════════════════
   video_cues.js — RF-011 · Preguntas en videos
   Lee el JSON `data-video-cue` de cada reproductor, sigue el tiempo de
   reproducción (YouTube IFrame API, Vimeo Player API o <video> HTML5) y, al
   llegar a `question_at`, pausa el video (si así se configuró) y muestra la
   pregunta que estaba oculta dentro de `.video-cue-gate`.
═══════════════════════════════════════════════════════════════════════════ */
(function () {
  const entries = [];
  const PLAYER_LOAD_TIMEOUT_MS = 10000;
  let scope = '';
  let ytReady = null;
  let vimeoReady = null;

  function storageKey(questionId) {
    return `mt-video-cue-${scope}-${questionId}`;
  }

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

  function isRevealed(step) {
    return step.dataset.videoRevealed === '1';
  }

  function reveal(step, reason) {
    if (!step || isRevealed(step)) return;
    step.dataset.videoRevealed = '1';
    step.querySelectorAll('.video-cue-gate').forEach(el => el.classList.remove('d-none'));
    const waiting = step.querySelector('.video-cue-waiting');
    if (waiting) {
      if (reason === 'fallback') {
        waiting.classList.replace('alert-primary', 'alert-warning');
        waiting.innerHTML = '<i class="bi bi-exclamation-triangle-fill fs-4"></i>'
          + '<div>No se pudo seguir la reproducción del video, así que la pregunta se muestra directamente.</div>';
      } else {
        waiting.classList.add('d-none');
      }
    }
    try { sessionStorage.setItem(storageKey(step.dataset.questionId), '1'); } catch (e) { /* modo privado */ }
    step.dispatchEvent(new CustomEvent('videocue:revealed', { bubbles: true, detail: { reason } }));
  }

  function onTime(entry, seconds) {
    if (isRevealed(entry.step) || seconds < entry.cue.question_at) return;
    if (entry.cue.pause_on_question) entry.pause();
    reveal(entry.step, 'cue');
  }

  function setupYouTube(entry, mount) {
    loadYouTubeApi().then(YT => {
      let timer = null;
      const player = new YT.Player(mount, {
        videoId: entry.cue.video_id,
        playerVars: { start: entry.cue.start || 0, rel: 0, playsinline: 1 },
        events: {
          onStateChange(ev) {
            clearInterval(timer);
            if (ev.data === YT.PlayerState.PLAYING) {
              timer = setInterval(() => onTime(entry, player.getCurrentTime()), 250);
            }
          },
          onError() { reveal(entry.step, 'fallback'); },
        },
      });
      entry.pause = () => { if (player.pauseVideo) player.pauseVideo(); };
    }).catch(() => reveal(entry.step, 'fallback'));
  }

  function setupVimeo(entry, iframe) {
    loadVimeoApi().then(Vimeo => {
      const player = new Vimeo.Player(iframe);
      player.on('timeupdate', data => onTime(entry, data.seconds));
      player.on('error', () => reveal(entry.step, 'fallback'));
      entry.pause = () => player.pause().catch(() => {});
    }).catch(() => reveal(entry.step, 'fallback'));
  }

  function setupFile(entry, video) {
    const start = entry.cue.start || 0;
    const seekToStart = () => { if (start && video.currentTime < start) video.currentTime = start; };
    // Con preload="metadata" los metadatos pueden llegar antes de init().
    if (video.readyState >= 1) seekToStart();
    else video.addEventListener('loadedmetadata', seekToStart, { once: true });
    video.addEventListener('timeupdate', () => onTime(entry, video.currentTime));
    video.addEventListener('error', () => reveal(entry.step, 'fallback'));
    entry.pause = () => video.pause();
  }

  function init(root, scopeKey) {
    scope = scopeKey || '';
    (root || document).querySelectorAll('.video-cue-player[data-video-cue]').forEach(container => {
      const step = container.closest('[data-video-gated]');
      if (!step) return;
      let cue;
      try { cue = JSON.parse(container.dataset.videoCue); } catch (e) { return reveal(step, 'fallback'); }

      let alreadySeen = false;
      try { alreadySeen = sessionStorage.getItem(storageKey(step.dataset.questionId)) === '1'; } catch (e) { /* noop */ }
      if (alreadySeen) reveal(step, 'restored');

      const entry = { step, cue, pause() {} };
      entries.push(entry);
      if (cue.provider === 'youtube') setupYouTube(entry, container.querySelector('.video-cue-yt'));
      else if (cue.provider === 'vimeo') setupVimeo(entry, container.querySelector('iframe'));
      else if (cue.provider === 'file') setupFile(entry, container.querySelector('video'));
      else reveal(step, 'fallback');
    });
  }

  window.VideoCues = {
    init,
    /** Muestra la pregunta sin esperar el video (p. ej. si ya tenía respuesta guardada). */
    reveal(questionId) {
      reveal(document.querySelector(`[data-video-gated][data-question-id="${questionId}"]`), 'restored');
    },
    /** Pausa los videos de las preguntas que no están en pantalla. */
    pauseAllExcept(step) {
      entries.forEach(entry => { if (entry.step !== step) entry.pause(); });
    },
  };
})();
