"""Pure game-state logic for a boss run (Ladder or Endless). No Flask.

State is a JSON-friendly dict so the web layer can keep it in the session.
Times are passed in as plain numbers (seconds) and randomness as an ``rng``
so tests control both.
"""

import math

import bosses
import rules

PLAYER_HP = 5
HISTORY_LIMIT = 60
HEARTS_PER_BOSS = 2  # hearts restored after each boss (no longer a full heal)

# Shot clock: after LIMIT seconds the boss heals 1 HP, then 1 more every REGEN.
CLOCK_LIMIT = 5.0
CLOCK_REGEN = 3.0
CLOCK_GRACE = 1.5  # time for the reveal animation before the clock starts

# Score (Endless high scores): every boss beaten and every round won counts.
POINTS_PER_BOSS = 100
POINTS_PER_WIN = 10

POWERUPS = {
    "shield": {
        "emoji": "🛡️",
        "name": "Shield",
        "desc": "Blocks the next round you lose.",
    },
    "double": {
        "emoji": "⚔️",
        "name": "Double Strike",
        "desc": "Your next win deals 2 damage.",
    },
    "peek": {
        "emoji": "👁️",
        "name": "Peek",
        "desc": "Once, see the boss's move before you pick.",
    },
    "heal": {"emoji": "❤️‍🩹", "name": "Full Heal", "desc": "Restore every heart now."},
    "vitality": {
        "emoji": "💖",
        "name": "+1 Max Heart",
        "desc": "One more heart, permanently, and heal 1.",
    },
}
OFFER_SIZE = 3


def new_game(
    mode: str, shot_clock: bool = False, now: float = 0.0, endless: bool = False
) -> dict:
    """Start a run against the first boss."""
    rules.moves_for(mode)  # validates the mode
    return {
        "mode": mode,
        "endless": bool(endless),
        "boss": 0,
        "boss_hp": bosses.boss_for(0)["hp"],
        "player_hp": PLAYER_HP,
        "player_max": PLAYER_HP,
        "status": "playing",
        "history": [],
        "stats": {
            "rounds": 0,
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "streak": 0,
            "bosses": 0,
        },
        "items": {"shield": 0, "double": 0, "peek": 0},
        "offer": [],
        "peeked": None,
        "submitted": False,
        "clock": {"on": bool(shot_clock), "start": now + CLOCK_GRACE, "healed": 0},
    }


def upgrade(state: dict, now: float = 0.0) -> dict:
    """Fill in keys added after a run was started (old session cookies)."""
    state.setdefault("endless", False)
    state.setdefault("player_max", PLAYER_HP)
    state.setdefault("items", {"shield": 0, "double": 0, "peek": 0})
    state.setdefault("offer", [])
    state.setdefault("peeked", None)
    state.setdefault("submitted", False)
    state["stats"].setdefault("bosses", 0)
    state.setdefault("clock", {"on": False, "start": now, "healed": 0})
    return state


def current_boss(state: dict) -> dict:
    """The boss being fought right now."""
    return bosses.boss_for(state["boss"])


def boss_count(state: dict):
    """Bosses in this run: 5 for the Ladder, None (unlimited) for Endless."""
    return None if state["endless"] else len(bosses.BOSSES)


def score(state: dict) -> int:
    """Points for this run (shown in both modes, recorded for Endless)."""
    stats = state["stats"]
    return stats["bosses"] * POINTS_PER_BOSS + stats["wins"] * POINTS_PER_WIN


def boss_history(state: dict) -> list:
    """Rounds played against the current boss only."""
    return [r for r in state["history"] if r["boss"] == state["boss"]]


def current_phase(state: dict) -> int:
    """1 or 2 for the current boss."""
    return bosses.phase(state["boss_hp"], current_boss(state)["hp"])


# ---------------------------------------------------------------- shot clock


def restart_clock(state: dict, now: float, grace: float = 0.0) -> None:
    """Start a fresh turn timer (e.g. after a dialog closes)."""
    state["clock"]["start"] = now + grace
    state["clock"]["healed"] = 0


def clock_view(state: dict, now: float) -> dict:
    """Seconds left before the boss starts healing (negative once overdue)."""
    clock = state["clock"]
    return {
        "on": clock["on"],
        "limit": CLOCK_LIMIT,
        "regen": CLOCK_REGEN,
        "left": round(CLOCK_LIMIT - (now - clock["start"]), 2),
        "healed": clock["healed"],
    }


def apply_delay(state: dict, now: float) -> int:
    """Heal the boss for delay of game; return HP healed by this call."""
    clock = state["clock"]
    if not clock["on"] or state["status"] != "playing" or state["offer"]:
        return 0
    overdue = now - clock["start"] - CLOCK_LIMIT
    if overdue < 0:
        return 0
    owed = math.floor(overdue / CLOCK_REGEN) + 1
    max_hp = current_boss(state)["hp"]
    gained = max(0, min(owed - clock["healed"], max_hp - state["boss_hp"]))
    clock["healed"] = owed  # penalties past full health are simply lost
    state["boss_hp"] += gained
    return gained


