/* Plan2Stream project page.
 * Data comes from media.json. Media files are GitHub Release assets in production and
 * the local media/ directory when served by tools/serve.py (localhost).
 */
(() => {
  "use strict";

  // ───────────────────────── helpers ─────────────────────────
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const seg = (p, a, b) => clamp((p - a) / (b - a));
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const easeOut = (t) => 1 - Math.pow(1 - t, 3);
  const hash = (i) => { const x = Math.sin(i * 12.9898 + 78.233) * 43758.5453; return x - Math.floor(x); };
  const pad2 = (n) => String(n).padStart(2, "0");
  const fmt = (s) => {
    s = Math.max(0, s || 0);
    const hh = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = Math.floor(s % 60);
    return hh ? `${hh}:${pad2(m)}:${pad2(r)}` : `${m}:${pad2(r)}`;
  };
  const fmtClock = (s) => { // hh:mm:ss.s
    s = Math.max(0, s || 0);
    const hh = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s - hh * 3600 - m * 60;
    return `${pad2(hh)}:${pad2(m)}:${r.toFixed(1).padStart(4, "0")}`;
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const h = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };

  const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const HOVER = matchMedia("(hover: hover) and (pointer: fine)").matches;
  const params = new URLSearchParams(location.search);
  const IS_LOCAL = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname) || params.has("local");
  let BASE = "media/";
  const url = (f) => (f ? BASE + f : "");

  const ICON = {
    play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h4v14H7zm6 0h4v14h-4z"/></svg>',
    sound:
      '<svg class="i-off" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4zm12.6 3 2.7-2.7-1.4-1.4-2.7 2.7-2.7-2.7-1.4 1.4 2.7 2.7-2.7 2.7 1.4 1.4 2.7-2.7 2.7 2.7 1.4-1.4z"/></svg>' +
      '<svg class="i-on" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4zm12.5 3a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4zM14 3.2v2.1a7 7 0 0 1 0 13.4v2.1a9 9 0 0 0 0-17.6z"/></svg>',
  };

  // ───────────────────────── tasks ─────────────────────────
  const TASKS = [
    { code: "T2V", I: false, A: false, out: "V", name: "Text → Video", desc: "A text prompt becomes a continuous video stream." },
    { code: "IT2V", I: true, A: false, out: "V", name: "Text + Image → Video", desc: "A reference image anchors the subject and scene as the stream unfolds." },
    { code: "TA2V", I: false, A: true, out: "V", name: "Text + Audio → Video", desc: "Video generated in sync with input audio, such as speech; the input audio plays with the output." },
    { code: "ITA2V", I: true, A: true, out: "V", name: "Text + Image + Audio → Video", desc: "A reference image and input audio, such as speech, drive a synchronized video." },
    { code: "T2AV", I: false, A: false, out: "AV", name: "Text → Audio + Video", desc: "Picture and sound generated jointly from text: speech, ambience and effects." },
    { code: "IT2AV", I: true, A: false, out: "AV", name: "Text + Image → Audio + Video", desc: "A reference image and text yield video with jointly generated, synchronized sound." },
    { code: "TA2AV", I: false, A: true, out: "AV", name: "Text + Audio → Audio + Video", desc: "Text and input audio condition the stream; audio and video are output together." },
    { code: "ITA2AV", I: true, A: true, out: "AV", name: "Text + Image + Audio → Audio + Video", desc: "A reference image and input audio condition the stream, with joint audio–video output." },
  ];
  const TASK = Object.fromEntries(TASKS.map((t) => [t.code, t]));
  const codeOf = (I, A, out) => `${I ? "I" : ""}T${A ? "A" : ""}2${out}`;

  // ───────────────────────── sound: a playing player is audible ─────────────────────────
  // Browsers allow audible playback only after a user gesture, so the first click / tap / key press
  // anywhere unlocks sound. From then on, the player that most recently started playing is audible
  // for as long as it plays, wherever the pointer is. Hover previews (thumbnails, hero wall tiles)
  // take the sound only while hovered and hand it back afterwards. The nav button is a master switch.
  const Sound = {
    master: true,
    unlocked: false,
    unlockedAt: -1e9,
    target: null, // temporary: the hovered preview
    owner: null, // the player that started playing most recently
    vids: new Set(),
    register(v) { v.muted = true; this.vids.add(v); },
    unregister(v) { this.vids.delete(v); if (this.target === v) this.target = null; if (this.owner === v) this.owner = null; },
    claim(v) { if (this.owner !== v) { this.owner = v; this.apply(); } },
    hover(v) { if (this.target !== v) { this.target = v; this.apply(); } },
    leave(v) { if (this.target === v) { this.target = null; this.apply(); } },
    justUnlocked() { return performance.now() - this.unlockedAt < 800; },
    apply() {
      const live = this.master && this.unlocked, audible = this.target || this.owner;
      this.vids.forEach((v) => { v.muted = !(live && v === audible); });
      document.documentElement.classList.toggle("sound-on", live);
      $("#sound-btn").setAttribute("aria-pressed", String(live));
      $("#sound-hint").hidden = this.unlocked || !this.master;
    },
    unlock() {
      if (this.unlocked) return;
      this.unlocked = true;
      this.unlockedAt = performance.now();
      // Re-issue play() inside the gesture so Safari treats these elements as user-started.
      this.vids.forEach((v) => { if (!v.paused) v.play().catch(() => {}); });
      this.apply();
    },
    setMaster(on) { this.master = on; this.apply(); },
  };
  ["pointerdown", "keydown", "touchstart"].forEach((ev) => document.addEventListener(ev, () => Sound.unlock(), { capture: true, passive: true }));
  // The first click only unlocks sound; later clicks toggle the master switch.
  $("#sound-btn").addEventListener("click", () => Sound.setMaster(Sound.justUnlocked() ? true : !Sound.master));
  if (!HOVER) $("#sound-hint span").textContent = "Tap anywhere to turn on sound";

  // ───────────────────────── player ─────────────────────────
  const viewIO = new IntersectionObserver((entries) => {
    for (const e of entries) {
      const root = e.target, v = $("video", root);
      root.classList.toggle("inview", e.isIntersecting);
      if (e.isIntersecting) {
        if (!root.dataset.userPaused && v.currentSrc) v.play().catch(() => {});
      } else if (!v.paused) v.pause();
    }
  }, { threshold: 0.55 });

  function makePlayer(root, { tagged = true, big = false } = {}) {
    root.classList.add("player", "paused");
    if (big) root.classList.add("player-lg");
    root.innerHTML = `
      <video playsinline loop muted preload="metadata" data-audible></video>
      <div class="pbig"><span>${ICON.play}</span></div>
      <span class="ptag"></span>
      <div class="pbar">
        <button class="pbtn pp" aria-label="Play or pause">${ICON.play}</button>
        <span class="ptime">0:00 / 0:00</span>
        <div class="pscrub" role="slider" aria-label="Seek" tabindex="0" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><i></i><b></b><div class="pprev"><i></i><span></span></div></div>
        <button class="pbtn snd" aria-label="Toggle sound">${ICON.sound}</button>
      </div>`;
    const v = $("video", root), fill = $(".pscrub i", root), time = $(".ptime", root);
    const pp = $(".pp", root), snd = $(".snd", root), scrub = $(".pscrub", root), tag = $(".ptag", root);
    const knob = $(".pscrub > b", root), prev = $(".pprev", root), prevImg = $(".pprev i", root), prevTime = $(".pprev span", root);
    let sprite = null, itemSecs = 0;
    v.muted = true; v.defaultMuted = true;
    Sound.register(v);
    v.addEventListener("play", () => Sound.claim(v)); // playing => audible, independent of the pointer
    const subs = [];
    let raf = 0;
    const tick = () => {
      const d = v.duration || 0, t = v.currentTime || 0, f = d ? t / d : 0;
      fill.style.width = `${f * 100}%`;
      knob.style.left = `${f * 100}%`;
      scrub.setAttribute("aria-valuenow", String(Math.round(f * 100)));
      time.textContent = `${fmt(t)} / ${fmt(d)}`;
      subs.forEach((fn) => fn(t, d));
      if (!v.paused) raf = requestAnimationFrame(tick);
    };
    v.addEventListener("play", () => { root.classList.remove("paused"); pp.innerHTML = ICON.pause; cancelAnimationFrame(raf); raf = requestAnimationFrame(tick); });
    v.addEventListener("pause", () => { root.classList.add("paused"); pp.innerHTML = ICON.play; tick(); });
    v.addEventListener("loadedmetadata", tick);
    v.addEventListener("seeked", tick);
    const toggle = () => {
      if (v.paused) { delete root.dataset.userPaused; Sound.claim(v); v.play().catch(() => {}); }
      else if (Sound.justUnlocked()) Sound.claim(v); // the first click only turns sound on
      else { root.dataset.userPaused = "1"; v.pause(); }
    };
    v.addEventListener("click", toggle);
    pp.addEventListener("click", (e) => { e.stopPropagation(); toggle(); });
    snd.addEventListener("click", (e) => {
      e.stopPropagation();
      const first = Sound.justUnlocked();
      Sound.claim(v);
      Sound.setMaster(first ? true : !Sound.master);
      if (v.paused) { delete root.dataset.userPaused; v.play().catch(() => {}); }
    });
    const seekTo = (x) => {
      const r = scrub.getBoundingClientRect();
      if (v.duration) v.currentTime = clamp((x - r.left) / r.width) * v.duration;
      tick();
    };
    scrub.addEventListener("pointerdown", (e) => {
      e.preventDefault(); e.stopPropagation();
      scrub.setPointerCapture(e.pointerId);
      seekTo(e.clientX);
      const mv = (ev) => seekTo(ev.clientX);
      const up = () => { scrub.removeEventListener("pointermove", mv); scrub.removeEventListener("pointerup", up); scrub.removeEventListener("pointercancel", up); };
      scrub.addEventListener("pointermove", mv); scrub.addEventListener("pointerup", up); scrub.addEventListener("pointercancel", up);
    });
    scrub.addEventListener("keydown", (e) => {
      const step = e.shiftKey ? 60 : 5;
      if (e.key === "ArrowRight") { v.currentTime = Math.min(v.duration || 0, v.currentTime + step); e.preventDefault(); }
      if (e.key === "ArrowLeft") { v.currentTime = Math.max(0, v.currentTime - step); e.preventDefault(); }
    });
    // Hover / drag preview: time label, plus the nearest per-minute thumbnail when a sprite exists.
    const showPrev = (x) => {
      const r = scrub.getBoundingClientRect(), f = clamp((x - r.left) / r.width), d = v.duration || itemSecs;
      const half = sprite ? 100 : 40;
      prev.style.left = `${clamp(f * r.width, half, Math.max(half, r.width - half))}px`;
      prevTime.textContent = fmt(f * d);
      if (sprite) {
        const idx = Math.min(sprite.count - 1, Math.round((f * d) / sprite.step));
        prevImg.style.backgroundPosition = `-${(idx % sprite.cols) * sprite.w}px -${Math.floor(idx / sprite.cols) * sprite.h}px`;
      }
      root.classList.add("previewing");
    };
    scrub.addEventListener("pointermove", (e) => showPrev(e.clientX));
    scrub.addEventListener("pointerleave", () => root.classList.remove("previewing"));
    viewIO.observe(root);
    return {
      root,
      video: v,
      onTime(fn) { subs.push(fn); },
      seekFrac(f) { if (v.duration) v.currentTime = clamp(f) * v.duration; },
      clear() {
        v.pause(); v.removeAttribute("src"); v.removeAttribute("poster"); v.load();
        tag.textContent = ""; sprite = null; root.classList.remove("has-sprite"); root.classList.add("paused");
      },
      load(item, label) {
        delete root.dataset.userPaused;
        cancelAnimationFrame(raf);
        v.poster = url(item.poster);
        v.src = url(item.src);
        itemSecs = item.seconds || 0;
        sprite = item.sprite || null;
        prevImg.style.backgroundImage = sprite ? `url("${url(sprite.src)}")` : "none";
        root.classList.toggle("has-sprite", !!sprite);
        root.style.aspectRatio = "";
        tag.textContent = tagged ? label || `${item.task} · ${fmt(item.seconds)}` : "";
        v.load();
        tick();
        if (root.classList.contains("inview")) v.play().catch(() => {});
      },
    };
  }

  // ───────────────────────── waveform ─────────────────────────
  function drawWave(canvas, peaks, frac) {
    if (!canvas || !peaks || !peaks.length) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = canvas.clientWidth, hgt = canvas.clientHeight;
    if (!w || !hgt) return;
    if (canvas.width !== Math.round(w * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(hgt * dpr); }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, hgt);
    const n = peaks.length, bw = w / n;
    const g = ctx.createLinearGradient(0, 0, w, 0);
    g.addColorStop(0, "#5a83ff"); g.addColorStop(0.5, "#3fe0ff"); g.addColorStop(1, "#a06bff");
    for (let i = 0; i < n; i++) {
      const amp = Math.max(2, peaks[i] * (hgt - 6));
      ctx.fillStyle = (i + 0.5) / n <= frac ? g : "rgba(255,255,255,.17)";
      ctx.fillRect(i * bw + bw * 0.18, (hgt - amp) / 2, Math.max(1, bw * 0.64), amp);
    }
    if (frac > 0 && frac < 1) { ctx.fillStyle = "#fff"; ctx.fillRect(frac * w - 1, 0, 2, hgt); }
  }

  // ───────────────────────── intro ─────────────────────────
  function initHero(wall) {
    const track = $("#hero-track"), hero = $("#top"), grid = $("#wall"), mask = $("#mask"), word = $("#mask-word");
    const focus = $("#mask-focus"), shade = $("#shade"), intro = $("#hero-intro"), hud = $("#hud");
    const fPlan = $("#front-plan"), fSyn = $("#front-syn"), LEAD = 0.3; // planner runs ahead of synthesis by LEAD × wall width
    // Intro timeline, in % of viewport height scrolled into the track (track = 100vh + T.end).
    const T = {
      sweep: [20, 130],      // planner + synthesis fronts cross the wall together
      holdAt: 136,           // detent: a fast swipe is caught here (fully streamed wall + both lines)
      introOut: [222, 240],  // copy, HUD and shade fade out after the hold
      mask: [240, 334],      // the wall condenses into the wordmark
      content: [348, 408],   // title, authors, links
      end: 440,
    };
    const cue = $("#cue"), kicker = $("#hero-kicker"), content = $("#hero-content"), ring = $("#lens-ring"), nav = $("#nav");
    const staticMode = REDUCED || !wall.length;
    if (staticMode) document.documentElement.classList.add("hero-static");

    let tiles = [], hovered = null, cols = 0, rows = 0, S0 = 60, geo = { dx: 0, dy: 0, lift: 0 }, heroVisible = true, p = 0, queued = false;

    const mkVideo = (src, poster, cls, preload = "auto") => {
      const v = document.createElement("video");
      v.className = cls; v.muted = true; v.defaultMuted = true; v.loop = true; v.playsInline = true;
      v.setAttribute("muted", ""); v.setAttribute("playsinline", ""); v.preload = preload;
      if (poster) v.poster = poster;
      v.src = src;
      return v;
    };
    const play = (v) => { if (v.paused) v.play().catch(() => {}); };

    function buildTiles() {
      if (!wall.length) return;
      const W = innerWidth, H = innerHeight;
      const c = W >= 1100 ? 5 : W >= 700 ? 4 : 2;
      let r = Math.max(3, Math.min(5, Math.round(c * (H / W) * 1.5)));
      r = Math.min(r, Math.floor(22 / c));
      if (c === cols && r === rows) return;
      cols = c; rows = r;
      grid.style.setProperty("--cols", c); grid.style.setProperty("--rows", r);
      tiles.forEach((t) => Sound.unregister(t.syn));
      grid.innerHTML = "";
      tiles = [];
      hovered = null;
      for (let i = 0; i < c * r; i++) {
        const w = wall[i % wall.length];
        const tile = h("div", "tile");
        const plan = mkVideo(url(w.plan), url(w.poster), "plan");
        const syn = mkVideo(url(w.src), url(w.poster), "synth", "metadata");
        tile.append(plan, syn);
        if (w.has_audio) { Sound.register(syn); tile.classList.add("has-audio"); tile.append(h("b", "tile-snd", '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4zm12.5 3a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4zM14 3.2v2.1a7 7 0 0 1 0 13.4v2.1a9 9 0 0 0 0-17.6z"/></svg>')); }
        grid.append(tile);
        tiles.push({ tile, plan, syn, i, x0: 0, x1: 1, w: -1, wp: -1, audio: !!w.has_audio });
      }
      // Planner tiles (small) load first; the full-resolution streamed tiles buffer shortly
      // after, or as soon as the visitor starts scrolling.
      const built = tiles;
      const warm = () => built.forEach((t) => { if (t.syn.preload !== "auto") t.syn.preload = "auto"; });
      setTimeout(warm, 1500);
      addEventListener("scroll", warm, { once: true, passive: true });
    }
    function measure() {
      const gr = grid.getBoundingClientRect();
      tiles.forEach((t) => {
        const r = t.tile.getBoundingClientRect();
        t.x0 = (r.left - gr.left) / gr.width;
        t.x1 = (r.right - gr.left) / gr.width;
      });
      // Word-mask geometry, measured untransformed and relative to the hero box.
      word.style.transform = "none";
      const hr = hero.getBoundingClientRect(), wr = word.getBoundingClientRect(), fr = focus.getBoundingClientRect();
      const fx = fr.left + fr.width / 2, fy = fr.top + fr.height * 0.55;
      word.style.transformOrigin = `${fx - wr.left}px ${fy - wr.top}px`;
      const H = hr.height;
      geo.dx = hr.width / 2 - (fx - hr.left);
      geo.dy = H / 2 - (fy - hr.top);
      geo.lift = H * 0.13;
      const stroke = Math.max(4, fr.width * 0.4);
      S0 = clamp((Math.hypot(hr.width, H) / stroke) * 1.35, 20, 600);
      // Supporting copy sits around the final wordmark.
      const wordH = wr.height, center = H * 0.5 - geo.lift;
      kicker.style.top = `${Math.max(20, center - wordH * 0.62 - 26)}px`;
      content.style.top = `${center + wordH * 0.55 + 14}px`;
    }

    function paint() {
      queued = false;
      const r = track.getBoundingClientRect();
      const travel = Math.max(1, track.offsetHeight - innerHeight);
      p = staticMode ? T.end : detent((clamp(-r.top, 0, travel) / innerHeight) * 100);

      // 1) Concurrent fronts: the planner front (noise → plan) runs LEAD ahead while the synthesis
      //    front (plan → stream) follows; both sweep the wall at the same time.
      const xs = staticMode ? 2 : -0.04 + 1.1 * seg(p, ...T.sweep);
      const xp = staticMode ? 2 : xs + LEAD;
      for (const t of tiles) {
        const span = Math.max(1e-6, t.x1 - t.x0);
        const ws = clamp((xs - t.x0) / span), wp = clamp((xp - t.x0) / span);
        if (ws !== t.w || wp !== t.wp) {
          t.tile.style.setProperty("--w", ws.toFixed(4));
          t.tile.style.setProperty("--wp", wp.toFixed(4));
          t.tile.classList.toggle("planned", wp >= 1); // noise fully covered → stop animating it
          if (heroVisible) {
            if (ws > 0 && t.w <= 0 && t.syn.duration) { try { t.syn.currentTime = t.plan.currentTime % t.syn.duration; } catch (_) {} }
            if (ws > 0 || t === hovered) play(t.syn); else t.syn.pause();
            if (wp > 0 && ws < 1) play(t.plan); else t.plan.pause();
          }
          t.w = ws; t.wp = wp;
        }
      }
      const introFade = 1 - seg(p, ...T.introOut);
      fPlan.style.left = `${xp * 100}%`;
      fSyn.style.left = `${xs * 100}%`;
      fPlan.style.opacity = String(xp > 0 && xp < 1 ? introFade : 0);
      fSyn.style.opacity = String(xs > 0 && xs < 1 ? introFade : 0);
      intro.classList.toggle("streaming", xs > 0);

      // 2) intro copy / HUD / cue
      intro.style.opacity = String(introFade);
      hud.style.opacity = String(introFade);
      cue.style.opacity = String(1 - seg(p, 0, 14));
      shade.style.opacity = String(0.62 * introFade);

      // 3) the wall condenses into the wordmark
      const m = staticMode ? 1 : ease(seg(p, ...T.mask));
      const c = staticMode ? 1 : easeOut(seg(p, ...T.content));
      mask.style.visibility = m > 0 ? "visible" : "hidden";
      const s = Math.pow(S0, 1 - m);
      word.style.transform = `translate3d(${geo.dx * (1 - m)}px, ${geo.dy * (1 - m) - geo.lift * c}px, 0) scale(${s})`;

      // 4) title block
      kicker.style.opacity = String(c);
      content.style.opacity = String(c);
      content.style.transform = `translateY(${(1 - c) * 26}px)`;
      content.classList.toggle("live", c > 0.6);
      hero.classList.toggle("settled", c > 0.98);
      nav.classList.toggle("show", p > T.end - 12 || r.bottom < 90);
    }
    const queue = () => { if (!queued) { queued = true; requestAnimationFrame(paint); } };

    // Detent at T.holdAt: when a swipe carries the page past the fully streamed wall, pin it there and
    // swallow the rest of that gesture (including trackpad momentum). Once input has been quiet for
    // 320 ms the hold releases, so the next swipe continues. Scrolling back above re-arms it.
    let armed = true, holding = false, lastY = null, quiet = 0;
    const release = () => { clearTimeout(quiet); quiet = setTimeout(() => { holding = false; }, 320); };
    const trackTop = () => track.getBoundingClientRect().top + scrollY;
    function detent(y) {
      if (lastY === null) { lastY = y; if (y > T.holdAt) armed = false; return y; } // deep link / restored scroll
      if (y < T.holdAt - 30) armed = true;
      const crossed = armed && lastY <= T.holdAt && y > T.holdAt + 0.5;
      if (crossed) { holding = true; armed = false; release(); }
      if (holding && y > T.holdAt + 0.5) {
        scrollTo(0, trackTop() + (T.holdAt / 100) * innerHeight);
        y = T.holdAt;
      }
      lastY = y;
      return y;
    }
    const swallow = (e) => {
      if (!holding) return;
      if (e.type === "wheel" && e.deltaY <= 0) return; // scrolling back up is never blocked
      if (e.cancelable) e.preventDefault();
      release();
    };
    if (!staticMode) {
      addEventListener("wheel", swallow, { passive: false });
      addEventListener("touchmove", swallow, { passive: false });
    }

    // Hovering (or tapping) a tile with audio makes that tile audible; the streamed copy keeps
    // playing even while it is still hidden behind the plan view.
    const tileAt = (x, y) => {
      if (!tiles.length) return null;
      const r = grid.getBoundingClientRect();
      const c = Math.floor(((x - r.left) / r.width) * cols), rr = Math.floor(((y - r.top) / r.height) * rows);
      return c >= 0 && rr >= 0 && c < cols && rr < rows ? tiles[rr * cols + c] || null : null;
    };
    const setHovered = (t) => {
      const next = t && t.audio ? t : null;
      if (next === hovered) return;
      const prev = hovered;
      hovered = next;
      if (prev) { prev.tile.classList.remove("hover"); Sound.leave(prev.syn); if (prev.w <= 0) prev.syn.pause(); }
      if (next) { next.tile.classList.add("hover"); if (heroVisible) play(next.syn); Sound.hover(next.syn); }
    };
    // Until the first click unlocks sound, a small hint follows the cursor over audible tiles.
    const cursorHint = h("div", "cursor-hint", `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4zm12.5 3a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4zM14 3.2v2.1a7 7 0 0 1 0 13.4v2.1a9 9 0 0 0 0-17.6z"/></svg><span>Click once to turn on sound</span>`);
    cursorHint.hidden = true;
    cursorHint.setAttribute("aria-hidden", "true");
    document.body.append(cursorHint);
    const moveHint = (e) => {
      const show = HOVER && !Sound.unlocked && Sound.master && !!hovered;
      cursorHint.hidden = !show;
      if (!show) return;
      const x = Math.min(e.clientX + 16, innerWidth - cursorHint.offsetWidth - 8), y = Math.min(e.clientY + 18, innerHeight - cursorHint.offsetHeight - 8);
      cursorHint.style.transform = `translate(${Math.max(8, x)}px, ${Math.max(8, y)}px)`;
    };
    document.addEventListener("pointerdown", () => { cursorHint.hidden = true; }, { capture: true, passive: true });
    hero.addEventListener("pointermove", (e) => {
      if (e.pointerType === "touch") return;
      // lens + hover sound live on the wordmark; the title / author block below stays plain and clickable
      setHovered(e.target.closest(".hero-content, .hero-kicker") ? null : tileAt(e.clientX, e.clientY));
      moveHint(e);
    });
    hero.addEventListener("pointerdown", (e) => { if (e.pointerType === "touch") setHovered(tileAt(e.clientX, e.clientY)); });
    hero.addEventListener("pointerleave", (e) => { if (e.pointerType !== "touch") { setHovered(null); cursorHint.hidden = true; } });

    // Cursor lens on the settled wordmark: peek at the full stream wall.
    let lr = 0, lrTarget = 0, mx = 0, my = 0, lensRaf = 0;
    const lensLoop = () => {
      lr += (lrTarget - lr) * 0.16;
      if (Math.abs(lrTarget - lr) < 0.3) lr = lrTarget;
      mask.style.setProperty("--lr", `${Math.max(0.01, lr).toFixed(2)}px`);
      mask.style.setProperty("--mx", `${mx}px`); mask.style.setProperty("--my", `${my}px`);
      ring.style.width = ring.style.height = `${lr * 2}px`;
      ring.style.left = `${mx}px`; ring.style.top = `${my}px`;
      ring.style.opacity = lr > 2 ? "1" : "0";
      lensRaf = lr !== lrTarget ? requestAnimationFrame(lensLoop) : 0;
    };
    const kickLens = () => { if (!lensRaf) lensRaf = requestAnimationFrame(lensLoop); };
    if (HOVER && !staticMode) {
      hero.addEventListener("pointermove", (e) => {
        const r = hero.getBoundingClientRect();
        mx = e.clientX - r.left; my = e.clientY - r.top;
        lrTarget = hero.classList.contains("settled") && !e.target.closest(".hero-content, .hero-kicker") ? Math.min(150, innerWidth * 0.11) : 0;
        mask.style.setProperty("--mx", `${mx}px`); mask.style.setProperty("--my", `${my}px`);
        ring.style.left = `${mx}px`; ring.style.top = `${my}px`;
        kickLens();
      });
      hero.addEventListener("pointerleave", () => { lrTarget = 0; kickLens(); });
    }

    function relayout() { buildTiles(); measure(); tiles.forEach((t) => { t.w = -1; }); paint(); }
    relayout();
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { measure(); paint(); });
    let rt = 0;
    addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(relayout, 150); });
    addEventListener("scroll", queue, { passive: true });
    new IntersectionObserver(([e]) => {
      heroVisible = e.isIntersecting;
      if (!heroVisible) tiles.forEach((t) => { t.plan.pause(); t.syn.pause(); });
      else { tiles.forEach((t) => { t.w = -1; }); paint(); }
    }, { threshold: 0.01 }).observe(hero);
  }

  // ───────────────────────── task switchboard ─────────────────────────
  function initBoard(items) {
    const by = Object.fromEntries(TASKS.map((t) => [t.code, items.filter((i) => i.task === t.code)]));
    const player = makePlayer($("#task-player"));
    const io = $("#io"), thumbs = $("#thumbs"), codeEl = $("#task-code");
    let cur = null, curItem = null, waves = [];

    // Matrix: 4 input combinations × 2 outputs.
    const mx = $("#matrix");
    mx.innerHTML = '<span></span><span class="mx-h">→ Audio + Video</span><span class="mx-h">→ Video</span>';
    const ROWS = [[false, false, "Text"], [true, false, "+ Image"], [false, true, "+ Audio"], [true, true, "+ Image + Audio"]];
    for (const [I, A, label] of ROWS) {
      mx.append(h("span", "mx-r", esc(label)));
      for (const out of ["AV", "V"]) {
        const code = codeOf(I, A, out), n = by[code].length;
        const b = h("button", "mx-cell", `<b>${code}</b><small>${n ? `${n} demo${n === 1 ? "" : "s"}` : "coming soon"}</small>`);
        b.dataset.task = code;
        b.setAttribute("aria-pressed", "false");
        b.addEventListener("click", () => setTask(code));
        mx.append(b);
      }
    }
    $$(".chip[data-in]").forEach((b) => {
      if (b.dataset.in === "T") return;
      b.addEventListener("click", () => {
        const t = TASK[cur];
        const I = b.dataset.in === "I" ? !t.I : t.I, A = b.dataset.in === "A" ? !t.A : t.A;
        setTask(codeOf(I, A, t.out));
      });
    });
    $$(".seg button[data-out]").forEach((b) => b.addEventListener("click", () => setTask(codeOf(TASK[cur].I, TASK[cur].A, b.dataset.out))));

    function renderCode(code, prev) {
      const chars = code.split("");
      codeEl.innerHTML = chars.map((ch, i) => `<span class="${ch === "2" ? "two" : ""}">${ch}</span>`).join("");
      if (prev == null) return;
      $$("span", codeEl).forEach((s, i) => { if (prev[i] !== chars[i]) { s.style.setProperty("--d", i); s.classList.add("flip"); } });
    }

    function setTask(code) {
      if (code === cur) return;
      const prev = cur;
      cur = code;
      const t = TASK[code];
      $$(".chip[data-in='I']").forEach((b) => b.setAttribute("aria-pressed", String(t.I)));
      $$(".chip[data-in='A']").forEach((b) => b.setAttribute("aria-pressed", String(t.A)));
      $$(".seg button[data-out]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.out === t.out)));
      $$(".mx-cell").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.task === code)));
      renderCode(code, prev);
      $("#task-name").textContent = t.name;
      $("#task-desc").textContent = t.desc;
      thumbs.innerHTML = "";
      by[code].forEach((it, i) => {
        const b = h("button", "thumb", `<img loading="lazy" alt="" src="${esc(url(it.poster))}"><span class="tm"><span>${esc(it.title || it.id)}</span><span>${it.has_audio ? "♪ " : ""}${fmt(it.seconds)}</span></span>`);
        b.style.setProperty("--d", i);
        b.dataset.id = it.id;
        b.addEventListener("click", () => select(it));
        if (HOVER) {
          let pv = null;
          b.addEventListener("pointerenter", () => {
            pv = document.createElement("video");
            pv.loop = true; pv.playsInline = true; pv.src = url(it.src);
            Sound.register(pv);
            b.insertBefore(pv, b.querySelector(".tm"));
            if (it.has_audio) Sound.hover(pv);
            const v = pv;
            v.play().catch(() => { v.muted = true; v.play().catch(() => {}); });
          });
          b.addEventListener("pointerleave", () => { if (pv) { Sound.leave(pv); Sound.unregister(pv); pv.pause(); pv.remove(); pv = null; } });
        }
        thumbs.append(b);
      });
      if (by[code].length) select(by[code][0]);
      else { player.clear(); io.innerHTML = '<div class="io-card"><p class="io-text">Demos for this task are coming soon.</p></div>'; }
    }

    function select(it) {
      curItem = it;
      const t = TASK[it.task];
      $$(".thumb", thumbs).forEach((b) => b.setAttribute("aria-current", String(b.dataset.id === it.id)));
      player.load(it, `${it.task} · ${fmt(it.seconds)} · ${it.width}×${it.height}`);
      // Inputs → outputs panel
      const cards = [];
      cards.push(`<div class="io-card"><p class="io-k"><span class="tag in">IN</span>Text prompt</p>
        <h3 class="io-title">${esc(it.title || "")}</h3><p class="io-text">${esc(it.caption || "")}</p></div>`);
      if (t.I && it.input_image) {
        cards.push(`<div class="io-card"><p class="io-k"><span class="tag in">IN</span>Reference image</p>
          <img class="io-img" loading="lazy" alt="Reference image" src="${esc(url(it.input_image))}">
          ${it.input_image_is_first_frame ? '<p class="io-note">Shown: first frame of the output.</p>' : ""}</div>`);
      }
      if (t.A) {
        if (t.out === "V" && it.input_audio_is_output_audio && it.waveform) {
          cards.push(`<div class="io-card"><p class="io-k"><span class="tag in">IN</span>Audio · plays with the output</p><canvas class="wave" data-wave></canvas></div>`);
        } else if (it.input_audio) {
          cards.push(`<div class="io-card"><p class="io-k"><span class="tag in">IN</span>Audio</p>
            <button class="audio-btn" data-input-audio="${esc(url(it.input_audio))}">${ICON.play}<span>Play input audio</span></button></div>`);
        } else {
          cards.push(`<div class="io-card"><p class="io-k"><span class="tag in">IN</span>Audio</p><p class="io-note">Input audio preview not available for this sample.</p></div>`);
        }
      }
      if (t.out === "AV" && it.waveform) {
        cards.push(`<div class="io-card"><p class="io-k"><span class="tag out">OUT</span>${t.A ? "Output audio" : "Generated audio"}</p><canvas class="wave" data-wave></canvas></div>`);
      }
      cards.push(`<div class="io-card"><p class="io-k"><span class="tag out">OUT</span>${t.out === "AV" ? "Audio + video" : "Video"}</p>
        <div class="io-meta"><span>${fmt(it.seconds)}</span><span>${it.width}×${it.height}</span><span>24 fps</span>${it.has_audio ? "<span>with audio</span>" : ""}</div></div>`);
      io.innerHTML = cards.join("");
      $$(".io-card", io).forEach((c, i) => c.style.setProperty("--d", i));
      waves = $$("canvas[data-wave]", io);
      waves.forEach((c) => {
        drawWave(c, it.waveform, 0);
        c.addEventListener("click", (e) => { const r = c.getBoundingClientRect(); player.seekFrac((e.clientX - r.left) / r.width); });
      });
      const ab = $("[data-input-audio]", io);
      if (ab) {
        const a = new Audio(ab.dataset.inputAudio);
        ab.addEventListener("click", () => {
          if (a.paused) { player.video.pause(); a.play().catch(() => {}); ab.querySelector("span").textContent = "Pause input audio"; }
          else { a.pause(); ab.querySelector("span").textContent = "Play input audio"; }
        });
        a.addEventListener("ended", () => { ab.querySelector("span").textContent = "Play input audio"; });
      }
    }
    player.onTime((tm, d) => { if (curItem && waves.length) waves.forEach((c) => drawWave(c, curItem.waveform, d ? tm / d : 0)); });
    addEventListener("resize", () => { if (curItem) waves.forEach((c) => drawWave(c, curItem.waveform, player.video.duration ? player.video.currentTime / player.video.duration : 0)); });

    const first = TASKS.find((t) => by[t.code].length);
    setTask(first ? first.code : "T2V");
  }

  // ───────────────────────── long-horizon ─────────────────────────
  function initHour(hours, items) {
    // Hour-scale videos from media.json; falls back to the longest demo items if none are listed.
    // Seeking uses the player's own scrubber (drag anywhere; hover shows the per-minute preview).
    const longs = hours.length ? hours
      : items.filter((i) => i.seconds >= 45).sort((a, b) => b.seconds - a.seconds || a.id.localeCompare(b.id)).slice(0, 5);
    if (!longs.length) { $("#hour").hidden = true; $$('a[href="#hour"]').forEach((a) => a.remove()); return; }
    const player = makePlayer($("#long-player"), { big: true });
    const clock = $("#long-clock"), tabs = $("#long-tabs"), cap = $("#long-caption");
    const pick = (it) => {
      $$("button", tabs).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === it.id)));
      player.load(it, `${it.task} · one continuous ${fmt(it.seconds)} rollout`);
      cap.textContent = it.caption || "";
    };
    longs.forEach((it) => {
      const b = h("button", "", `${esc(it.title || it.id)}<small>${it.task} · ${fmt(it.seconds)}</small>`);
      b.dataset.id = it.id;
      b.addEventListener("click", () => pick(it));
      tabs.append(b);
    });
    player.onTime((t, d) => { clock.innerHTML = `${fmtClock(t)}<span class="tot"> / ${fmt(d)}</span>`; });
    pick(longs[0]);
  }

  // ───────────────────────── method schematic (3D, iframe) ─────────────────────────
  // Tell the embedded schematic when it is off-screen so it stops rendering.
  function initMethod3d() {
    const f = $("#method3d");
    if (!f) return;
    let visible = false;
    const send = () => {
      try { f.contentWindow.postMessage({ p2s: "visibility", visible }, location.origin === "null" ? "*" : location.origin); } catch (_) {}
    };
    f.addEventListener("load", send);
    new IntersectionObserver(([e]) => { visible = e.isIntersecting; send(); }, { threshold: 0 }).observe(f);
  }

  // ───────────────────────── comparisons (optional) ─────────────────────────
  function initCompare(list) {
    if (!list || !list.length) { $$('[data-optional="compare"]').forEach((a) => a.remove()); return; }
    $("#compare").hidden = false;
    const wrap = $("#compare-list");
    list.forEach((c) => {
      const row = h("div", "cmp reveal");
      row.innerHTML = `<h3 class="cmp-title">${esc(c.title || "")}</h3><div class="cmp-pair"><div></div><div class="ours"></div></div>${c.prompt ? `<p class="cmp-prompt">${esc(c.prompt)}</p>` : ""}`;
      wrap.append(row);
      const [l, r] = $$(".cmp-pair > div", row);
      const pl = makePlayer(l), pr = makePlayer(r);
      pl.load({ src: c.left.src, poster: c.left.poster, task: "", seconds: 0 }, c.left.label);
      pr.load({ src: c.right.src, poster: c.right.poster, task: "", seconds: 0 }, c.right.label || "Plan2Stream");
      // keep the pair on the same clock
      pr.video.addEventListener("play", () => { if (pl.video.paused) pl.video.play().catch(() => {}); });
      pr.video.addEventListener("pause", () => { if (!pl.video.paused) pl.video.pause(); });
      pr.video.addEventListener("seeked", () => { pl.video.currentTime = pr.video.currentTime; });
      setInterval(() => { if (!pr.video.paused && Math.abs(pl.video.currentTime - pr.video.currentTime) > 0.25) pl.video.currentTime = pr.video.currentTime; }, 1000);
      revealIO.observe(row);
    });
  }

  // ───────────────────────── chrome: reveal, nav, counters, bib ─────────────────────────
  const revealIO = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); revealIO.unobserve(e.target); } }), { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });
  $$(".reveal").forEach((e) => revealIO.observe(e));
  $$(".features .feature, .cards .card").forEach((e, i) => e.style.setProperty("transition-delay", `${(i % 3) * 90}ms`));

  $$(".feature").forEach((f) => f.addEventListener("pointermove", (e) => {
    const r = f.getBoundingClientRect();
    f.style.setProperty("--mx", `${e.clientX - r.left}px`); f.style.setProperty("--my", `${e.clientY - r.top}px`);
  }));

  const countIO = new IntersectionObserver((es) => es.forEach((e) => {
    if (!e.isIntersecting) return;
    countIO.unobserve(e.target);
    const el = e.target, to = Number(el.dataset.count), t0 = performance.now(), dur = 1200;
    if (REDUCED) return;
    const step = (ts) => { const k = easeOut(clamp((ts - t0) / dur)); el.textContent = String(Math.round(to * k)); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }), { threshold: 0.6 });
  $$("[data-count]").forEach((e) => countIO.observe(e));

  const navLinks = $$(".nav-links a");
  const secIO = new IntersectionObserver((es) => es.forEach((e) => {
    if (e.isIntersecting) navLinks.forEach((a) => a.classList.toggle("active", a.getAttribute("href") === `#${e.target.id}`));
  }), { rootMargin: "-45% 0px -50% 0px" });
  $$("main .section").forEach((s) => secIO.observe(s));

  $("#bib-copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("#bib-text").textContent); $("#bib-copy").textContent = "Copied"; }
    catch (_) { $("#bib-copy").textContent = "Select & copy"; }
    setTimeout(() => { $("#bib-copy").textContent = "Copy"; }, 1600);
  });
  $$('a[aria-disabled="true"]').forEach((a) => a.addEventListener("click", (e) => e.preventDefault()));

  // ───────────────────────── project film (inline, before Overview; the hero "Video" pill links to it) ─────────────────────────
  function initFilm(film) {
    const sec = $("#video"), root = $("#film-player");
    if (!sec || !root) return;
    if (!film || !film.src) {
      sec.hidden = true;
      const b = $("#film-btn");
      if (b) b.style.display = "none";
      return;
    }
    const player = makePlayer(root, { tagged: false, big: true });
    player.load(film);
  }

  // ───────────────────────── boot ─────────────────────────
  Sound.apply();
  initMethod3d();
  fetch("media.json", { cache: "no-cache" })
    .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then((data) => {
      if (!IS_LOCAL) {
        const rel = data.release || {};
        BASE = data.assets_base ? `${data.assets_base.replace(/\/+$/, "")}/` : `https://github.com/${rel.owner}/${rel.repo}/releases/download/${rel.tag}/`;
      }
      const items = data.items || [];
      initHero(data.wall || []);
      initBoard(items);
      initHour(data.hour || [], items);
      initCompare(data.comparisons);
      try { initFilm(data.film); } catch (e) { console.warn("film", e); }
    })
    .catch((err) => {
      const box = $("#load-error");
      box.hidden = false;
      box.textContent = `Could not load media.json (${err.message}). Serve the page over HTTP, e.g. python3 tools/serve.py.`;
      initHero([]);
    });
})();
