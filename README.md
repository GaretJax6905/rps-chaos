# RPS Chaos

Rock Paper Scissors — or Rock Paper Scissors Lizard Spock — against a ladder of five bosses. The last one, **ORACLE**, learns your patterns and plays to beat them.

Built as a follow-up to the IS218 RPS-001 lab ([my-rps-001](https://github.com/GaretJax6905/my-rps-001)), with Claude (AI) as a coding partner.

## Features

- **Two rulesets:** classic RPS (3 moves) or Lizard Spock (5 moves, each beats two and loses to two). The rules are data tables in `rules.py`, so explanations like "Spock vaporizes rock" come from the same place as the results.
- **Boss ladder:** five opponents, each with one readable strategy.

  | Boss | HP | How it plays |
  | --- | --- | --- |
  | 🪨 Rocky Boulderson | 3 | Rock about 70% of the time |
  | 🪞 Mirror Max | 3 | Copies your previous move |
  | 🤖 CYCLE-BOT 9000 | 4 | Cycles through the moves in order |
  | 😈 The Contrarian | 4 | Plays what beats your previous move |
  | 🔮 ORACLE | 5 | Predicts you from patterns across the whole run |

- **Pattern-learning AI** (`brain.py`): several detectors vote on your next move — your favorite move, what follows your last move, what you do after a win/loss/tie, and two-move sequences. The scouting report shows what it has learned. During the ORACLE fight its prediction is locked.
- **Effects:** rock-paper-scissors hand pump, reveal pop, screen shake on a loss, confetti on a boss defeat, WebAudio sound effects with a mute toggle, and HP bars/hearts.
- **Keyboard:** `1`/`2` choose the mode; `R` `P` `S` `L` `K` (or `1`–`5`) play moves.

You have 5 hearts. Win a round to damage the boss; lose one to lose a heart; ties do nothing. Beating a boss restores your hearts.

## Run it (WSL/Ubuntu, Python 3.12)

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install --with-deps chromium
.venv/bin/python run.py
```

Open http://127.0.0.1:5050. Use `PORT=5051 .venv/bin/python run.py` if 5050 is busy.

## Checks

```sh
.venv/bin/python check.py
```

Runs Black, Pylint, the unit and integration tests, and real Chromium browser tests. CI runs the same command on every push and PR.

| File | What it covers |
| --- | --- |
| `tests/test_rules.py` | All 9 classic and 25 Lizard Spock matchups, written out literally; explanations |
| `tests/test_ai.py` | ORACLE's predictions, each boss strategy, HP, boss advancement, game over, champion |
| `tests/test_api.py` | Real Flask requests: new game, rounds, session state, HTTP 400 for bad modes and moves |
| `tests/e2e/test_game.py` | Real browser: beat the first boss, Lizard Spock with keyboard, game over and retry |

Tests fix only the boss's move when they need a predictable result; the real rules, HTTP, and session always run.

## Code map

`rules.py` rulesets · `brain.py` ORACLE's predictions · `bosses.py` boss strategies · `battle.py` game state (pure, no Flask) · `app.py` page + JSON API · `static/app.js` screens, animation, sound, keyboard · `static/style.css` look.
