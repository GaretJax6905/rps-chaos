"""The boss ladder: five opponents, each with a readable strategy per phase.

A strategy takes (mode, history, rng) and returns (move, thought). ``thought``
is revealed after the round so the player can learn how each boss works.
At half health or less, every boss switches to its phase 2 strategy.
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


def _rocky2(mode, _history, rng):
    if rng.random() < 0.7:
        return "paper", "Rock has failed me. I am PAPER now."
    return rng.choice(rules.moves_for(mode)), "Old habits… maybe."


def _mirror(mode, history, rng):
    if not history:
        return rng.choice(rules.moves_for(mode)), "Nothing to copy yet… improvising."
    move = history[-1]["player"]
    return move, f"You played {move} last time, so I did too."


def _mirror2(mode, history, rng):
    if len(history) < 2:
        return _mirror(mode, history, rng)
    move = history[-2]["player"]
    return move, f"Delayed reflection: I copied your move from two rounds ago ({move})."


def _cycler(mode, history, _rng):
    moves = rules.moves_for(mode)
    move = moves[len(history) % len(moves)]
    return move, f"Executing sequence step {len(history) % len(moves) + 1}: {move}."


def _cycler2(mode, history, _rng):
    moves = rules.moves_for(mode)[::-1]
    move = moves[len(history) % len(moves)]
    return (
        move,
        f"REVERSE PROTOCOL ENGAGED. Step {len(history) % len(moves) + 1}: {move}.",
    )


def _contrarian(mode, history, rng):
    if not history:
        return rng.choice(rules.moves_for(mode)), "First round. Watching closely."
    last = history[-1]["player"]
    move = rng.choice(rules.counters(mode, last))
    return move, f"You just played {last}. I picked {move} to beat a repeat."


def _contrarian2(mode, history, rng):
    if not history:
        return _contrarian(mode, history, rng)
    last = history[-1]["player"]
    # Expect the player to switch to whatever beats the obvious counter.
    expected = rng.choice(rules.counters(mode, rng.choice(rules.counters(mode, last))))
    move = rng.choice(rules.counters(mode, expected))
    return move, f"Double bluff: I figured you'd switch to {expected}, so {move}."


def _oracle(mode, history, rng):
    read = brain.predict(mode, history)
    if read["counter"] is None:
        return rng.choice(rules.moves_for(mode)), read["insight"]
    pct = round(read["confidence"] * 100)
    return read["counter"], (
        f"I predicted {read['prediction']} ({pct}% sure). {read['insight']}."
    )


def _oracle2(mode, history, rng):
    return brain.meta_choose(mode, history, rng)


STRATEGIES = {
    ("rocky", 1): _rocky,
    ("rocky", 2): _rocky2,
    ("mirror", 1): _mirror,
    ("mirror", 2): _mirror2,
    ("cycler", 1): _cycler,
    ("cycler", 2): _cycler2,
    ("contrarian", 1): _contrarian,
    ("contrarian", 2): _contrarian2,
    ("oracle", 1): _oracle,
    ("oracle", 2): _oracle2,
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
        "phase2": "Enough! If you can't beat them, join them. PAPER MODE!",
    },
    {
        "id": "mirror",
        "name": "Mirror Max",
        "emoji": "🪞",
        "title": "The Copycat",
        "hp": 3,
        "intro": "Whatever you do, I do. Eventually.",
        "hint": "Remembers your last move a little too well.",
        "phase2": "My reflection is… lagging. Two rounds behind, to be exact.",
    },
    {
        "id": "cycler",
        "name": "CYCLE-BOT 9000",
        "emoji": "🤖",
        "title": "The Loop",
        "hp": 4,
        "intro": "BEEP. SEQUENCE INITIALIZED. BOOP.",
        "hint": "Runs a fixed program.",
        "phase2": "ERROR. ERROR. REVERSING ALL SEQUENCES. ETADPU MARGORP.",
    },
    {
        "id": "contrarian",
        "name": "The Contrarian",
        "emoji": "😈",
        "title": "Professional Disagreer",
        "hp": 4,
        "intro": "Do it again. I dare you.",
        "hint": "Expects you to repeat yourself.",
        "phase2": "You think you've figured me out? Now I'm out-thinking you.",
    },
    {
        "id": "oracle",
        "name": "ORACLE",
        "emoji": "🔮",
        "title": "Final Boss · Reads Your Patterns",
        "hp": 5,
        "intro": "I have already seen how this ends.",
        "hint": "Learns from every move you make. Be unpredictable.",
        "phase2": "FULL POWER. I now know when you try to out-think me.",
    },
)


def phase(boss_hp, max_hp):
    """Phase 2 begins once the boss is at half health or less."""
    return 2 if boss_hp * 2 <= max_hp else 1


def choose(boss_id, mode, history, rng, boss_phase=1):
    """Return (move, thought) for the given boss and phase."""
    return STRATEGIES[(boss_id, boss_phase)](mode, history, rng)


ROMAN = ("", "", " II", " III", " IV", " V", " VI", " VII", " VIII", " IX", " X")


def boss_for(index):
    """The boss at a ladder position. Past the fifth, Endless mode loops the
    roster in tougher tiers: +2 HP per tier and a Roman numeral on the name."""
    base = BOSSES[index % len(BOSSES)]
    tier = index // len(BOSSES) + 1
    if tier == 1:
        return {**base, "tier": 1}
    suffix = ROMAN[tier] if tier < len(ROMAN) else f" {tier}"
    return {
        **base,
        "name": base["name"] + suffix,
        "title": f"Tier {tier} · {base['title']}",
        "hp": base["hp"] + 2 * (tier - 1),
        "tier": tier,
    }
