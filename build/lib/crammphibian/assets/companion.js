/* Crammy, the pixel frog companion.
 *
 * Injected once into the Streamlit page by crammphibian/companion.py and kept
 * alive across reruns. Python talks to it through window.__crammy:
 *   configure({name, frames, tips, thinking, writing})
 *   say(text, {mood, hold, id, tip})
 *
 * Sprites are plain image URLs keyed by frame name (idle, blink, talk, think,
 * happy, sad, sleep, lilypad); swap the PNGs in assets/frog/ to change the look.
 */
(function () {
  "use strict";
  if (window.__crammy) return;

  // ---------- small helpers ----------
  const store = {
    get(k, d) {
      try { const v = localStorage.getItem("crammy." + k); return v === null ? d : JSON.parse(v); }
      catch (e) { return d; }
    },
    set(k, v) { try { localStorage.setItem("crammy." + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  const now = () => Date.now();
  const pick = (list, avoid) => {
    if (!list || !list.length) return "";
    if (list.length === 1) return list[0];
    let t;
    do { t = list[Math.floor(Math.random() * list.length)]; } while (t === avoid);
    return t;
  };
  const calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const cfg = { name: "Crammy", frames: {}, tips: [], thinking: ["Hmm, let me look…"], writing: ["Writing it up…"] };

  // ---------- DOM ----------
  const root = document.createElement("div");
  root.id = "crammy";
  root.className = "crammy";
  root.innerHTML = `
    <div class="crammy-bubble" role="status" aria-live="polite" hidden>
      <button class="crammy-close" type="button" aria-label="Close">×</button>
      <div class="crammy-name"></div>
      <div class="crammy-text"></div>
      <div class="crammy-actions">
        <button type="button" data-act="tip">Another tip</button>
        <button type="button" data-act="sound"></button>
        <button type="button" data-act="nap">Nap</button>
      </div>
    </div>
    <div class="crammy-fx" aria-hidden="true"></div>
    <button class="crammy-frog" type="button">
      <img class="crammy-pad" alt="" draggable="false">
      <img class="crammy-sprite" alt="" draggable="false">
    </button>`;
  document.body.appendChild(root);

  const $ = (s) => root.querySelector(s);
  const bubble = $(".crammy-bubble"), textEl = $(".crammy-text"), nameEl = $(".crammy-name");
  const frog = $(".crammy-frog"), sprite = $(".crammy-sprite"), pad = $(".crammy-pad"), fx = $(".crammy-fx");
  const soundBtn = root.querySelector('[data-act="sound"]');
  sprite.addEventListener("animationend", () => frog.classList.remove("hop", "perk", "shiver", "land"));

  // ---------- state ----------
  let mood = "idle";          // resting face: idle | happy | sad | think | sleep
  let blink = false, flap = false, mouthOpen = false;
  let busy = false, busySince = 0, lastMutation = 0, wroteDuringRun = false;
  let bubbleKind = null;      // null | "say" | "think"
  let hideTimer = 0, moodTimer = 0, typeTimer = 0;
  let lastActivity = now(), asleep = false, hovering = false;
  let clicks = [];
  let lastTip = "";
  let sound = store.get("sound", false);
  let napping = store.get("nap", false);
  const said = new Set();

  // ---------- drawing ----------
  function render() {
    let face = mood;
    if (asleep || napping) face = "sleep";
    else if (flap) face = mouthOpen ? "talk" : "idle";
    else if (blink && (mood === "idle" || mood === "think")) face = "blink";
    const src = cfg.frames[face] || cfg.frames.idle;
    if (src && sprite.getAttribute("src") !== src) sprite.setAttribute("src", src);
    root.dataset.mood = face;
    root.classList.toggle("is-napping", napping);
    root.classList.toggle("is-asleep", asleep && !napping);
    root.classList.toggle("is-busy", busy);
    soundBtn.textContent = sound ? "Sound: on" : "Sound: off";
    soundBtn.setAttribute("aria-pressed", String(sound));
    frog.setAttribute("aria-label", `${cfg.name} the frog. ${napping ? "Napping, click to wake." : "Click for a study tip."}`);
  }

  function setMood(m, ms) {
    mood = m;
    clearTimeout(moodTimer);
    if (ms) moodTimer = setTimeout(() => { mood = busy ? "think" : "idle"; render(); }, ms);
    render();
  }

  function retrigger(el, cls) {
    if (calm) return;
    el.classList.remove(cls);
    void el.offsetWidth; // restart the CSS animation
    el.classList.add(cls);
  }

  function particles(kind, n) {
    if (calm) return;
    for (let i = 0; i < n; i++) {
      const p = document.createElement("span");
      p.className = "crammy-p crammy-p-" + kind;
      p.style.left = 30 + Math.random() * 40 + "%";
      p.style.animationDelay = i * 110 + "ms";
      p.style.setProperty("--drift", (Math.random() * 30 - 15).toFixed(0) + "px");
      fx.appendChild(p);
      setTimeout(() => p.remove(), 1600 + i * 110);
    }
  }

  // ---------- sound (tiny synthesised croak, off by default) ----------
  let audio = null;
  function croak(high) {
    if (!sound) return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      const t = audio.currentTime, base = high ? 700 : 430;
      [0, 1].forEach((i) => {
        const o = audio.createOscillator(), g = audio.createGain(), s = t + i * 0.09;
        o.type = "square";
        o.frequency.setValueAtTime(base * (i ? 0.8 : 1), s);
        o.frequency.exponentialRampToValueAtTime(base * 0.55, s + 0.08);
        g.gain.setValueAtTime(0.0001, s);
        g.gain.exponentialRampToValueAtTime(0.05, s + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, s + 0.08);
        o.connect(g).connect(audio.destination);
        o.start(s);
        o.stop(s + 0.09);
      });
    } catch (e) { /* no audio, no problem */ }
  }

  // ---------- speech bubble ----------
  function showBubble(text, kind, withActions) {
    clearTimeout(hideTimer);
    clearInterval(typeTimer);
    bubbleKind = kind;
    bubble.hidden = false;
    bubble.classList.toggle("is-thinking", kind === "think");
    bubble.classList.toggle("has-actions", !!withActions);
    retrigger(bubble, "pop");
    if (calm || kind === "think") {
      textEl.textContent = text;
      return Promise.resolve();
    }
    // typewriter, with the mouth flapping while the words come out
    textEl.textContent = "";
    let i = 0;
    flap = true;
    return new Promise((done) => {
      typeTimer = setInterval(() => {
        i = Math.min(text.length, i + 2);
        textEl.textContent = text.slice(0, i);
        mouthOpen = !mouthOpen;
        render();
        if (i >= text.length) {
          clearInterval(typeTimer);
          flap = false;
          mouthOpen = false;
          render();
          done();
        }
      }, 28);
    });
  }

  function hideBubble(delay) {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(function tryHide() {
      if (hovering || bubble.matches(":hover") || bubble.contains(document.activeElement)) {
        hideTimer = setTimeout(tryHide, 1200);
        return;
      }
      bubble.hidden = true;
      bubbleKind = null;
    }, delay || 0);
  }

  function say(text, opts) {
    opts = opts || {};
    if (!text) return;
    if (opts.id) {
      if (said.has(opts.id)) return;
      said.add(opts.id);
    }
    wake(true);
    if (napping) { setMood(opts.mood || "idle", 2500); retrigger(frog, "hop"); return; }
    const hold = opts.hold || Math.min(12000, 4000 + text.length * 45);
    croak(opts.mood === "happy");
    if (opts.mood === "happy") { retrigger(frog, "hop"); particles("heart", 3); }
    if (opts.mood === "sad") retrigger(frog, "shiver");
    showBubble(text, "say", !!opts.tip).then(() => setMood(opts.mood && opts.mood !== "talk" ? opts.mood : "idle", hold));
    hideBubble(hold + 800);
  }

  function nextTip() {
    lastTip = pick(cfg.tips, lastTip) || "Ribbit!";
    say(lastTip, { mood: "happy", tip: true });
  }

  // ---------- nap / sleep ----------
  function setNap(on) {
    napping = on;
    store.set("nap", on);
    if (on) { bubble.hidden = true; bubbleKind = null; particles("z", 2); }
    else { retrigger(frog, "hop"); }
    render();
  }

  function wake(silent) {
    lastActivity = now();
    if (!asleep) return;
    asleep = false;
    render();
    if (!silent && !napping && !busy) {
      retrigger(frog, "hop");
      say(pick(["Oh! I'm up, I'm up.", "Was I snoring? Back to studying!", "*yawn* Okay, where were we?"]), { mood: "happy", hold: 3500 });
    }
  }

  // ---------- pointer: click, hover, drag ----------
  const pos = store.get("pos", null); // {r, b}: distance from right/bottom edge
  function place(r, b) {
    const w = frog.offsetWidth || 128, h = frog.offsetHeight || 128;
    r = Math.max(0, Math.min(window.innerWidth - w, r));
    b = Math.max(0, Math.min(window.innerHeight - h, b));
    root.style.right = r + "px";
    root.style.bottom = b + "px";
    root.classList.toggle("on-left", r > window.innerWidth / 2 - w / 2);
    root.classList.toggle("on-top", b > window.innerHeight - 320);
    return { r, b };
  }
  if (pos) requestAnimationFrame(() => place(pos.r, pos.b));
  window.addEventListener("resize", () => { const p = store.get("pos", null); if (p) place(p.r, p.b); });

  let drag = null;
  frog.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const rect = root.getBoundingClientRect();
    drag = { x: e.clientX, y: e.clientY, r: window.innerWidth - rect.right, b: window.innerHeight - rect.bottom, moved: false };
    frog.setPointerCapture(e.pointerId);
  });
  frog.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 6) return;
    if (!drag.moved) { drag.moved = true; root.classList.add("is-dragging"); bubble.hidden = true; bubbleKind = null; }
    place(drag.r - dx, drag.b - dy);
  });
  frog.addEventListener("pointerup", (e) => {
    if (!drag) return;
    const d = drag;
    drag = null;
    root.classList.remove("is-dragging");
    if (d.moved) {
      const rect = root.getBoundingClientRect();
      store.set("pos", place(window.innerWidth - rect.right, window.innerHeight - rect.bottom));
      retrigger(frog, "land");
      return;
    }
    onPoke();
  });
  frog.addEventListener("dblclick", () => {
    if (!store.get("pos", null)) return; // already home: treat as two pokes
    store.set("pos", null);
    root.style.right = "";
    root.style.bottom = "";
    root.classList.remove("on-left", "on-top");
    say("Home sweet lily pad.", { mood: "happy", hold: 2000 });
  });
  frog.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPoke(); } });

  function onPoke() {
    wake(true);
    if (napping) { setNap(false); say("I'm back! Ask me anything… well, ask your notes.", { mood: "happy", hold: 3500 }); return; }
    const t = now();
    clicks = clicks.filter((c) => t - c < 2500).concat(t);
    retrigger(frog, "hop");
    croak(true);
    if (clicks.length >= 5) {
      clicks = [];
      particles("heart", 5);
      say(pick(["Hehe, that tickles!", "Okay okay, I'm awake!", "Ribbit! You found my ticklish spot."]), { mood: "happy", hold: 3000 });
      return;
    }
    if (!bubble.hidden && bubbleKind === "say" && bubble.classList.contains("has-actions")) { hideBubble(0); return; }
    nextTip();
  }

  frog.addEventListener("mouseenter", () => {
    hovering = true;
    wake(false);
    if (!busy && !napping && mood === "idle" && bubble.hidden) setMood("happy", 900);
    retrigger(frog, "perk");
  });
  frog.addEventListener("mouseleave", () => { hovering = false; });

  bubble.addEventListener("click", (e) => {
    const act = e.target.closest("button") && e.target.closest("button").dataset.act;
    if (e.target.closest(".crammy-close")) { hideBubble(0); return; }
    if (act === "tip") nextTip();
    if (act === "sound") { sound = !sound; store.set("sound", sound); render(); croak(true); }
    if (act === "nap") { say("Okay, quick nap. Click me when you need me!", { mood: "sleep", hold: 1800 }); setTimeout(() => setNap(true), 2300); }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !bubble.hidden) hideBubble(0); });

  // ---------- watch the app: thinking while Streamlit runs, talking while text streams ----------
  function appRunning() {
    const app = document.querySelector('[data-testid="stApp"]');
    if (app && app.getAttribute("data-test-script-state") === "running") return true;
    const w = document.querySelector('[data-testid="stStatusWidget"]');
    return !!(w && /running/i.test(w.textContent || ""));
  }

  const main = () => document.querySelector('[data-testid="stMain"]') || document.querySelector('[data-testid="stMainBlockContainer"]');
  let observed = null;
  const obs = new MutationObserver((list) => {
    if (!busy) return;
    for (const m of list) {
      if (root.contains(m.target)) continue;
      if (m.type === "characterData" || m.addedNodes.length) { lastMutation = now(); return; }
    }
  });

  let flapTick = 0;
  setInterval(() => {
    const m = main();
    if (m && m !== observed) { obs.disconnect(); obs.observe(m, { childList: true, subtree: true, characterData: true }); observed = m; }

    const running = appRunning();
    const t = now();
    if (running && !busy) { busy = true; busySince = t; wroteDuringRun = false; lastMutation = 0; wake(true); }
    if (!running && busy) {
      busy = false;
      flap = false;
      if (bubbleKind === "think") hideBubble(0);
      if (mood === "think") setMood(wroteDuringRun ? "happy" : "idle", wroteDuringRun ? 1500 : 0);
    }
    if (busy && t - busySince > 700) {
      // text still arriving well after the run started = an answer is streaming in
      const streaming = lastMutation && t - lastMutation < 300 && t - busySince > 1200;
      if (streaming && !wroteDuringRun) {
        wroteDuringRun = true;
        if (bubbleKind !== "say" && !napping) showBubble(pick(cfg.writing), "think");
      }
      if (mood !== "think" && bubbleKind !== "say") setMood("think");
      if (bubble.hidden && !napping && bubbleKind !== "say") showBubble(pick(cfg.thinking), "think");
      if (streaming && ++flapTick % 2 === 0) { flap = true; mouthOpen = !mouthOpen; render(); }
      else if (!streaming && flap && bubbleKind !== "say") { flap = false; render(); }
    }

    // doze off after a minute without the mouse or keyboard
    if (!busy && !asleep && !napping && t - lastActivity > 60000) { asleep = true; hideBubble(0); render(); }
    if (asleep && !napping && Math.random() < 0.06) particles("z", 1);
  }, 150);

  // ---------- blinking ----------
  (function blinkLoop() {
    setTimeout(() => {
      blink = true; render();
      setTimeout(() => {
        blink = false; render();
        if (Math.random() < 0.25) setTimeout(() => { blink = true; render(); setTimeout(() => { blink = false; render(); }, 110); }, 160);
      }, 130);
      blinkLoop();
    }, 2200 + Math.random() * 4200);
  })();

  ["mousemove", "keydown", "scroll", "pointerdown", "touchstart"].forEach((ev) =>
    window.addEventListener(ev, () => { if (asleep) wake(false); else lastActivity = now(); }, { passive: true, capture: true })
  );

  // ---------- public API ----------
  function configure(c) {
    Object.assign(cfg, c || {});
    nameEl.textContent = cfg.name;
    if (cfg.frames.lilypad) pad.setAttribute("src", cfg.frames.lilypad);
    pad.hidden = !cfg.frames.lilypad;
    render();
  }

  window.__crammy = { configure, say, tip: nextTip, nap: setNap };
  render();
})();
