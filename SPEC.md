# RPS Chaos — project record (IS218 Creative Extravaganza)

## Project and current status

- **Audience:** classmates and Demo Day visitors who want a quick, keyboard-friendly
  2–5 minute boss run, and a reason to come back and beat their best.
- **Dream:** a full boss gauntlet with talking bosses, unlockable challengers,
  online duels and a season leaderboard.
- **Promise (this term):** one complete journey: sign up → play a Boss Ladder run →
  the finished run is saved to my account → private dashboard → change my display
  name and password → sign out.
- **Experiment:** LLM-written boss taunts (see below), with the current hand-written
  lines as the fallback.
- **Stack:** Flask (already used here, and I can explain it) · Flask-Login for sessions
  · Werkzeug password hashing · Flask-SQLAlchemy + SQLite · Flask-WTF CSRF · pytest +
  Flask test client · pytest-playwright · GitHub Actions (existing `python.yml`).
- **Deferred:** saved results for Endless, Same Device and Online modes (they keep
  working, unscored); hosted database on Render; public leaderboard; password
  recovery; email.
- **Repository:** https://github.com/GaretJax6905/rps-chaos · demo:
  https://rps-chaos.onrender.com (current version, no accounts yet).
- **Stage:** Review 1 · Plan. Checks run: existing unit/integration suite, 115 passed
  locally on Nov 5, 2026 (e2e browser tests not run for this plan). No account,
  persistence or account-browser checks exist yet.

## Baseline (already built)

- Rules for RPS and RPS-Lizard-Spock (`rules.py`), five bosses with phase-2 strategies
  (`bosses.py`), ORACLE's pattern predictor (`brain.py`), power-ups and scoring
  (`battle.py`).
- The server already decides every round: a run lives in Flask's signed session
  cookie, and `/api/play` validates the move and computes the outcome.
- Endless high scores live in the browser's `localStorage`. The course brief says
  browser storage alone cannot count as saved scores, so this plan moves results to a
  server database tied to an account.

## 1 · Plan

### Evidence and assumptions

- Evidence: RPS Chaos is deployed and playable; classmates already know RPS rules.
- Assumption to check: players care more about "my best run and how far I got" than
  about lifetime win/loss totals. Ask two classmates on Nov 11.

### Two concepts

| | A · Boss Ladder with accounts (chosen) | B · Read My Mind |
|---|---|---|
| Idea | Save every finished ladder run to your account; the dashboard shows your best score, furthest boss and recent runs | A single opponent that learns your habits; the dashboard shows how predictable you are |
| Audience | Demo Day players who want quick replayable runs | Players curious about "AI" opponents |
| Decision | Chosen: the game core already works, so the term goes into the required account journey | ORACLE already covers this idea inside the ladder |

Presentation compared: (1) ladder map first, or (2) straight into the duel, with
ladder progress on the dashboard. Choosing (2): fastest path to play, and the
dashboard becomes meaningful. Tradeoff: less up-front spectacle.

### Unit of a saved result

**One finished Boss Ladder run** (won or lost): mode, bosses beaten, rounds won, final
score, outcome, finished time. Totals, dashboard and tests all use this unit.

### Five stories

| Story | Observable check |
|---|---|
| Join and return | Register, sign out, sign in. A duplicate email and a wrong password show clear errors. The database stores only a password hash. |
| Play and save | A signed-in player finishes a run and the server saves it once for that player. Re-sending the finishing request, or refreshing, does not add a second result. The client never sends its own score. |
| See my progress | The private dashboard shows best score, furthest boss, runs played and the last 10 runs. A new account sees a friendly empty state. Data survives a server restart. |
| Maintain my account | Change display name. Change password only by entering the current one. The old password then fails, and other signed-in sessions are signed out. |
| Leave safely | After logout, `/dashboard` and `/api/results` redirect or return 401. Account B cannot read or change account A's results by editing an ID. |

### Architecture sketch

```
Browser (templates/ + static/app.js)
  │  POST /api/new · POST /api/play · GET /dashboard · /account
  ▼
Flask routes (app.py) ──► auth: Flask-Login current_user, CSRF
  │
  ├─► game core (pure Python): rules.py · bosses.py · brain.py · battle.py   ◄ rules live here
  │
  └─► ResultStore (new) ──► SQLite via SQLAlchemy
        users(id, email UNIQUE, display_name, password_hash, session_version)
        runs(id UUID, user_id FK, mode, bosses_beaten, rounds_won, score,
             outcome, finished_at)
```

- The run id is created by the server at `/api/new`; saving uses it as the primary
  key, so a duplicate save is rejected by the database.
- Session revocation: `session_version` is stored in the login session. A password
  change increments it, and any session holding the old number is signed out.

### Pattern experiment

- Problem: routes will need to save and read runs. Where should that code live?
- A) SQL/ORM calls written directly inside the Flask routes (simpler).
- B) Repository: a small `ResultStore` with `save_run`, `runs_for` and `summary_for`,
  plus an in-memory fake for tests.
- Planned comparison: build the save and dashboard routes both ways. Compare how many
  tests need a real database, and what changes when "furthest boss" is added. Keep
  whichever is simpler to test and explain.
- Note: bosses already use function-based Strategy (`bosses.py`), so that pattern is
  part of the baseline, not this experiment.

### Creative experiment: LLM boss taunts

- Idea: each boss's post-round "thought" line is written by a model in that boss's
  voice, using only the move history.
- Stopping point: 2 work sessions. Drop it if replies take longer than 1.5 s, break
  character, or the API key cannot be kept out of the repo.
- Fallback: the current hand-written lines. Game outcomes never depend on the model.

### AI coding experiment

- Prediction: a coding agent will scaffold Flask-Login, the forms and the dashboard
  correctly. It will miss (1) duplicate-save protection and (2) signing out other
  sessions after a password change.
- Check: write those two tests from the stories above first, then run them against
  the agent's code. Record what passed, what failed and what I changed.

## 2 · First working slice

_Not started._

## 3 · Integrated build

_Not started._

## 4 · Improve and hand off

_Not started._
