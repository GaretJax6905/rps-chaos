"""Flask web layer: one page plus a small JSON API.

Boss-ladder runs live in the signed session cookie. Online rooms live in
memory (see rooms.py), so run a single server process.
"""

import os
import random
import time

from flask import Flask, jsonify, render_template, request, send_from_directory, session

import battle
import bosses
import brain
import rooms
import rules

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)

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
    return jsonify({"round": result, "state": _view(state)})


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
