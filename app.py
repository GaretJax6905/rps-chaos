"""Flask web layer: one page plus a small JSON API.

Boss-ladder runs live in the signed session cookie. Online rooms live in
memory (see rooms.py), so run a single server process.
"""

import os
import random
import time
import uuid

from flask import (
    Flask,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

import accounts
import battle
import bosses
import brain
import rooms
import rules

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)
app.config["DATABASE"] = os.environ.get("DATABASE_PATH", "rps_chaos.db")

RNG = random.Random()
clock = time.time  # tests replace this to control the shot clock


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _load():
    """The session's run, upgraded if it was started by an older version."""
    state = session.get("game")
    return battle.upgrade(state, clock()) if state is not None else None


def _save(state):
    session["game"] = state
    session.modified = True


def _view(state, healed=0):
    """Shape the session state for the browser."""
    boss = battle.current_boss(state)
    read = brain.predict(state["mode"], state["history"])
    if boss["id"] == "oracle" and state["status"] == "playing":
        read = {**read, "prediction": None, "counter": None, "locked": True}
    return {
        "mode": state["mode"],
        "endless": state["endless"],
        "moves": list(rules.moves_for(state["mode"])),
        "boss": {**boss, "index": state["boss"], "count": battle.boss_count(state)},
        "boss_hp": state["boss_hp"],
        "phase": battle.current_phase(state),
        "player_hp": state["player_hp"],
        "player_max": state["player_max"],
        "status": state["status"],
        "stats": state["stats"],
        "score": battle.score(state),
        "items": state["items"],
        "peeked": state["peeked"][0] if state["peeked"] else None,
        "offer": [{"id": key, **battle.POWERUPS[key]} for key in state["offer"]],
        "brain": read,
        "clock": battle.clock_view(state, clock()),
        "healed": healed,
    }


def _db():
    """One database connection per request."""
    if "db" not in g:
        g.db = accounts.connect(app.config["DATABASE"])
    return g.db


@app.teardown_appcontext
def _close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _user():
    """The signed-in user row, or None."""
    user_id = session.get("user_id")
    return accounts.get_user(_db(), user_id) if user_id else None


def _record_if_finished(state):
    """Save a finished Boss Ladder run for the signed-in player, once."""
    if state["endless"] or state["status"] not in ("champion", "lost"):
        return None
    user_id = session.get("user_id")
    if not user_id or "run_id" not in state:
        return None
    return accounts.save_run(_db(), user_id, state, battle.score(state))


def _error(message, status=400):
    return jsonify({"error": message}), status


@app.errorhandler(rooms.RoomError)
def _room_error(problem):
    return _error(str(problem), problem.status)


# ---------- pages ----------


@app.get("/")
@app.get("/r/<code>")
def index(code=None):
    """Serve the single-page game (optionally opening an online room)."""
    config = {
        "rulesets": {
            key: {
                "name": value["name"],
                "moves": list(value["moves"]),
                "beats": value["beats"],
            }
            for key, value in rules.RULESETS.items()
        },
        "symbols": rules.SYMBOLS,
        "bosses": [
            {key: b[key] for key in ("name", "emoji", "title", "hp")}
            for b in bosses.BOSSES
        ],
        "targets": list(rooms.TARGETS),
        "room": code.upper() if code else None,
    }
    return render_template("index.html", config=config)


@app.get("/manifest.webmanifest")
def manifest():
    """Web app manifest so phones can install the game."""
    return send_from_directory(
        app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json"
    )


@app.get("/sw.js")
def service_worker():
    """Service worker served from the root so it controls every page."""
    response = send_from_directory(app.static_folder, "sw.js")
    response.headers["Cache-Control"] = "no-cache"
    return response


# ---------- boss ladder ----------


@app.post("/api/new")
def new_game():
    """Start a new run in the chosen ruleset."""
    body = _body()
    mode = body.get("mode")
    if mode not in rules.RULESETS:
        return _error("Choose a game mode: classic or spock.")
    session["game"] = battle.new_game(
        mode, bool(body.get("shot_clock")), clock(), bool(body.get("endless"))
    )
    session["game"]["run_id"] = uuid.uuid4().hex
    return jsonify({"state": _view(session["game"])})


@app.get("/api/state")
def current_state():
    """Return the current run (applying any shot-clock healing), or null."""
    state = _load()
    if not state:
        return jsonify({"state": None})
    healed = battle.apply_delay(state, clock())
    if healed:
        _save(state)
    return jsonify({"state": _view(state, healed)})


