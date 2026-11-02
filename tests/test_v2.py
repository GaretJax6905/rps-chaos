"""Unit checks for v2: boss phase 2, full-power ORACLE, and the shot clock."""

# pytest injects fixtures by name.
# pylint: disable=missing-function-docstring,redefined-outer-name

import random

import pytest

import battle
import bosses
import brain
import rules

pytestmark = pytest.mark.unit


def rounds(*pairs):
    """Build history from (player, computer) pairs with real outcomes."""
    return [
        {
            "player": p,
            "computer": c,
            "outcome": rules.determine_winner("classic", p, c),
            "boss": 4,
        }
        for p, c in pairs
    ]


# ---------- phase 2 ----------


@pytest.mark.parametrize(
    ("hp", "max_hp", "expected"),
    [(3, 3, 1), (2, 3, 1), (1, 3, 2), (3, 4, 1), (2, 4, 2), (3, 5, 1), (2, 5, 2)],
)
def test_phase_two_starts_at_half_health(hp, max_hp, expected):
    assert bosses.phase(hp, max_hp) == expected


def test_every_boss_has_a_phase_two_line_and_strategy():
    for boss in bosses.BOSSES:
        assert boss["phase2"]
        assert (boss["id"], 2) in bosses.STRATEGIES


def test_rocky_switches_to_paper():
    rng = random.Random(7)
    picks = [bosses.choose("rocky", "classic", [], rng, 2)[0] for _ in range(200)]
    assert picks.count("paper") > 120


def test_mirror_two_copies_two_rounds_back():
    history = rounds(("rock", "rock"), ("paper", "rock"))
    move, _ = bosses.choose("mirror", "classic", history, random.Random(0), 2)
    assert move == "rock"


def test_cycler_reverses():
    moves = [
        bosses.choose("cycler", "classic", [{}] * n, random.Random(0), 2)[0]
        for n in range(3)
    ]
    assert moves == ["scissors", "paper", "rock"]


def test_phase_change_is_reported_once(monkeypatch):
    monkeypatch.setattr(bosses, "choose", lambda *_a: ("scissors", ""))
    state = battle.new_game("classic")
    state["boss"] = 2  # CYCLE-BOT, 4 HP
    state["boss_hp"] = 4
    first = battle.play_round(state, "rock", random.Random(0))
    second = battle.play_round(state, "rock", random.Random(0))
    third = battle.play_round(state, "rock", random.Random(0))
    assert (first["phase_change"], second["phase_change"], third["phase_change"]) == (
        False,
        True,
        False,
    )
    assert second["phase_line"].startswith("ERROR")
    assert third["phase"] == 2


# ---------- full-power ORACLE ----------


def test_meta_oracle_beats_a_player_who_counters_its_last_move():
    """A player who always plays what beats ORACLE's last move gets caught."""
    history = rounds(("rock", "scissors"))
    for _ in range(12):
        oracle_move, _ = brain.meta_choose("classic", history, random.Random(1))
        player = rules.counters("classic", history[-1]["computer"])[0]
        history += rounds((player, oracle_move))
    last_six = [r["outcome"] for r in history[-6:]]
    assert last_six.count("lose") >= 5  # "lose" is from the player's side


def test_meta_oracle_beats_a_cycle():
    cycle = ["rock", "paper", "scissors"]
    history = rounds(*[(cycle[i % 3], "rock") for i in range(9)])
    move, thought = brain.meta_choose("classic", history, random.Random(0))
    assert move == rules.counters("classic", cycle[9 % 3])[0]
    assert "Full power" in thought


def test_meta_oracle_falls_back_to_random_when_nothing_works():
    move, thought = brain.meta_choose("classic", rounds(), random.Random(0))
    assert move in rules.moves_for("classic")
    assert "instinct" in thought


def test_meta_oracle_works_in_spock_mode():
    history = [
        {"player": "lizard", "computer": "rock", "outcome": "lose", "boss": 4}
    ] * 6
    move, _ = brain.meta_choose("spock", history, random.Random(0))
    assert rules.determine_winner("spock", move, "lizard") == "win"


# ---------- shot clock ----------


def test_clock_off_never_heals():
    state = battle.new_game("classic", shot_clock=False, now=0)
    state["boss_hp"] = 1
    assert battle.apply_delay(state, 100) == 0
    assert state["boss_hp"] == 1


def test_clock_heals_after_limit_then_every_regen():
    state = battle.new_game("classic", shot_clock=True, now=0)
    state["boss"], state["boss_hp"] = 4, 1  # ORACLE, 5 max
    start = battle.CLOCK_GRACE
    assert battle.apply_delay(state, start + 4.9) == 0
    assert battle.apply_delay(state, start + 5.0) == 1
    assert battle.apply_delay(state, start + 7.9) == 0
    assert battle.apply_delay(state, start + 8.0) == 1
    assert battle.apply_delay(state, start + 14.5) == 2
    assert state["boss_hp"] == 5


def test_clock_never_heals_past_full():
    state = battle.new_game("classic", shot_clock=True, now=0)
    assert battle.apply_delay(state, 60) == 0
    assert state["boss_hp"] == bosses.BOSSES[0]["hp"]


def test_playing_a_round_applies_delay_then_restarts_clock(monkeypatch):
    monkeypatch.setattr(bosses, "choose", lambda *_a: ("scissors", ""))
    state = battle.new_game("classic", shot_clock=True, now=0)
    state["boss_hp"] = 1
    result = battle.play_round(state, "rock", random.Random(0), now=10)
    assert result["healed"] == 2  # 1 at 6.5s, 1 at 9.5s
    assert state["boss_hp"] == 2  # healed to 3, then took 1 damage
    assert battle.clock_view(state, 10)["left"] == battle.CLOCK_LIMIT + 1.5
