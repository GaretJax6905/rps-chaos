# RPS Chaos

**▶ Play it: https://rps-chaos.onrender.com** (free hosting: the first visit after a quiet spell can take ~30–60 s to wake up)

Rock Paper Scissors — or Rock Paper Scissors Lizard Spock — four ways:

- **🏆 Boss Ladder (vs CPU):** five bosses, each with a phase 2, and a power-up after every win. The last one, **ORACLE**, learns your patterns and, at full power, learns when you try to out-think it.
- **♾️ Endless:** the bosses keep coming in tougher laps (+2 HP per lap). Chase a spot on the arcade-style top 10.
- **🤝 Same Device:** two players pass one phone or laptop back and forth.
- **🌐 Online:** create a room, send the link, and play a friend anywhere.

Built as a follow-up to the IS218 RPS-001 lab ([my-rps-001](https://github.com/GaretJax6905/my-rps-001)), with Claude (AI) as a coding partner.

## Features

### Boss Ladder

| Boss | HP | Phase 1 | Phase 2 (half HP or less) |
| --- | --- | --- | --- |
| 🪨 Rocky Boulderson | 3 | Rock ~70% of the time | Switches to paper ~70% |
| 🪞 Mirror Max | 3 | Copies your previous move | Copies your move from two rounds ago |
| 🤖 CYCLE-BOT 9000 | 4 | Cycles through the moves | Cycles in reverse |
| 😈 The Contrarian | 4 | Beats your previous move | Double bluff: expects you to dodge the obvious counter |
| 🔮 ORACLE | 5 | Pattern voting (`brain.predict`) | Meta-strategy (`brain.meta_choose`) |

You have 5 hearts. Win a round to damage the boss; lose one to lose a heart; ties do nothing. Beating a boss restores 2 hearts and offers **3 of 5 power-ups**:

| Power-up | Effect |
| --- | --- |
| 🛡️ Shield | Blocks the next round you lose |
| ⚔️ Double Strike | Your next win deals 2 damage |
| 👁️ Peek | Once, see the boss's next move before you pick (the server locks that move in, so it's honest) |
| ❤️‍🩹 Full Heal | Restore every heart |
| 💖 +1 Max Heart | One more heart for the rest of the run |

**Score:** 100 per boss beaten + 10 per round won. **Endless high scores** work like an arcade cabinet: each device keeps its own top 10 per ruleset (in the browser's local storage), and you only enter your initials if you make the board.

**ORACLE, phase 1** votes on your next move using your favorite move, what follows your last move, what you do after a win/loss/tie, and two-move sequences. The scouting report shows what it has learned.

**ORACLE, phase 2** runs four predictors (your patterns, repeating yourself, countering its last move, your favorite) at three "levels of thinking ahead" each, replays every strategy over your history with decaying scores, and plays the one that would have won most. If nothing is working, it plays randomly so it can't be exploited.

**⏱ Shot clock (optional):** 5 seconds per move. Stall and the boss heals +1 for delay of game, then +1 every 3 seconds, up to full health. The server keeps time, so the penalty is real.

### Two players

- **Same Device:** player 1 picks, a hand-off screen hides it, player 2 picks, then both are revealed. First to 1, 2, 3, or 5.
- **Online:** each player's move stays on the server, hidden from the other until both lock in. Rooms have a 4-character code and a link like `/r/K7QX`; refreshing the page rejoins the same seat. Rematches need both players to agree.

### Polish

Hand-pump countdown, clash reveal, floating damage/heal numbers, phase-2 slam and glitch, boss explosion, slow-mo final blow, confetti, screen shake, a WebAudio chiptune soundtrack with **a different track for each boss** (faster, a semitone higher, and with drums in phase 2), sound effects, and keyboard controls (`1`/`2`/`3` on the menu; `R` `P` `S` `L` `K` or `1`–`5` to play). It installs on a phone home screen (web app manifest + service worker).

## Run it (WSL/Ubuntu, Python 3.12)

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install --with-deps chromium
.venv/bin/python run.py
```

Open http://127.0.0.1:5050. Use `PORT=5051 .venv/bin/python run.py` if 5050 is busy.

## Play with someone else

`127.0.0.1` only works on your own computer. Three ways to share:

1. **Public site (any distance, no laptop needed): Render.** This repo has a `render.yaml`. In Render, choose **New → Blueprint**, connect this GitHub repo, and apply. You get a URL like `https://rps-chaos.onrender.com`. The free plan sleeps after ~15 idle minutes (the first visit then takes ~30–60 s) and restarts clear any open online rooms.
2. **Temporary public link (any distance, laptop must stay on): Cloudflare quick tunnel.** With the game running, in a second terminal:

   ```sh
   curl -L -o cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i cloudflared.deb
   cloudflared tunnel --url http://127.0.0.1:5050
   ```

   It prints an `https://….trycloudflare.com` address. Open that, create the online room there, and share the room link.
3. **Same Wi-Fi only:** run `HOST=0.0.0.0 .venv/bin/python run.py`. WSL2 may need mirrored networking or a Windows port-forward for other devices to reach it, so options 1–2 are usually easier.

## Checks

```sh
.venv/bin/python check.py
```

Runs Black, Pylint, unit and integration tests, and real Chromium browser tests. CI runs the same command on every push and PR.

| File | What it covers |
| --- | --- |
| `tests/test_rules.py` | All 9 classic and 25 Lizard Spock matchups, written out literally; explanations |
| `tests/test_ai.py` | Phase-1 ORACLE, each boss strategy, HP, advancing, game over, champion |
| `tests/test_v2.py` | Phase 2 thresholds and strategies, full-power ORACLE (catches cycles and counter-players), shot clock timing |
| `tests/test_v3.py` | Power-up choice, Shield, Double Strike, Peek honesty, heals, Endless tiers and scoring, shot clock pausing during the choice |
| `tests/test_rooms.py` | Hidden moves, scoring from both seats, match end and rematch, full rooms, strangers, expiry, HTTP errors, PWA files |
| `tests/test_api.py` | Ladder API: new game, rounds, session, HTTP 400 for bad modes and moves |
| `tests/e2e/test_game.py` | Real browser: ladder with phase 2 and boss defeat, Lizard Spock by keyboard, game over, shot clock healing, Endless power-up pick and high-score entry, same-device match, two separate browsers playing online |

Tests fix only the boss's move (or shrink the shot clock) when they need a predictable result; the real rules, HTTP, and sessions always run.

## Code map

`rules.py` rulesets · `brain.py` ORACLE (both phases) · `bosses.py` boss strategies and phases · `battle.py` run state, power-ups, Endless, score, shot clock (pure, no Flask) · `rooms.py` online rooms · `app.py` page + JSON API · `static/app.js` screens, animation, music, keyboard · `static/style.css` look · `static/sw.js` + `static/manifest.webmanifest` phone install · `render.yaml` deployment.
