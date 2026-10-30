"""Data-driven rules for Rock Paper Scissors and Rock Paper Scissors Lizard Spock.

Each ruleset maps a move to the moves it beats and the verb that explains why.
Adding a move means adding table entries, not new if/else branches.
"""

CLASSIC = "classic"
SPOCK = "spock"

RULESETS = {
    CLASSIC: {
        "name": "Rock Paper Scissors",
        "moves": ("rock", "paper", "scissors"),
        "beats": {
            "rock": {"scissors": "crushes"},
            "paper": {"rock": "covers"},
            "scissors": {"paper": "cuts"},
        },
    },
    SPOCK: {
        "name": "Rock Paper Scissors Lizard Spock",
        "moves": ("rock", "paper", "scissors", "lizard", "spock"),
        "beats": {
            "rock": {"scissors": "crushes", "lizard": "crushes"},
            "paper": {"rock": "covers", "spock": "disproves"},
            "scissors": {"paper": "cuts", "lizard": "decapitates"},
            "lizard": {"spock": "poisons", "paper": "eats"},
            "spock": {"scissors": "smashes", "rock": "vaporizes"},
        },
    },
}

SYMBOLS = {
    "rock": "✊",
    "paper": "✋",
    "scissors": "✌️",
    "lizard": "🦎",
    "spock": "🖖",
}


def moves_for(mode: str) -> tuple:
    """Return the legal moves for a ruleset, raising ValueError if unknown."""
    if mode not in RULESETS:
        raise ValueError(f"Unknown mode: {mode!r}")
    return RULESETS[mode]["moves"]


def determine_winner(mode: str, player: str, computer: str) -> str:
    """Return 'win', 'lose', or 'tie' from the player's perspective."""
    legal = moves_for(mode)
    if player not in legal or computer not in legal:
        raise ValueError(f"Illegal move for {mode}: {player!r} vs {computer!r}")
    if player == computer:
        return "tie"
    if computer in RULESETS[mode]["beats"][player]:
        return "win"
    return "lose"


def explain(mode: str, player: str, computer: str) -> str:
    """Return a sentence such as 'Paper covers rock' or 'Same move' for a tie."""
    outcome = determine_winner(mode, player, computer)
    if outcome == "tie":
        return f"Both chose {player} — it's a stalemate"
    winner, loser = (player, computer) if outcome == "win" else (computer, player)
    verb = RULESETS[mode]["beats"][winner][loser]
    return f"{winner.capitalize()} {verb} {loser}"


def counters(mode: str, move: str) -> tuple:
    """Return every move that beats ``move`` in this ruleset, in move order."""
    beats = RULESETS[mode]["beats"]
    return tuple(m for m in moves_for(mode) if move in beats[m])
