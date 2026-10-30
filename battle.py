"""Pure game-state logic for a boss-ladder run. No Flask, no randomness of its own.

State is a JSON-friendly dict so the web layer can keep it in the session.
Times are passed in as plain numbers (seconds) so tests control the clock.
"""

import math

import bosses
import rules

PLAYER_HP = 5
HISTORY_LIMIT = 60

# Shot clock: after LIMIT seconds the boss heals 1 HP, then 1 more every REGEN.
CLOCK_LIMIT = 5.0
CLOCK_REGEN = 3.0
CLOCK_GRACE = 1.5  # time for the reveal animation before the clock starts


def new_game(mode: str, shot_clock: bool = False, now: float = 0.0) -> dict:
    """Start a run against the first boss."""
    rules.moves_for(mode)  # validates the mode
    return {
        "mode": mode,
        "boss": 0,
        "boss_hp": bosses.BOSSES[0]["hp"],
        "player_hp": PLAYER_HP,
        "status": "playing",
        "history": [],
        "stats": {"rounds": 0, "wins": 0, "losses": 0, "ties": 0, "streak": 0},
        "clock": {"on": bool(shot_clock), "start": now + CLOCK_GRACE, "healed": 0},
    }


def boss_history(state: dict) -> list:
    """Rounds played against the current boss only."""
    return [r for r in state["history"] if r["boss"] == state["boss"]]


def current_phase(state: dict) -> int:
    """1 or 2 for the current boss."""
    return bosses.phase(state["boss_hp"], bosses.BOSSES[state["boss"]]["hp"])


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
    if not clock["on"] or state["status"] != "playing":
        return 0
    overdue = now - clock["start"] - CLOCK_LIMIT
    if overdue < 0:
        return 0
    owed = math.floor(overdue / CLOCK_REGEN) + 1
    max_hp = bosses.BOSSES[state["boss"]]["hp"]
    gained = max(0, min(owed - clock["healed"], max_hp - state["boss_hp"]))
    clock["healed"] = owed  # penalties past full health are simply lost
    state["boss_hp"] += gained
    return gained


def play_round(state: dict, move: str, rng, now: float = 0.0) -> dict:
    """Play one round, mutate ``state``, and return a description of the round.

    Raises ValueError for an illegal move or a run that is already over.
    """
    if state["status"] != "playing":
        raise ValueError("This run is over. Start a new game.")
    mode = state["mode"]
    if move not in rules.moves_for(mode):
        raise ValueError(f"Choose one of: {', '.join(rules.moves_for(mode))}.")

    healed = apply_delay(state, now)
    boss = bosses.BOSSES[state["boss"]]
    phase_before = current_phase(state)
    # ORACLE has been watching the whole run; other bosses only see their fight.
    seen = state["history"] if boss["id"] == "oracle" else boss_history(state)
    computer, thought = bosses.choose(boss["id"], mode, seen, rng, phase_before)
    outcome = rules.determine_winner(mode, move, computer)

    stats = state["stats"]
    stats["rounds"] += 1
    if outcome == "win":
        state["boss_hp"] -= 1
        stats["wins"] += 1
        stats["streak"] += 1
    elif outcome == "lose":
        state["player_hp"] -= 1
        stats["losses"] += 1
        stats["streak"] = 0
    else:
        stats["ties"] += 1

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
        if state["boss"] + 1 < len(bosses.BOSSES):
            state["boss"] += 1
            state["boss_hp"] = bosses.BOSSES[state["boss"]]["hp"]
            state["player_hp"] = PLAYER_HP
        else:
            state["status"] = "champion"
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
        "defeated": defeated,
    }
