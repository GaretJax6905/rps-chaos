/* RPS Chaos front end: menu, boss ladder, same-device and online duels,
   animation, music, sound, keyboard. Talks to the Flask JSON API in app.py. */
(() => {
  "use strict";

  const CONFIG = JSON.parse(document.getElementById("config").textContent);
  const SYM = CONFIG.symbols;
  const KEYS = { rock: "r", paper: "p", scissors: "s", lizard: "l", spock: "k" };
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (id) => document.getElementById(id);
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  const wait = (ms) => new Promise((r) => setTimeout(r, REDUCED ? 0 : ms));
  const isLocalHost = ["127.0.0.1", "localhost", "[::1]"].includes(location.hostname);

  // ====================================================================
  // Storage (best effort: private windows may throw)
  // ====================================================================
  const store = {
    get(key, fallback) {
      try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); }
      catch { return fallback; }
    },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ } },
  };
  const settings = {
    music: store.get("rpsChaosMusic", false),
    sound: !store.get("rpsChaosMuted", false),
    clock: store.get("rpsChaosClock", false),
    ruleset: store.get("rpsChaosRuleset", "classic"),
  };
  let best = store.get("rpsChaosBest", 0);

  // ====================================================================
  // Audio: sound effects + a tiny chiptune sequencer (all WebAudio, no files)
  // ====================================================================
  let audio = null;
  function ctx() {
    if (!audio) {
      try { audio = new (window.AudioContext || window.webkitAudioContext)(); } catch { audio = null; }
    }
    if (audio && audio.state === "suspended") audio.resume();
    return audio;
  }
  function tone(freq, start, dur, type = "square", vol = 0.06, dest = null) {
    const ac = ctx(); if (!ac) return;
    const t = Math.max(ac.currentTime, start);
    const osc = ac.createOscillator(); const gain = ac.createGain();
    osc.type = type; osc.frequency.setValueAtTime(freq, t);
    gain.gain.setValueAtTime(vol, t);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(gain).connect(dest || ac.destination);
    osc.start(t); osc.stop(t + dur + 0.02);
  }
  function noise(start, dur, vol, dest) {
    const ac = ctx(); if (!ac) return;
    const buffer = ac.createBuffer(1, Math.floor(ac.sampleRate * dur), ac.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
    const src = ac.createBufferSource(); const gain = ac.createGain(); const hp = ac.createBiquadFilter();
    hp.type = "highpass"; hp.frequency.value = 7000;
    src.buffer = buffer; gain.gain.setValueAtTime(vol, start);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + dur);
    src.connect(hp).connect(gain).connect(dest); src.start(start);
  }
  function fx(fn) {
    if (!settings.sound) return;
    const ac = ctx(); if (!ac) return;
    try { fn(ac.currentTime); } catch { /* ignore */ }
  }
  const sfx = {
    tick: () => fx((t) => [0, 0.3, 0.6].forEach((s, i) => tone(330 + i * 60, t + s, 0.08))),
    win: () => fx((t) => [523, 659, 784].forEach((f, i) => tone(f, t + i * 0.08, 0.14, "triangle", 0.09))),
    lose: () => fx((t) => [311, 233, 156].forEach((f, i) => tone(f, t + i * 0.1, 0.18, "sawtooth", 0.05))),
    tie: () => fx((t) => tone(440, t, 0.15, "sine", 0.07)),
    lock: () => fx((t) => tone(880, t, 0.06, "square", 0.04)),
    join: () => fx((t) => [392, 523, 659].forEach((f, i) => tone(f, t + i * 0.07, 0.12, "triangle", 0.08))),
    heal: () => fx((t) => [523, 784].forEach((f, i) => tone(f, t + i * 0.06, 0.15, "sine", 0.07))),
    power: () => fx((t) => {
      for (let i = 0; i < 12; i++) tone(110 * 2 ** (i / 6), t + i * 0.05, 0.12, "sawtooth", 0.05);
    }),
    fanfare: () => fx((t) => [523, 659, 784, 1047, 784, 1047].forEach((f, i) => tone(f, t + i * 0.11, 0.2, "triangle", 0.1))),
    gameover: () => fx((t) => [392, 330, 262, 196].forEach((f, i) => tone(f, t + i * 0.18, 0.3, "sawtooth", 0.05))),
  };

  const NOTE = (n) => 440 * 2 ** ((n - 69) / 12); // MIDI note -> Hz
  const music = {
    mood: "menu", step: 0, next: 0, timer: null, bus: null,
    moods: {
      // bass roots (MIDI), chord intervals, bpm, hats
      menu: { bpm: 104, roots: [45, 41, 43, 40], chord: [0, 3, 7, 12], hats: false },
      battle: { bpm: 128, roots: [45, 45, 41, 43], chord: [0, 7, 12, 15], hats: true },
      boss: { bpm: 150, roots: [45, 46, 45, 43], chord: [0, 3, 6, 12], hats: true },
    },
    start() {
      if (this.timer || !settings.music) return;
      const ac = ctx(); if (!ac) return;
      this.bus = ac.createGain(); this.bus.gain.value = 0.55; this.bus.connect(ac.destination);
      this.next = ac.currentTime + 0.05; this.step = 0;
      this.timer = setInterval(() => this.schedule(), 25);
    },
    stop() {
      clearInterval(this.timer); this.timer = null;
      if (this.bus) { try { this.bus.disconnect(); } catch { /* ignore */ } this.bus = null; }
    },
    setMood(mood) { this.mood = mood; },
    schedule() {
      const ac = ctx(); if (!ac || !this.bus) return;
      while (this.next < ac.currentTime + 0.12) {
        const m = this.moods[this.mood];
        const sixteenth = 60 / m.bpm / 4;
        const bar = Math.floor(this.step / 16) % m.roots.length;
        const s = this.step % 16;
        const root = m.roots[bar];
        if (s % 4 === 0) tone(NOTE(root), this.next, sixteenth * 3, "triangle", 0.09, this.bus);
        if (s % 4 === 2) tone(NOTE(root + 12), this.next, sixteenth, "triangle", 0.05, this.bus);
        const arp = m.chord[s % m.chord.length];
        tone(NOTE(root + 24 + arp), this.next, sixteenth * 0.9, "square", 0.018, this.bus);
        if (m.hats && s % 2 === 1) noise(this.next, 0.04, 0.05, this.bus);
        if (m.hats && (s === 4 || s === 12)) noise(this.next, 0.12, 0.08, this.bus);
        this.next += sixteenth; this.step++;
      }
    },
  };
  function setMusic(on) {
    settings.music = on; store.set("rpsChaosMusic", on);
    $("opt-music").checked = on;
    document.querySelectorAll("[data-toggle-music]").forEach((b) => {
      b.textContent = on ? "🎵 On" : "🎵 Off"; b.setAttribute("aria-pressed", String(on));
    });
    if (on) music.start(); else music.stop();
  }

  // ====================================================================
  // Visual effects
  // ====================================================================
  const canvas = $("confetti");
  const c2d = canvas.getContext("2d");
  let pieces = [];
  function confetti(amount = 140, x = innerWidth / 2, y = innerHeight / 3) {
    if (REDUCED) return;
    canvas.width = innerWidth; canvas.height = innerHeight;
    const colors = ["#ff4fa3", "#3ef0ff", "#b8ff3e", "#ffd23f", "#ffffff"];
    const start = pieces.length === 0;
    for (let i = 0; i < amount; i++) {
      pieces.push({
        x: x + (Math.random() - 0.5) * 120, y,
        vx: (Math.random() - 0.5) * 16, vy: -Math.random() * 14 - 4,
        r: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 0.4,
        w: 6 + Math.random() * 6, h: 8 + Math.random() * 10,
        c: colors[i % colors.length], life: 140 + Math.random() * 60,
      });
    }
    if (start) requestAnimationFrame(drawConfetti);
  }
  function drawConfetti() {
    c2d.clearRect(0, 0, canvas.width, canvas.height);
    pieces = pieces.filter((p) => p.life-- > 0 && p.y < canvas.height + 40);
    for (const p of pieces) {
      p.vy += 0.35; p.vx *= 0.99; p.x += p.vx; p.y += p.vy; p.r += p.vr;
      c2d.save(); c2d.translate(p.x, p.y); c2d.rotate(p.r);
      c2d.fillStyle = p.c; c2d.fillRect(-p.w / 2, -p.h / 2, p.w, p.h); c2d.restore();
    }
    if (pieces.length) requestAnimationFrame(drawConfetti);
    else c2d.clearRect(0, 0, canvas.width, canvas.height);
  }
  function retrigger(el, cls) { el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls); }
  function floatText(el, text, cls) {
    if (REDUCED) return;
    const r = el.getBoundingClientRect();
    const span = document.createElement("span");
    span.className = `float ${cls}`; span.textContent = text;
    span.style.left = `${r.left + r.width / 2}px`; span.style.top = `${r.top + r.height / 2}px`;
    document.body.appendChild(span);
    setTimeout(() => span.remove(), 1200);
  }
  function slam(text) {
    const el = $("slam"); el.textContent = text; retrigger(el, "go");
  }
  function centerOf(el) { const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }

  // ====================================================================
  // API + screens + overlay
  // ====================================================================
  async function api(path, body, headers = {}) {
    const res = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = {};
    try { data = await res.json(); } catch { /* not JSON */ }
    if (!res.ok) { const err = new Error(data.error || "Something went wrong."); err.status = res.status; throw err; }
    return data;
  }

  let screen = "menu";
  function show(id) {
    screen = id;
    for (const s of ["menu", "setup", "battle", "duel"]) $(s).hidden = s !== id;
    $("overlay").hidden = true;
    if (id !== "battle") ladder.stopClock();
    if (id !== "duel") online.stopPolling();
    music.setMood(id === "battle" || id === "duel" ? "battle" : "menu");
    window.scrollTo(0, 0);
  }

  function overlay(emoji, title, text, actions) {
    $("overlay-emoji").textContent = emoji;
    $("overlay-title").textContent = title;
    $("overlay-text").textContent = text;
    const box = $("overlay-actions"); box.innerHTML = "";
    actions.forEach(([label, fn], i) => {
      const btn = document.createElement("button");
      btn.type = "button"; btn.className = i === 0 ? "primary" : "ghost"; btn.textContent = label;
      btn.addEventListener("click", fn); box.appendChild(btn);
    });
    $("overlay").hidden = false;
    const first = box.querySelector("button"); if (first) first.focus();
  }
  function closeOverlay() { $("overlay").hidden = true; }

  function buildMoves(box, moves) {
    box.style.setProperty("--count", moves.length);
    box.innerHTML = moves.map((m) => `
      <button type="button" class="move" data-move="${m}" aria-keyshortcuts="${KEYS[m]}">
        <kbd>${KEYS[m].toUpperCase()}</kbd><span class="sym" aria-hidden="true">${SYM[m]}</span><span>${m}</span>
      </button>`).join("");
  }
  function buildRules(mode) {
    const lines = [];
    for (const [winner, losers] of Object.entries(CONFIG.rulesets[mode].beats)) {
      for (const [loser, verb] of Object.entries(losers)) {
        lines.push(`<li>${SYM[winner]} ${cap(winner)} ${verb} ${loser} ${SYM[loser]}</li>`);
      }
    }
    document.querySelectorAll(".rules-list").forEach((ul) => { ul.innerHTML = lines.join(""); });
  }
  function setMovesDisabled(box, disabled) {
    box.querySelectorAll(".move").forEach((b) => { b.disabled = disabled; });
  }

  // Rules on the client are used only for same-device play (online and ladder use the server).
  function judge(mode, a, b) {
    if (a === b) return { outcome: "tie", text: `Both chose ${a} — it's a stalemate` };
    const beats = CONFIG.rulesets[mode].beats;
    if (beats[a][b]) return { outcome: "win", text: `${cap(a)} ${beats[a][b]} ${b}` };
    return { outcome: "lose", text: `${cap(b)} ${beats[b][a]} ${a}` };
  }

  // ====================================================================
  // Menu
  // ====================================================================
  function renderLadderPreview() {
    $("menu").querySelector(".ladder-preview").innerHTML = CONFIG.bosses
      .map((b, i) => `<li class="${i === CONFIG.bosses.length - 1 ? "final" : ""}"><b>${b.emoji}</b>${b.name}</li>`)
      .join("");
  }
  function ruleset() { return document.querySelector('input[name="ruleset"]:checked').value; }
  function initMenu() {
    renderLadderPreview();
    const radio = document.querySelector(`input[name="ruleset"][value="${settings.ruleset}"]`);
    if (radio) radio.checked = true;
    document.querySelectorAll('input[name="ruleset"]').forEach((r) => r.addEventListener("change", () => {
      settings.ruleset = ruleset(); store.set("rpsChaosRuleset", settings.ruleset);
    }));
    $("opt-clock").checked = settings.clock;
    $("opt-clock").addEventListener("change", (e) => { settings.clock = e.target.checked; store.set("rpsChaosClock", settings.clock); });
    $("opt-sound").checked = settings.sound;
    $("opt-sound").addEventListener("change", (e) => { settings.sound = e.target.checked; store.set("rpsChaosMuted", !settings.sound); });
    $("opt-music").addEventListener("change", (e) => setMusic(e.target.checked));
    setMusic(settings.music);
    document.querySelectorAll("[data-toggle-music]").forEach((b) => b.addEventListener("click", () => setMusic(!settings.music)));
    document.querySelectorAll(".mode-card").forEach((card) => card.addEventListener("click", () => choosePlay(card.dataset.play)));
    document.querySelectorAll("[data-back]").forEach((b) => b.addEventListener("click", goMenu));
  }
  function choosePlay(kind) {
    if (kind === "ladder") ladder.start(ruleset());
    else openSetup(kind);
  }
  function goMenu() {
    online.code = null; online.room = null; local.s = null;
    show("menu");
    if (location.pathname !== "/") history.replaceState(null, "", "/");
    $("menu").querySelector(".mode-card").focus();
  }

  // ====================================================================
  // Setup screen (same-device names / online create / online join)
  // ====================================================================
  let setupKind = null;
  function openSetup(kind, code = null) {
    setupKind = kind;
    show("setup");
    $("setup-error").textContent = "";
    const savedName = store.get("rpsChaosName", "");
    $("name1").value = kind === "local" ? store.get("rpsChaosP1", "") : savedName;
    $("name2").value = store.get("rpsChaosP2", "");
    $("target").innerHTML = CONFIG.targets.map((t) => `<option value="${t}" ${t === 3 ? "selected" : ""}>First to ${t}</option>`).join("");
    $("field-name2").hidden = kind !== "local";
    $("field-target").hidden = kind === "join";
    $("label-name1").textContent = kind === "local" ? "Player 1 name" : "Your name";
    const rules = CONFIG.rulesets[ruleset()].name;
    if (kind === "local") {
      $("setup-title").textContent = "Same Device";
      $("setup-lede").textContent = `${rules}. Take turns picking while the other player looks away.`;
      $("setup-go").textContent = "Start match";
    } else if (kind === "online") {
      $("setup-title").textContent = "Online Match";
      $("setup-lede").textContent = `${rules}. You'll get a link to send to your opponent.`;
      $("setup-go").textContent = "Create room";
    } else {
      $("setup-title").textContent = `Join room ${code}`;
      $("setup-lede").textContent = "Someone invited you to a match. Pick a name and jump in.";
      $("setup-go").textContent = "Join match";
      $("setup-form").dataset.code = code;
    }
    $("name1").focus();
  }
  $("setup-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name1 = $("name1").value.trim(); const name2 = $("name2").value.trim();
    const target = Number($("target").value);
    $("setup-error").textContent = "";
    try {
      if (setupKind === "local") {
        store.set("rpsChaosP1", name1); store.set("rpsChaosP2", name2);
        local.start(ruleset(), target, [name1 || "Player 1", name2 || "Player 2"]);
      } else if (setupKind === "online") {
        store.set("rpsChaosName", name1);
        const data = await api("/api/rooms", { mode: ruleset(), target, name: name1 });
        online.enter(data.room.code, data.token, data.room);
      } else {
        store.set("rpsChaosName", name1);
        const code = $("setup-form").dataset.code;
        const data = await api(`/api/rooms/${code}/join`, { name: name1 });
        online.enter(code, data.token, data.room);
      }
    } catch (err) {
      $("setup-error").textContent = err.message;
    }
  });

  // ====================================================================
  // Boss ladder (vs CPU)
  // ====================================================================
  const ladder = {
    state: null, busy: false, deadline: 0, raf: 0, polling: false, lastPoll: 0,

    async start(mode) {
      const data = await api("/api/new", { mode, shot_clock: settings.clock });
      this.state = data.state;
      show("battle");
      buildMoves($("moves"), this.state.moves); buildRules(mode);
      this.resetArena();
      $("arena").classList.remove("boss-dead");
      this.render();
      this.banner("", "Make your move", "Click a move or press its key.");
      $("boss-speech").textContent = this.state.boss.intro;
      this.syncClock();
    },

    resetArena() {
      $("you-hand").textContent = "✊"; $("boss-hand").textContent = "✊";
      $("you-pick").innerHTML = "&nbsp;"; $("boss-pick").innerHTML = "&nbsp;";
    },
    banner(outcome, title, detail) {
      const b = $("banner");
      if (outcome) b.dataset.outcome = outcome; else delete b.dataset.outcome;
      $("banner-title").textContent = title; $("banner-detail").textContent = detail;
    },

    render() {
      const s = this.state;
      $("battle").querySelector(".ladder").innerHTML = CONFIG.bosses.map((b, i) => {
        const done = i < s.boss.index || s.status === "champion";
        const cls = done ? "done" : i === s.boss.index ? "current" : "";
        return `<li class="${cls}" title="${b.name}"><span aria-hidden="true">${b.emoji}</span><span class="sr">${b.name}${done ? " (defeated)" : ""}</span></li>`;
      }).join("");
      const p2 = s.phase === 2 && s.status === "playing";
      $("boss-name").textContent = (p2 ? "⚡ " : "") + s.boss.name;
      $("boss-avatar").textContent = s.boss.emoji;
      $("boss-title").textContent = `Boss ${s.boss.index + 1}/${s.boss.count} · ${p2 ? "PHASE 2" : s.boss.title}`;
      $("arena").classList.toggle("phase2", p2);
      $("boss-card").classList.toggle("phase2", p2);
      const hp = Math.max(0, s.boss_hp);
      $("boss-hpfill").style.width = `${(hp / s.boss.hp) * 100}%`;
      const bar = $("boss-hpbar");
      bar.setAttribute("aria-valuemax", s.boss.hp); bar.setAttribute("aria-valuenow", hp);
      bar.setAttribute("aria-valuetext", `${hp} of ${s.boss.hp}`);
      const hearts = $("you-hp");
      hearts.innerHTML = Array.from({ length: s.player_max }, (_, i) =>
        `<span class="${i < s.player_hp ? "" : "lost"}" aria-hidden="true">❤️</span>`).join("");
      hearts.setAttribute("aria-label", `Your health: ${Math.max(0, s.player_hp)} of ${s.player_max}`);
      const read = s.brain; const pct = Math.round(read.confidence * 100);
      $("brain-title").textContent = s.boss.id === "oracle" ? "🔮 ORACLE is reading you" : "🔮 ORACLE's scouting report";
      $("brain-insight").textContent = read.insight;
      $("brain-meter").style.width = `${pct}%`;
      $("brain-predict").textContent = read.locked
        ? `🔒 Prediction locked — ${pct}% confident. Break your pattern!`
        : read.prediction
          ? `Predicts your next move: ${SYM[read.prediction]} ${read.prediction.toUpperCase()} (${pct}% sure)`
          : "Watching… ORACLE learns from every move you make.";
      const st = s.stats;
      best = Math.max(best, st.streak); store.set("rpsChaosBest", best);
      $("stat-wins").textContent = st.wins; $("stat-losses").textContent = st.losses;
      $("stat-ties").textContent = st.ties; $("stat-streak").textContent = st.streak;
      $("stat-best").textContent = best;
      music.setMood(p2 || s.boss.id === "oracle" ? "boss" : "battle");
    },

    async play(move) {
      if (this.busy || !this.state || this.state.status !== "playing" || !$("overlay").hidden) return;
      this.busy = true; setMovesDisabled($("moves"), true);
      this.resetArena();
      $("you-pick").textContent = "Rock…";
      this.banner("", "Rock… Paper… Scissors…", "");
      retrigger($("arena"), "shaking"); sfx.tick();
      try {
        const [data] = await Promise.all([api("/api/play", { move }), wait(900)]);
        $("arena").classList.remove("shaking");
        const round = data.round;
        if (round.healed) this.showHeal(round.healed);
        this.reveal(round, data.state);
        this.state = data.state;
        if (!round.defeated) this.render();
        await this.after(round);
      } catch (err) {
        $("arena").classList.remove("shaking");
        this.banner("lose", "Oops", err.message);
      } finally {
        this.busy = false;
        setMovesDisabled($("moves"), !this.state || this.state.status !== "playing");
        this.syncClock();
      }
    },

    reveal(round, next) {
      const you = $("you-hand"); const boss = $("boss-hand");
      you.textContent = SYM[round.player]; boss.textContent = SYM[round.computer];
      retrigger(you, "clash"); retrigger(boss, "clash");
      $("you-pick").textContent = round.player; $("boss-pick").textContent = round.computer;
      $("boss-speech").textContent = round.thought;
      const name = this.state.boss.name;
      const titles = { win: "You win!", lose: `${name} wins`, tie: "It's a tie" };
      this.banner(round.outcome, titles[round.outcome], round.explanation);
      if (round.outcome === "win") {
        sfx.win(); retrigger($("arena"), "flash-win"); retrigger($("boss-hpbar"), "hit");
        floatText($("boss-hpbar"), "-1", "dmg");
      } else if (round.outcome === "lose") {
        sfx.lose(); retrigger($("arena"), "flash-lose"); retrigger(document.body, "shake");
        retrigger($("you-hp"), "hit"); floatText($("you-hp"), "-1 ❤️", "dmg");
      } else {
        sfx.tie(); floatText($("arena"), "TIE", "hit");
      }
      if (round.defeated) {
        // Final blow: show the empty HP bar before the boss explodes.
        $("boss-hpfill").style.width = "0%";
        retrigger($("arena"), "slowmo");
      }
      if (round.phase_change) {
        setTimeout(() => {
          slam("PHASE 2"); sfx.power(); retrigger($("boss-card"), "glitch");
          $("boss-speech").textContent = round.phase_line;
          this.banner("lose", `${name} enters PHASE 2`, "New strategy. Watch closely.");
        }, REDUCED ? 0 : 650);
      }
      return next;
    },

    showHeal(amount) {
      sfx.heal();
      floatText($("boss-hpbar"), `+${amount}`, "heal");
      this.banner("lose", "Delay of game!", `${this.state.boss.name} healed +${amount} while you hesitated.`);
    },

    async after(round) {
      const s = this.state;
      if (round.defeated) {
        await wait(500);
        const [x, y] = centerOf($("boss-hand"));
        $("arena").classList.add("boss-dead");
        confetti(90, x, y); sfx.fanfare();
        await wait(1000);
        $("arena").classList.remove("boss-dead");
        this.render();
      }
      if (s.status === "champion") {
        confetti(260); setTimeout(() => confetti(200), 600);
        overlay("👑", "Champion!", `You beat all five bosses — including ORACLE at full power. ${s.stats.wins} wins, ${s.stats.losses} losses, ${s.stats.ties} ties.`, [
          ["Play again", () => this.start(s.mode)], ["Menu", goMenu],
        ]);
      } else if (round.defeated) {
        const next = s.boss;
        overlay(next.emoji, "Boss defeated!", `Next up: ${next.name}, ${next.title}. Hint: ${next.hint} Your health is restored.`, [
          [`Fight ${next.name}`, async () => {
            closeOverlay(); this.resetArena();
            this.banner("", "New challenger!", `${next.name} enters the arena.`);
            $("boss-speech").textContent = next.intro;
            const data = await api("/api/clock/restart", {});
            this.state = data.state; this.syncClock();
          }],
        ]);
      } else if (s.status === "lost") {
        await wait(700); sfx.gameover();
        overlay("💀", "Game over", `${s.boss.name} knocked you out. Hint: ${s.boss.hint}`, [
          ["Try again", () => this.start(s.mode)], ["Menu", goMenu],
        ]);
      }
    },

    // ----- shot clock -----
    syncClock() {
      const c = this.state && this.state.clock;
      $("shotclock").hidden = !(c && c.on);
      cancelAnimationFrame(this.raf);
      if (!c || !c.on || this.state.status !== "playing") return;
      this.deadline = performance.now() + c.left * 1000;
      const tick = () => {
        if (screen !== "battle") return;
        const left = (this.deadline - performance.now()) / 1000;
        const paused = this.busy || !$("overlay").hidden;
        const shown = Math.max(0, Math.min(c.limit, left));
        $("shotclock-fill").style.width = `${(shown / c.limit) * 100}%`;
        $("shotclock").classList.toggle("warn", left > 0 && left < 2);
        $("shotclock").classList.toggle("over", left <= 0);
        $("shotclock-label").textContent = left > 0 ? `⏱ ${shown.toFixed(1)}s` : "⏱ Delay!";
        if (left <= 0 && !paused && !this.polling && performance.now() - this.lastPoll > 900) this.poll();
        this.raf = requestAnimationFrame(tick);
      };
      this.raf = requestAnimationFrame(tick);
    },
    async poll() {
      this.polling = true; this.lastPoll = performance.now();
      try {
        const data = await api("/api/state");
        if (data.state && !this.busy && screen === "battle") {
          if (data.state.healed) { this.state = data.state; this.showHeal(data.state.healed); this.render(); }
        }
      } catch { /* try again next tick */ }
      this.polling = false;
    },
    stopClock() { cancelAnimationFrame(this.raf); },
  };
  $("moves").addEventListener("click", (e) => {
    const btn = e.target.closest(".move"); if (btn) ladder.play(btn.dataset.move);
  });

  // ====================================================================
  // Shared duel view (same device + online)
  // ====================================================================
  const duel = {
    setup(mode, target, names) {
      show("duel");
      buildMoves($("duel-moves"), CONFIG.rulesets[mode].moves); buildRules(mode);
      $("duel-target").textContent = `First to ${target} · ${CONFIG.rulesets[mode].name}`;
      this.names(names); this.scores([0, 0]); this.resetHands();
      $("duel-lock0").textContent = ""; $("duel-lock1").textContent = "";
    },
    names(names) {
      [0, 1].forEach((i) => {
        $(`duel-name${i}`).textContent = names[i]; $(`duel-label${i}`).textContent = names[i];
      });
    },
    scores(scores) { [0, 1].forEach((i) => { $(`duel-score${i}`).textContent = scores[i]; }); },
    resetHands() {
      $("duel-hand0").textContent = "✊"; $("duel-hand1").textContent = "✊";
      $("duel-pick0").innerHTML = "&nbsp;"; $("duel-pick1").innerHTML = "&nbsp;";
    },
    banner(outcome, title, detail) {
      const b = $("duel-banner");
      if (outcome) b.dataset.outcome = outcome; else delete b.dataset.outcome;
      $("duel-title").textContent = title; $("duel-detail").textContent = detail;
    },
    // moves/names from the left player's point of view; winner: 0 left, 1 right, null tie
    async reveal(moves, winner, explanation, names, leftIsYou) {
      this.resetHands(); retrigger($("duel-arena"), "shaking"); sfx.tick();
      this.banner("", "Rock… Paper… Scissors…", "");
      await wait(900);
      $("duel-arena").classList.remove("shaking");
      [0, 1].forEach((i) => {
        $(`duel-hand${i}`).textContent = SYM[moves[i]]; retrigger($(`duel-hand${i}`), "clash");
        $(`duel-pick${i}`).textContent = moves[i];
      });
      if (winner === null) {
        sfx.tie(); this.banner("tie", "It's a tie", explanation); floatText($("duel-arena"), "TIE", "hit");
      } else {
        const good = leftIsYou ? winner === 0 : true;
        (good ? sfx.win : sfx.lose)();
        retrigger($("duel-arena"), winner === 0 ? "flash-win" : "flash-lose");
        if (leftIsYou && winner === 1) retrigger(document.body, "shake");
        this.banner(leftIsYou ? (winner === 0 ? "win" : "lose") : "win",
          leftIsYou ? (winner === 0 ? "You win the round!" : `${names[1]} wins the round`) : `${names[winner]} wins the round!`,
          explanation);
        floatText($(`duel-score${winner}`), "+1", "heal");
      }
    },
  };

  // ----- same device -----
  const local = {
    s: null, busy: false,
    start(mode, target, names) {
      this.s = { mode, target, names, scores: [0, 0], picks: [null, null], turn: 0 };
      duel.setup(mode, target, names);
      $("share").hidden = true;
      this.prompt();
    },
    prompt() {
      const s = this.s; const who = s.names[s.turn]; const other = s.names[1 - s.turn];
      duel.banner("", `${who}, pick your move`, `${other}: look away! 👀`);
      $("duel-lock0").textContent = s.picks[0] ? "Locked in ✓" : "";
      $("duel-lock1").textContent = s.picks[1] ? "Locked in ✓" : "";
      setMovesDisabled($("duel-moves"), false);
    },
    async pick(move) {
      const s = this.s; if (!s || this.busy || !$("overlay").hidden) return;
      s.picks[s.turn] = move; sfx.lock();
      if (s.turn === 0) {
        s.turn = 1; $("duel-lock0").textContent = "Locked in ✓";
        setMovesDisabled($("duel-moves"), true);
        overlay("🙈", `Pass to ${s.names[1]}`, `${s.names[0]} has locked in. ${s.names[0]}, no peeking at their pick!`, [
          [`I'm ${s.names[1]} — ready`, () => { closeOverlay(); this.prompt(); }],
        ]);
        return;
      }
      this.busy = true; setMovesDisabled($("duel-moves"), true);
      $("duel-lock1").textContent = "Locked in ✓";
      const [a, b] = s.picks; const res = judge(s.mode, a, b);
      const winner = { win: 0, lose: 1, tie: null }[res.outcome];
      await duel.reveal([a, b], winner, res.text, s.names, false);
      if (winner !== null) s.scores[winner] += 1;
      duel.scores(s.scores);
      s.picks = [null, null]; s.turn = 0; this.busy = false;
      const champ = s.scores.findIndex((x) => x >= s.target);
      if (champ >= 0) {
        await wait(700); sfx.fanfare(); confetti(200);
        overlay("🏆", `${s.names[champ]} wins!`, `Final score ${s.scores[0]}–${s.scores[1]}.`, [
          ["Rematch", () => this.start(s.mode, s.target, s.names)], ["Menu", goMenu],
        ]);
      } else {
        await wait(1200);
        if (this.s === s) this.prompt();
      }
    },
  };

  // ----- online -----
  const online = {
    code: null, token: null, room: null, timer: null, shownRound: 0, busy: false, lastStatus: null,
    enter(code, token, room) {
      this.code = code; this.token = token; this.room = room;
      store.set(`rpsRoom:${code}`, token);
      if (location.pathname !== `/r/${code}`) history.replaceState(null, "", `/r/${code}`);
      duel.setup(room.mode, room.target, this.names(room));
      this.shownRound = room.round; this.lastStatus = null;
      const link = `${location.origin}/r/${code}`;
      $("share-link").value = link; $("share-code").textContent = code;
      $("share-native").hidden = !navigator.share;
      this.update(room);
      this.startPolling();
    },
    names(room) {
      const me = room.names[room.you] || "You"; const them = room.names[1 - room.you] || "Waiting…";
      return [`${me} (you)`, them];
    },
    startPolling() {
      this.stopPolling();
      this.timer = setInterval(() => this.poll(), 1000);
    },
    stopPolling() { clearInterval(this.timer); this.timer = null; },
    async poll() {
      if (!this.code || this.busy) return;
      try {
        const data = await api(`/api/rooms/${this.code}`, undefined, { "X-Player-Token": this.token });
        await this.update(data.room);
      } catch (err) {
        if (err.status === 404 || err.status === 403) {
          this.stopPolling();
          overlay("🚪", "Room closed", err.message, [["Menu", goMenu]]);
        }
      }
    },
    async update(room) {
      this.room = room;
      const you = room.you; const them = 1 - you;
      const names = this.names(room);
      duel.names(names);
      $("share").hidden = room.status !== "waiting";
      if (room.status === "waiting") {
        duel.banner("", "Waiting for your opponent", isLocalHost
          ? "Heads up: a 127.0.0.1 link only works on this computer. Deploy the game or use a tunnel to play someone else."
          : "Send them the link above. The match starts as soon as they join.");
      }
      if (this.lastStatus === "waiting" && room.status === "playing") {
        sfx.join(); floatText($("duel-label1"), "joined!", "heal");
      }
      // A new round finished: animate it from our point of view.
      if (room.round > this.shownRound && room.last) {
        this.shownRound = room.round; this.busy = true;
        const mine = room.last.moves[you]; const theirs = room.last.moves[them];
        const winner = room.last.winner === null ? null : room.last.winner === you ? 0 : 1;
        await duel.reveal([mine, theirs], winner, room.last.explanation, names, true);
        this.busy = false;
      }
      duel.scores([room.scores[you], room.scores[them]]);
      $("duel-lock0").textContent = room.your_move ? "Locked in ✓" : "";
      $("duel-lock1").textContent = room.status === "playing" ? (room.opponent_locked ? "Locked in ✓" : "Thinking…") : "";
      const canMove = room.status === "playing" && !room.your_move;
      setMovesDisabled($("duel-moves"), !canMove);
      if (room.status === "playing" && this.lastStatus !== "playing" && !room.your_move && !room.last) {
        duel.banner("", "Pick your move", `First to ${room.target} wins. Your opponent can't see your pick.`);
      }
      if (room.status === "playing" && room.your_move) {
        duel.banner("", "Locked in!", room.opponent_locked ? "Revealing…" : `Waiting for ${names[1]}…`);
      }
      if (room.status === "finished" && this.lastStatus !== "finished") {
        const won = room.winner === you;
        if (won) { sfx.fanfare(); confetti(200); } else { sfx.gameover(); }
        this.finishedOverlay(room, names);
      } else if (room.status === "finished") {
        if (room.rematch.you) $("overlay-text").textContent = `Waiting for ${names[1]} to accept the rematch…`;
      }
      if (this.lastStatus === "finished" && room.status === "playing") {
        closeOverlay(); duel.resetHands(); this.shownRound = room.round;
        duel.banner("", "Rematch!", "Scores reset. Pick your move.");
      }
      this.lastStatus = room.status;
    },
    finishedOverlay(room, names) {
      const won = room.winner === room.you;
      overlay(won ? "🏆" : "😵", won ? "You win the match!" : `${names[1]} wins the match`,
        `Final score ${room.scores[room.you]}–${room.scores[1 - room.you]}.`, [
          ["Rematch", async () => {
            try {
              const data = await api(`/api/rooms/${this.code}/rematch`, {}, { "X-Player-Token": this.token });
              await this.update(data.room);
            } catch (err) { $("overlay-text").textContent = err.message; }
          }],
          ["Menu", goMenu],
        ]);
      if (room.rematch.opponent) $("overlay-text").textContent += ` ${names[1]} wants a rematch!`;
    },
    async pick(move) {
      if (!this.room || this.room.status !== "playing" || this.room.your_move || this.busy) return;
      setMovesDisabled($("duel-moves"), true); sfx.lock();
      try {
        const data = await api(`/api/rooms/${this.code}/move`, { move }, { "X-Player-Token": this.token });
        await this.update(data.room);
      } catch (err) {
        duel.banner("lose", "Oops", err.message);
        setMovesDisabled($("duel-moves"), false);
      }
    },
    async open(code) {
      const token = store.get(`rpsRoom:${code}`, null);
      if (token) {
        try {
          const data = await api(`/api/rooms/${code}`, undefined, { "X-Player-Token": token });
          this.enter(code, token, data.room); return;
        } catch { /* stale token: join fresh */ }
      }
      openSetup("join", code);
    },
  };
  $("duel-moves").addEventListener("click", (e) => {
    const btn = e.target.closest(".move"); if (!btn) return;
    if (online.code && screen === "duel" && online.room) online.pick(btn.dataset.move);
    else local.pick(btn.dataset.move);
  });
  $("share-copy").addEventListener("click", async () => {
    const input = $("share-link");
    try { await navigator.clipboard.writeText(input.value); } catch { input.select(); document.execCommand("copy"); }
    $("share-copy").textContent = "Copied!"; setTimeout(() => { $("share-copy").textContent = "Copy"; }, 1500);
  });
  $("share-native").addEventListener("click", () => {
    navigator.share({ title: "RPS Chaos", text: "Play me in RPS Chaos!", url: $("share-link").value }).catch(() => {});
  });

  // ====================================================================
  // Keyboard
  // ====================================================================
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.target.closest('input:not([type="checkbox"]):not([type="radio"]), select, textarea')) return;
    if (!$("overlay").hidden) return;
    const key = e.key.toLowerCase();
    if (screen === "menu") {
      const kind = { 1: "ladder", 2: "local", 3: "online" }[key];
      if (kind) { e.preventDefault(); choosePlay(kind); }
      return;
    }
    let moves = null;
    if (screen === "battle" && ladder.state) moves = ladder.state.moves;
    if (screen === "duel") moves = online.room ? online.room.moves : local.s ? CONFIG.rulesets[local.s.mode].moves : null;
    if (!moves) return;
    const byLetter = moves.find((m) => KEYS[m] === key || (m === "spock" && key === "v"));
    const move = byLetter || (/^[1-5]$/.test(key) ? moves[Number(key) - 1] : null);
    if (!move) return;
    e.preventDefault();
    if (screen === "battle") ladder.play(move);
    else if (online.room) online.pick(move);
    else local.pick(move);
  });

  // Browsers only allow audio after a user gesture: start music on the first one.
  document.addEventListener("pointerdown", () => { if (settings.music) music.start(); }, { once: true });
  document.addEventListener("keydown", () => { if (settings.music) music.start(); }, { once: true });

  // ====================================================================
  // Boot
  // ====================================================================
  initMenu();
  if (CONFIG.room) online.open(CONFIG.room);
  else show("menu");
  if ("serviceWorker" in navigator && !navigator.webdriver) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
})();
