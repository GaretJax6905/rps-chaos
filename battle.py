"""Pure game-state logic for a boss-ladder run. No Flask, no randomness of its own.

State is a JSON-friendly dict so the web layer can keep it in the session.
"""

import bosses
import rules

PLAYER_HP = 5
HISTORY_LIMIT = 60


def new_game(mode: str) -> dict:
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
    }


def boss_history(state: dict) -> list:
    """Rounds played against the current boss only."""
    return [r for r in state["history"] if r["boss"] == state["boss"]]


def play_round(state: dict, move: str, rng) -> dict:
    """Play one round, mutate ``state``, and return a description of the round.

    Raises ValueError for an illegal move or a run that is already over.
    """
    if state["status"] != "playing":
        raise ValueError("This run is over. Start a new game.")
    mode = state["mode"]
    if move not in rules.moves_for(mode):
        raise ValueError(f"Choose one of: {', '.join(rules.moves_for(mode))}.")

    boss = bosses.BOSSES[state["boss"]]
    # ORACLE has been watching the whole run; other bosses only see their fight.
    seen = state["history"] if boss["id"] == "oracle" else boss_history(state)
    computer, thought = bosses.choose(boss["id"], mode, seen, rng)
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

    return {
        "player": move,
        "computer": computer,
        "outcome": outcome,
        "explanation": rules.explain(mode, move, computer),
        "thought": thought,
        "defeated": defeated,
    }
