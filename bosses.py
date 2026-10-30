"""The boss ladder: five opponents, each with one readable strategy.

A strategy takes (mode, history, rng) and returns (move, thought). ``thought``
is revealed after the round so the player can learn how each boss works.
"""

import brain
import rules


def _rocky(mode, _history, rng):
    if rng.random() < 0.7:
        return "rock", "ROCK. Always rock. Rock is life."
    return (
        rng.choice(rules.moves_for(mode)),
        "Okay, a little variety. Don't tell anyone.",
    )


def _mirror(mode, history, rng):
    if not history:
        return rng.choice(rules.moves_for(mode)), "Nothing to copy yet… improvising."
    move = history[-1]["player"]
    return move, f"You played {move} last time, so I did too."


def _cycler(mode, history, _rng):
    moves = rules.moves_for(mode)
    move = moves[len(history) % len(moves)]
    return move, f"Executing sequence step {len(history) % len(moves) + 1}: {move}."


def _contrarian(mode, history, rng):
    if not history:
        return rng.choice(rules.moves_for(mode)), "First round. Watching closely."
    last = history[-1]["player"]
    move = rng.choice(rules.counters(mode, last))
    return move, f"You just played {last}. I picked {move} to beat a repeat."


def _oracle(mode, history, rng):
    read = brain.predict(mode, history)
    if read["counter"] is None:
        return rng.choice(rules.moves_for(mode)), read["insight"]
    pct = round(read["confidence"] * 100)
    return read["counter"], (
        f"I predicted {read['prediction']} ({pct}% sure). {read['insight']}."
    )


STRATEGIES = {
    "rocky": _rocky,
    "mirror": _mirror,
    "cycler": _cycler,
    "contrarian": _contrarian,
    "oracle": _oracle,
}

BOSSES = (
    {
        "id": "rocky",
        "name": "Rocky Boulderson",
        "emoji": "🪨",
        "title": "The Stone Cold Opener",
        "hp": 3,
        "intro": "I have one move and I'm proud of it.",
        "hint": "Has a… favorite.",
    },
    {
        "id": "mirror",
        "name": "Mirror Max",
        "emoji": "🪞",
        "title": "The Copycat",
        "hp": 3,
        "intro": "Whatever you do, I do. Eventually.",
        "hint": "Remembers your last move a little too well.",
    },
    {
        "id": "cycler",
        "name": "CYCLE-BOT 9000",
        "emoji": "🤖",
        "title": "The Loop",
        "hp": 4,
        "intro": "BEEP. SEQUENCE INITIALIZED. BOOP.",
        "hint": "Runs a fixed program.",
    },
    {
        "id": "contrarian",
        "name": "The Contrarian",
        "emoji": "😈",
        "title": "Professional Disagreer",
        "hp": 4,
        "intro": "Do it again. I dare you.",
        "hint": "Expects you to repeat yourself.",
    },
    {
        "id": "oracle",
        "name": "ORACLE",
        "emoji": "🔮",
        "title": "Final Boss · Reads Your Patterns",
        "hp": 5,
        "intro": "I have already seen how this ends.",
        "hint": "Learns from every move you make. Be unpredictable.",
    },
)


def choose(boss_id, mode, history, rng):
    """Return (move, thought) for the given boss."""
    return STRATEGIES[boss_id](mode, history, rng)