@app.post("/api/clock/restart")
def restart_clock():
    """Start a fresh shot clock, e.g. after a dialog was closed."""
    state = _load()
    if not state:
        return _error("Start a game first.")
    battle.restart_clock(state, clock())
    _save(state)
    return jsonify({"state": _view(state)})


@app.post("/api/play")
def play():
    """Play one round with the submitted move."""
    state = _load()
    if not state:
        return _error("Start a game first.")
    try:
        result = battle.play_round(state, _body().get("move"), RNG, clock())
    except ValueError as problem:
        return _error(str(problem))
    _save(state)
    saved = _record_if_finished(state)
    return jsonify({"round": result, "state": _view(state), "saved": saved})


@app.post("/api/powerup")
def powerup():
    """Take one of the power-ups offered after a boss falls."""
    state = _load()
    if not state:
        return _error("Start a game first.")
    try:
        picked = battle.choose_powerup(state, _body().get("id"), clock())
    except ValueError as problem:
        return _error(str(problem))
    _save(state)
    return jsonify({"picked": picked, "state": _view(state)})


@app.post("/api/peek")
def peek():
    """Spend a Peek to see the boss's next move."""
    state = _load()
    if not state:
        return _error("Start a game first.")
    try:
        move = battle.use_peek(state, RNG)
    except ValueError as problem:
        return _error(str(problem))
    _save(state)
    return jsonify({"move": move, "state": _view(state)})


# ---------- accounts and saved runs ----------


@app.route("/register", methods=["GET", "POST"])
def register():
    """Create an account, then sign in."""
    error = None
    if request.method == "POST":
        try:
            user_id = accounts.register(
                _db(),
                request.form.get("email", ""),
                request.form.get("password", ""),
                request.form.get("display_name", ""),
            )
        except accounts.AccountError as problem:
            error = str(problem)
        else:
            session.clear()
            session["user_id"] = user_id
            return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register", error=error), (
        400 if error else 200
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    """Sign in with email and password."""
    error = None
    if request.method == "POST":
        user = accounts.authenticate(
            _db(), request.form.get("email", ""), request.form.get("password", "")
        )
        if user:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        error = "Wrong email or password."
    return render_template("auth.html", mode="login", error=error), (
        401 if error else 200
    )


@app.post("/logout")
def logout():
    """Sign out and forget the current run."""
    session.clear()
    return redirect(url_for("login"))


@app.get("/dashboard")
def dashboard():
    """Private dashboard: this player's saved runs."""
    user = _user()
    if not user:
        return redirect(url_for("login"))
    return render_template(
        "dashboard.html",
        user=user,
        summary=accounts.summary(_db(), user["id"]),
        runs=accounts.runs_for(_db(), user["id"]),
    )


@app.get("/api/results")
def results():
    """JSON of this player's saved runs; 401 when signed out."""
    user = _user()
    if not user:
        return _error("Sign in to see your results.", 401)
    return jsonify(
        {
            "summary": accounts.summary(_db(), user["id"]),
            "runs": accounts.runs_for(_db(), user["id"]),
        }
    )


@app.get("/api/me")
def me():
    """Who is signed in (for the game page's account link)."""
    user = _user()
    return jsonify({"user": {"name": user["display_name"]} if user else None})


# ---------- online rooms ----------


def _token():
    return request.headers.get("X-Player-Token", "")


@app.post("/api/rooms")
def create_room():
    """Open an online room. The creator is player 1."""
    body = _body()
    mode = body.get("mode")
    if mode not in rules.RULESETS:
        return _error("Choose a game mode: classic or spock.")
    target = body.get("target", 3)
    code, token = rooms.create(mode, target, body.get("name"), time.time())
    return jsonify({"token": token, "room": rooms.state(code, token, time.time())})


@app.post("/api/rooms/<code>/join")
def join_room(code):
    """Take the second seat in a room."""
    token = rooms.join(code, _body().get("name"), time.time())
    return jsonify({"token": token, "room": rooms.state(code, token, time.time())})


@app.get("/api/rooms/<code>")
def room_state(code):
    """Poll a room as the player identified by the X-Player-Token header."""
    return jsonify({"room": rooms.state(code, _token(), time.time())})


@app.post("/api/rooms/<code>/move")
def room_move(code):
    """Lock in this player's move for the current round."""
    room = rooms.submit(code, _token(), _body().get("move"), time.time())
    return jsonify({"room": room})


@app.post("/api/rooms/<code>/rematch")
def room_rematch(code):
    """Vote for a rematch after the match ends."""
    return jsonify({"room": rooms.rematch(code, _token(), time.time())})
