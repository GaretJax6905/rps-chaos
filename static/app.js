/* RPS Chaos front end: screens, animations, sound, keyboard. Talks to /api/*. */
(() => {
  "use strict";

  const CONFIG = JSON.parse(document.getElementById("config").textContent);
  const SYM = CONFIG.symbols;
  const KEYS = { rock: "r", paper: "p", scissors: "s", lizard: "l", spock: "k" };
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (id) => document.getElementById(id);

  let state = null;
  let busy = false;

  // ---------- storage (best effort) ----------
  const store = {
    get(key, fallback) {
      try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); }
      catch { return fallback; }
    },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ } },
  };
  let muted = store.get("rpsChaosMuted", false);
  let best = store.get("rpsChaosBest", 0);

  // ---------- sound ----------
  let audio = null;
  function tone(freq, start, dur, type = "square", vol = 0.06) {
    if (muted) return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      const t = audio.currentTime + start;
      const osc = audio.createOscillator();
      const gain = audio.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, t);
      gain.gain.setValueAtTime(vol, t);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      osc.connect(gain).connect(audio.destination);
      osc.start(t);
      osc.stop(t + dur + 0.02);
    } catch { /* audio unavailable */ }
  }
  const sfx = {
    tick: () => [0, 0.3, 0.6].forEach((s, i) => tone(330 + i * 60, s, 0.08)),
    win: () => [523, 659, 784].forEach((f, i) => tone(f, i * 0.08, 0.14, "triangle", 0.09)),
    lose: () => [311, 233, 156].forEach((f, i) => tone(f, i * 0.1, 0.18, "sawtooth", 0.05)),
    tie: () => tone(440, 0, 0.15, "sine", 0.07),
    fanfare: () => [523, 659, 784, 1047, 784, 1047].forEach((f, i) => tone(f, i * 0.11, 0.2, "triangle", 0.1)),
    gameover: () => [392, 330, 262, 196].forEach((f, i) => tone(f, i * 0.18, 0.3, "sawtooth", 0.05)),
  };

  // ---------- confetti ----------
  const canvas = $("confetti");
  const ctx = canvas.getContext("2d");
  let pieces = [];
  function confetti(amount = 140) {
    if (REDUCED) return;
    canvas.width = innerWidth; canvas.height = innerHeight;
    const colors = ["#ff4fa3", "#3ef0ff", "#b8ff3e", "#ffd23f", "#ffffff"];
    for (let i = 0; i < amount; i++) {
      pieces.push({
        x: innerWidth / 2 + (Math.random() - 0.5) * 200, y: innerHeight / 3,
        vx: (Math.random() - 0.5) * 16, vy: -Math.random() * 14 - 4,
        r: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 0.4,
        w: 6 + Math.random() * 6, h: 8 + Math.random() * 10,
        c: colors[i % colors.length], life: 140 + Math.random() * 60,
      });
    }
    if (pieces.length === amount) requestAnimationFrame(drawConfetti);
  }
  function drawConfetti() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    pieces = pieces.filter((p) => p.life-- > 0 && p.y < canvas.height + 40);
    for (const p of pieces) {
      p.vy += 0.35; p.vx *= 0.99; p.x += p.vx; p.y += p.vy; p.r += p.vr;
      ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.r);
      ctx.fillStyle = p.c; ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h); ctx.restore();
    }
    if (pieces.length) requestAnimationFrame(drawConfetti);
    else ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  // ---------- helpers ----------
  async function api(path, body) {
    const res = await fetch(path, {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Something went wrong.");
    return data;
  }
  const wait = (ms) => new Promise((r) => setTimeout(r, REDUCED ? 0 : ms));
  function retrigger(el, cls) { el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls); }
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

  // ---------- start screen ----------
  function renderLadderPreview() {
    $("start").querySelector(".ladder-preview").innerHTML = CONFIG.bosses
      .map((b, i) => `<li class="${i === CONFIG.bosses.length - 1 ? "final" : ""}"><b>${b.emoji}</b>${b.name}</li>`)
      .join("");
  }
  function showStart() {
    state = null;
    $("battle").hidden = true; $("overlay").hidden = true; $("start").hidden = false;
    $("start").querySelector(".mode-card").focus();
  }

  async function startGame(mode) {
    const data = await api("/api/new", { mode });
    state = data.state;
    $("start").hidden = true; $("overlay").hidden = true; $("battle").hidden = false;
    buildMoves(); buildRules(); resetArena();
    render();
    setBanner("", "Make your move", "Click a move or press its key.");
    $("boss-speech").textContent = state.boss.intro;
  }

  // ---------- battle screen ----------
  function buildMoves() {
    const box = $("moves");
    box.style.setProperty("--count", state.moves.length);
    box.innerHTML = state.moves.map((m) => `
      <button type="button" class="move" data-move="${m}" aria-keyshortcuts="${KEYS[m]}">
        <kbd>${KEYS[m].toUpperCase()}</kbd><span class="sym" aria-hidden="true">${SYM[m]}</span><span>${m}</span>
      </button>`).join("");
  }
  function buildRules() {
    const beats = CONFIG.rulesets[state.mode].beats;
    const lines = [];
    for (const [winner, losers] of Object.entries(beats)) {
      for (const [loser, verb] of Object.entries(losers)) {
        lines.push(`<li>${SYM[winner]} ${cap(winner)} ${verb} ${loser} ${SYM[loser]}</li>`);
      }
    }
    $("rules-list").innerHTML = lines.join("");
  }
  function resetArena() {
    $("you-hand").textContent = "✊"; $("boss-hand").textContent = "✊";
    $("you-pick").innerHTML = "&nbsp;"; $("boss-pick").innerHTML = "&nbsp;";
  }
  function setBanner(outcome, title, detail) {
    const b = $("banner");
    if (outcome) b.dataset.outcome = outcome; else delete b.dataset.outcome;
    $("banner-title").textContent = title;
    $("banner-detail").textContent = detail;
  }

  function render() {
    const s = state;
    // ladder
    $("battle").querySelector(".ladder").innerHTML = CONFIG.bosses.map((b, i) => {
      const done = i < s.boss.index || s.status === "champion";
      const cls = done ? "done" : i === s.boss.index ? "current" : "";
      return `<li class="${cls}" title="${b.name}"><span aria-hidden="true">${b.emoji}</span><span class="sr">${b.name}${done ? " (defeated)" : ""}</span></li>`;
    }).join("");
    // boss
    $("boss-name").textContent = s.boss.name;
    $("boss-avatar").textContent = s.boss.emoji;
    $("boss-title").textContent = `Boss ${s.boss.index + 1}/${s.boss.count} · ${s.boss.title}`;
    const hp = Math.max(0, s.boss_hp);
    $("boss-hpfill").style.width = `${(hp / s.boss.hp) * 100}%`;
    const bar = $("boss-hpbar");
    bar.setAttribute("aria-valuemax", s.boss.hp); bar.setAttribute("aria-valuenow", hp);
    bar.setAttribute("aria-valuetext", `${hp} of ${s.boss.hp}`);
    // player hearts
    const hearts = $("you-hp");
    hearts.innerHTML = Array.from({ length: s.player_max }, (_, i) =>
      `<span class="${i < s.player_hp ? "" : "lost"}" aria-hidden="true">❤️</span>`).join("");
    hearts.setAttribute("aria-label", `Your health: ${Math.max(0, s.player_hp)} of ${s.player_max}`);
    // brain
    const read = s.brain;
    const oracleFight = s.boss.id === "oracle";
    $("brain-title").textContent = oracleFight ? "🔮 ORACLE is reading you" : "🔮 ORACLE's scouting report";
    $("brain-insight").textContent = read.insight;
    $("brain-meter").style.width = `${Math.round(read.confidence * 100)}%`;
    $("brain-predict").textContent = read.locked
      ? `🔒 Prediction locked — ${Math.round(read.confidence * 100)}% confident. Break your pattern!`
      : read.prediction
        ? `Predicts your next move: ${SYM[read.prediction]} ${read.prediction.toUpperCase()} (${Math.round(read.confidence * 100)}% sure)`
        : "Watching… ORACLE learns from every move you make.";
    // stats
    const st = s.stats;
    best = Math.max(best, st.streak); store.set("rpsChaosBest", best);
    $("stat-wins").textContent = st.wins; $("stat-losses").textContent = st.losses;
    $("stat-ties").textContent = st.ties; $("stat-streak").textContent = st.streak;
    $("stat-best").textContent = best;
    // mute
    $("mute").textContent = muted ? "🔇 Muted" : "🔊 Sound";
    $("mute").setAttribute("aria-pressed", String(muted));
  }

  async function play(move) {
    if (busy || !state || state.status !== "playing") return;
    busy = true;
    document.querySelectorAll(".move").forEach((b) => { b.disabled = true; });
    const arena = $("arena");
    resetArena();
    $("you-pick").textContent = "Rock…";
    setBanner("", "Rock… Paper… Scissors…", "");
    retrigger(arena, "shaking");
    sfx.tick();
    try {
      const [data] = await Promise.all([api("/api/play", { move }), wait(900)]);
      arena.classList.remove("shaking");
      reveal(data.round);
      state = data.state;
      render();
      await afterRound(data.round);
    } catch (err) {
      arena.classList.remove("shaking");
      setBanner("lose", "Oops", err.message);
    } finally {
      busy = false;
      document.querySelectorAll(".move").forEach((b) => { b.disabled = state && state.status !== "playing"; });
    }
  }

  function reveal(round) {
    const you = $("you-hand"); const boss = $("boss-hand");
    you.textContent = SYM[round.player]; boss.textContent = SYM[round.computer];
    retrigger(you, "reveal"); retrigger(boss, "reveal");
    $("you-pick").textContent = round.player; $("boss-pick").textContent = round.computer;
    $("boss-speech").textContent = round.thought;
    const titles = { win: "You win!", lose: `${state.boss.name} wins`, tie: "It's a tie" };
    setBanner(round.outcome, titles[round.outcome], round.explanation);
    const arena = $("arena");
    if (round.outcome === "win") {
      sfx.win(); retrigger(arena, "flash-win"); retrigger($("boss-hpbar"), "hit");
    } else if (round.outcome === "lose") {
      sfx.lose(); retrigger(arena, "flash-lose"); retrigger(document.body, "shake"); retrigger($("you-hp"), "hit");
    } else {
      sfx.tie();
    }
  }

  async function afterRound(round) {
    if (state.status === "champion") {
      await wait(700);
      sfx.fanfare(); confetti(260); setTimeout(() => confetti(200), 600);
      overlay("👑", "Champion!", `You beat all five bosses — including ORACLE. ${state.stats.wins} wins, ${state.stats.losses} losses, ${state.stats.ties} ties.`, [
        ["Play again", () => startGame(state.mode)], ["Change mode", showStart],
      ]);
    } else if (round.defeated) {
      await wait(600);
      sfx.fanfare(); confetti();
      const next = state.boss;
      overlay(next.emoji, "Boss defeated!", `Next up: ${next.name}, ${next.title}. Hint: ${next.hint} Your health is restored.`, [
        [`Fight ${next.name}`, () => {
          closeOverlay(); resetArena();
          setBanner("", "New challenger!", `${next.name} enters the arena.`);
          $("boss-speech").textContent = next.intro;
        }],
      ]);
    } else if (state.status === "lost") {
      await wait(700);
      sfx.gameover();
      overlay("💀", "Game over", `${state.boss.name} knocked you out. Hint: ${state.boss.hint}`, [
        ["Try again", () => startGame(state.mode)], ["Change mode", showStart],
      ]);
    }
  }

  function overlay(emoji, title, text, actions) {
    $("overlay-emoji").textContent = emoji;
    $("overlay-title").textContent = title;
    $("overlay-text").textContent = text;
    const box = $("overlay-actions");
    box.innerHTML = "";
    actions.forEach(([label, fn], i) => {
      const btn = document.createElement("button");
      btn.type = "button"; btn.className = i === 0 ? "primary" : "ghost"; btn.textContent = label;
      btn.addEventListener("click", fn);
      box.appendChild(btn);
    });
    $("overlay").hidden = false;
    box.querySelector("button").focus();
  }
  function closeOverlay() {
    $("overlay").hidden = true;
    const first = document.querySelector(".move"); if (first) first.focus();
  }

  // ---------- events ----------
  document.querySelectorAll(".mode-card").forEach((card) =>
    card.addEventListener("click", () => startGame(card.dataset.mode)));
  $("moves").addEventListener("click", (e) => {
    const btn = e.target.closest(".move"); if (btn) play(btn.dataset.move);
  });
  $("quit").addEventListener("click", showStart);
  $("mute").addEventListener("click", () => { muted = !muted; store.set("rpsChaosMuted", muted); render(); });

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const key = e.key.toLowerCase();
    if (!$("overlay").hidden) return;
    if (!$("start").hidden) {
      if (key === "1") startGame("classic");
      if (key === "2") startGame("spock");
      return;
    }
    if (!state) return;
    const byLetter = state.moves.find((m) => KEYS[m] === key || (m === "spock" && key === "v"));
    const byNumber = state.moves[Number(key) - 1];
    const move = byLetter || (/^[1-5]$/.test(key) ? byNumber : null);
    if (move) { e.preventDefault(); play(move); }
  });

  renderLadderPreview();
})();
