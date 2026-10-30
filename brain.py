"""ORACLE's brain: predict the player's next move from their own history.

History is a list of rounds, oldest first: {"player", "computer", "outcome"}.
Several simple pattern detectors vote; stronger, more specific patterns get
more weight. Everything is plain counting, so every guess can be explained.
"""

from collections import Counter

import rules

MIN_ROUNDS = 3


def _following(history, matches):
    """Count the player's next move after every round where ``matches`` is true."""
    counts = Counter()
    for earlier, later in zip(history, history[1:]):
        if matches(earlier):
            counts[later["player"]] += 1
    return counts


def _pair_following(history, pair):
    """Count the next move after the player's last two moves equal ``pair``."""
    counts = Counter()
    for first, second, nxt in zip(history, history[1:], history[2:]):
        if (first["player"], second["player"]) == pair:
            counts[nxt["player"]] += 1
    return counts


def _detectors(history):
    """Yield (weight, counts, description) for each pattern detector."""
    last = history[-1]
    yield (
        1,
        Counter(r["player"] for r in history),
        "Your favorite move is {move}",
    )
    yield (
        2,
        _following(history, lambda r: r["player"] == last["player"]),
        f"After {last['player']} you usually play {{move}}",
    )
    outcome_word = {"win": "a win", "lose": "a loss", "tie": "a tie"}[last["outcome"]]
    yield (
        2,
        _following(history, lambda r: r["outcome"] == last["outcome"]),
        f"After {outcome_word} you tend to pick {{move}}",
    )
    if len(history) >= 2:
        pair = (history[-2]["player"], last["player"])
        yield (
            3,
            _pair_following(history, pair),
            f"After {pair[0]} then {pair[1]}, you go {{move}}",
        )


def _vote(history, moves):
    """Let every detector vote; return (scores per move, strongest pattern text)."""
    scores = Counter({move: 0.0 for move in moves})
    best_hint, best_strength = "", 0.0
    for weight, counts, description in _detectors(history):
        total = sum(counts.values())
        if not total:
            continue
        for move, count in counts.items():
            scores[move] += weight * count / total
        move, count = counts.most_common(1)[0]
        strength = weight * count / total * min(total, 4) / 4
        if strength > best_strength:
            best_strength = strength
            best_hint = f"{description.format(move=move.upper())} ({count}/{total})"
    return scores, best_hint


def predict(mode, history):
    """Return {prediction, confidence, insight, counter} for the next round.

    ``prediction`` and ``counter`` are None until enough rounds are seen.
    ``confidence`` is 0..1: the predicted move's share of the weighted votes.
    """
    moves = rules.moves_for(mode)
    if len(history) < MIN_ROUNDS:
        left = MIN_ROUNDS - len(history)
        return {
            "prediction": None,
            "confidence": 0.0,
            "insight": f"Studying you… {left} more round{'s' * (left != 1)}",
            "counter": None,
        }

    scores, best_hint = _vote(history, moves)
    prediction = max(moves, key=lambda m: (scores[m], -moves.index(m)))
    total_score = sum(scores.values())
    confidence = scores[prediction] / total_score if total_score else 0.0
    return {
        "prediction": prediction,
        "confidence": round(confidence, 2),
        "insight": best_hint or "No pattern yet — you're unpredictable",
        "counter": best_counter(mode, scores),
    }


def best_counter(mode, scores):
    """Pick the move with the best expected result against the vote scores."""
    moves = rules.moves_for(mode)
    value = {"win": 1, "tie": 0, "lose": -1}

    def expected(mine):
        return sum(
            scores[theirs] * value[rules.determine_winner(mode, mine, theirs)]
            for theirs in moves
        )

    return max(moves, key=lambda m: (expected(m), -moves.index(m)))


# ---------------------------------------------------------------------------
# Phase 2 ORACLE: meta-strategy ("thinking ahead") on top of simple predictors.
# ---------------------------------------------------------------------------

DECAY = 0.85
LEVEL_WORDS = (
    "countering it directly",
    "assuming you'd see that coming",
    "assuming you'd think one step further",
)


def _beat(mode, move):
    """The first move (in move order) that beats ``move``."""
    return rules.counters(mode, move)[0]


def _base_guesses(mode, history):
    """Each simple predictor's guess for the player's next move (or None)."""
    if not history:
        return {}
    last = history[-1]
    favorite = Counter(r["player"] for r in history).most_common(1)[0][0]
    return {
        "your patterns": predict(mode, history)["prediction"],
        "you repeating yourself": last["player"],
        "you countering my last move": _beat(mode, last["computer"]),
        "your favorite move": favorite,
    }


def _strategies(mode, history):
    """Map (predictor, level) -> ORACLE's move, for every usable predictor."""
    plays = {}
    for name, guess in _base_guesses(mode, history).items():
        if guess is None:
            continue
        move = _beat(mode, guess)
        for level in range(len(LEVEL_WORDS)):
            plays[(name, level)] = move
            # The player anticipates ``move`` and plays its counter;
            # the next level counters that instead.
            move = _beat(mode, _beat(mode, move))
    return plays


def meta_choose(mode, history, rng):
    """Return (move, thought): the strategy that would have scored best so far.

    Every (predictor, level) pair is replayed over the history with decaying
    scores (+1 would have won, -1 would have lost). If nothing is working,
    ORACLE falls back to a random move so it cannot be exploited.
    """
    scores = Counter()
    for t in range(MIN_ROUNDS, len(history)):
        actual = history[t]["player"]
        for key in scores:
            scores[key] *= DECAY
        for key, move in _strategies(mode, history[:t]).items():
            result = rules.determine_winner(mode, move, actual)
            scores[key] += {"win": 1, "lose": -1, "tie": 0}[result]

    plays = _strategies(mode, history)
    ranked = [key for key, _ in scores.most_common() if key in plays]
    if not ranked or scores[ranked[0]] <= 0:
        return rng.choice(rules.moves_for(mode)), (
            "None of my strategies are working on you… going on instinct."
        )
    name, level = ranked[0]
    return plays[(name, level)], (
        f"Full power. Predicting {name}, {LEVEL_WORDS[level]} "
        f"(strategy score {scores[(name, level)]:.1f})."
    )