# ------------------------------------------------------------------ power-ups


def choose_powerup(state: dict, choice: str, now: float = 0.0) -> str:
    """Take one of the offered power-ups. Returns a sentence describing it."""
    if choice not in state["offer"]:
        raise ValueError("Pick one of the offered power-ups.")
    state["offer"] = []
    if choice == "heal":
        state["player_hp"] = state["player_max"]
    elif choice == "vitality":
        state["player_max"] += 1
        state["player_hp"] = min(state["player_max"], state["player_hp"] + 1)
    else:
        state["items"][choice] += 1
    restart_clock(state, now)
    return f"{POWERUPS[choice]['emoji']} {POWERUPS[choice]['name']}"


def _seen(state):
    # ORACLE has watched the whole run; other bosses only see their own fight.
    boss = current_boss(state)
    return state["history"] if boss["id"] == "oracle" else boss_history(state)


def use_peek(state: dict, rng) -> str:
    """Spend a Peek: lock in the boss's next move now and reveal it."""
    if state["status"] != "playing" or state["offer"]:
        raise ValueError("You can't peek right now.")
    if state["peeked"]:
        return state["peeked"][0]
    if state["items"]["peek"] < 1:
        raise ValueError("You don't have a Peek.")
    state["items"]["peek"] -= 1
    boss = current_boss(state)
    move, thought = bosses.choose(
        boss["id"], state["mode"], _seen(state), rng, current_phase(state)
    )
    state["peeked"] = [move, thought]
    return move


# ---------------------------------------------------------------------- round


def _check_can_play(state, move):
    if state["status"] != "playing":
        raise ValueError("This run is over. Start a new game.")
    if state["offer"]:
        raise ValueError("Choose a power-up first.")
    if move not in rules.moves_for(state["mode"]):
        raise ValueError(f"Choose one of: {', '.join(rules.moves_for(state['mode']))}.")


def _apply_outcome(state, outcome):
    """Update HP and stats; return {damage, shielded, doubled}."""
    stats = state["stats"]
    stats["rounds"] += 1
    damage, shielded, doubled = 0, False, False
    if outcome == "win":
        doubled = state["items"]["double"] > 0
        if doubled:
            state["items"]["double"] -= 1
        damage = 2 if doubled else 1
        state["boss_hp"] -= damage
        stats["wins"] += 1
        stats["streak"] += 1
    elif outcome == "lose":
        shielded = state["items"]["shield"] > 0
        if shielded:
            state["items"]["shield"] -= 1
        else:
            state["player_hp"] -= 1
        stats["losses"] += 1
        stats["streak"] = 0
    else:
        stats["ties"] += 1
    return {"damage": damage, "shielded": shielded, "doubled": doubled}


def _after_boss_defeat(state, rng):
    state["stats"]["bosses"] += 1
    count = boss_count(state)
    if count is not None and state["boss"] + 1 >= count:
        state["status"] = "champion"
        return
    state["boss"] += 1
    state["boss_hp"] = current_boss(state)["hp"]
    state["player_hp"] = min(state["player_max"], state["player_hp"] + HEARTS_PER_BOSS)
    state["offer"] = rng.sample(sorted(POWERUPS), OFFER_SIZE)


def play_round(state: dict, move: str, rng, now: float = 0.0) -> dict:
    """Play one round, mutate ``state``, and return a description of the round.

    Raises ValueError for an illegal move, a pending power-up choice, or a
    run that is already over.
    """
    _check_can_play(state, move)
    mode = state["mode"]
    healed = apply_delay(state, now)
    boss = current_boss(state)
    phase_before = current_phase(state)
    if state["peeked"]:
        computer, thought = state["peeked"]
        state["peeked"] = None
    else:
        computer, thought = bosses.choose(
            boss["id"], mode, _seen(state), rng, phase_before
        )
    outcome = rules.determine_winner(mode, move, computer)
    hit = _apply_outcome(state, outcome)

    state["history"].append(
        {
            "player": move,
            "computer": computer,
            "outcome": outcome,
            "boss": state["boss"],
        }
    )
    del state["history"][:-HISTORY_LIMIT]

    defeated = None
    phase_change = False
    if state["boss_hp"] <= 0:
        defeated = boss["id"]
        _after_boss_defeat(state, rng)
    elif state["player_hp"] <= 0:
        state["status"] = "lost"
    else:
        phase_change = current_phase(state) == 2 and phase_before == 1

    restart_clock(state, now, CLOCK_GRACE)
    return {
        "player": move,
        "computer": computer,
        "outcome": outcome,
        "explanation": rules.explain(mode, move, computer),
        "thought": thought,
        "phase": phase_before,
        "phase_change": phase_change,
        "phase_line": boss["phase2"] if phase_change else None,
        "healed": healed,
        **hit,
        "defeated": defeated,
    }
