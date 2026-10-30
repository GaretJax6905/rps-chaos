"""Flask web layer: one page plus a tiny JSON API backed by the session."""

import os
import random

from flask import Flask, jsonify, render_template, request, session

import battle
import bosses
import brain
import rules

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)

RNG = random.Random()


def _view(state):
    """Shape the session state for the browser."""
    boss = bosses.BOSSES[state["boss"]]
    read = brain.predict(state["mode"], state["history"])
    if boss["id"] == "oracle" and state["status"] == "playing":
        read = {**read, "prediction": None, "counter": None, "locked": True}
    return {
        "mode": state["mode"],
        "moves": list(rules.moves_for(state["mode"])),
        "boss": {**boss, "index": state["boss"], "count": len(bosses.BOSSES)},
        "boss_hp": state["boss_hp"],
        "player_hp": state["player_hp"],
        "player_max": battle.PLAYER_HP,
        "status": state["status"],
        "stats": state["stats"],
        "brain": read,
    }


def _error(message, status=400):
    return jsonify({"error": message}), status


@app.get("/")
def index():
    """Serve the single-page game."""
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
    }
    return render_template("index.html", config=config)


@app.post("/api/new")
def new_game():
    """Start a new run in the chosen ruleset."""
    mode = (request.get_json(silent=True) or {}).get("mode")
    if mode not in rules.RULESETS:
        return _error("Choose a game mode: classic or spock.")
    session["game"] = battle.new_game(mode)
    return jsonify({"state": _view(session["game"])})


@app.get("/api/state")
def current_state():
    """Return the current run, or null if none has started."""
    state = session.get("game")
    return jsonify({"state": _view(state) if state else None})


@app.post("/api/play")
def play():
    """Play one round with the submitted move."""
    state = session.get("game")
    if not state:
        return _error("Start a game first.")
    move = (request.get_json(silent=True) or {}).get("move")
    try:
        result = battle.play_round(state, move, RNG)
    except ValueError as problem:
        return _error(str(problem))
    session["game"] = state
    session.modified = True
    return jsonify({"round": result, "state": _view(state)})
